"""
Simulation harness for The Unfought Battle v5.

Provides AI strategy players and a game runner that can play thousands of
games to measure emergent properties. The strategies range from brain-dead
(random) to competent (heuristic), allowing us to test whether the game
rewards skill, creates diverse outcomes, and avoids degenerate states.

v5: Supply lines gate special orders. Forces without supply can only Move.

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

MAX_TURNS = 25  # Safety valve — Noose should end games well before this


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
    supply_cut_forces: int = 0  # force-turns where supply was cut
    total_force_turns: int = 0  # total force-turns (for normalization)
    unique_positions: int = 0  # unique hexes occupied across game
    per_power_orders: Dict[int, Dict[str, int]] = field(default_factory=dict)
    moves_used: int = 0  # free moves (for decision density)


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
    Rush toward the center with strong forces. Protect the sovereign.
    Attack enemies with power-4/5, use charge to close distance,
    and fortify when holding a position or facing adjacent threats.
    """
    name = "aggressive"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        # Sovereign in 3rd slot (middle of cluster), strong forces in front
        powers = [5, 4, 1, 3, 2]
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)
        alive = player.get_alive_forces()

        for force in alive:
            enemies = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adjacent = [e for e in enemies
                               if hex_distance(force.position[0], force.position[1],
                                               e.position[0], e.position[1]) <= 1]
            on_contentious = any(force.position == c for c in contentious)

            # Sovereign: advance toward center but stop when enemies are near
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
                    # Enemies visible but not adjacent — fortify, don't advance
                    orders.append(Order(OrderType.FORTIFY, force))
                else:
                    # No enemies in sight — advance toward center
                    best = _move_toward(force, center, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            # On contentious hex with enemies near: fortify to hold it
            if on_contentious and enemies_adjacent:
                if _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                    continue

            # Strong forces (power 4-5): attack strategically
            if force.power and force.power >= 4 and enemies:
                # Prefer known-weaker targets, then unknown, avoid known-stronger
                best_target = None
                best_target_dist = 999
                for e in enemies:
                    if e.id in player.known_enemy_powers:
                        known_pwr = player.known_enemy_powers[e.id]
                        if known_pwr >= force.power:
                            continue  # Skip known-stronger enemies
                    dist_e = hex_distance(force.position[0], force.position[1],
                                         e.position[0], e.position[1])
                    if dist_e < best_target_dist:
                        best_target = e
                        best_target_dist = dist_e

                if best_target:
                    if best_target_dist <= 2 and _can_order(force, player, OrderType.CHARGE):
                        orders.append(Order(OrderType.CHARGE, force, target_hex=best_target.position))
                        continue
                    best = _move_toward(force, best_target.position, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        continue

            # Mid-power forces (2-3): scout unscouted enemies before engaging
            if force.power and force.power in (2, 3) and enemies:
                unscouted = [e for e in enemies if e.id not in player.known_enemy_powers]
                if unscouted and _can_order(force, player, OrderType.SCOUT):
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=unscouted[0].id))
                    continue

            # Weaker forces with adjacent enemies: fortify for defense
            if enemies_adjacent and _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))
                continue

            # No immediate threats: advance toward contentious hexes
            uncontrolled = [c for c in contentious if game_state.get_force_at_position(c) is None
                           or game_state.get_force_owner(game_state.get_force_at_position(c).id).id != player_id]
            if uncontrolled:
                target = min(uncontrolled, key=lambda c: hex_distance(
                    force.position[0], force.position[1], c[0], c[1]))
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

            # Sovereign: stay back, flee if threatened
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
                # Otherwise stay put
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

            # If sovereign found, send power-3+ to kill it
            if sovereign_pos and force.power and force.power >= 3:
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
    Advance together, use charge aggressively. Attacks any visible enemy with
    power-4/5, charges to close range-2 gaps. Counter to defensive/position
    strategies that sit on hexes. Weak against scouting strategies that know
    where it's coming from.
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
                    # Move toward group center of mass
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

            # Power-4/5: charge any visible enemy
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

            # Power-2/3: scout visible enemies
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

STRATEGY_MAP = {s.name: s for s in ALL_STRATEGIES}


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

        # Track sovereign revelation via scouting
        for scout_result in result.get('scouts', []):
            if scout_result.get('revealed_power') == 1:
                target_id = scout_result.get('scouted_force')
                for pid in ['p1', 'p2']:
                    p = game.get_player_by_id(pid)
                    if p and p.get_force_by_id(target_id):
                        # This is the force's owner — the OTHER player discovered it
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
