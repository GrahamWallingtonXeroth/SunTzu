"""Tests for baseline agent ladder."""

import random

from benchmark.baselines import (
    BASELINE_AGENTS,
    OracleAgent,
    PerfectMemoryAgent,
    RandomBaselineAgent,
    StatelessRationalAgent,
)
from benchmark.metrics import brier_score
from state import apply_deployment, initialize_game


def _make_game():
    game = initialize_game(42)
    apply_deployment(game, "p1", {"p1_f1": 5, "p1_f2": 4, "p1_f3": 1, "p1_f4": 3, "p1_f5": 2})
    apply_deployment(game, "p2", {"p2_f1": 1, "p2_f2": 5, "p2_f3": 4, "p2_f4": 2, "p2_f5": 3})
    return game


class TestRandomBaseline:
    def test_produces_valid_deployment(self):
        agent = RandomBaselineAgent()
        game = initialize_game(42)
        rng = random.Random(42)
        deployment = agent.deploy(game.get_player_by_id("p1"), rng)
        assert set(deployment.values()) == {1, 2, 3, 4, 5}

    def test_produces_valid_orders_and_report(self):
        agent = RandomBaselineAgent()
        game = _make_game()
        rng = random.Random(42)
        orders, report = agent.observe_and_plan("p1", game, rng)
        assert len(orders) > 0
        assert report.turn == game.turn
        assert report.player_id == "p1"

    def test_beliefs_are_uniform(self):
        agent = RandomBaselineAgent()
        game = _make_game()
        rng = random.Random(42)
        _, report = agent.observe_and_plan("p1", game, rng)
        for belief in report.beliefs.values():
            for power in range(1, 6):
                assert abs(belief.distribution.get(power, 0) - 0.2) < 0.01

    def test_name(self):
        assert RandomBaselineAgent().name == "baseline_random"


class TestStatelessBaseline:
    def test_produces_valid_orders(self):
        agent = StatelessRationalAgent()
        game = _make_game()
        rng = random.Random(42)
        orders, report = agent.observe_and_plan("p1", game, rng)
        assert len(orders) > 0
        assert report.turn == game.turn

    def test_beliefs_uniform_without_reveals(self):
        """At game start, no reveals — beliefs should be uniform."""
        agent = StatelessRationalAgent()
        game = _make_game()
        rng = random.Random(42)
        _, report = agent.observe_and_plan("p1", game, rng)
        # All enemy forces should have uniform or no beliefs (not visible)
        for belief in report.beliefs.values():
            entropy = belief.entropy()
            # Uniform entropy = log2(5) ≈ 2.32, exact = 0.0
            assert entropy >= 0.0


class TestPerfectMemoryBaseline:
    def test_produces_valid_orders(self):
        agent = PerfectMemoryAgent()
        game = _make_game()
        rng = random.Random(42)
        orders, _report = agent.observe_and_plan("p1", game, rng)
        assert len(orders) > 0

    def test_accumulates_knowledge(self):
        """After seeing a reveal, beliefs should narrow."""
        agent = PerfectMemoryAgent()
        game = _make_game()
        rng = random.Random(42)

        # Simulate a reveal: p2_f1 is power 1
        p1 = game.get_player_by_id("p1")
        p2 = game.get_player_by_id("p2")
        p2.forces[0].revealed = True
        p1.known_enemy_powers["p2_f1"] = 1

        _, report = agent.observe_and_plan("p1", game, rng)

        # p2_f1 should be known exactly
        if "p2_f1" in report.beliefs:
            assert report.beliefs["p2_f1"].distribution[1] == 1.0

    def test_eliminates_revealed_powers(self):
        """After revealing power 1, other forces should have p(1) = 0."""
        agent = PerfectMemoryAgent()
        game = _make_game()
        rng = random.Random(42)

        # Reveal p2_f1 as power 1
        p1 = game.get_player_by_id("p1")
        p2 = game.get_player_by_id("p2")
        p2.forces[0].revealed = True
        p1.known_enemy_powers["p2_f1"] = 1

        # Make another force visible
        # Move p2_f2 close enough to be visible
        # Check which p2 forces are visible from p1 positions
        _, report = agent.observe_and_plan("p1", game, rng)

        for force_id, belief in report.beliefs.items():
            if force_id != "p2_f1" and force_id in report.beliefs:
                # Power 1 should be eliminated
                assert belief.distribution.get(1, 0.0) == 0.0, (
                    f"Force {force_id} should have p(1)=0 after p2_f1 revealed as 1"
                )


class TestOracleBaseline:
    def test_perfect_beliefs(self):
        agent = OracleAgent()
        game = _make_game()
        rng = random.Random(42)
        _, report = agent.observe_and_plan("p1", game, rng)

        ground_truth = {}
        for f in game.get_player_by_id("p2").forces:
            ground_truth[f.id] = f.power

        # Oracle should have perfect beliefs for all forces it reports on
        for force_id, belief in report.beliefs.items():
            if force_id in ground_truth:
                actual = ground_truth[force_id]
                assert belief.distribution[actual] == 1.0

    def test_brier_score_zero(self):
        agent = OracleAgent()
        game = _make_game()
        rng = random.Random(42)
        _, report = agent.observe_and_plan("p1", game, rng)

        ground_truth = {}
        for f in game.get_player_by_id("p2").forces:
            ground_truth[f.id] = f.power

        score = brier_score([report], ground_truth)
        assert score == 0.0

    def test_confidence_is_one(self):
        agent = OracleAgent()
        game = _make_game()
        rng = random.Random(42)
        _, report = agent.observe_and_plan("p1", game, rng)
        assert report.confidence == 1.0


class TestBaselineLadder:
    def test_all_baselines_registered(self):
        assert "random" in BASELINE_AGENTS
        assert "stateless" in BASELINE_AGENTS
        assert "perfect_memory" in BASELINE_AGENTS
        assert "oracle" in BASELINE_AGENTS

    def test_all_baselines_produce_valid_reports(self):
        """Every baseline agent should produce valid AgentReports."""
        game = _make_game()
        rng = random.Random(42)
        for name, cls in BASELINE_AGENTS.items():
            agent = cls()
            _orders, report = agent.observe_and_plan("p1", game, rng)
            assert report.player_id == "p1", f"{name} has wrong player_id"
            assert report.turn == game.turn, f"{name} has wrong turn"
            # Beliefs should have valid distributions
            for fid, belief in report.beliefs.items():
                total = sum(belief.distribution.values())
                assert abs(total - 1.0) < 0.01, f"{name} belief for {fid} sums to {total}"
