"""
Baseline agent ladder for calibrating benchmark measurements.

Four agents at increasing sophistication establish an interpretable scale:

1. RandomBaseline: uniform beliefs, random orders → absolute floor
2. StatelessRational: current-turn only, no memory → single-turn reasoning floor
3. PerfectMemory: accumulates all reveals, applies permutation constraints → memory ceiling
4. Oracle: sees all powers → absolute ceiling

An LLM scoring below StatelessRational is confused about the rules.
An LLM scoring between StatelessRational and PerfectMemory reasons within
a turn but can't maintain beliefs. An LLM exceeding PerfectMemory is doing
genuine strategic inference beyond direct observation.
"""

from __future__ import annotations

import random

from benchmark.llm_agent_interface import LLMAgent
from benchmark.telemetry import AgentReport, BeliefState
from map_gen import get_hex_neighbors, hex_distance
from models import Player
from orders import ORDER_COSTS, Order, OrderType, _load_order_config, has_supply
from state import GameState


def _valid_moves(force, game_state: GameState) -> list[tuple[int, int]]:
    """Get valid move targets for a force (no friendly collision)."""
    targets = []
    for nq, nr in get_hex_neighbors(force.position[0], force.position[1]):
        if game_state.is_valid_position((nq, nr)):
            occupant = game_state.get_force_at_position((nq, nr))
            if (
                occupant is None
                or game_state.get_force_owner(occupant.id).id != game_state.get_force_owner(force.id).id
            ):
                targets.append((nq, nr))
    return targets


def _can_order(force, player: Player, order_type: OrderType) -> bool:
    """Check if a force can execute an order (Shih + supply)."""
    if player.shih < ORDER_COSTS[order_type]:
        return False
    if order_type in (OrderType.SCOUT, OrderType.FORTIFY, OrderType.AMBUSH, OrderType.CHARGE):
        cfg = _load_order_config()
        if not has_supply(force, player.forces, cfg["supply_range"], max_hops=cfg["max_supply_hops"]):
            return False
    return True


def _move_toward(force, target: tuple[int, int], game_state: GameState) -> tuple[int, int] | None:
    """Find adjacent hex closest to target."""
    moves = _valid_moves(force, game_state)
    if not moves:
        return None
    return min(moves, key=lambda m: hex_distance(m[0], m[1], target[0], target[1]))


def _build_uniform_beliefs(opponent: Player | None) -> dict[str, BeliefState]:
    """Uniform beliefs for all alive enemy forces."""
    beliefs = {}
    if opponent:
        for force in opponent.get_alive_forces():
            beliefs[force.id] = BeliefState.uniform()
    return beliefs


def _build_report(
    turn: int, player_id: str, strategy: str, beliefs: dict[str, BeliefState], orders: list[Order]
) -> AgentReport:
    """Build an AgentReport from beliefs and orders."""
    order_strs = []
    for o in orders:
        if o.order_type == OrderType.SCOUT:
            order_strs.append(f"Scout {o.force.id} -> {o.scout_target_id}")
        elif o.target_hex:
            order_strs.append(f"{o.order_type.value} {o.force.id} {o.target_hex}")
        else:
            order_strs.append(f"{o.order_type.value} {o.force.id}")

    return AgentReport(
        turn=turn,
        player_id=player_id,
        strategy=strategy,
        beliefs=beliefs,
        chosen_orders=order_strs,
        confidence=0.5,
    )


class RandomBaselineAgent(LLMAgent):
    """Uniform beliefs, random valid orders. Absolute measurement floor.

    Establishes: Brier ~0.16, log_loss ~1.61.
    Any agent scoring near this level is not reasoning at all.
    """

    @property
    def name(self) -> str:
        return "baseline_random"

    def deploy(self, player: Player, rng: random.Random) -> dict[str, int]:
        powers = [1, 2, 3, 4, 5]
        rng.shuffle(powers)
        return {f.id: p for f, p in zip(player.forces, powers, strict=False)}

    def observe_and_plan(
        self,
        player_id: str,
        game_state: GameState,
        rng: random.Random,
    ) -> tuple[list[Order], AgentReport]:
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)
        beliefs = _build_uniform_beliefs(opponent)

        orders = []
        for force in player.get_alive_forces():
            moves = _valid_moves(force, game_state)
            if moves:
                orders.append(Order(OrderType.MOVE, force, target_hex=rng.choice(moves)))

        report = _build_report(game_state.turn, player_id, self.name, beliefs, orders)
        return orders, report


class StatelessRationalAgent(LLMAgent):
    """Uses only current-turn observations. No cross-turn memory.

    Beliefs: uniform for unknown, exact for currently revealed (combat/scout).
    Orders: simple heuristic — advance toward center, protect sovereign.
    Establishes: single-turn reasoning floor.
    """

    @property
    def name(self) -> str:
        return "baseline_stateless"

    def deploy(self, player: Player, rng: random.Random) -> dict[str, int]:
        ids = [f.id for f in player.forces]
        # Sovereign in middle, strong forces in front
        powers = [5, 4, 1, 3, 2]
        return dict(zip(ids, powers, strict=False))

    def observe_and_plan(
        self,
        player_id: str,
        game_state: GameState,
        rng: random.Random,
    ) -> tuple[list[Order], AgentReport]:
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)

        # Build beliefs from current-turn observations only
        beliefs = {}
        if opponent:
            for force in opponent.get_alive_forces():
                if force.revealed:
                    dist = {i: 0.0 for i in range(1, 6)}
                    dist[force.power] = 1.0
                    beliefs[force.id] = BeliefState(distribution=dist)
                elif force.id in player.known_enemy_powers:
                    known = player.known_enemy_powers[force.id]
                    if known > 0:
                        dist = {i: 0.0 for i in range(1, 6)}
                        dist[known] = 1.0
                        beliefs[force.id] = BeliefState(distribution=dist)
                    else:
                        beliefs[force.id] = BeliefState.uniform()
                else:
                    beliefs[force.id] = BeliefState.uniform()

        # Simple heuristic orders
        center = (3, 3)
        orders = []
        for force in player.get_alive_forces():
            if force.is_sovereign:
                # Sovereign: move toward center, fortify if enemies nearby
                enemies_near = opponent and any(
                    hex_distance(force.position[0], force.position[1], e.position[0], e.position[1]) <= 2
                    for e in opponent.get_alive_forces()
                )
                if enemies_near and _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                else:
                    best = _move_toward(force, center, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
            else:
                best = _move_toward(force, center, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))

        report = _build_report(game_state.turn, player_id, self.name, beliefs, orders)
        return orders, report


class PerfectMemoryAgent(LLMAgent):
    """Perfect Bayesian updater from direct observations. No strategic inference.

    Accumulates all reveals across turns. Applies permutation constraints:
    if force A is revealed as power 3, all other forces get p(3)=0 and
    are renormalized.

    Establishes: what observation memory alone buys. An LLM exceeding this
    is doing genuine strategic inference.
    """

    def __init__(self):
        self._accumulated_knowledge: dict[str, int] = {}  # force_id -> known power
        self._eliminated_powers: set[int] = set()  # powers confirmed assigned

    @property
    def name(self) -> str:
        return "baseline_perfect_memory"

    def deploy(self, player: Player, rng: random.Random) -> dict[str, int]:
        ids = [f.id for f in player.forces]
        powers = [5, 4, 1, 3, 2]
        return dict(zip(ids, powers, strict=False))

    def observe_and_plan(
        self,
        player_id: str,
        game_state: GameState,
        rng: random.Random,
    ) -> tuple[list[Order], AgentReport]:
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)

        # Update accumulated knowledge
        if opponent:
            for force in opponent.get_alive_forces():
                if force.revealed and force.power is not None:
                    self._accumulated_knowledge[force.id] = force.power
                    self._eliminated_powers.add(force.power)
                elif force.id in player.known_enemy_powers:
                    known = player.known_enemy_powers[force.id]
                    if known > 0:
                        self._accumulated_knowledge[force.id] = known
                        self._eliminated_powers.add(known)

        # Build beliefs with permutation constraints
        beliefs = {}
        if opponent:
            remaining_powers = {p for p in range(1, 6)} - self._eliminated_powers

            for force in opponent.get_alive_forces():
                if force.id in self._accumulated_knowledge:
                    # Known exactly
                    power = self._accumulated_knowledge[force.id]
                    dist = {i: 0.0 for i in range(1, 6)}
                    dist[power] = 1.0
                    beliefs[force.id] = BeliefState(distribution=dist)
                else:
                    # Uniform over remaining (unassigned) powers
                    dist = {i: 0.0 for i in range(1, 6)}
                    if remaining_powers:
                        prob = 1.0 / len(remaining_powers)
                        for p in remaining_powers:
                            dist[p] = prob
                    else:
                        # Shouldn't happen, but fallback to uniform
                        dist = {i: 0.2 for i in range(1, 6)}
                    beliefs[force.id] = BeliefState(distribution=dist)

        # Heuristic orders: attack known-weak, scout unknown, protect sovereign
        center = (3, 3)
        orders = []
        for force in player.get_alive_forces():
            if force.is_sovereign:
                if _can_order(force, player, OrderType.FORTIFY):
                    orders.append(Order(OrderType.FORTIFY, force))
                else:
                    best = _move_toward(force, center, game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            # Try to scout unknown nearby enemies
            if opponent and force.power and force.power <= 3:
                visible_enemies = [
                    e
                    for e in opponent.get_alive_forces()
                    if hex_distance(force.position[0], force.position[1], e.position[0], e.position[1]) <= 2
                ]
                unscouted = [e for e in visible_enemies if e.id not in self._accumulated_knowledge]
                if unscouted and _can_order(force, player, OrderType.SCOUT):
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=unscouted[0].id))
                    continue

            best = _move_toward(force, center, game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))

        report = _build_report(game_state.turn, player_id, self.name, beliefs, orders)
        return orders, report


class OracleAgent(LLMAgent):
    """Sees all powers. Absolute ceiling for decision and belief quality.

    Brier = 0.0, log_loss = 0.0, calibration = 0.0.
    NOTE: Requires full GameState (not fog-filtered). The runner handles this.
    """

    @property
    def name(self) -> str:
        return "baseline_oracle"

    def deploy(self, player: Player, rng: random.Random) -> dict[str, int]:
        ids = [f.id for f in player.forces]
        # Optimal: sovereign in back, strongest in front
        powers = [5, 4, 1, 3, 2]
        return dict(zip(ids, powers, strict=False))

    def observe_and_plan(
        self,
        player_id: str,
        game_state: GameState,
        rng: random.Random,
    ) -> tuple[list[Order], AgentReport]:
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)

        # Perfect beliefs
        beliefs = {}
        if opponent:
            for force in opponent.get_alive_forces():
                dist = {i: 0.0 for i in range(1, 6)}
                if force.power is not None:
                    dist[force.power] = 1.0
                beliefs[force.id] = BeliefState(distribution=dist)

        # Optimal heuristic: charge enemy sovereign, ambush against strong enemies
        orders = []
        sovereign_target = None
        if opponent:
            for ef in opponent.get_alive_forces():
                if ef.is_sovereign:
                    sovereign_target = ef.position
                    break

        for force in player.get_alive_forces():
            if force.is_sovereign:
                if _can_order(force, player, OrderType.AMBUSH):
                    orders.append(Order(OrderType.AMBUSH, force))
                else:
                    # Move away from enemies
                    best = _move_toward(force, (0, 0) if player_id == "p1" else (6, 6), game_state)
                    if best:
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            if sovereign_target and force.power and force.power >= 4:
                # Rush enemy sovereign
                best = _move_toward(force, sovereign_target, game_state)
                if best:
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))
                continue

            # Default: move toward center
            best = _move_toward(force, (3, 3), game_state)
            if best:
                orders.append(Order(OrderType.MOVE, force, target_hex=best))

        report = _build_report(game_state.turn, player_id, self.name, beliefs, orders)
        report.confidence = 1.0
        return orders, report


# All baselines for easy import
BASELINE_AGENTS = {
    "random": RandomBaselineAgent,
    "stateless": StatelessRationalAgent,
    "perfect_memory": PerfectMemoryAgent,
    "oracle": OracleAgent,
}
