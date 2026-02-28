"""
Concrete LLM agent for the reasoning benchmark.

Implements the three-stage pipeline:
  1. Perception: Render game state using configurable format
  2. Reasoning: LLM reasons freely in natural language
  3. Extraction: Convert reasoning to structured beliefs + orders

The prompt design is neutral — no CoT instructions, no example outputs,
no format constraints on reasoning. This avoids contaminating the measurement
of natural reasoning ability.
"""

from __future__ import annotations

import random

from benchmark.extraction import (
    ExtractionResult,
    extract_beliefs_and_orders,
    extract_deployment,
)
from benchmark.llm_agent_interface import LLMAgent
from benchmark.providers import LLMProvider
from benchmark.renderers import RENDERERS, render_rules_reference
from benchmark.telemetry import AgentReport
from models import Player
from orders import Order, OrderType
from state import GameState, get_player_view, load_config


class ReasoningAgent(LLMAgent):
    """LLM-based agent that reasons about the game in natural language.

    Configurable across dimensions that matter for scientific evaluation:
    - render_format: how game state is presented (format invariance testing)
    - extraction_method: how structured data is extracted from reasoning
    - history_mode: how much history context is provided
    """

    def __init__(
        self,
        provider: LLMProvider,
        render_format: str = "narrative",
        extraction_method: str = "tool_calling",
        history_mode: str = "full",
        history_limit: int = 5,
        agent_name: str | None = None,
    ):
        self._provider = provider
        self._render_format = render_format
        self._extraction_method = extraction_method
        self._history_mode = history_mode
        self._history_limit = history_limit
        self._agent_name = agent_name or f"reasoning_{provider.model_id}_{render_format}"
        self._turn_history: list[dict] = []
        self._config = load_config()
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_latency_ms = 0.0

    @property
    def name(self) -> str:
        return self._agent_name

    @property
    def total_tokens(self) -> int:
        return self._total_input_tokens + self._total_output_tokens

    @property
    def total_cost_estimate(self) -> float:
        """Rough cost estimate in USD (Sonnet pricing as baseline)."""
        return (self._total_input_tokens * 3.0 + self._total_output_tokens * 15.0) / 1_000_000

    def deploy(self, player: Player, rng: random.Random) -> dict[str, int]:
        """LLM chooses deployment via API call with tool extraction."""
        force_ids = [f.id for f in player.forces]
        positions = [(f.position[0], f.position[1]) for f in player.forces]

        system = render_rules_reference(self._config)
        user_msg = (
            f"You are Player {player.id}. Deploy your 5 forces by assigning "
            f"power values 1-5 (each used exactly once).\n\n"
            f"Power 1 is your Sovereign — if captured, you lose the game. "
            f"Higher power means stronger in combat.\n\n"
            f"Your forces and starting positions:\n"
        )
        for fid, pos in zip(force_ids, positions, strict=False):
            user_msg += f"  {fid} at ({pos[0]},{pos[1]})\n"
        user_msg += (
            "\nConsider which positions are most exposed to enemy contact "
            "and where your Sovereign will be safest. Reason about your "
            "deployment strategy, then assign powers."
        )

        try:
            # First: get reasoning
            response = self._provider.complete(
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                temperature=0.0,
            )
            self._track_tokens(response)

            # Second: extract deployment
            assignments = extract_deployment(
                response.content,
                player.id,
                force_ids,
                self._provider,
            )
            if set(assignments.values()) == {1, 2, 3, 4, 5}:
                return assignments
        except Exception:
            pass

        # Fallback: random deployment
        powers = [1, 2, 3, 4, 5]
        rng.shuffle(powers)
        return dict(zip(force_ids, powers, strict=False))

    def observe_and_plan(
        self,
        player_id: str,
        game_state: GameState,
        rng: random.Random,
    ) -> tuple[list[Order], AgentReport]:
        """Three-stage pipeline: perceive → reason → extract."""

        # Stage 1: Perception — render state
        view = get_player_view(game_state, player_id)
        renderer = RENDERERS.get(self._render_format, RENDERERS["narrative"])

        history = self._get_history()
        rendered_state = renderer(view, self._config, history=history)

        # Stage 2: Reasoning — free-form LLM call
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(rendered_state, view)

        reasoning_response = self._provider.complete(
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.0,
        )
        self._track_tokens(reasoning_response)
        reasoning_text = reasoning_response.content

        # Stage 3: Extraction — convert to structured data
        extraction = extract_beliefs_and_orders(
            reasoning_text,
            view,
            player_id,
            self._provider,
            method=self._extraction_method,
        )
        self._track_tokens_from_extraction()

        # Convert to Order objects
        orders = self._build_orders(extraction, player_id, game_state)

        # Build AgentReport
        report = self._build_report(
            game_state.turn,
            player_id,
            extraction,
            reasoning_text,
        )

        # Update history
        self._update_history(game_state, view)

        return orders, report

    def _build_system_prompt(self) -> str:
        """Fixed system prompt with rules reference."""
        rules = render_rules_reference(self._config)
        return (
            f"You are playing The Unfought Battle, a strategic reasoning game "
            f"on a 7x7 hex grid.\n\n"
            f"{rules}\n\n"
            f"Your goal: Capture the enemy's Sovereign (power 1) or achieve "
            f"domination by controlling 2+ Contentious hexes for "
            f"{self._config.get('domination_turns_required', 4)} consecutive turns. "
            f"Protect your own Sovereign.\n\n"
            f"Each turn you will receive the current game state. Reason carefully about:\n"
            f"1. What you know and don't know about enemy force identities\n"
            f"2. What your opponent is likely trying to do based on their movements\n"
            f"3. What orders you should give each force, and why\n\n"
            f"Think step by step. Be explicit about your uncertainty."
        )

    def _build_user_prompt(self, rendered_state: str, view: dict) -> str:
        """Per-turn user prompt with state and reasoning request."""
        turn = view.get("turn", 0)
        return (
            f"CURRENT STATE (Turn {turn}):\n"
            f"{rendered_state}\n\n"
            f"Reason about the current situation. Consider what each enemy force "
            f"might be, what your opponent's strategy appears to be, and what you "
            f"should do this turn."
        )

    def _get_history(self) -> list[dict] | None:
        """Get history based on history_mode setting."""
        if self._history_mode == "none" or not self._turn_history:
            return None
        if self._history_mode == "last_n":
            return self._turn_history[-self._history_limit :]
        return self._turn_history  # "full" mode

    def _update_history(self, game_state: GameState, view: dict) -> None:
        """Record events from this turn for future history context."""
        # Extract relevant events from the game log
        for log_entry in game_state.log:
            if log_entry.get("turn") == game_state.turn:
                self._turn_history.append(
                    {
                        "turn": game_state.turn,
                        "type": "game_event",
                        "event": log_entry.get("event", ""),
                    }
                )

    def _build_orders(
        self,
        extraction: ExtractionResult,
        player_id: str,
        game_state: GameState,
    ) -> list[Order]:
        """Convert extracted order dicts to Order objects."""
        from map_gen import get_hex_neighbors

        player = game_state.get_player_by_id(player_id)
        if not player:
            return []

        orders = []
        ordered_forces = set()

        for order_dict in extraction.orders:
            force_id = order_dict.get("force_id", "")
            force = player.get_force_by_id(force_id)
            if not force or not force.alive or force_id in ordered_forces:
                continue

            order_type_str = order_dict.get("order_type", "Move")
            try:
                order_type = OrderType(order_type_str)
            except ValueError:
                order_type = OrderType.MOVE

            target_hex = order_dict.get("target_hex")
            scout_target = order_dict.get("scout_target_id")

            if order_type in (OrderType.MOVE, OrderType.CHARGE):
                if target_hex and game_state.is_valid_position(target_hex):
                    orders.append(Order(order_type, force, target_hex=target_hex))
                    ordered_forces.add(force_id)
                else:
                    # Fallback: move toward center
                    center = (3, 3)
                    neighbors = get_hex_neighbors(force.position[0], force.position[1])
                    valid = [n for n in neighbors if game_state.is_valid_position(n)]
                    if valid:
                        best = min(valid, key=lambda p: abs(p[0] - center[0]) + abs(p[1] - center[1]))
                        orders.append(Order(OrderType.MOVE, force, target_hex=best))
                        ordered_forces.add(force_id)
            elif order_type == OrderType.SCOUT:
                if scout_target:
                    orders.append(Order(OrderType.SCOUT, force, scout_target_id=scout_target))
                    ordered_forces.add(force_id)
            elif order_type in (OrderType.FORTIFY, OrderType.AMBUSH):
                orders.append(Order(order_type, force))
                ordered_forces.add(force_id)

        # Fallback: any unordered alive force gets Move toward center
        for force in player.get_alive_forces():
            if force.id not in ordered_forces:
                from map_gen import get_hex_neighbors

                neighbors = get_hex_neighbors(force.position[0], force.position[1])
                valid = [n for n in neighbors if game_state.is_valid_position(n)]
                if valid:
                    center = (3, 3)
                    best = min(valid, key=lambda p: abs(p[0] - center[0]) + abs(p[1] - center[1]))
                    orders.append(Order(OrderType.MOVE, force, target_hex=best))

        return orders

    def _build_report(
        self,
        turn: int,
        player_id: str,
        extraction: ExtractionResult,
        reasoning_text: str,
    ) -> AgentReport:
        """Build AgentReport from extraction results."""
        order_strs = []
        for o in extraction.orders:
            force_id = o.get("force_id", "?")
            order_type = o.get("order_type", "?")
            target = o.get("target_hex", "")
            scout = o.get("scout_target_id", "")
            s = f"{order_type} {force_id}"
            if target:
                s += f" {target}"
            if scout:
                s += f" -> {scout}"
            order_strs.append(s)

        return AgentReport(
            turn=turn,
            player_id=player_id,
            strategy=self.name,
            beliefs=extraction.beliefs,
            chosen_orders=order_strs,
            confidence=extraction.confidence,
            raw_reasoning=reasoning_text,
        )

    def _track_tokens(self, response) -> None:
        """Track token usage for cost reporting."""
        self._total_input_tokens += response.input_tokens
        self._total_output_tokens += response.output_tokens
        self._total_latency_ms += response.latency_ms

    def _track_tokens_from_extraction(self) -> None:
        """Placeholder for tracking extraction-step tokens."""
        # Extraction tokens are tracked within the provider calls
        pass
