"""
Simulation harness for The Unfought Battle v3.

Provides AI strategy players and a game runner that can play thousands of
games to measure emergent properties. The strategies range from brain-dead
(random) to competent (heuristic), allowing us to test whether the game
rewards skill, creates diverse outcomes, and avoids degenerate states.

This module is the engine. The tests are in test_gameplay.py.
"""

import random
import itertools
from typing import List, Dict, Tuple, Any, Optional
from dataclasses import dataclass, field

from state import initialize_game, apply_deployment, GameState
from orders import (
    Order, OrderType, OrderValidationError, resolve_orders,
    is_adjacent, within_range, ORDER_COSTS,
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
    noose_kills: int = 0
    sovereign_killed_by_noose: bool = False
    p1_forces_lost: int = 0
    p2_forces_lost: int = 0
    p1_shih_spent: int = 0
    p2_shih_spent: int = 0
    domination_turns_reached: Dict[str, int] = field(default_factory=dict)
    contentious_control_turns: Dict[str, int] = field(default_factory=dict)


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
            choices = [OrderType.FORTIFY]
            moves = _valid_moves(force, game_state)
            if moves:
                choices.append(OrderType.MOVE)
            if player.shih >= ORDER_COSTS[OrderType.AMBUSH]:
                choices.append(OrderType.AMBUSH)
            pick = rng.choice(choices)
            if pick == OrderType.MOVE:
                orders.append(Order(pick, force, target_hex=rng.choice(moves)))
            else:
                if player.shih >= ORDER_COSTS[pick]:
                    orders.append(Order(pick, force))
                else:
                    # Fall back to free move or fortify
                    if moves:
                        orders.append(Order(OrderType.MOVE, force, target_hex=rng.choice(moves)))
                    else:
                        orders.append(Order(OrderType.FORTIFY, force))
        return orders


class AggressiveStrategy(Strategy):
    """
    Rush toward the center. Attack anything in sight with strongest forces first.
    Never scouts, never ambushes. Pure aggression.
    """
    name = "aggressive"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        # Put sovereign on the last force (back of the pack), strongest in front
        ids = [f.id for f in player.forces]
        # First force gets power 5 (vanguard), last gets power 1 (sovereign)
        powers = [5, 4, 3, 2, 1]
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)

        for force in player.get_alive_forces():
            enemies = _visible_enemies(force, player_id, game_state, max_range=1)
            if enemies:
                # Attack! Move toward nearest enemy
                target_enemy = min(enemies, key=lambda e: hex_distance(
                    force.position[0], force.position[1], e.position[0], e.position[1]))
                best = _move_toward(force, target_enemy.position, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # No enemies visible — move toward nearest uncontrolled contentious hex
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
                orders.append(Order(OrderType.FORTIFY, force))

        return orders


class CautiousStrategy(Strategy):
    """
    Advance slowly. Fortify when near enemies. Scout when possible.
    Protect the sovereign by keeping it behind other forces.
    """
    name = "cautious"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        # Sovereign in the middle of the pack for deception
        ids = [f.id for f in player.forces]
        powers = [3, 5, 1, 4, 2]
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)

        for force in player.get_alive_forces():
            enemies_near = _visible_enemies(force, player_id, game_state, max_range=2)

            # If enemies are adjacent and we're not the sovereign, fortify
            enemies_adjacent = [e for e in enemies_near
                                if hex_distance(force.position[0], force.position[1],
                                                e.position[0], e.position[1]) <= 1]
            if enemies_adjacent and force.power and force.power > 1:
                if player.shih >= ORDER_COSTS[OrderType.FORTIFY]:
                    orders.append(Order(OrderType.FORTIFY, force))
                    continue

            # If enemies are in scout range and we haven't scouted them, scout
            unscouted = [e for e in enemies_near if e.id not in player.known_enemy_powers]
            if unscouted and player.shih >= ORDER_COSTS[OrderType.SCOUT]:
                target = unscouted[0]
                orders.append(Order(OrderType.SCOUT, force, scout_target_id=target.id))
                continue

            # If we're the sovereign and enemies are near, retreat toward own corner
            if force.is_sovereign and enemies_adjacent:
                own_corner = (0, 0) if player_id == 'p1' else (6, 6)
                best = _move_toward(force, own_corner, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # Otherwise advance toward center
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            else:
                orders.append(Order(OrderType.FORTIFY, force))

        return orders


class AmbushStrategy(Strategy):
    """
    Rush to contentious hexes, then set ambushes. Dares the enemy to come.
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

            # If on a contentious hex with enemies nearby, ambush
            if on_contentious and enemies_near and player.shih >= ORDER_COSTS[OrderType.AMBUSH]:
                orders.append(Order(OrderType.AMBUSH, force))
                continue

            # If on a contentious hex with no enemies, fortify to hold it cheaply
            if on_contentious and not enemies_near:
                if player.shih >= ORDER_COSTS[OrderType.FORTIFY]:
                    orders.append(Order(OrderType.FORTIFY, force))
                    continue

            # Move toward nearest contentious hex
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            else:
                orders.append(Order(OrderType.FORTIFY, force))

        return orders


class TurtleStrategy(Strategy):
    """
    Never advance. Fortify everything. Wait for the Noose to solve the problem.
    This strategy SHOULD lose — if it wins, the game rewards passivity.
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
            if player.shih >= ORDER_COSTS[OrderType.FORTIFY]:
                orders.append(Order(OrderType.FORTIFY, force))
            else:
                # No shih — just sit there doing nothing (move to same... no, fortify is 1)
                # With 0 shih, only free action is move. But turtle doesn't move.
                # Issue a move to current position? No, that's invalid.
                # Just skip this force (no order).
                moves = _valid_moves(force, game_state)
                if moves:
                    # Move toward center to avoid noose at least
                    best = _move_toward(force, (3, 3), game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
        return orders


class SovereignHunterStrategy(Strategy):
    """
    Scout aggressively. When we find the sovereign, send the power-5 to kill it.
    Tests whether the Sovereign assassination path is viable.
    """
    name = "hunter"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        powers = [5, 4, 1, 3, 2]  # Power 5 in front
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)

        # Do we know where the sovereign is?
        sovereign_id = None
        sovereign_pos = None
        for fid, power in player.known_enemy_powers.items():
            if power == 1:
                ef = opponent.get_force_by_id(fid)
                if ef and ef.alive:
                    sovereign_id = fid
                    sovereign_pos = ef.position
                    break

        for force in player.get_alive_forces():
            enemies_near = _visible_enemies(force, player_id, game_state, max_range=2)

            # If we know where the sovereign is and this is our strongest, go kill it
            if sovereign_pos and force.power == 5:
                best = _move_toward(force, sovereign_pos, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # Scout unscouted enemies
            unscouted = [e for e in enemies_near if e.id not in player.known_enemy_powers]
            if unscouted and player.shih >= ORDER_COSTS[OrderType.SCOUT]:
                orders.append(Order(OrderType.SCOUT, force, scout_target_id=unscouted[0].id))
                continue

            # Otherwise move toward center
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            else:
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
    SovereignHunterStrategy(),
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

    while game.phase != 'ended' and game.turn <= MAX_TURNS:
        if game.phase != 'plan':
            break

        p1_orders = p1_strategy.plan('p1', game, rng)
        p2_orders = p2_strategy.plan('p2', game, rng)

        # Track order usage
        for o in p1_orders + p2_orders:
            if o.order_type == OrderType.SCOUT:
                record.scouts_used += 1
            elif o.order_type == OrderType.AMBUSH:
                record.ambushes_used += 1
            elif o.order_type == OrderType.FORTIFY:
                record.fortifies_used += 1

        game.phase = 'resolve'
        result = resolve_orders(p1_orders, p2_orders, game)
        record.combats += len(result.get('combats', []))

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
