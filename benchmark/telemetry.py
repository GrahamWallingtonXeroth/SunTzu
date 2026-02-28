"""
Telemetry schemas for benchmark instrumentation.

Captures per-turn beliefs, predictions, and events for measuring strategic
reasoning quality. All schemas are JSON-serializable for JSONL output.

Usage:
    report = AgentReport(turn=5, player_id='p1', strategy='bayesian_hunter')
    report.beliefs['p2_f1'] = BeliefState(distribution={1: 0.1, 2: 0.2, ...})
    report.action_predictions['p2_f1'] = {'Move': 0.4, 'Charge': 0.3, ...}

    event_log = EventLog(turn=5)
    event_log.add_combat('p1_f3', 'p2_f1', 4, 2, 'attacker_wins')
    event_log.add_scout_reveal('p1_f2', 'p2_f4', 'band_high', 5)
"""

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BeliefState:
    """Probability distribution over an enemy force's hidden power value."""

    distribution: dict[int, float] = field(default_factory=dict)

    def entropy(self) -> float:
        """Shannon entropy H = -sum(p * log2(p))."""
        h = 0.0
        for p in self.distribution.values():
            if p > 0:
                h -= p * math.log2(p)
        return h

    def max_probability(self) -> float:
        """Maximum probability in the distribution (confidence)."""
        return max(self.distribution.values()) if self.distribution else 0.0

    def predicted_power(self) -> int:
        """Most likely power value."""
        if not self.distribution:
            return 0
        return max(self.distribution, key=self.distribution.get)

    @staticmethod
    def uniform() -> "BeliefState":
        """Uniform prior over power values 1-5."""
        return BeliefState(distribution={i: 0.2 for i in range(1, 6)})

    def to_dict(self) -> dict:
        return {str(k): v for k, v in self.distribution.items()}


@dataclass
class AgentReport:
    """Per-turn report from an agent, capturing beliefs and predictions.

    This is the primary telemetry unit for measuring strategic reasoning.
    Each turn, the agent reports:
    - beliefs: probability distributions over each enemy force's power
    - action_predictions: predicted opponent orders per force
    - objective_prediction: predicted opponent high-level objective
    - chosen_orders: the orders this agent chose
    - confidence: self-reported confidence (0-1)
    """

    turn: int
    player_id: str
    strategy: str
    beliefs: dict[str, BeliefState] = field(default_factory=dict)
    action_predictions: dict[str, dict[str, float]] = field(default_factory=dict)
    objective_prediction: dict[str, float] = field(default_factory=dict)
    chosen_orders: list[str] = field(default_factory=list)
    confidence: float = 0.5
    raw_reasoning: str = ""  # Free-text reasoning output for analysis

    def belief_entropy(self) -> float:
        """Average entropy across all belief distributions."""
        if not self.beliefs:
            return 0.0
        return sum(b.entropy() for b in self.beliefs.values()) / len(self.beliefs)

    def prediction_confidence(self) -> float:
        """Average max probability across action predictions."""
        if not self.action_predictions:
            return 0.0
        confs = []
        for pred in self.action_predictions.values():
            if pred:
                confs.append(max(pred.values()))
        return sum(confs) / len(confs) if confs else 0.0

    def to_dict(self) -> dict:
        d = {
            "turn": self.turn,
            "player_id": self.player_id,
            "strategy": self.strategy,
            "beliefs": {k: v.to_dict() for k, v in self.beliefs.items()},
            "action_predictions": self.action_predictions,
            "objective_prediction": self.objective_prediction,
            "chosen_orders": self.chosen_orders,
            "confidence": self.confidence,
        }
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class EventLog:
    """Per-turn event log capturing game events for ground truth.

    Events include: combat results, scout reveals, noose kills, movements.
    Used to compute prediction accuracy against actual outcomes.
    """

    turn: int
    events: list[dict[str, Any]] = field(default_factory=list)

    def add_combat(
        self, attacker_id: str, defender_id: str, attacker_power: int, defender_power: int, result: str
    ) -> None:
        self.events.append(
            {
                "type": "combat",
                "attacker": attacker_id,
                "defender": defender_id,
                "attacker_power": attacker_power,
                "defender_power": defender_power,
                "result": result,
            }
        )

    def add_scout_reveal(self, scout_id: str, target_id: str, revealed: str, actual_power: int) -> None:
        self.events.append(
            {
                "type": "scout_reveal",
                "scout": scout_id,
                "target": target_id,
                "revealed": revealed,
                "actual_power": actual_power,
            }
        )

    def add_noose_kill(self, force_id: str, position: tuple[int, int], was_sovereign: bool) -> None:
        self.events.append(
            {
                "type": "noose_kill",
                "force": force_id,
                "position": list(position),
                "was_sovereign": was_sovereign,
            }
        )

    def add_movement(self, force_id: str, from_pos: tuple[int, int], to_pos: tuple[int, int]) -> None:
        self.events.append(
            {
                "type": "movement",
                "force": force_id,
                "from": list(from_pos),
                "to": list(to_pos),
            }
        )

    def to_dict(self) -> dict:
        return {"turn": self.turn, "events": self.events}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class GameTelemetry:
    """Complete telemetry record for a single game.

    Collects all AgentReports and EventLogs, then provides methods to
    compute benchmark metrics.
    """

    game_id: str = ""
    p1_strategy: str = ""
    p2_strategy: str = ""
    seed: int = 0
    agent_reports: list[AgentReport] = field(default_factory=list)
    event_logs: list[EventLog] = field(default_factory=list)
    comprehension_results: list["ComprehensionResult"] = field(default_factory=list)
    winner: str | None = None
    victory_type: str | None = None
    turns: int = 0

    def add_report(self, report: AgentReport) -> None:
        self.agent_reports.append(report)

    def add_event_log(self, event_log: EventLog) -> None:
        self.event_logs.append(event_log)

    def get_reports_for_player(self, player_id: str) -> list[AgentReport]:
        return [r for r in self.agent_reports if r.player_id == player_id]

    def to_jsonl(self) -> str:
        """Serialize as JSONL (one JSON object per line)."""
        lines = []
        header = {
            "type": "game_header",
            "game_id": self.game_id,
            "p1_strategy": self.p1_strategy,
            "p2_strategy": self.p2_strategy,
            "seed": self.seed,
            "winner": self.winner,
            "victory_type": self.victory_type,
            "turns": self.turns,
        }
        lines.append(json.dumps(header))
        for report in self.agent_reports:
            entry = {"type": "agent_report"}
            entry.update(report.to_dict())
            lines.append(json.dumps(entry))
        for event_log in self.event_logs:
            entry = {"type": "event_log"}
            entry.update(event_log.to_dict())
            lines.append(json.dumps(entry))
        return "\n".join(lines)

    def add_comprehension_result(self, result: "ComprehensionResult") -> None:
        self.comprehension_results.append(result)

    def write_jsonl(self, filepath: str) -> None:
        """Write telemetry to a JSONL file."""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w") as f:
            f.write(self.to_jsonl())
            f.write("\n")


@dataclass
class ComprehensionResult:
    """Per-turn comprehension probe results.

    Records whether the agent correctly understood the game state
    before reasoning metrics are computed.
    """

    turn: int
    player_id: str
    probes: list[dict[str, Any]] = field(default_factory=list)
    # Each probe: {question, expected, response, correct}
    score: float = 0.0  # Fraction correct (0.0 to 1.0)

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "player_id": self.player_id,
            "probes": self.probes,
            "score": self.score,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
