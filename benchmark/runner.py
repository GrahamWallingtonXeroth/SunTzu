"""
Batch evaluation runner for the LLM reasoning benchmark.

Runs N games x M formats x K agents x L opponents, collects telemetry,
computes metrics with confidence intervals, and generates reports.

Usage:
    python -m benchmark.runner --help
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any

from benchmark.comprehension import (
    COMPREHENSION_THRESHOLD,
    format_probes_as_prompt,
    generate_probes,
    parse_probe_responses,
    score_comprehension,
)
from benchmark.llm_agent_interface import LLMAgent
from benchmark.metrics import (
    compute_extended_game_metrics,
)
from benchmark.telemetry import ComprehensionResult, EventLog, GameTelemetry
from orders import resolve_orders
from state import GameState, apply_deployment, get_player_view, initialize_game, load_config
from upkeep import perform_upkeep

MAX_TURNS = 30


@dataclass
class ExperimentConfig:
    """Configuration for a benchmark experiment."""

    agents: list[LLMAgent]
    opponents: list[LLMAgent]
    seeds: list[int] = field(default_factory=lambda: list(range(30)))
    formats: list[str] = field(default_factory=lambda: ["narrative"])
    games_per_condition: int = 30
    comprehension_frequency: int = 3  # probe every N turns (0 = disabled)
    output_dir: str = "benchmark_results"


@dataclass
class GameResult:
    """Result of a single benchmark game."""

    telemetry: GameTelemetry
    metrics: dict[str, float]
    comprehension_scores: list[float]
    format_used: str
    agent_name: str
    opponent_name: str
    seed: int
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "agent": self.agent_name,
            "opponent": self.opponent_name,
            "format": self.format_used,
            "seed": self.seed,
            "winner": self.telemetry.winner,
            "victory_type": self.telemetry.victory_type,
            "turns": self.telemetry.turns,
            "metrics": self.metrics,
            "comprehension_scores": self.comprehension_scores,
            "avg_comprehension": (
                sum(self.comprehension_scores) / len(self.comprehension_scores) if self.comprehension_scores else 0.0
            ),
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_latency_ms": self.total_latency_ms,
        }


@dataclass
class ExperimentReport:
    """Aggregate results from a benchmark experiment."""

    game_results: list[GameResult] = field(default_factory=list)
    aggregate_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    format_sensitivity_scores: dict[str, float] = field(default_factory=dict)
    baseline_comparisons: dict[str, dict[str, Any]] = field(default_factory=dict)
    comprehension_summary: dict[str, float] = field(default_factory=dict)


class BenchmarkRunner:
    """Runs benchmark experiments with scientific controls."""

    def __init__(self, config: ExperimentConfig):
        self.config = config
        self._game_config = load_config()

    def run_single_game(
        self,
        agent: LLMAgent,
        opponent: LLMAgent,
        seed: int,
        rng_seed: int = 0,
    ) -> GameResult:
        """Run one game between agent and opponent.

        Adapted from tests/simulate.py:run_game() but uses LLMAgent interface.
        """
        game = initialize_game(seed)
        rng = __import__("random").Random(rng_seed)

        # Deploy
        p1_deploy = agent.deploy(game.get_player_by_id("p1"), rng)
        p2_deploy = opponent.deploy(game.get_player_by_id("p2"), rng)
        apply_deployment(game, "p1", p1_deploy)
        apply_deployment(game, "p2", p2_deploy)

        telemetry = GameTelemetry(
            game_id=f"{agent.name}_vs_{opponent.name}_seed{seed}",
            p1_strategy=agent.name,
            p2_strategy=opponent.name,
            seed=seed,
        )

        comprehension_scores: list[float] = []

        while game.phase != "ended" and game.turn <= MAX_TURNS:
            if game.phase != "plan":
                break

            # Run comprehension probes (if enabled)
            if (
                self.config.comprehension_frequency > 0
                and game.turn % self.config.comprehension_frequency == 1
                and hasattr(agent, "_provider")
            ):
                comp_result = self._run_comprehension_probes(
                    agent,
                    "p1",
                    game,
                )
                if comp_result:
                    telemetry.add_comprehension_result(comp_result)
                    comprehension_scores.append(comp_result.score)

            # Get orders from both agents
            p1_orders, p1_report = agent.observe_and_plan("p1", game, rng)
            p2_orders, p2_report = opponent.observe_and_plan("p2", game, rng)
            telemetry.add_report(p1_report)
            telemetry.add_report(p2_report)

            # Resolve
            event_log = EventLog(turn=game.turn)
            game.phase = "resolve"
            result = resolve_orders(p1_orders, p2_orders, game)

            # Record events
            for combat in result.get("combats", []):
                event_log.add_combat(
                    combat.get("attacker_id", ""),
                    combat.get("defender_id", ""),
                    combat.get("attacker_power", 0),
                    combat.get("defender_power", 0),
                    combat.get("outcome", ""),
                )
            for scout in result.get("scouts", []):
                revealed = str(scout.get("revealed_power", scout.get("revealed_band", "")))
                event_log.add_scout_reveal(
                    scout.get("scouting_force", ""),
                    scout.get("scouted_force", ""),
                    revealed,
                    scout.get("actual_power", 0),
                )

            telemetry.add_event_log(event_log)

            # Upkeep
            sovereign_capture = result.get("sovereign_captured")
            upkeep = perform_upkeep(game, sovereign_capture)

            for evt in upkeep.get("noose_events", []):
                if evt.get("type") == "force_scorched":
                    event_log.add_noose_kill(
                        evt["force_id"],
                        tuple(evt.get("position", [0, 0])),
                        evt.get("was_sovereign", False),
                    )

            if upkeep.get("winner"):
                break

        # Finalize telemetry
        telemetry.winner = game.winner
        telemetry.victory_type = game.victory_type
        telemetry.turns = min(game.turn, MAX_TURNS)

        # Compute metrics
        ground_truth = {}
        revealed_powers = {}
        for pid in ["p1", "p2"]:
            p = game.get_player_by_id(pid)
            for f in p.forces:
                ground_truth[f.id] = f.power
                if f.revealed:
                    revealed_powers[f.id] = f.power

        metrics = compute_extended_game_metrics(telemetry, ground_truth, revealed_powers)

        # Add win/loss
        metrics["p1_win"] = 1.0 if game.winner == "p1" else 0.0
        metrics["p2_win"] = 1.0 if game.winner == "p2" else 0.0

        return GameResult(
            telemetry=telemetry,
            metrics=metrics,
            comprehension_scores=comprehension_scores,
            format_used="default",
            agent_name=agent.name,
            opponent_name=opponent.name,
            seed=seed,
        )

    def run_experiment(self) -> ExperimentReport:
        """Run full experiment across all conditions."""
        report = ExperimentReport()

        for agent in self.config.agents:
            for opponent in self.config.opponents:
                for seed_idx, seed in enumerate(self.config.seeds[: self.config.games_per_condition]):
                    game_result = self.run_single_game(
                        agent,
                        opponent,
                        seed,
                        rng_seed=seed_idx * 1000,
                    )
                    report.game_results.append(game_result)

        # Aggregate metrics
        report.aggregate_metrics = self._aggregate_metrics(report.game_results)
        report.comprehension_summary = self._aggregate_comprehension(report.game_results)

        return report

    def _run_comprehension_probes(
        self,
        agent: LLMAgent,
        player_id: str,
        game_state: GameState,
    ) -> ComprehensionResult | None:
        """Run comprehension probes and score responses."""
        view = get_player_view(game_state, player_id)
        probes = generate_probes(view, game_state, player_id, self._game_config, n_probes=5)

        if not probes or not hasattr(agent, "_provider"):
            return None

        prompt = format_probes_as_prompt(probes)

        try:
            response = agent._provider.complete(
                system="Answer each question briefly and precisely. Number your answers.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=500,
            )
            responses = parse_probe_responses(response.content, len(probes))
            score = score_comprehension(probes, responses)

            probe_records = []
            for probe, resp in zip(probes, responses, strict=False):
                probe_records.append(
                    {
                        "question": probe.question,
                        "expected": probe.expected_answer,
                        "response": resp,
                        "correct": probe.validate(resp),
                        "category": probe.category,
                    }
                )

            return ComprehensionResult(
                turn=game_state.turn,
                player_id=player_id,
                probes=probe_records,
                score=score,
            )
        except Exception:
            return None

    def _aggregate_metrics(
        self,
        results: list[GameResult],
    ) -> dict[str, dict[str, float]]:
        """Aggregate metrics across games with confidence intervals."""
        # Group by agent
        by_agent: dict[str, list[dict[str, float]]] = {}
        for r in results:
            if r.agent_name not in by_agent:
                by_agent[r.agent_name] = []
            by_agent[r.agent_name].append(r.metrics)

        aggregate = {}
        for agent_name, metrics_list in by_agent.items():
            # Collect all metric keys
            all_keys: set[str] = set()
            for m in metrics_list:
                all_keys.update(m.keys())

            agent_agg = {}
            for key in sorted(all_keys):
                values = [m.get(key, 0.0) for m in metrics_list if key in m]
                if not values:
                    continue
                n = len(values)
                mean = sum(values) / n
                if n >= 2:
                    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
                    std = math.sqrt(variance)
                    # 95% CI using t-distribution approximation (z=1.96 for large n)
                    ci_margin = 1.96 * std / math.sqrt(n)
                else:
                    std = 0.0
                    ci_margin = 0.0

                agent_agg[key] = {
                    "mean": mean,
                    "std": std,
                    "ci_lower": mean - ci_margin,
                    "ci_upper": mean + ci_margin,
                    "n": n,
                }
            aggregate[agent_name] = agent_agg

        return aggregate

    def _aggregate_comprehension(
        self,
        results: list[GameResult],
    ) -> dict[str, float]:
        """Aggregate comprehension scores by agent."""
        by_agent: dict[str, list[float]] = {}
        for r in results:
            if r.comprehension_scores:
                if r.agent_name not in by_agent:
                    by_agent[r.agent_name] = []
                by_agent[r.agent_name].extend(r.comprehension_scores)

        summary = {}
        for agent_name, scores in by_agent.items():
            avg = sum(scores) / len(scores) if scores else 0.0
            summary[f"{agent_name}_avg_comprehension"] = avg
            summary[f"{agent_name}_comprehension_pass_rate"] = (
                sum(1 for s in scores if s >= COMPREHENSION_THRESHOLD) / len(scores) if scores else 0.0
            )

        return summary

    def generate_report(self, experiment: ExperimentReport) -> str:
        """Generate human-readable summary report."""
        lines = [
            "=" * 70,
            "  LLM REASONING BENCHMARK REPORT",
            "=" * 70,
            "",
        ]

        # Per-agent performance
        lines.append("AGENT PERFORMANCE:")
        lines.append("-" * 70)
        for agent_name, metrics in experiment.aggregate_metrics.items():
            lines.append(f"\n  Agent: {agent_name}")
            for metric_name, stats in sorted(metrics.items()):
                if metric_name.startswith("p1_"):
                    display_name = metric_name[3:]  # strip p1_ prefix
                    lines.append(
                        f"    {display_name:<30} "
                        f"{stats['mean']:.4f} +/- {stats['std']:.4f} "
                        f"[{stats['ci_lower']:.4f}, {stats['ci_upper']:.4f}] "
                        f"(n={stats['n']})"
                    )

        # Comprehension
        if experiment.comprehension_summary:
            lines.append("\n\nCOMPREHENSION GATE:")
            lines.append("-" * 70)
            for key, value in experiment.comprehension_summary.items():
                lines.append(f"  {key}: {value:.3f}")

        # Format sensitivity
        if experiment.format_sensitivity_scores:
            lines.append("\n\nFORMAT SENSITIVITY (CV):")
            lines.append("-" * 70)
            for metric, cv in experiment.format_sensitivity_scores.items():
                flag = " *** HIGH ***" if cv > 0.15 else ""
                lines.append(f"  {metric:<30} CV={cv:.4f}{flag}")

        lines.append("\n" + "=" * 70)
        return "\n".join(lines)

    def write_results(self, experiment: ExperimentReport, output_dir: str | None = None) -> None:
        """Write all results to disk."""
        out = output_dir or self.config.output_dir
        os.makedirs(out, exist_ok=True)

        # Summary report
        report_text = self.generate_report(experiment)
        with open(os.path.join(out, "summary_report.txt"), "w") as f:
            f.write(report_text)

        # Per-game results as JSONL
        with open(os.path.join(out, "game_results.jsonl"), "w") as f:
            for result in experiment.game_results:
                f.write(json.dumps(result.to_dict()) + "\n")

        # Aggregate metrics
        with open(os.path.join(out, "aggregate_metrics.json"), "w") as f:
            json.dump(experiment.aggregate_metrics, f, indent=2)

        # Comprehension summary
        with open(os.path.join(out, "comprehension.json"), "w") as f:
            json.dump(experiment.comprehension_summary, f, indent=2)

        # Per-game telemetry
        telemetry_dir = os.path.join(out, "telemetry")
        os.makedirs(telemetry_dir, exist_ok=True)
        for i, result in enumerate(experiment.game_results):
            filepath = os.path.join(
                telemetry_dir,
                f"game_{i:04d}_{result.agent_name}_vs_{result.opponent_name}.jsonl",
            )
            result.telemetry.write_jsonl(filepath)
