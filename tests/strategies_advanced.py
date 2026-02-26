"""
Advanced Strategy Tiers: The Path to Chess for the AI Age.

Our evaluation harness is only as good as the players in it. Simple heuristic
bots produce simple games and simple measurements. To know whether this game
has chess-level depth, we need chess-level players.

=== THE STRATEGY LADDER ===

TIER 1 — Reactive Heuristics (simulate.py, existing)
    Stateless, single-turn, per-force decisions. "If enemy nearby, attack."
    Tests: Does the game work? Are mechanics used?
    Limitation: Can't distinguish deep game from shallow one.

TIER 2 — Stateful Planners (this file)
    Memory between turns. Pattern recognition. Multi-turn intent.
    Tests: Does the game reward planning? Does memory help?
    Key strategies: PatternReader, SupplyCutter

TIER 3 — Information-Theoretic Players (this file)
    Bayesian belief tracking over hidden enemy powers. Information-seeking
    behavior. Deception through non-standard play.
    Tests: Does hidden information create genuine depth? Does reasoning
    about uncertainty beat acting on partial knowledge?
    Key strategies: BayesianHunter

TIER 4 — Search-Based Players (this file)
    Forward simulation. Evaluate actions by predicting outcomes across
    multiple possible worlds (belief states).
    Tests: Does COMPUTATION help? This is THE anti-calculability test.
    If deeper search monotonically dominates, the game is calculable.
    If search hits diminishing returns, the game resists AI solving.
    Key strategy: LookaheadPlayer

=== WHY THIS MATTERS ===

Chess is deep because Kasparov plays differently from a club player who
plays differently from a beginner. Each level of sophistication unlocks
new strategic possibilities. If our game has that property — if smarter
play reveals new strategies — then we have depth. If smarter play just
means "rush sovereign faster," the game is shallow.

The Depth Score measures the GRADIENT: how much does each tier of
sophistication improve over the previous one? And critically: does the
gradient flatten? A game where Tier 4 barely beats Tier 3 but Tier 3
clearly beats Tier 2 has the right shape — computation has diminishing
returns but strategic understanding always helps.
"""

import copy
import math
import random
import itertools
from typing import List, Dict, Tuple, Any, Optional, Set
from collections import defaultdict

from state import GameState
from orders import (
    Order, OrderType, resolve_orders, has_supply,
)
from upkeep import perform_upkeep, get_controlled_contentious
from map_gen import get_hex_neighbors, hex_distance, BOARD_SIZE
from models import Force, Player

from tests.simulate import (
    Strategy, _valid_moves, _valid_charge_targets, _visible_enemies,
    _contentious_hexes, _move_toward, _can_order,
)


# ===========================================================================
# TIER 2: STATEFUL PLANNERS — Memory and Pattern Recognition
# ===========================================================================

class StatefulStrategy(Strategy):
    """Base class for strategies with between-turn memory.

    Tier 1 strategies are pure functions: plan(state) → orders.
    Tier 2 strategies accumulate knowledge across turns:
    - Enemy positions over time (movement patterns)
    - Which forces retreated (likely sovereign)
    - Where combat happened (territory pressure)
    - What we've scouted and inferred

    This is the minimum sophistication needed to measure whether
    the game rewards intelligence beyond reactive play.
    """
    name = "stateful_base"

    def __init__(self):
        self._turn_history: List[Dict] = []  # snapshot per turn
        self._enemy_positions: Dict[str, List[Tuple]] = defaultdict(list)  # force_id → positions
        self._suspected_sovereign: Dict[str, float] = defaultdict(float)  # force_id → score
        self._my_player_id: Optional[str] = None

    def _observe(self, player_id: str, game_state: GameState):
        """Record observable state for pattern analysis."""
        self._my_player_id = player_id
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        if not opponent:
            return

        # Track enemy positions
        for force in opponent.get_alive_forces():
            visible = any(
                hex_distance(f.position[0], f.position[1],
                             force.position[0], force.position[1]) <= 2
                for f in player.get_alive_forces()
            )
            if visible:
                self._enemy_positions[force.id].append(force.position)

        # Detect retreat behavior: if enemy force moved away from our forces
        for force_id, positions in self._enemy_positions.items():
            if len(positions) >= 2:
                prev = positions[-2]
                curr = positions[-1]
                if prev != curr:
                    # Find nearest of our forces to their previous position
                    our_nearest = min(
                        (hex_distance(prev[0], prev[1], f.position[0], f.position[1])
                         for f in player.get_alive_forces()),
                        default=99
                    )
                    our_nearest_now = min(
                        (hex_distance(curr[0], curr[1], f.position[0], f.position[1])
                         for f in player.get_alive_forces()),
                        default=99
                    )
                    # If they moved AWAY from us, that's retreat behavior
                    if our_nearest_now > our_nearest:
                        self._suspected_sovereign[force_id] += 1.5

        # Forces that stay behind the front line are likely sovereign
        if opponent.get_alive_forces():
            center = (3, 3)
            avg_dist = sum(
                hex_distance(f.position[0], f.position[1], center[0], center[1])
                for f in opponent.get_alive_forces()
            ) / len(opponent.get_alive_forces())

            for force in opponent.get_alive_forces():
                dist = hex_distance(force.position[0], force.position[1],
                                    center[0], center[1])
                if dist > avg_dist + 0.5:  # further from center than average
                    self._suspected_sovereign[force.id] += 0.3

        # If we KNOW a force's power from scouting/combat, update sovereign scores
        for fid, power in player.known_enemy_powers.items():
            if power == 1:
                self._suspected_sovereign[fid] = 100.0  # definitely sovereign
            elif power > 1:
                self._suspected_sovereign[fid] = -100.0  # definitely NOT sovereign

    def _get_likely_sovereign_id(self, player_id: str, game_state: GameState) -> Optional[str]:
        """Return the enemy force most likely to be the sovereign."""
        opponent = game_state.get_opponent(player_id)
        if not opponent:
            return None
        alive_ids = {f.id for f in opponent.get_alive_forces()}
        candidates = {fid: score for fid, score in self._suspected_sovereign.items()
                      if fid in alive_ids}
        if not candidates:
            return None
        return max(candidates, key=candidates.get)


class PatternReaderStrategy(StatefulStrategy):
    """
    TIER 2: Infers enemy sovereign location from movement patterns.

    Innovation: First strategy that READS THE OPPONENT instead of
    just reacting to visible state. Tracks which enemy forces retreat,
    which stay behind the front line, and which the opponent protects.
    Uses this to hunt the sovereign WITHOUT scouting.

    This tests whether the game creates readable patterns — the
    foundation of the human skill of "reading" opponents.
    """
    name = "pattern_reader"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        # Sovereign in non-standard position (not always middle)
        # This makes US harder to read
        powers = [4, 1, 5, 3, 2]
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        self._observe(player_id, game_state)

        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)

        # Find our best guess for enemy sovereign
        likely_sov_id = self._get_likely_sovereign_id(player_id, game_state)
        likely_sov_pos = None
        if likely_sov_id and opponent:
            ef = opponent.get_force_by_id(likely_sov_id)
            if ef and ef.alive:
                likely_sov_pos = ef.position

        for force in player.get_alive_forces():
            enemies = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adj = [e for e in enemies
                           if hex_distance(force.position[0], force.position[1],
                                           e.position[0], e.position[1]) <= 1]

            # Sovereign: flee + fortify, prefer staying behind our front line
            if force.is_sovereign:
                if enemies_adj:
                    nearest = min(enemies_adj, key=lambda e: hex_distance(
                        force.position[0], force.position[1],
                        e.position[0], e.position[1]))
                    moves = _valid_moves(force, game_state)
                    if moves:
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], nearest.position[0], nearest.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        continue
                elif enemies and _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                    continue
                # Move toward center but slowly
                best = _move_toward(force, center, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            # HUNT MODE: if we have a likely sovereign target, send strong forces
            if likely_sov_pos and force.power and force.power >= 4:
                dist = hex_distance(force.position[0], force.position[1],
                                    likely_sov_pos[0], likely_sov_pos[1])
                if dist <= 2 and _can_order(force, player, OrderType.CHARGE):
                    orders.append(Order(OrderType.CHARGE, force, target_hex=likely_sov_pos))
                    continue
                if dist <= 1:
                    orders.append(Order(OrderType.MOVE, force, target_hex=likely_sov_pos))
                    continue
                best = _move_toward(force, likely_sov_pos, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # PROBE MODE: low power forces advance to create retreat patterns
            if force.power and force.power <= 3:
                # Move toward nearest enemy to force them to reveal behavior
                if enemies:
                    nearest = min(enemies, key=lambda e: hex_distance(
                        force.position[0], force.position[1],
                        e.position[0], e.position[1]))
                    # Don't charge in — just get adjacent to observe response
                    best = _move_toward(force, nearest.position, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        continue

            # Default: advance toward contentious
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            elif _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))

        return orders


class SupplyCutterStrategy(StatefulStrategy):
    """
    TIER 2: Deliberately cuts enemy supply chains.

    Innovation: First strategy that targets the SUPPLY MECHANIC.
    Identifies the enemy sovereign's position (known or inferred),
    then positions forces between the sovereign and outlying enemy
    forces. Supply-cut forces can only Move — no Fortify, no Charge,
    no Scout. This creates the positional squeeze that longer games need.

    This tests whether the supply mechanic is a real strategic lever
    or just decoration. If supply cutting wins games, the mechanic
    has depth we haven't been measuring.
    """
    name = "supply_cutter"

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        # Sovereign protected at position 1 (non-standard)
        powers = [3, 1, 4, 5, 2]
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        self._observe(player_id, game_state)

        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)
        ordered_forces = set()

        if not opponent:
            return orders

        # Find enemy sovereign (known or suspected)
        likely_sov_id = self._get_likely_sovereign_id(player_id, game_state)
        enemy_sov_pos = None
        if likely_sov_id:
            ef = opponent.get_force_by_id(likely_sov_id)
            if ef and ef.alive:
                enemy_sov_pos = ef.position

        # Identify enemy outlying forces (far from their sovereign)
        enemy_alive = opponent.get_alive_forces()
        enemy_centroid = None
        if enemy_alive:
            avg_q = sum(f.position[0] for f in enemy_alive) / len(enemy_alive)
            avg_r = sum(f.position[1] for f in enemy_alive) / len(enemy_alive)
            enemy_centroid = (avg_q, avg_r)

        for force in player.get_alive_forces():
            if force.id in ordered_forces:
                continue

            enemies = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adj = [e for e in enemies
                           if hex_distance(force.position[0], force.position[1],
                                           e.position[0], e.position[1]) <= 1]

            # Sovereign: flee, fortify, stay protected
            if force.is_sovereign:
                if enemies_adj:
                    nearest = min(enemies_adj, key=lambda e: hex_distance(
                        force.position[0], force.position[1],
                        e.position[0], e.position[1]))
                    moves = _valid_moves(force, game_state)
                    if moves:
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], nearest.position[0], nearest.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        ordered_forces.add(force.id)
                        continue
                elif enemies and _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                    ordered_forces.add(force.id)
                    continue
                best = _move_toward(force, center, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                ordered_forces.add(force.id)
                continue

            # SUPPLY CUT MODE: mid-power forces (2-3) try to interpose
            # between enemy sovereign and enemy outlying forces
            if force.power and force.power in (2, 3) and enemy_sov_pos:
                # Target: hexes between enemy sovereign and enemy centroid
                if enemy_centroid:
                    interpose_q = (enemy_sov_pos[0] + enemy_centroid[0]) / 2
                    interpose_r = (enemy_sov_pos[1] + enemy_centroid[1]) / 2
                    interpose_target = (round(interpose_q), round(interpose_r))

                    # Move toward interposition point
                    best = _move_toward(force, interpose_target, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        ordered_forces.add(force.id)
                        continue

            # STRIKE MODE: strong forces (4-5) attack supply-cut enemies
            # or hunt the sovereign
            if force.power and force.power >= 4:
                # Priority: attack enemy sovereign if known
                if enemy_sov_pos:
                    dist = hex_distance(force.position[0], force.position[1],
                                        enemy_sov_pos[0], enemy_sov_pos[1])
                    if dist <= 2 and _can_order(force, player, OrderType.CHARGE):
                        orders.append(Order(OrderType.CHARGE, force, target_hex=enemy_sov_pos))
                        ordered_forces.add(force.id)
                        continue
                    if dist <= 1:
                        orders.append(Order(OrderType.MOVE, force, target_hex=enemy_sov_pos))
                        ordered_forces.add(force.id)
                        continue

                # Scout unscouted enemies to find sovereign
                unscouted = [e for e in enemies if e.id not in player.known_enemy_powers]
                if unscouted and _can_order(force, player, OrderType.SCOUT):
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=unscouted[0].id))
                    ordered_forces.add(force.id)
                    continue

                # Move toward enemy centroid
                if enemy_centroid:
                    target = (round(enemy_centroid[0]), round(enemy_centroid[1]))
                    best = _move_toward(force, target, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        ordered_forces.add(force.id)
                        continue

            # Default: advance toward contentious
            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            elif _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))

        return orders


# ===========================================================================
# TIER 3: INFORMATION-THEORETIC — Bayesian Belief Tracking
# ===========================================================================

class BayesianHunterStrategy(StatefulStrategy):
    """
    TIER 3: Maintains probability distribution over enemy power assignments.

    Innovation: First strategy that uses PROBABILISTIC REASONING about
    hidden information. Maintains the set of all possible enemy power
    assignments (5! = 120 initially), filters by observations:
    - Scouted force X has power P → keep only assignments where X = P
    - Fought force X, learned power P → same
    - Process of elimination: if 3 forces are known, narrows possibilities

    Decision-making uses expected value:
    - P(force X = sovereign) computed from remaining assignments
    - Attack the force with highest P(sovereign)
    - Scout the force where information gain is highest
    - Avoid attacking forces likely to be strong

    This tests whether the game's hidden information creates genuine
    strategic depth — whether REASONING about uncertainty beats
    acting on partial knowledge.
    """
    name = "bayesian_hunter"

    def __init__(self):
        super().__init__()
        self._belief: Optional[List[Dict[str, int]]] = None
        self._enemy_force_ids: Optional[List[str]] = None

    def _init_beliefs(self, opponent: Player):
        """Initialize all 120 possible power assignments."""
        self._enemy_force_ids = [f.id for f in opponent.forces]
        self._belief = []
        for perm in itertools.permutations([1, 2, 3, 4, 5]):
            assignment = dict(zip(self._enemy_force_ids, perm))
            self._belief.append(assignment)

    def _update_beliefs(self, player: Player, opponent: Player):
        """Filter beliefs based on all observations."""
        if self._belief is None:
            self._init_beliefs(opponent)

        # Filter by known powers (from scouting + combat)
        known = player.known_enemy_powers
        self._belief = [
            b for b in self._belief
            if all(b.get(fid) == power for fid, power in known.items()
                   if fid in b)
        ]

        # Safety: if all filtered out (shouldn't happen), reset
        if not self._belief:
            self._init_beliefs(opponent)

    def _sovereign_probability(self, force_id: str) -> float:
        """P(force = sovereign) given current beliefs."""
        if not self._belief or force_id not in (self._enemy_force_ids or []):
            return 0.2  # uniform prior
        count = sum(1 for b in self._belief if b.get(force_id) == 1)
        return count / len(self._belief) if self._belief else 0.2

    def _expected_power(self, force_id: str) -> float:
        """E[power] given current beliefs."""
        if not self._belief or force_id not in (self._enemy_force_ids or []):
            return 3.0  # uniform mean
        powers = [b[force_id] for b in self._belief if force_id in b]
        return sum(powers) / len(powers) if powers else 3.0

    def _info_gain(self, force_id: str) -> float:
        """Information gain from scouting this force (Shannon entropy reduction)."""
        if not self._belief or force_id not in (self._enemy_force_ids or []):
            return 0.0
        total = len(self._belief)
        if total == 0:
            return 0.0
        # Count beliefs per power level for this force
        counts = defaultdict(int)
        for b in self._belief:
            counts[b.get(force_id, 0)] += 1
        # Current entropy of this force's power
        entropy = 0.0
        for c in counts.values():
            if c > 0:
                p = c / total
                entropy -= p * math.log2(p)
        return entropy

    def _combined_sovereign_score(self, force_id: str) -> float:
        """Blend Bayesian P(sovereign) with pattern-based suspicion.

        v9 fix: Tier 3 was losing to Tier 2 because it only used Bayesian
        probability and ignored the pattern-reading signals from StatefulStrategy.
        This method combines both, giving Tier 3 the UNION of Tier 2's intuition
        and its own probabilistic reasoning.
        """
        bayes_prob = self._sovereign_probability(force_id)
        pattern_score = self._suspected_sovereign.get(force_id, 0.0)
        # Normalize pattern score to [0, 1] range
        max_pattern = max((abs(s) for s in self._suspected_sovereign.values()), default=1.0)
        if max_pattern > 0:
            pattern_norm = max(0.0, min(1.0, (pattern_score / max_pattern + 1.0) / 2.0))
        else:
            pattern_norm = 0.2  # uniform prior
        # Weighted blend: Bayesian reasoning is primary, patterns supplement
        return 0.6 * bayes_prob + 0.4 * pattern_norm

    def deploy(self, player: Player, rng: random.Random) -> Dict[str, int]:
        ids = [f.id for f in player.forces]
        # Non-standard deployment: sovereign in position 4 (unexpected)
        powers = [5, 3, 4, 1, 2]
        return dict(zip(ids, powers))

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        self._observe(player_id, game_state)

        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)

        if not opponent:
            return orders

        # Update Bayesian beliefs
        self._update_beliefs(player, opponent)

        # Find highest-probability sovereign using COMBINED score (v9 fix)
        alive_enemies = opponent.get_alive_forces()

        for force in player.get_alive_forces():
            enemies = _visible_enemies(force, player_id, game_state, max_range=2)
            enemies_adj = [e for e in enemies
                           if hex_distance(force.position[0], force.position[1],
                                           e.position[0], e.position[1]) <= 1]

            # Sovereign: retreat + fortify
            if force.is_sovereign:
                if enemies_adj:
                    nearest = min(enemies_adj, key=lambda e: hex_distance(
                        force.position[0], force.position[1],
                        e.position[0], e.position[1]))
                    moves = _valid_moves(force, game_state)
                    if moves:
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], nearest.position[0], nearest.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        continue
                elif enemies and _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                    continue
                best = _move_toward(force, center, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            # EARLY GAME EXPLORATION: when no enemies visible and early turns,
            # advance scout-role forces toward unexplored areas
            if not enemies and game_state.turn < 6 and force.power and force.power <= 3:
                best = _move_toward(force, center, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                    continue

            # BAYESIAN + PATTERN ATTACK: use combined score to choose targets
            if force.power and force.power >= 4 and enemies:
                best_target = None
                best_score = -999.0
                for e in enemies:
                    sov_p = self._combined_sovereign_score(e.id)
                    exp_power = self._expected_power(e.id)
                    score = sov_p * 10.0 - exp_power * 0.5
                    dist = hex_distance(force.position[0], force.position[1],
                                        e.position[0], e.position[1])
                    score -= dist * 0.5
                    if score > best_score:
                        best_score = score
                        best_target = e

                if best_target and best_score > 0:
                    dist = hex_distance(force.position[0], force.position[1],
                                        best_target.position[0], best_target.position[1])
                    if dist <= 2 and _can_order(force, player, OrderType.CHARGE):
                        orders.append(Order(OrderType.CHARGE, force, target_hex=best_target.position))
                        continue
                    if dist <= 1:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best_target.position))
                        continue
                    best = _move_toward(force, best_target.position, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        continue

            # INFORMATION SEEKING: scout the force with highest info gain
            if force.power and force.power <= 3 and enemies:
                unscouted = [e for e in enemies if e.id not in player.known_enemy_powers]
                if unscouted and _can_order(force, player, OrderType.SCOUT):
                    best_target = max(unscouted, key=lambda e: self._info_gain(e.id))
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=best_target.id))
                    continue

            # AVOID STRONG ENEMIES: if adjacent to likely-strong enemy, retreat
            retreated = False
            for e in enemies_adj:
                exp = self._expected_power(e.id)
                if force.power and exp > force.power + 1:
                    moves = _valid_moves(force, game_state)
                    if moves:
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], e.position[0], e.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        retreated = True
                        break
            if retreated:
                continue

            # Default: advance toward high-sov-probability enemy or contentious
            if alive_enemies:
                sov_target = max(alive_enemies,
                                 key=lambda e: self._combined_sovereign_score(e.id))
                if self._combined_sovereign_score(sov_target.id) > 0.3:
                    best = _move_toward(force, sov_target.position, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        continue

            target = min(contentious, key=lambda c: hex_distance(
                force.position[0], force.position[1], c[0], c[1])) if contentious else center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            elif _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))

        return orders


# ===========================================================================
# TIER 4: SEARCH-BASED — Forward Simulation with Belief Sampling
# ===========================================================================

def _clone_game_state(game_state: GameState) -> GameState:
    """Deep-copy game state for forward simulation."""
    return copy.deepcopy(game_state)


def _simple_opponent_orders(opponent: Player, game_state: GameState) -> List[Order]:
    """Generate plausible opponent orders for forward simulation.

    Uses a simple heuristic: advance toward center, protect sovereign,
    attack with strong forces. Not perfect, but good enough for 1-ply
    evaluation. The POINT is not to predict the opponent perfectly —
    it's to evaluate whether our actions leave us in a good position
    regardless of reasonable opponent responses.
    """
    orders = []
    center = (3, 3)
    contentious = _contentious_hexes(game_state)

    for force in opponent.get_alive_forces():
        if force.is_sovereign:
            # Sovereign retreats from threats
            enemies = []
            other_player = game_state.get_opponent(opponent.id)
            if other_player:
                enemies = [f for f in other_player.get_alive_forces()
                           if hex_distance(force.position[0], force.position[1],
                                           f.position[0], f.position[1]) <= 2]
            if enemies:
                nearest = min(enemies, key=lambda e: hex_distance(
                    force.position[0], force.position[1],
                    e.position[0], e.position[1]))
                if hex_distance(force.position[0], force.position[1],
                                nearest.position[0], nearest.position[1]) <= 1:
                    moves = _valid_moves(force, game_state)
                    if moves:
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], nearest.position[0], nearest.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        continue
            best = _move_toward(force, center, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            continue

        # Non-sovereign: move toward contentious
        target = min(contentious, key=lambda c: hex_distance(
            force.position[0], force.position[1], c[0], c[1])) if contentious else center
        best = _move_toward(force, target, game_state)
        if best:
            orders.append(Order(OrderType.MOVE, force, target_hex=best))

    return orders


def _evaluate_state(game_state: GameState, my_player_id: str) -> float:
    """Evaluate a game state from my perspective.

    This is the "chess evaluation function" — but for a game with hidden
    information. It combines material, position, information, and safety.

    Returns: score (positive = good for me, negative = bad).
    """
    player = game_state.get_player_by_id(my_player_id)
    opponent = game_state.get_opponent(my_player_id)

    if not player or not opponent:
        return 0.0

    # Game-ending conditions
    if game_state.winner == my_player_id:
        return 1000.0
    if game_state.winner and game_state.winner != my_player_id:
        return -1000.0

    my_alive = player.get_alive_forces()
    opp_alive = opponent.get_alive_forces()

    # Check if sovereign alive
    my_sov_alive = any(f.is_sovereign and f.alive for f in player.forces)
    opp_sov_alive = any(f.is_sovereign and f.alive for f in opponent.forces)
    if not my_sov_alive:
        return -1000.0
    if not opp_sov_alive:
        return 1000.0

    score = 0.0

    # Material: force count and power sum
    score += (len(my_alive) - len(opp_alive)) * 3.0
    my_power = sum(f.power for f in my_alive if f.power)
    opp_power = sum(f.power for f in opp_alive if f.power)
    score += (my_power - opp_power) * 0.5

    # Territory: contentious hex control
    contentious = _contentious_hexes(game_state)
    my_cont = sum(1 for c in contentious
                  if any(f.position == c for f in my_alive))
    opp_cont = sum(1 for c in contentious
                   if any(f.position == c for f in opp_alive))
    score += (my_cont - opp_cont) * 2.0

    # Domination progress
    score += player.domination_turns * 3.0
    score -= opponent.domination_turns * 3.0

    # Sovereign safety: distance from nearest enemy
    my_sov = next((f for f in my_alive if f.is_sovereign), None)
    if my_sov:
        nearest_enemy_dist = min(
            (hex_distance(my_sov.position[0], my_sov.position[1],
                          e.position[0], e.position[1])
             for e in opp_alive),
            default=10
        )
        score += min(nearest_enemy_dist, 4) * 2.5  # safer sovereign = better (v9: increased weight)

    # Information advantage: how many enemy powers we know
    known_count = sum(1 for fid in player.known_enemy_powers
                      if any(f.id == fid and f.alive for f in opponent.forces))
    score += known_count * 0.5

    # Resource advantage
    score += (player.shih - opponent.shih) * 0.3

    return score


class LookaheadStrategy(BayesianHunterStrategy):
    """
    TIER 4: Evaluates WHOLE-TURN plans by forward simulation across belief states.

    Innovation: First strategy that CALCULATES. Generates candidate plans
    (complete order sets for all forces), simulates each across multiple
    sampled enemy power assignments, and picks the plan with the highest
    expected evaluation.

    THIS IS THE ANTI-CALCULABILITY TEST. If this strategy dominates
    Tiers 1-3 by a large margin, the game is calculable — brute force
    search beats human-like reasoning. If it barely beats Tier 3, the
    game resists calculation — understanding and adaptation matter more
    than lookahead depth.

    v9 fix: Replaced broken per-force greedy (which lost coordination)
    with whole-turn plan evaluation. Generates 3 candidate plans:
    baseline (Bayesian logic), aggressive variant, defensive variant.
    Evaluates each as a COMPLETE set of orders across belief samples.
    """
    name = "lookahead"

    def __init__(self, n_samples: int = 8):
        super().__init__()
        self._n_samples = n_samples

    def _sample_beliefs(self, n: int) -> List[Dict[str, int]]:
        """Sample n power assignments from current beliefs."""
        if not self._belief:
            return []
        if len(self._belief) <= n:
            return list(self._belief)
        return random.sample(self._belief, n)

    def _generate_aggressive_variant(self, player_id: str, game_state: GameState,
                                     rng: random.Random) -> Optional[List[Order]]:
        """Generate an aggressive plan: charge/move toward enemies."""
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        if not player or not opponent:
            return None

        orders = []
        alive_enemies = opponent.get_alive_forces()
        if not alive_enemies:
            return None

        # Find best sovereign target using combined score
        sov_target = max(alive_enemies,
                         key=lambda e: self._combined_sovereign_score(e.id))
        sov_pos = sov_target.position

        for force in player.get_alive_forces():
            if force.is_sovereign:
                # Even aggressive plan protects sovereign
                enemies_adj = [e for e in alive_enemies
                               if hex_distance(force.position[0], force.position[1],
                                               e.position[0], e.position[1]) <= 1]
                if enemies_adj:
                    moves = _valid_moves(force, game_state)
                    if moves:
                        nearest = min(enemies_adj, key=lambda e: hex_distance(
                            force.position[0], force.position[1],
                            e.position[0], e.position[1]))
                        best = max(moves, key=lambda m: hex_distance(
                            m[0], m[1], nearest.position[0], nearest.position[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        continue
                elif _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                    continue
                best = _move_toward(force, (3, 3), game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            # Aggressive: charge if possible, otherwise move toward sovereign target
            dist = hex_distance(force.position[0], force.position[1],
                                sov_pos[0], sov_pos[1])
            if dist <= 2 and _can_order(force, player, OrderType.CHARGE):
                orders.append(Order(OrderType.CHARGE, force, target_hex=sov_pos))
                continue

            best = _move_toward(force, sov_pos, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            elif _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))

        return orders if orders else None

    def _generate_defensive_variant(self, player_id: str, game_state: GameState,
                                    rng: random.Random) -> Optional[List[Order]]:
        """Generate a defensive plan: fortify on contentious hexes, scout enemies."""
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        if not player or not opponent:
            return None

        orders = []
        contentious = _contentious_hexes(game_state)
        center = (3, 3)

        for force in player.get_alive_forces():
            enemies = _visible_enemies(force, player_id, game_state, max_range=2)

            if force.is_sovereign:
                # Defensive sovereign: fortify if enemies nearby, otherwise stay back
                if enemies and _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                    continue
                best = _move_toward(force, center, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            # Scout if enemies visible and unscouted
            if enemies and force.power and force.power <= 3:
                unscouted = [e for e in enemies if e.id not in player.known_enemy_powers]
                if unscouted and _can_order(force, player, OrderType.SCOUT):
                    best_target = max(unscouted, key=lambda e: self._info_gain(e.id))
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=best_target.id))
                    continue

            # Fortify on or move toward contentious hexes
            if force.position in contentious and _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))
                continue

            if contentious:
                target = min(contentious, key=lambda c: hex_distance(
                    force.position[0], force.position[1], c[0], c[1]))
            else:
                target = center
            best = _move_toward(force, target, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))
            elif _can_order(force, player, OrderType.FORTIFY):
                orders.append(Order(OrderType.FORTIFY, force))

        return orders if orders else None

    def _simulate_full_plan(self, plan: List[Order], player_id: str,
                            game_state: GameState,
                            belief_sample: Dict[str, int]) -> float:
        """Simulate a complete plan and return evaluation score.

        v9 fix: evaluates ALL orders together instead of per-force.
        """
        try:
            clone = _clone_game_state(game_state)

            # Apply belief sample to enemy forces
            opponent = clone.get_opponent(player_id)
            if opponent:
                for fid, power in belief_sample.items():
                    f = opponent.get_force_by_id(fid)
                    if f and f.alive:
                        f.power = power

            # Remap orders to cloned forces
            player = clone.get_player_by_id(player_id)
            cloned_orders = []
            for order in plan:
                cloned_force = player.get_force_by_id(order.force.id) if player else None
                if cloned_force and cloned_force.alive:
                    cloned_orders.append(Order(
                        order.order_type, cloned_force,
                        target_hex=order.target_hex,
                        scout_target_id=order.scout_target_id,
                    ))

            # Generate opponent orders
            opp_orders = _simple_opponent_orders(opponent, clone) if opponent else []

            if player_id == 'p1':
                p1_orders, p2_orders = cloned_orders, opp_orders
            else:
                p1_orders, p2_orders = opp_orders, cloned_orders

            resolve_orders(p1_orders, p2_orders, clone)

            sov_captured = None
            for p in clone.players:
                sov = next((f for f in p.forces if f.power == 1), None)
                if sov and not sov.alive:
                    opp = clone.get_opponent(p.id)
                    sov_captured = {'winner': opp.id if opp else None}

            perform_upkeep(clone, sov_captured)
            return _evaluate_state(clone, player_id)
        except Exception:
            return 0.0

    def plan(self, player_id: str, game_state: GameState, rng: random.Random) -> List[Order]:
        """Whole-turn plan evaluation: compare 3 candidate plans across belief samples."""
        self._observe(player_id, game_state)

        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        if not opponent:
            return []

        self._update_beliefs(player, opponent)
        samples = self._sample_beliefs(self._n_samples)
        if not samples:
            return super().plan(player_id, game_state, rng)

        # Generate candidate plans
        baseline = super().plan(player_id, game_state, rng)
        aggressive = self._generate_aggressive_variant(player_id, game_state, rng)
        defensive = self._generate_defensive_variant(player_id, game_state, rng)

        candidates = [baseline]
        if aggressive:
            candidates.append(aggressive)
        if defensive:
            candidates.append(defensive)

        # Evaluate each complete plan across belief samples
        best_plan = baseline
        best_score = -9999.0

        for candidate in candidates:
            total = sum(
                self._simulate_full_plan(candidate, player_id, game_state, s)
                for s in samples
            )
            avg = total / len(samples)
            if avg > best_score:
                best_score = avg
                best_plan = candidate

        return best_plan


# ===========================================================================
# Strategy collections for the depth harness
# ===========================================================================

TIER1_STRATEGIES = []  # populated from simulate.py at import time
TIER2_STRATEGIES = [PatternReaderStrategy(), SupplyCutterStrategy()]
TIER3_STRATEGIES = [BayesianHunterStrategy()]
TIER4_STRATEGIES = [LookaheadStrategy(n_samples=4)]

ALL_ADVANCED_STRATEGIES = TIER2_STRATEGIES + TIER3_STRATEGIES + TIER4_STRATEGIES
