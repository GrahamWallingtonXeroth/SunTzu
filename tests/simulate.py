"""
Simulation harness for The Unfought Battle v10.

Provides AI strategy players and a game runner that can play thousands of
games to measure emergent properties. The strategies range from brain-dead
(random) to competent (heuristic), allowing us to test whether the game
rewards skill, creates diverse outcomes, and avoids degenerate states.

v10: Strategic reasoning benchmark. Charge bonus +2, ambush bonus +2,
     sovereign defense removed. AggressiveV10 and BlitzerV10 replace
     scout-before-charge with charge-first. Noisy scouting support.
v9: Sovereign defense bonus. Wider starting separation.
v8: Anti-Goodhart overhaul. Added adversarial/ablation strategies.

This module is the engine. The tests are in test_gameplay.py.
"""

import random
import itertools
from typing import List, Dict, Tuple, Any, Optional
from dataclasses import dataclass, field

from state import initialize_game, apply_deployment, GameState
from orders import (
    Order, OrderType, OrderValidationError, resolve_orders,
    is_adjacent, within_range, ORDER_COSTS, has_supply,
)
from upkeep import perform_upkeep
from map_gen import get_hex_neighbors, hex_distance, is_valid_hex, BOARD_SIZE, distance_from_center
from models import Force, Player

MAX_TURNS = 30  # Safety valve — v10 games may run longer with multi-tier strategies


@dataclass
class GameRecord:
    """Post-mortem record of a completed game."""
    winner: Optional[str]
    victory_type: Optional[str]
    turns: int
    p1_strategy: str
    p2_strategy: str
    combats: int = 0
    scouts_used: int = 0
    ambushes_used: int = 0
    fortifies_used: int = 0
    charges_used: int = 0
    retreats: int = 0
    noose_kills: int = 0
    sovereign_killed_by_noose: bool = False
    p1_forces_lost: int = 0
    p2_forces_lost: int = 0
    p1_shih_spent: int = 0
    p2_shih_spent: int = 0
    domination_turns_reached: Dict[str, int] = field(default_factory=dict)
    contentious_control_turns: Dict[str, int] = field(default_factory=dict)
    # --- Extended tracking for fun scoring ---
    first_combat_turn: int = -1
    combat_details: List[Dict] = field(default_factory=list)
    sovereign_revealed_turn: Dict[str, int] = field(default_factory=dict)
    supply_cut_forces: int = 0  # force-turns where supply was cut (aggregate)
    supply_cut_p1: int = 0     # force-turns where p1 supply was cut
    supply_cut_p2: int = 0     # force-turns where p2 supply was cut
    total_force_turns: int = 0  # total force-turns (for normalization)
    unique_positions: int = 0  # unique hexes occupied across game
    per_power_orders: Dict[int, Dict[str, int]] = field(default_factory=dict)
    moves_used: int = 0  # free moves (for decision density)
    # --- Per-turn snapshots for narrative analysis ---
    turn_snapshots: List[Dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Strategy interface
# ---------------------------------------------------------------------------

class Strategy:
    """Base class for AI strategies."""
    name: str = "base"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        """Return a force_id -> power mapping."""
        raise NotImplementedError

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        """Return a list of orders for all alive forces."""
        raise NotImplementedError


def _valid_moves(force: Force, game_state: GameState) -> List[Tuple[int, int]]:
    """Get valid move targets for a force."""
    targets = []
    for nq, nr in get_hex_neighbors(force.position[0], force.position[1]):
        if game_state.is_valid_position((nq, nr)):
            # Don't move onto friendly forces
            occupant = game_state.get_force_at_position((nq, nr))
            if occupant is None or game_state.get_force_owner(occupant.id).id != game_state.get_force_owner(force.id).id:
                targets.append((nq, nr))
    return targets


def _valid_charge_targets(force: Force, game_state: GameState) -> List[Tuple[int, int]]:
    """Get valid charge targets (hexes within 2 distance with valid path)."""
    targets = []
    pos = force.position
    owner = game_state.get_force_owner(force.id)
    # All hexes within distance 2
    for q in range(max(0, pos[0] - 2), min(BOARD_SIZE, pos[0] + 3)):
        for r in range(max(0, pos[1] - 2), min(BOARD_SIZE, pos[1] + 3)):
            target = (q, r)
            if target == pos:
                continue
            dist = hex_distance(pos[0], pos[1], q, r)
            if dist < 1 or dist > 2:
                continue
            if not game_state.is_valid_position(target):
                continue
            # Check it's not occupied by friendly
            occupant = game_state.get_force_at_position(target)
            if occupant and owner and game_state.get_force_owner(occupant.id).id == owner.id:
                continue
            if dist == 2:
                # Need a valid intermediate hex
                intermediates = set(get_hex_neighbors(pos[0], pos[1]))
                target_neighbors = set(get_hex_neighbors(q, r))
                shared = intermediates & target_neighbors
                if not any(game_state.is_valid_position(h) for h in shared):
                    continue
            targets.append(target)
    return targets


def _visible_enemies(force: Force, player_id: str, game_state: GameState, max_range: int = 2) -> List[Force]:
    """Get enemy forces within range of a force."""
    opponent = game_state.get_opponent(player_id)
    if not opponent:
        return []
    return [
        f for f in opponent.get_alive_forces()
        if hex_distance(force.position[0], force.position[1],
                        f.position[0], f.position[1]) <= max_range
    ]


def _contentious_hexes(game_state: GameState) -> List[Tuple[int, int]]:
    """Get all Contentious hex positions."""
    return [pos for pos, h in game_state.map_data.items() if h.terrain == 'Contentious']


def _move_toward(force: Force, target: Tuple[int, int], game_state: GameState) -> Optional[Tuple[int, int]]:
    """Find the adjacent hex that brings us closest to target."""
    moves = _valid_moves(force, game_state)
    if not moves:
        return None
    best = min(moves, key=lambda m: hex_distance(m[0], m[1], target[0], target[1]))
    return best


def _can_order(force: Force, player: Player, order_type: OrderType) -> bool:
    """Check if a force can execute an order (sufficient Shih + supply line)."""
    if player.shih < ORDER_COSTS[order_type]:
        return False
    if order_type in (OrderType.SCOUT, OrderType.FORTIFY, OrderType.AMBUSH, OrderType.CHARGE):
        from orders import _load_order_config
        cfg = _load_order_config()
        if not has_supply(force, player.forces, cfg['supply_range'],
                          max_hops=cfg['max_supply_hops']):
            return False
    return True


# ---------------------------------------------------------------------------
# Concrete strategies
# ---------------------------------------------------------------------------

class RandomStrategy(Strategy):
    """Pure random play. The lower bound. If a strategy can't beat this, it's useless."""
    name = "random"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        powers = [1, 2, 3, 4, 5]
        rng.shuffle(powers)
        return {f.id: p for f, p in zip(player.forces, powers)}

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        orders = []
        for force in player.get_alive_forces():
            choices = []
            moves = _valid_moves(force, game_state)
            if moves:
                choices.append(OrderType.MOVE)
            if _can_order(force, player, OrderType.FORTIFY):
                choices.append(OrderType.FORTIFY)
            if _can_order(force, player, OrderType.AMBUSH):
                choices.append(OrderType.AMBUSH)
            if _can_order(force, player, OrderType.CHARGE):
                charges = _valid_charge_targets(force, game_state)
                if charges:
                    choices.append(OrderType.CHARGE)
            if not choices:
                continue
            pick = rng.choice(choices)
            if pick == OrderType.MOVE:
                orders.append(Order(pick, force, target_hex=rng.choice(moves)))
            elif pick == OrderType.CHARGE:
                charges = _valid_charge_targets(force, game_state)
                if charges:
                    orders.append(Order(pick, force, target_hex=rng.choice(charges)))
                elif moves:
                    orders.append(Order(OrderType.MOVE, force, target_hex=rng.choice(moves)))
            else:
                orders.append(Order(pick, force))
        return orders


class AggressiveStrategy(Strategy):
    """
    v10: Charge-first sovereign rush. Strong forces charge on sight without
    scouting first (charge bonus +2 makes blind charges profitable). All
    forces scout when no enemies are visible to find the sovereign. Once
    sovereign location is known, converge and charge.
    """
    name = "aggressive"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        # Sovereign in 3rd slot (middle of cluster), strong forces in front
        powers = [5, 4, 1, 3, 2]
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)
        alive = player.get_alive_forces()

        # Find known enemy sovereign location
        sovereign_pos = None
        if opponent:
            for fid, power in player.known_enemy_powers.items():
                if power == 1:
                    ef = opponent.get_force_by_id(fid)
                    if ef and ef.alive:
                        sovereign_pos = ef.position
                        break

        for force in alive:
            enemies = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adjacent = [e for e in enemies
                               if hex_distance(force.position[0], force.position[1],
                                               e.position[0], e.position[1]) <= 1]

            # Sovereign: advance toward center but flee from adjacent enemies
            if force.is_sovereign:
                if enemies_adjacent:
                    nearest = min(enemies_adjacent, key=lambda e: hex_distance(
                        force.position[0], force.position[1], e.position[0], e.position[1]))
                    moves = _valid_moves(force, game_state)
                    if moves:
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], nearest.position[0], nearest.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                elif enemies and _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                else:
                    best = _move_toward(force, center, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            # If sovereign found, rush it with power 4-5
            if sovereign_pos and force.power and force.power >= 4:
                dist = hex_distance(force.position[0], force.position[1],
                                   sovereign_pos[0], sovereign_pos[1])
                if dist <= 2 and _can_order(force, player, OrderType.CHARGE):
                    orders.append(Order(OrderType.CHARGE, force, target_hex=sovereign_pos))
                    continue
                best = _move_toward(force, sovereign_pos, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # Strong forces (power 4-5): charge-first, no scout delay
            if force.power and force.power >= 4 and enemies:
                # Charge the nearest enemy directly
                target_enemy = min(enemies, key=lambda e: hex_distance(
                    force.position[0], force.position[1], e.position[0], e.position[1]))
                dist_e = hex_distance(force.position[0], force.position[1],
                                     target_enemy.position[0], target_enemy.position[1])
                if dist_e <= 2 and _can_order(force, player, OrderType.CHARGE):
                    orders.append(Order(OrderType.CHARGE, force, target_hex=target_enemy.position))
                    continue
                best = _move_toward(force, target_enemy.position, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # Mid/low power forces (2-3): scout visible enemies to find sovereign
            if force.power and force.power in (2, 3) and enemies:
                unscouted = [e for e in enemies if e.id not in player.known_enemy_powers]
                if unscouted and _can_order(force, player, OrderType.SCOUT):
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=unscouted[0].id))
                    continue

            # Weaker forces with adjacent enemies: fortify for defense
            if enemies_adjacent and _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))
                continue

            # Default: advance toward enemy base / contentious hexes
            # Aim toward enemy cluster rather than just contentious hexes
            if opponent:
                opp_alive = opponent.get_alive_forces()
                if opp_alive:
                    avg_q = sum(f.position[0] for f in opp_alive) // len(opp_alive)
                    avg_r = sum(f.position[1] for f in opp_alive) // len(opp_alive)
                    target = (avg_q, avg_r)
                else:
                    target = center
            else:
                target = center

            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            else:
                if _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))

        return orders


class CautiousStrategy(Strategy):
    """
    Intelligence-led offense. Scout first, then strike with information advantage.
    Counter to ambush: scouts to find the sovereign, then hunts it while routing
    around traps. Avoids attacking non-sovereign forces unless clearly stronger.
    Weak against aggressive rush (spends time scouting while aggressive takes center).
    """
    name = "cautious"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        powers = [3, 5, 1, 4, 2]  # Sovereign in middle, strong forces on flanks
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)

        # Find known sovereign location
        sovereign_pos = None
        if opponent:
            for fid, power in player.known_enemy_powers.items():
                if power == 1:
                    ef = opponent.get_force_by_id(fid)
                    if ef and ef.alive:
                        sovereign_pos = ef.position
                        break

        for force in player.get_alive_forces():
            enemies_near = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adjacent = [e for e in enemies_near
                                if hex_distance(force.position[0], force.position[1],
                                                e.position[0], e.position[1]) <= 1]

            # Sovereign: stay safe — flee from enemies or hold position
            if force.is_sovereign:
                if enemies_adjacent:
                    nearest = min(enemies_adjacent, key=lambda e: hex_distance(
                        force.position[0], force.position[1], e.position[0], e.position[1]))
                    moves = _valid_moves(force, game_state)
                    if moves:
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], nearest.position[0], nearest.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        continue
                    if _can_order(force, player, OrderType.FORTIFY):
                        orders.append(Order(OrderType.FORTIFY, force))
                        continue
                elif enemies_near and _can_order(force, player, OrderType.FORTIFY):
                    # Enemies close but not adjacent — fortify defensively
                    orders.append(Order(OrderType.FORTIFY, force))
                else:
                    best = _move_toward(force, center, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            # PRIORITY 1: Hunt sovereign if found — NO RANGE LIMIT — send power-4/5
            if sovereign_pos and force.power and force.power >= 4:
                dist = hex_distance(force.position[0], force.position[1],
                                   sovereign_pos[0], sovereign_pos[1])
                if dist == 1:
                    # Adjacent to sovereign — attack directly
                    orders.append(Order(OrderType.MOVE, force, target_hex=sovereign_pos))
                    continue
                if dist == 2 and _can_order(force, player, OrderType.CHARGE):
                    orders.append(Order(OrderType.CHARGE, force, target_hex=sovereign_pos))
                    continue
                # Move toward sovereign, avoiding non-sovereign enemy hexes
                moves = _valid_moves(force, game_state)
                if moves:
                    safe = [m for m in moves if game_state.get_force_at_position(m) is None]
                    pool = safe if safe else moves
                    best = min(pool, key=lambda m: hex_distance(
                        m[0], m[1], sovereign_pos[0], sovereign_pos[1]))
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # PRIORITY 2: Attack known sovereign if adjacent (use charge for bonus)
            sov_attacked = False
            for enemy in enemies_adjacent:
                if enemy.id in player.known_enemy_powers and player.known_enemy_powers[enemy.id] == 1:
                    if _can_order(force, player, OrderType.CHARGE):
                        orders.append(Order(OrderType.CHARGE, force, target_hex=enemy.position))
                    else:
                        orders.append(Order(OrderType.MOVE, force, target_hex=enemy.position))
                    sov_attacked = True
                    break
            if sov_attacked:
                continue

            # PRIORITY 3: Scout unscouted enemies (only if sovereign not yet found)
            if not sovereign_pos:
                unscouted = [e for e in enemies_near if e.id not in player.known_enemy_powers]
                if unscouted and _can_order(force, player, OrderType.SCOUT):
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=unscouted[0].id))
                    continue

            # PRIORITY 4: Attack known-weaker enemies (use charge for decisive kills)
            attacked = False
            for enemy in enemies_near:
                if enemy.id in player.known_enemy_powers:
                    known_power = player.known_enemy_powers[enemy.id]
                    if force.power and force.power >= known_power + 2:
                        dist = hex_distance(force.position[0], force.position[1],
                                           enemy.position[0], enemy.position[1])
                        if dist <= 2 and _can_order(force, player, OrderType.CHARGE):
                            orders.append(Order(OrderType.CHARGE, force, target_hex=enemy.position))
                        elif dist <= 1:
                            orders.append(Order(OrderType.MOVE, force, target_hex=enemy.position))
                        else:
                            continue
                        attacked = True
                        break
            if attacked:
                continue

            # PRIORITY 5: Retreat from known-stronger enemies
            retreated = False
            for enemy in enemies_adjacent:
                if enemy.id in player.known_enemy_powers:
                    known_power = player.known_enemy_powers[enemy.id]
                    if force.power and known_power >= force.power + 1:
                        moves = _valid_moves(force, game_state)
                        if moves:
                            best = max(moves, key=lambda m: hex_distance(
                                m[0], m[1], enemy.position[0], enemy.position[1]))
                            orders.append(Order(OrderType.MOVE, force, target_hex=best))
                            retreated = True
                            break
            if retreated:
                continue

            # PRIORITY 6: Hold contentious hexes — ambush if enemies near, fortify otherwise
            on_contentious = any(force.position == c for c in contentious)
            if on_contentious:
                enemies_near_here = _visible_enemies(force, player_id, game_state, max_range=2)
                if enemies_near_here and force.power and force.power >= 3:
                    if _can_order(force, player, OrderType.AMBUSH):
                        orders.append(Order(OrderType.AMBUSH, force))
                        continue
                if _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                    continue

            # PRIORITY 7: Advance toward contentious/center
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))

        return orders


class AmbushStrategy(Strategy):
    """
    Rush to contentious hexes, then set ambushes. Strong forces ambush,
    weak forces scout. Counter to aggressive rushers who don't scout first.
    Weak against intel-led strategies that can identify and avoid the traps.
    """
    name = "ambush"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        powers = [2, 4, 5, 1, 3]
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)

        for force in player.get_alive_forces():
            on_contentious = any(force.position == c for c in contentious)
            enemies_near = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adjacent = [e for e in enemies_near
                               if hex_distance(force.position[0], force.position[1],
                                               e.position[0], e.position[1]) <= 1]

            # Sovereign: flee if adjacent enemies, fortify if nearby enemies
            if force.is_sovereign:
                if enemies_adjacent:
                    nearest = min(enemies_adjacent, key=lambda e: hex_distance(
                        force.position[0], force.position[1], e.position[0], e.position[1]))
                    moves = _valid_moves(force, game_state)
                    if moves:
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], nearest.position[0], nearest.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        continue
                if enemies_near and _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                    continue
                # Move toward safe-ish position (near center but behind own forces)
                best = _move_toward(force, center, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            # On contentious hex with enemies: ambush (high power) or scout (low power)
            if on_contentious and enemies_near:
                if force.power and force.power >= 3 and _can_order(force, player, OrderType.AMBUSH):
                    orders.append(Order(OrderType.AMBUSH, force))
                    continue
                elif force.power and force.power <= 3:
                    unscouted = [e for e in enemies_near if e.id not in player.known_enemy_powers]
                    if unscouted and _can_order(force, player, OrderType.SCOUT):
                        orders.append(Order(OrderType.SCOUT, force, scout_target_id=unscouted[0].id))
                        continue

            # On contentious hex without enemies: fortify
            if on_contentious and not enemies_near:
                if _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                    continue

            # Move toward nearest contentious hex
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            elif _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))

        return orders


class TurtleStrategy(Strategy):
    """
    Never advance. Fortify everything. Refuse to move toward the fight.
    This strategy SHOULD lose — if it wins, the game rewards passivity.
    Pure passivity: stay at starting positions, fortify, and wait to die.
    """
    name = "turtle"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        powers = [1, 2, 3, 4, 5]
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        orders = []
        for force in player.get_alive_forces():
            if _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))
            # Never move — pure passivity. The Noose will handle the rest.
        return orders


class NooseDodgerStrategy(Strategy):
    """
    Rush to center and hold contentious hexes with basic tactics.
    Sovereign stays protected at back. Tests center-rush with sovereign protection.
    """
    name = "dodger"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        powers = [3, 4, 1, 5, 2]  # Sovereign in middle, strong forces in front
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        orders = []
        center = (3, 3)
        contentious = _contentious_hexes(game_state)

        for force in player.get_alive_forces():
            enemies_near = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adjacent = [e for e in enemies_near
                               if hex_distance(force.position[0], force.position[1],
                                               e.position[0], e.position[1]) <= 1]

            # Sovereign: flee if threatened, otherwise move toward center
            # v9: Noose at turn 5 means sovereign must start moving early
            if force.is_sovereign:
                if enemies_adjacent:
                    nearest = min(enemies_adjacent, key=lambda e: hex_distance(
                        force.position[0], force.position[1], e.position[0], e.position[1]))
                    moves = _valid_moves(force, game_state)
                    if moves:
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], nearest.position[0], nearest.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                elif enemies_near and _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                else:
                    # Move toward center to dodge Noose
                    best = _move_toward(force, center, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            on_contentious = any(force.position == c for c in contentious)

            # Low-power forces with enemies: scout for intel
            if force.power and force.power <= 3 and enemies_near:
                unscouted = [e for e in enemies_near if e.id not in player.known_enemy_powers]
                if unscouted and _can_order(force, player, OrderType.SCOUT):
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=unscouted[0].id))
                    continue

            # High-power forces: charge at enemies when possible
            if force.power and force.power >= 4 and enemies_near:
                target_enemy = min(enemies_near, key=lambda e: hex_distance(
                    force.position[0], force.position[1], e.position[0], e.position[1]))
                dist = hex_distance(force.position[0], force.position[1],
                                   target_enemy.position[0], target_enemy.position[1])
                if dist <= 2 and _can_order(force, player, OrderType.CHARGE):
                    orders.append(Order(OrderType.CHARGE, force, target_hex=target_enemy.position))
                    continue
                best = _move_toward(force, target_enemy.position, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # On contentious hex with enemies near: fortify to hold it
            if on_contentious and enemies_near and _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))
                continue

            # Move toward nearest contentious hex or center
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
        return orders


class CoordinatorStrategy(Strategy):
    """
    Keep forces in formation for support bonus. Attack when supported.
    Exploits the support mechanic by maintaining adjacency and striking together.
    Supported forces (2+ adjacent friendlies) attack aggressively.
    """
    name = "coordinator"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        powers = [4, 5, 1, 3, 2]  # Sovereign in middle of cluster
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)
        alive = player.get_alive_forces()

        for force in alive:
            enemies_near = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adjacent = [e for e in enemies_near
                               if hex_distance(force.position[0], force.position[1],
                                               e.position[0], e.position[1]) <= 1]
            adj_friends = sum(1 for f in alive if f.id != force.id
                            and is_adjacent(f.position, force.position))
            on_contentious = any(force.position == c for c in contentious)

            # Sovereign: stay with formation, fortify when threatened
            if force.is_sovereign:
                if enemies_adjacent and _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                else:
                    moves = _valid_moves(force, game_state)
                    if moves:
                        scored = []
                        for m in moves:
                            dist = hex_distance(m[0], m[1], center[0], center[1])
                            adj = sum(1 for f in alive if f.id != force.id
                                     and hex_distance(f.position[0], f.position[1], m[0], m[1]) <= 1)
                            scored.append((dist - adj * 2, m))
                        scored.sort()
                        orders.append(Order(OrderType.MOVE, force, target_hex=scored[0][1]))
                continue

            # Low-power forces (2-3): scout when enemies are near
            if force.power and force.power <= 3 and enemies_near:
                unscouted = [e for e in enemies_near if e.id not in player.known_enemy_powers]
                if unscouted and _can_order(force, player, OrderType.SCOUT):
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=unscouted[0].id))
                    continue

            # Well-supported (2+ adj friends) and enemies near: attack!
            if adj_friends >= 2 and enemies_near and force.power and force.power >= 3:
                target_enemy = min(enemies_near, key=lambda e: hex_distance(
                    force.position[0], force.position[1], e.position[0], e.position[1]))
                dist = hex_distance(force.position[0], force.position[1],
                                   target_enemy.position[0], target_enemy.position[1])
                if dist <= 2 and _can_order(force, player, OrderType.CHARGE):
                    orders.append(Order(OrderType.CHARGE, force, target_hex=target_enemy.position))
                    continue
                best = _move_toward(force, target_enemy.position, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # On contentious with support: hold position
            if on_contentious and adj_friends >= 1:
                if enemies_near and _can_order(force, player, OrderType.AMBUSH):
                    orders.append(Order(OrderType.AMBUSH, force))
                elif _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                continue

            # Move toward contentious hex, preferring adjacency to friendlies
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            moves = _valid_moves(force, game_state)
            if moves:
                scored = []
                for m in moves:
                    dist_to_target = hex_distance(m[0], m[1], target[0], target[1])
                    adj_count = sum(1 for f in alive if f.id != force.id
                                  and hex_distance(f.position[0], f.position[1], m[0], m[1]) <= 1)
                    scored.append((dist_to_target - adj_count, m))
                scored.sort()
                orders.append(Order(OrderType.MOVE, force, target_hex=scored[0][1]))

        return orders


class SovereignHunterStrategy(Strategy):
    """
    Scout-first strategy: advance as a group, scout aggressively with power-2/3,
    then send power-4/5 to kill the sovereign once found. Uses intel to avoid
    bad fights and pick favorable ones. Counter to strategies that hide the
    sovereign behind a screen of forces.
    """
    name = "hunter"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        powers = [4, 5, 1, 2, 3]  # Scouts (2/3) at flanks for early contact
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)
        alive = player.get_alive_forces()

        # Do we know where the sovereign is?
        sovereign_pos = None
        if opponent:
            for fid, power in player.known_enemy_powers.items():
                if power == 1:
                    ef = opponent.get_force_by_id(fid)
                    if ef and ef.alive:
                        sovereign_pos = ef.position
                        break

        for force in alive:
            enemies_near = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adjacent = [e for e in enemies_near
                               if hex_distance(force.position[0], force.position[1],
                                               e.position[0], e.position[1]) <= 1]

            # Sovereign: stay near group, flee if threatened
            if force.is_sovereign:
                if enemies_adjacent:
                    nearest = min(enemies_adjacent, key=lambda e: hex_distance(
                        force.position[0], force.position[1], e.position[0], e.position[1]))
                    moves = _valid_moves(force, game_state)
                    if moves:
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], nearest.position[0], nearest.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                elif enemies_near and _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                else:
                    best = _move_toward(force, center, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            # If sovereign found, send power-4+ to kill it
            # v9: sovereign defense bonus means power-3 can't reliably kill
            if sovereign_pos and force.power and force.power >= 4:
                dist = hex_distance(force.position[0], force.position[1],
                                   sovereign_pos[0], sovereign_pos[1])
                if dist <= 2 and dist >= 1 and _can_order(force, player, OrderType.CHARGE):
                    orders.append(Order(OrderType.CHARGE, force, target_hex=sovereign_pos))
                    continue
                if dist == 1:
                    orders.append(Order(OrderType.MOVE, force, target_hex=sovereign_pos))
                    continue
                best = _move_toward(force, sovereign_pos, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # Power-2/3: scout aggressively (this is the core of the strategy)
            if force.power and force.power <= 3:
                unscouted = [e for e in enemies_near if e.id not in player.known_enemy_powers]
                if unscouted and _can_order(force, player, OrderType.SCOUT):
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=unscouted[0].id))
                    continue

            # Attack known-weaker enemies with power advantage
            attacked = False
            for enemy in enemies_near:
                if enemy.id in player.known_enemy_powers:
                    known_power = player.known_enemy_powers[enemy.id]
                    if force.power and force.power >= known_power + 2:
                        dist = hex_distance(force.position[0], force.position[1],
                                           enemy.position[0], enemy.position[1])
                        if dist <= 2 and _can_order(force, player, OrderType.CHARGE):
                            orders.append(Order(OrderType.CHARGE, force, target_hex=enemy.position))
                        elif dist <= 1:
                            orders.append(Order(OrderType.MOVE, force, target_hex=enemy.position))
                        else:
                            continue
                        attacked = True
                        break
            if attacked:
                continue

            # Avoid known-stronger adjacent enemies
            avoided = False
            for enemy in enemies_adjacent:
                if enemy.id in player.known_enemy_powers:
                    known_power = player.known_enemy_powers[enemy.id]
                    if force.power and known_power > force.power:
                        moves = _valid_moves(force, game_state)
                        if moves:
                            best = max(moves, key=lambda m: hex_distance(
                                m[0], m[1], enemy.position[0], enemy.position[1]))
                            orders.append(Order(OrderType.MOVE, force, target_hex=best))
                            avoided = True
                            break
            if avoided:
                continue

            # Advance toward contentious hexes / center
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            elif _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))

        return orders


class BlitzerStrategy(Strategy):
    """
    v10: Charge-first blitz. Power 4-5 forces charge any visible enemy
    without scouting first (charge bonus +2 makes this profitable).
    Low-power forces scout. Advances as a group. Counter to defensive/
    position strategies. Weak against scouting strategies.
    """
    name = "blitzer"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        powers = [5, 4, 1, 2, 3]
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)
        alive = player.get_alive_forces()

        # Find known sovereign location
        sovereign_pos = None
        if opponent:
            for fid, power in player.known_enemy_powers.items():
                if power == 1:
                    ef = opponent.get_force_by_id(fid)
                    if ef and ef.alive:
                        sovereign_pos = ef.position
                        break

        for force in alive:
            enemies_near = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adjacent = [e for e in enemies_near
                               if hex_distance(force.position[0], force.position[1],
                                               e.position[0], e.position[1]) <= 1]

            # Sovereign: stay near group centroid, flee if threatened
            if force.is_sovereign:
                if enemies_adjacent:
                    nearest = min(enemies_adjacent, key=lambda e: hex_distance(
                        force.position[0], force.position[1], e.position[0], e.position[1]))
                    moves = _valid_moves(force, game_state)
                    if moves:
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], nearest.position[0], nearest.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                elif enemies_near and _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                else:
                    non_sov = [f for f in alive if not f.is_sovereign]
                    if non_sov:
                        avg_q = sum(f.position[0] for f in non_sov) // len(non_sov)
                        avg_r = sum(f.position[1] for f in non_sov) // len(non_sov)
                        best = _move_toward(force, (avg_q, avg_r), game_state)
                        if best:
                            orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            # If sovereign found, charge power-4/5 toward it
            if sovereign_pos and force.power and force.power >= 4:
                dist = hex_distance(force.position[0], force.position[1],
                                   sovereign_pos[0], sovereign_pos[1])
                if dist <= 2 and _can_order(force, player, OrderType.CHARGE):
                    orders.append(Order(OrderType.CHARGE, force, target_hex=sovereign_pos))
                    continue
                best = _move_toward(force, sovereign_pos, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # Power-4/5: charge-first, no scout delay (v10)
            if force.power and force.power >= 4 and enemies_near:
                target_enemy = min(enemies_near, key=lambda e: hex_distance(
                    force.position[0], force.position[1], e.position[0], e.position[1]))
                dist = hex_distance(force.position[0], force.position[1],
                                   target_enemy.position[0], target_enemy.position[1])
                if dist <= 2 and _can_order(force, player, OrderType.CHARGE):
                    orders.append(Order(OrderType.CHARGE, force, target_hex=target_enemy.position))
                    continue
                best = _move_toward(force, target_enemy.position, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # Power-2/3: scout visible enemies (low-power scouts)
            if force.power and force.power <= 3 and enemies_near:
                unscouted = [e for e in enemies_near if e.id not in player.known_enemy_powers]
                if unscouted and _can_order(force, player, OrderType.SCOUT):
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=unscouted[0].id))
                    continue

            # Default: advance toward contentious/center together
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))

        return orders


# ---------------------------------------------------------------------------
# Adversarial / ablation strategies (v8)
# ---------------------------------------------------------------------------

class SmartPassiveStrategy(Strategy):
    """
    Intelligent passivity: moves toward center to dodge Noose, fortifies at
    contentious hexes, but NEVER initiates combat. Retreats from all enemies.
    If the game is well-designed, this should lose to every active strategy.
    Unlike Turtle (which never moves), this tests whether the game punishes
    passivity even when the passive player adapts to the board.
    """
    name = "smart_passive"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        powers = [3, 4, 1, 5, 2]  # Sovereign in middle
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)

        for force in player.get_alive_forces():
            enemies_near = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adjacent = [e for e in enemies_near
                               if hex_distance(force.position[0], force.position[1],
                                               e.position[0], e.position[1]) <= 1]
            on_contentious = any(force.position == c for c in contentious)

            # ALWAYS retreat from adjacent enemies — never fight
            if enemies_adjacent:
                nearest = min(enemies_adjacent, key=lambda e: hex_distance(
                    force.position[0], force.position[1], e.position[0], e.position[1]))
                moves = _valid_moves(force, game_state)
                if moves:
                    # Retreat away from enemy, prefer toward center
                    best = max(moves, key=lambda m: (
                        hex_distance(m[0], m[1], nearest.position[0], nearest.position[1])
                        - hex_distance(m[0], m[1], center[0], center[1]) * 0.3
                    ))
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue
                # Cornered — fortify as last resort
                if _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                continue

            # On contentious hex with no adjacent enemies: fortify to hold
            if on_contentious:
                if _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                    continue

            # Move toward contentious hexes or center (dodge the Noose)
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            elif _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))

        return orders


class NeverScoutVariant(CautiousStrategy):
    """
    Ablation test: identical to CautiousStrategy but NEVER scouts.
    If this performs equally to Cautious, scouting is decorative.
    """
    name = "never_scout"

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        orders = super().plan(player_id, game_state, rng)
        # Strip all scout orders; replace with fortify or move toward center
        player = game_state.get_player_by_id(player_id)
        center = (3, 3)
        filtered = []
        for o in orders:
            if o.order_type == OrderType.SCOUT:
                # Replace with move toward center
                best = _move_toward(o.force, center, game_state)
                if best:
                    filtered.append(Order(OrderType.MOVE, o.force, target_hex=best))
                elif _can_order(o.force, player, OrderType.FORTIFY):
                    filtered.append(Order(OrderType.FORTIFY, o.force))
            else:
                filtered.append(o)
        return filtered


class NoChargeVariant(BlitzerStrategy):
    """
    Ablation test: identical to BlitzerStrategy but NEVER charges.
    Replaces all Charge orders with Move toward the same target.
    If this performs equally to Blitzer, charge is decorative.
    """
    name = "no_charge"

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        orders = super().plan(player_id, game_state, rng)
        filtered = []
        for o in orders:
            if o.order_type == OrderType.CHARGE:
                # Replace with move toward the charge target
                best = _move_toward(o.force, o.target_hex, game_state)
                if best:
                    filtered.append(Order(OrderType.MOVE, o.force, target_hex=best))
            else:
                filtered.append(o)
        return filtered


class PowerBlindStrategy(Strategy):
    """
    Makes ALL decisions WITHOUT checking force.power. Moves toward center /
    contentious, fortifies when enemies near, scouts enemies, attacks adjacent
    enemies — but treats all forces identically regardless of power.
    Tests genuine role emergence: if power levels produce differentiated
    outcomes under this strategy, that's real emergence, not programmed behavior.
    """
    name = "power_blind"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        # Random deployment — no power-aware positioning
        powers = [1, 2, 3, 4, 5]
        rng.shuffle(powers)
        return {f.id: p for f, p in zip(player.forces, powers)}

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)

        for force in player.get_alive_forces():
            enemies_near = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adjacent = [e for e in enemies_near
                               if hex_distance(force.position[0], force.position[1],
                                               e.position[0], e.position[1]) <= 1]
            on_contentious = any(force.position == c for c in contentious)

            # Adjacent enemy: attack (no power check!)
            if enemies_adjacent:
                target = enemies_adjacent[0]
                orders.append(Order(OrderType.MOVE, force, target_hex=target.position))
                continue

            # Enemies at range 2: scout one if unscouted
            if enemies_near:
                unscouted = [e for e in enemies_near if e.id not in player.known_enemy_powers]
                if unscouted and _can_order(force, player, OrderType.SCOUT):
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=unscouted[0].id))
                    continue

            # On contentious: fortify
            if on_contentious and _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))
                continue

            # Move toward contentious / center
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            elif _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))

        return orders


class DominationStallerStrategy(Strategy):
    """
    Degenerate exploit test: rush strong forces to 2 contentious hexes,
    then fortify/ambush and refuse all other combat. Sovereign stays far back.
    Tests whether stalling for domination victory is an exploitable path.
    """
    name = "dom_staller"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        # Sovereign in back (slot 4), strong forces in front for hex control
        powers = [5, 4, 3, 2, 1]
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)

        # Sort contentious hexes by distance to our sovereign for priority
        sov = None
        for f in player.get_alive_forces():
            if f.is_sovereign:
                sov = f
                break

        for force in player.get_alive_forces():
            enemies_adjacent = [e for e in _visible_enemies(force, player_id, game_state, max_range=1)
                               if hex_distance(force.position[0], force.position[1],
                                               e.position[0], e.position[1]) <= 1]
            on_contentious = any(force.position == c for c in contentious)

            # Sovereign: flee to center, never fight
            if force.is_sovereign:
                if enemies_adjacent:
                    moves = _valid_moves(force, game_state)
                    if moves:
                        nearest = enemies_adjacent[0]
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], nearest.position[0], nearest.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        continue
                best = _move_toward(force, center, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                elif _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                continue

            # On contentious: HOLD IT — fortify/ambush, never leave
            if on_contentious:
                if enemies_adjacent and _can_order(force, player, OrderType.AMBUSH):
                    orders.append(Order(OrderType.AMBUSH, force))
                elif _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                continue

            # Not on contentious: rush to nearest uncontrolled contentious hex
            uncontrolled = [c for c in contentious if game_state.get_force_at_position(c) is None
                           or game_state.get_force_owner(game_state.get_force_at_position(c).id).id != player_id]
            if uncontrolled:
                target = min(uncontrolled, key=lambda c: hex_distance(
                    force.position[0], force.position[1], c[0], c[1]))
            else:
                # All contentious held by us — move toward center
                target = center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            elif _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))

        return orders


# ---------------------------------------------------------------------------
# All strategies
# ---------------------------------------------------------------------------

ALL_STRATEGIES = [
    RandomStrategy(),
    AggressiveStrategy(),
    CautiousStrategy(),
    AmbushStrategy(),
    TurtleStrategy(),
    NooseDodgerStrategy(),
    CoordinatorStrategy(),
    SovereignHunterStrategy(),
    BlitzerStrategy(),
]

ADVERSARIAL_STRATEGIES = [
    SmartPassiveStrategy(),
    NeverScoutVariant(),
    NoChargeVariant(),
    PowerBlindStrategy(),
    DominationStallerStrategy(),
]

EXTENDED_STRATEGIES = ALL_STRATEGIES + ADVERSARIAL_STRATEGIES

STRATEGY_MAP = {s.name: s for s in EXTENDED_STRATEGIES}


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------

def run_game(
    p1_strategy: Strategy,
    p2_strategy: Strategy,
    seed: int = 42,
    rng_seed: int = 0,
) -> GameRecord:
    """
    Run a complete game between two strategies. Returns a GameRecord.
    """
    game = initialize_game(seed)
    rng = random.Random(rng_seed)

    # Deploy
    p1_assign = p1_strategy.deploy(game.get_player_by_id('p1'), rng)
    p2_assign = p2_strategy.deploy(game.get_player_by_id('p2'), rng)
    apply_deployment(game, 'p1', p1_assign)
    apply_deployment(game, 'p2', p2_assign)

    record = GameRecord(
        winner=None, victory_type=None, turns=0,
        p1_strategy=p1_strategy.name, p2_strategy=p2_strategy.name,
        domination_turns_reached={'p1': 0, 'p2': 0},
        contentious_control_turns={'p1': 0, 'p2': 0},
    )

    p1_starting_shih = game.get_player_by_id('p1').shih
    p2_starting_shih = game.get_player_by_id('p2').shih

    all_positions = set()  # Track unique hexes used across game

    while game.phase != 'ended' and game.turn <= MAX_TURNS:
        if game.phase != 'plan':
            break

        # --- Track supply status and positions BEFORE orders ---
        from orders import _load_order_config
        supply_cfg = _load_order_config()
        for pid in ['p1', 'p2']:
            p = game.get_player_by_id(pid)
            if not p:
                continue
            alive = p.get_alive_forces()
            for f in alive:
                record.total_force_turns += 1
                all_positions.add(f.position)
                if not has_supply(f, p.forces, supply_cfg['supply_range'],
                                  max_hops=supply_cfg['max_supply_hops']):
                    record.supply_cut_forces += 1
                    if pid == 'p1':
                        record.supply_cut_p1 += 1
                    else:
                        record.supply_cut_p2 += 1

        p1_orders = p1_strategy.plan('p1', game, rng)
        p2_orders = p2_strategy.plan('p2', game, rng)

        game.phase = 'resolve'
        result = resolve_orders(p1_orders, p2_orders, game)

        # Track actually-executed specials (from validated orders, not submitted)
        counts = result.get('order_counts', {})
        record.scouts_used += counts.get('scout', 0)
        record.fortifies_used += counts.get('fortify', 0)
        record.ambushes_used += counts.get('ambush', 0)
        record.charges_used += counts.get('charge', 0)
        record.moves_used += counts.get('move', 0)
        record.combats += len(result.get('combats', []))

        # Track per-power order usage
        for order_list, pid in [(p1_orders, 'p1'), (p2_orders, 'p2')]:
            for o in order_list:
                pw = o.force.power
                if pw is not None:
                    if pw not in record.per_power_orders:
                        record.per_power_orders[pw] = {}
                    key = o.order_type.value.lower()
                    record.per_power_orders[pw][key] = record.per_power_orders[pw].get(key, 0) + 1

        # Track combat details and retreats
        for combat_result in result.get('combats', []):
            if combat_result.get('outcome', '').endswith('_retreat'):
                record.retreats += 1
            record.combat_details.append({
                'turn': game.turn,
                'attacker_base': combat_result.get('attacker_base_power'),
                'defender_base': combat_result.get('defender_base_power'),
                'attacker_eff': combat_result.get('attacker_power'),
                'defender_eff': combat_result.get('defender_power'),
                'outcome': combat_result.get('outcome'),
            })
            # Track first combat turn
            if record.first_combat_turn < 0:
                record.first_combat_turn = game.turn

            # Track sovereign revelation via combat
            for role, pid_key in [('attacker', 'attacker_id'), ('defender', 'defender_id')]:
                base_key = f'{role}_base_power'
                if combat_result.get(base_key) == 1:
                    force_id = combat_result.get(f'{role}_id')
                    # Figure out which player's sovereign was revealed
                    for pid in ['p1', 'p2']:
                        p = game.get_player_by_id(pid)
                        if p and p.get_force_by_id(force_id):
                            continue  # it's the owner's force, check opponent
                        opp_pid = 'p2' if pid == 'p1' else 'p1'
                        if opp_pid not in record.sovereign_revealed_turn:
                            record.sovereign_revealed_turn[opp_pid] = game.turn

        # Track sovereign revelation via scouting (exact or band)
        for scout_result in result.get('scouts', []):
            is_sov_reveal = scout_result.get('revealed_power') == 1
            # Band reveal: band_low includes power 1-2
            if not is_sov_reveal and scout_result.get('scout_type') == 'band':
                if scout_result.get('revealed_band') == 'band_low':
                    if scout_result.get('actual_power') == 1:
                        is_sov_reveal = True
            if is_sov_reveal:
                target_id = scout_result.get('scouted_force')
                for pid in ['p1', 'p2']:
                    p = game.get_player_by_id(pid)
                    if p and p.get_force_by_id(target_id):
                        opp_pid = 'p2' if pid == 'p1' else 'p1'
                        if opp_pid not in record.sovereign_revealed_turn:
                            record.sovereign_revealed_turn[opp_pid] = game.turn
                        break

        sovereign_capture = result.get('sovereign_captured')
        upkeep = perform_upkeep(game, sovereign_capture)

        # Track noose kills
        for evt in upkeep.get('noose_events', []):
            if evt.get('type') == 'force_scorched':
                record.noose_kills += 1
                if evt.get('was_sovereign'):
                    record.sovereign_killed_by_noose = True

        # Track domination progress
        for pid in ['p1', 'p2']:
            p = game.get_player_by_id(pid)
            if p:
                record.domination_turns_reached[pid] = max(
                    record.domination_turns_reached[pid], p.domination_turns)

        # Track contentious control
        for pid in ['p1', 'p2']:
            p = game.get_player_by_id(pid)
            if p:
                from upkeep import get_controlled_contentious
                controlled = get_controlled_contentious(p, game)
                if controlled:
                    record.contentious_control_turns[pid] = \
                        record.contentious_control_turns.get(pid, 0) + 1

        # --- Per-turn snapshot for narrative analysis ---
        snap = {
            'turn': game.turn,
            'p1_alive': 0, 'p2_alive': 0,
            'p1_power_sum': 0, 'p2_power_sum': 0,
            'p1_contentious': 0, 'p2_contentious': 0,
            'p1_shih': 0, 'p2_shih': 0,
            'combats_this_turn': len(result.get('combats', [])),
            'p1_killed_this_turn': 0, 'p2_killed_this_turn': 0,
            'p1_hidden_to_opp': 0, 'p2_hidden_to_opp': 0,
            'p1_orders': dict(counts) if counts else {},
            'p2_orders': {},
            'shrink_stage': game.shrink_stage,
        }
        for pid in ['p1', 'p2']:
            p = game.get_player_by_id(pid)
            opp = game.get_opponent(pid)
            if not p:
                continue
            alive = p.get_alive_forces()
            prefix = pid
            snap[f'{prefix}_alive'] = len(alive)
            snap[f'{prefix}_power_sum'] = sum(f.power for f in alive if f.power)
            snap[f'{prefix}_shih'] = p.shih
            # Count forces hidden from opponent
            if opp:
                hidden = sum(1 for f in alive if not f.revealed
                             and f.id not in opp.known_enemy_powers)
                snap[f'{prefix}_hidden_to_opp'] = hidden
        # Count kills this turn by comparing to last snapshot
        if record.turn_snapshots:
            prev = record.turn_snapshots[-1]
            snap['p1_killed_this_turn'] = max(0, prev['p1_alive'] - snap['p1_alive'])
            snap['p2_killed_this_turn'] = max(0, prev['p2_alive'] - snap['p2_alive'])
        # p2 order counts (separate from p1's in the `counts` var)
        p2_counts_this_turn = {}
        for o in p2_orders:
            key = o.order_type.value.lower()
            p2_counts_this_turn[key] = p2_counts_this_turn.get(key, 0) + 1
        snap['p2_orders'] = p2_counts_this_turn
        # p1 order counts (recalculate to be player-specific)
        p1_counts_this_turn = {}
        for o in p1_orders:
            key = o.order_type.value.lower()
            p1_counts_this_turn[key] = p1_counts_this_turn.get(key, 0) + 1
        snap['p1_orders'] = p1_counts_this_turn
        # Contentious control this turn
        for pid in ['p1', 'p2']:
            p = game.get_player_by_id(pid)
            if p:
                from upkeep import get_controlled_contentious as _gcc
                snap[f'{pid}_contentious'] = len(_gcc(p, game))
        record.turn_snapshots.append(snap)

        if upkeep.get('winner'):
            record.winner = upkeep['winner']
            record.victory_type = upkeep['victory_type']

    if game.phase != 'ended' and game.turn > MAX_TURNS:
        # Game didn't end — treat as a draw
        record.victory_type = 'timeout'

    record.turns = min(game.turn, MAX_TURNS)
    record.unique_positions = len(all_positions)

    # Count forces lost
    p1 = game.get_player_by_id('p1')
    p2 = game.get_player_by_id('p2')
    record.p1_forces_lost = sum(1 for f in p1.forces if not f.alive)
    record.p2_forces_lost = sum(1 for f in p2.forces if not f.alive)
    record.p1_shih_spent = p1_starting_shih - p1.shih  # Approximate (ignores income)
    record.p2_shih_spent = p2_starting_shih - p2.shih

    return record


def run_tournament(
    strategies: List[Strategy],
    games_per_matchup: int = 50,
    map_seeds: Optional[List[int]] = None,
) -> List[GameRecord]:
    """
    Round-robin tournament. Each strategy pair plays N games on different maps.
    Returns all game records.
    """
    if map_seeds is None:
        map_seeds = list(range(games_per_matchup))

    records = []
    for s1, s2 in itertools.combinations(strategies, 2):
        for i, seed in enumerate(map_seeds):
            # Each pair plays twice: once as p1, once as p2
            records.append(run_game(s1, s2, seed=seed, rng_seed=i * 1000))
            records.append(run_game(s2, s1, seed=seed, rng_seed=i * 1000 + 500))

    return records
