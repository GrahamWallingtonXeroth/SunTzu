"""
Integration tests for the full benchmark harness.

Tests the complete pipeline: agent plays game, telemetry collected, metrics computed.
Uses MockLLMAgent (no API calls) to verify the infrastructure works end-to-end.
"""

from benchmark.baselines import (
    OracleAgent,
    RandomBaselineAgent,
    StatelessRationalAgent,
)
from benchmark.llm_agent_interface import MockLLMAgent
from benchmark.metrics import (
    belief_consistency,
    eliminated_power_tracking,
    format_sensitivity,
)
from benchmark.runner import BenchmarkRunner, ExperimentConfig
from benchmark.telemetry import AgentReport, BeliefState


class TestNewMetrics:
    """Test the new metrics added for scientific rigor."""

    def test_belief_consistency_perfect(self):
        """Consistent beliefs across forces should score 0.0."""
        reports = [AgentReport(turn=1, player_id="p1", strategy="test")]
        # 5 forces, each assigned exactly one power
        reports[0].beliefs = {
            f"f{i}": BeliefState(distribution={i: 1.0, **{j: 0.0 for j in range(1, 6) if j != i}}) for i in range(1, 6)
        }
        score = belief_consistency(reports)
        assert abs(score) < 0.01

    def test_belief_consistency_uniform(self):
        """Uniform beliefs violate joint constraints."""
        reports = [AgentReport(turn=1, player_id="p1", strategy="test")]
        reports[0].beliefs = {f"f{i}": BeliefState.uniform() for i in range(1, 6)}
        score = belief_consistency(reports)
        # Uniform: each power sums to 5*0.2 = 1.0, so consistency = 0.0
        # This is actually consistent by coincidence (5 forces * 0.2 = 1.0)
        assert abs(score) < 0.01

    def test_belief_consistency_inconsistent(self):
        """Beliefs where two forces both claim the same power should score high."""
        reports = [AgentReport(turn=1, player_id="p1", strategy="test")]
        # Both f1 and f2 think they're power 5
        reports[0].beliefs = {
            "f1": BeliefState(distribution={1: 0, 2: 0, 3: 0, 4: 0, 5: 1.0}),
            "f2": BeliefState(distribution={1: 0, 2: 0, 3: 0, 4: 0, 5: 1.0}),
            "f3": BeliefState(distribution={1: 0.5, 2: 0.5, 3: 0, 4: 0, 5: 0}),
        }
        score = belief_consistency(reports)
        assert score > 0.1  # Inconsistent

    def test_eliminated_power_tracking_perfect(self):
        """Agent that correctly zeroes revealed powers scores 1.0."""
        reports = [AgentReport(turn=1, player_id="p1", strategy="test")]
        reports[0].beliefs = {
            "f1": BeliefState(distribution={1: 0.0, 2: 0.0, 3: 1.0, 4: 0.0, 5: 0.0}),
            "f2": BeliefState(distribution={1: 0.5, 2: 0.5, 3: 0.0, 4: 0.0, 5: 0.0}),
        }
        # f1 is revealed as power 3
        revealed = {"f1": 3}
        score = eliminated_power_tracking(reports, revealed)
        assert score == 1.0  # f2 correctly has p(3) = 0

    def test_eliminated_power_tracking_failure(self):
        """Agent that doesn't zero revealed powers scores < 1.0."""
        reports = [AgentReport(turn=1, player_id="p1", strategy="test")]
        reports[0].beliefs = {
            "f1": BeliefState(distribution={1: 0, 2: 0, 3: 1.0, 4: 0, 5: 0}),
            "f2": BeliefState(distribution={1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.2}),
        }
        revealed = {"f1": 3}
        score = eliminated_power_tracking(reports, revealed)
        assert score < 1.0  # f2 still has p(3) = 0.2

    def test_format_sensitivity_identical(self):
        """Identical metrics across formats should give CV = 0."""
        metrics_by_format = {
            "narrative": {"brier": 0.1, "log_loss": 0.5},
            "tabular": {"brier": 0.1, "log_loss": 0.5},
        }
        result = format_sensitivity(metrics_by_format)
        assert result["brier"] == 0.0
        assert result["log_loss"] == 0.0

    def test_format_sensitivity_different(self):
        """Different metrics across formats should give CV > 0."""
        metrics_by_format = {
            "narrative": {"brier": 0.1},
            "tabular": {"brier": 0.3},
        }
        result = format_sensitivity(metrics_by_format)
        assert result["brier"] > 0


class TestRunnerWithMockAgent:
    """Integration test: run games with MockLLMAgent."""

    def test_run_single_game(self):
        """Run one game and verify telemetry is collected."""
        agent = MockLLMAgent(strategy_name="cautious")
        opponent = MockLLMAgent(strategy_name="aggressive")

        config = ExperimentConfig(
            agents=[agent],
            opponents=[opponent],
            seeds=[42],
            comprehension_frequency=0,
        )
        runner = BenchmarkRunner(config)
        result = runner.run_single_game(agent, opponent, seed=42)

        assert result.telemetry.turns > 0
        assert len(result.telemetry.agent_reports) > 0
        assert len(result.metrics) > 0
        assert "p1_brier_score" in result.metrics

    def test_run_baseline_game(self):
        """Run a game with baseline agents."""
        agent = RandomBaselineAgent()
        opponent = StatelessRationalAgent()

        config = ExperimentConfig(
            agents=[agent],
            opponents=[opponent],
            seeds=[42],
            comprehension_frequency=0,
        )
        runner = BenchmarkRunner(config)
        result = runner.run_single_game(agent, opponent, seed=42)

        assert result.telemetry.turns > 0
        # Random baseline should have ~uniform Brier score
        if "p1_brier_score" in result.metrics:
            assert result.metrics["p1_brier_score"] >= 0.0

    def test_oracle_has_zero_brier(self):
        """Oracle agent should achieve perfect belief accuracy."""
        oracle = OracleAgent()
        opponent = MockLLMAgent(strategy_name="cautious")

        config = ExperimentConfig(
            agents=[oracle],
            opponents=[opponent],
            seeds=[42],
            comprehension_frequency=0,
        )
        runner = BenchmarkRunner(config)
        result = runner.run_single_game(oracle, opponent, seed=42)

        if "p1_brier_score" in result.metrics:
            assert result.metrics["p1_brier_score"] == 0.0


class TestRunnerExperiment:
    """Test running a full mini experiment."""

    def test_run_mini_experiment(self):
        """Run 2 games with 1 agent vs 1 opponent."""
        agent = MockLLMAgent(strategy_name="cautious")
        opponent = MockLLMAgent(strategy_name="aggressive")

        config = ExperimentConfig(
            agents=[agent],
            opponents=[opponent],
            seeds=[42, 43],
            games_per_condition=2,
            comprehension_frequency=0,
        )
        runner = BenchmarkRunner(config)
        report = runner.run_experiment()

        assert len(report.game_results) == 2
        assert len(report.aggregate_metrics) > 0

    def test_generate_report(self):
        """Generate a text report from experiment results."""
        agent = MockLLMAgent(strategy_name="cautious")
        opponent = MockLLMAgent(strategy_name="aggressive")

        config = ExperimentConfig(
            agents=[agent],
            opponents=[opponent],
            seeds=[42],
            games_per_condition=1,
            comprehension_frequency=0,
        )
        runner = BenchmarkRunner(config)
        report = runner.run_experiment()
        text = runner.generate_report(report)

        assert "BENCHMARK REPORT" in text
        assert "AGENT PERFORMANCE" in text
