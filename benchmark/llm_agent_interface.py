"""
LLM agent interface for The Unfought Battle v10 benchmark.

Defines the abstract interface that LLM-based agents must implement,
plus a MockLLMAgent for testing the harness without actual API calls.

Usage:
    agent = MockLLMAgent(strategy='bayesian_hunter')
    report = agent.observe_and_plan(player_id, game_state, rng)
    orders = report.chosen_orders  # List of Order objects

To implement a real LLM agent:
    1. Subclass LLMAgent
    2. Implement observe() to format game state for the LLM
    3. Implement plan() to parse LLM output into orders
    4. Return AgentReport with beliefs and predictions
"""

import random
from abc import ABC, abstractmethod

from benchmark.telemetry import AgentReport, BeliefState
from models import Player
from orders import Order, OrderType
from state import GameState


class LLMAgent(ABC):
    """Abstract interface for LLM-based game agents.

    The benchmark framework calls observe_and_plan() each turn.
    The agent must:
    1. Observe the current game state
    2. Update internal beliefs about hidden enemy information
    3. Generate orders for all alive forces
    4. Return an AgentReport with beliefs, predictions, and orders
    """

    @abstractmethod
    def observe_and_plan(
        self,
        player_id: str,
        game_state: GameState,
        rng: random.Random,
    ) -> tuple[list[Order], AgentReport]:
        """
        Observe the game state and generate orders + telemetry.

        Args:
            player_id: This agent's player ID ('p1' or 'p2')
            game_state: Current game state (filtered by fog of war)
            rng: Random number generator for reproducibility

        Returns:
            Tuple of (list of orders, AgentReport with beliefs/predictions)
        """
        ...

    @abstractmethod
    def deploy(
        self,
        player: Player,
        rng: random.Random,
    ) -> dict[str, int]:
        """
        Assign power values (1-5) to forces during deployment.

        Args:
            player: This agent's player object
            rng: Random number generator

        Returns:
            Dict mapping force_id -> power value (1-5, each used once)
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for logging and metrics."""
        ...


class MockLLMAgent(LLMAgent):
    """Mock LLM agent that wraps an existing strategy for testing.

    Delegates game decisions to a Strategy object from simulate.py,
    but generates proper AgentReport telemetry as if it were an LLM.
    Used to validate the benchmark harness without API calls.
    """

    def __init__(self, strategy_name: str = "cautious"):
        self._strategy_name = strategy_name
        self._strategy = None
        self._beliefs: dict[str, BeliefState] = {}

    @property
    def name(self) -> str:
        return f"mock_llm_{self._strategy_name}"

    def _get_strategy(self):
        """Lazy-load strategy to avoid circular imports."""
        if self._strategy is None:
            from tests.simulate import STRATEGY_MAP

            self._strategy = STRATEGY_MAP.get(self._strategy_name)
            if self._strategy is None:
                from tests.simulate import CautiousStrategy

                self._strategy = CautiousStrategy()
        return self._strategy

    def deploy(self, player: Player, rng: random.Random) -> dict[str, int]:
        return self._get_strategy().deploy(player, rng)

    def observe_and_plan(
        self,
        player_id: str,
        game_state: GameState,
        rng: random.Random,
    ) -> tuple[list[Order], AgentReport]:
        strategy = self._get_strategy()
        player = game_state.get_player_by_id(player_id)
        opponent = game_state.get_opponent(player_id)

        # Generate orders from the underlying strategy
        orders = strategy.plan(player_id, game_state, rng)

        # Build beliefs from known_enemy_powers + uniform prior
        beliefs = {}
        if opponent:
            for force in opponent.forces:
                if not force.alive:
                    continue
                if force.id in player.known_enemy_powers:
                    known = player.known_enemy_powers[force.id]
                    if known > 0:
                        # Exact knowledge
                        dist = {i: 0.0 for i in range(1, 6)}
                        dist[known] = 1.0
                        beliefs[force.id] = BeliefState(distribution=dist)
                    elif known < 0:
                        # Band knowledge from noisy scouting
                        band_map = {-1: [1, 2], -3: [3], -4: [4, 5]}
                        band = band_map.get(known, [1, 2, 3, 4, 5])
                        dist = {i: 0.0 for i in range(1, 6)}
                        for p in band:
                            dist[p] = 1.0 / len(band)
                        beliefs[force.id] = BeliefState(distribution=dist)
                    else:
                        beliefs[force.id] = BeliefState.uniform()
                else:
                    beliefs[force.id] = BeliefState.uniform()

        # Build simple action predictions (uniform)
        action_predictions = {}
        if opponent:
            for force in opponent.get_alive_forces():
                action_predictions[force.id] = {
                    "Move": 0.3,
                    "Charge": 0.2,
                    "Scout": 0.2,
                    "Fortify": 0.15,
                    "Ambush": 0.15,
                }

        # Format chosen orders as strings
        order_strs = []
        for o in orders:
            if o.order_type == OrderType.SCOUT:
                order_strs.append(f"Scout {o.force.id} -> {o.scout_target_id}")
            elif o.target_hex:
                order_strs.append(f"{o.order_type.value} {o.force.id} {o.target_hex}")
            else:
                order_strs.append(f"{o.order_type.value} {o.force.id}")

        report = AgentReport(
            turn=game_state.turn,
            player_id=player_id,
            strategy=self.name,
            beliefs=beliefs,
            action_predictions=action_predictions,
            chosen_orders=order_strs,
            confidence=0.5,
        )

        return orders, report
