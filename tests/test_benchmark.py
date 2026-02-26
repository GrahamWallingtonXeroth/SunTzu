"""
Benchmark tests for The Unfought Battle v10.

Tests the benchmark instrumentation layer: telemetry schemas, metric
computation, and the LLM agent interface. Also validates benchmark
properties that ensure the game remains a valid strategic reasoning
benchmark.

Quick mode: pytest tests/test_benchmark.py -k quick (~30s)
Full mode:  pytest tests/test_benchmark.py (~2min)
"""

import pytest
import math
import random
import json
import os
import tempfile
from typing import Dict, List

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmark.telemetry import BeliefState, AgentReport, EventLog, GameTelemetry
from benchmark.metrics import (
    brier_score, log_loss, calibration_error,
    information_gain, uncertainty_reduction, tom_delta,
    compute_game_metrics,
)
from benchmark.llm_agent_interface import MockLLMAgent
from state import initialize_game, apply_deployment
from orders import resolve_orders
from upkeep import perform_upkeep
from tests.simulate import run_game, run_tournament, CautiousStrategy, AggressiveStrategy


# ===========================================================================
# Telemetry schema tests
# ===========================================================================

class TestBeliefState:
    def test_uniform_entropy(self):
        """Uniform distribution over 5 values has entropy log2(5) ≈ 2.32."""
        b = BeliefState.uniform()
        assert abs(b.entropy() - math.log2(5)) < 0.01

    def test_certain_entropy(self):
        """Certain distribution has entropy 0."""
        b = BeliefState(distribution={3: 1.0, 1: 0.0, 2: 0.0, 4: 0.0, 5: 0.0})
        assert b.entropy() == 0.0

    def test_predicted_power(self):
        b = BeliefState(distribution={1: 0.1, 2: 0.1, 3: 0.5, 4: 0.2, 5: 0.1})
        assert b.predicted_power() == 3

    def test_max_probability(self):
        b = BeliefState(distribution={1: 0.1, 2: 0.1, 3: 0.5, 4: 0.2, 5: 0.1})
        assert b.max_probability() == 0.5

    def test_to_dict_roundtrip(self):
        b = BeliefState.uniform()
        d = b.to_dict()
        assert set(d.keys()) == {'1', '2', '3', '4', '5'}
        assert abs(sum(float(v) for v in d.values()) - 1.0) < 0.001


class TestAgentReport:
    def test_empty_report(self):
        r = AgentReport(turn=1, player_id='p1', strategy='test')
        assert r.belief_entropy() == 0.0
        assert r.prediction_confidence() == 0.0

    def test_report_with_beliefs(self):
        r = AgentReport(turn=1, player_id='p1', strategy='test')
        r.beliefs['p2_f1'] = BeliefState.uniform()
        r.beliefs['p2_f2'] = BeliefState(distribution={3: 1.0, 1: 0, 2: 0, 4: 0, 5: 0})
        # Average entropy: (log2(5) + 0) / 2
        expected = math.log2(5) / 2
        assert abs(r.belief_entropy() - expected) < 0.01

    def test_to_json_roundtrip(self):
        r = AgentReport(turn=3, player_id='p1', strategy='mock')
        r.beliefs['p2_f1'] = BeliefState.uniform()
        r.chosen_orders = ['Move p1_f1 (3,3)']
        j = r.to_json()
        d = json.loads(j)
        assert d['turn'] == 3
        assert d['strategy'] == 'mock'
        assert len(d['beliefs']['p2_f1']) == 5


class TestEventLog:
    def test_add_events(self):
        log = EventLog(turn=5)
        log.add_combat('p1_f1', 'p2_f1', 5, 2, 'attacker_wins')
        log.add_scout_reveal('p1_f2', 'p2_f4', 'band_high', 5)
        log.add_noose_kill('p2_f5', (0, 0), False)
        assert len(log.events) == 3
        assert log.events[0]['type'] == 'combat'
        assert log.events[1]['type'] == 'scout_reveal'
        assert log.events[2]['type'] == 'noose_kill'

    def test_to_json(self):
        log = EventLog(turn=5)
        log.add_combat('p1_f1', 'p2_f1', 5, 2, 'attacker_wins')
        d = json.loads(log.to_json())
        assert d['turn'] == 5
        assert len(d['events']) == 1


class TestGameTelemetry:
    def test_jsonl_output(self):
        gt = GameTelemetry(game_id='test1', p1_strategy='a', p2_strategy='b')
        gt.add_report(AgentReport(turn=1, player_id='p1', strategy='a'))
        gt.add_event_log(EventLog(turn=1))
        lines = gt.to_jsonl().strip().split('\n')
        assert len(lines) == 3  # header + 1 report + 1 event
        header = json.loads(lines[0])
        assert header['type'] == 'game_header'

    def test_write_and_read_jsonl(self):
        gt = GameTelemetry(game_id='test2', p1_strategy='x', p2_strategy='y',
                          winner='p1', victory_type='sovereign_capture', turns=10)
        gt.add_report(AgentReport(turn=1, player_id='p1', strategy='x'))
        gt.add_report(AgentReport(turn=1, player_id='p2', strategy='y'))

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            path = f.name
        try:
            gt.write_jsonl(path)
            with open(path) as f:
                lines = [l for l in f.readlines() if l.strip()]
            assert len(lines) == 3  # header + 2 reports
        finally:
            os.unlink(path)


# ===========================================================================
# Metrics tests
# ===========================================================================

class TestMetrics:
    def test_brier_perfect(self):
        """Perfect predictions have Brier score 0."""
        reports = [AgentReport(turn=1, player_id='p1', strategy='test')]
        reports[0].beliefs['f1'] = BeliefState(
            distribution={1: 0, 2: 0, 3: 1.0, 4: 0, 5: 0}
        )
        score = brier_score(reports, {'f1': 3})
        assert score == 0.0

    def test_brier_uniform(self):
        """Uniform predictions have Brier score 0.16 (normalized by K classes)."""
        reports = [AgentReport(turn=1, player_id='p1', strategy='test')]
        reports[0].beliefs['f1'] = BeliefState.uniform()
        score = brier_score(reports, {'f1': 3})
        # 4*(0.2)^2 + (0.2-1)^2 = 0.16 + 0.64 = 0.80, / 5 = 0.16
        assert abs(score - 0.16) < 0.01

    def test_log_loss_perfect(self):
        """Perfect predictions have log loss 0."""
        reports = [AgentReport(turn=1, player_id='p1', strategy='test')]
        reports[0].beliefs['f1'] = BeliefState(
            distribution={1: 0, 2: 0, 3: 1.0, 4: 0, 5: 0}
        )
        score = log_loss(reports, {'f1': 3})
        assert abs(score) < 0.001

    def test_log_loss_uniform(self):
        """Uniform predictions have log loss log(5) ≈ 1.61."""
        reports = [AgentReport(turn=1, player_id='p1', strategy='test')]
        reports[0].beliefs['f1'] = BeliefState.uniform()
        score = log_loss(reports, {'f1': 3})
        assert abs(score - math.log(5)) < 0.01

    def test_information_gain_positive(self):
        """Learning should produce positive information gain."""
        r1 = AgentReport(turn=1, player_id='p1', strategy='test')
        r1.beliefs['f1'] = BeliefState.uniform()  # entropy 2.32
        r2 = AgentReport(turn=2, player_id='p1', strategy='test')
        r2.beliefs['f1'] = BeliefState(
            distribution={1: 0, 2: 0.5, 3: 0.5, 4: 0, 5: 0}
        )  # entropy 1.0
        gains = information_gain([r1, r2])
        assert len(gains) == 1
        assert gains[0] > 0

    def test_uncertainty_reduction(self):
        """Full learning gives uncertainty reduction = 1.0."""
        r1 = AgentReport(turn=1, player_id='p1', strategy='test')
        r1.beliefs['f1'] = BeliefState.uniform()
        r2 = AgentReport(turn=5, player_id='p1', strategy='test')
        r2.beliefs['f1'] = BeliefState(
            distribution={1: 0, 2: 0, 3: 1.0, 4: 0, 5: 0}
        )
        assert uncertainty_reduction([r1, r2]) == 1.0

    def test_tom_delta_positive(self):
        """Better beliefs should produce positive ToM delta."""
        gt = {'f1': 3}
        good = [AgentReport(turn=1, player_id='p1', strategy='good')]
        good[0].beliefs['f1'] = BeliefState(
            distribution={1: 0, 2: 0.1, 3: 0.8, 4: 0.1, 5: 0}
        )
        bad = [AgentReport(turn=1, player_id='p1', strategy='bad')]
        bad[0].beliefs['f1'] = BeliefState.uniform()
        delta = tom_delta(good, bad, gt)
        assert delta > 0  # good agent is better than uniform baseline

    def test_calibration_perfect(self):
        """Perfect calibration has error 0."""
        reports = [AgentReport(turn=1, player_id='p1', strategy='test')]
        reports[0].beliefs['f1'] = BeliefState(
            distribution={1: 0, 2: 0, 3: 1.0, 4: 0, 5: 0}
        )
        err = calibration_error(reports, {'f1': 3})
        assert err < 0.01


# ===========================================================================
# LLM agent interface tests
# ===========================================================================

class TestMockLLMAgent:
    """quick"""

    def test_mock_agent_produces_orders(self):
        """MockLLMAgent should produce valid orders."""
        agent = MockLLMAgent(strategy_name='cautious')
        game = initialize_game(42)
        rng = random.Random(42)
        deployment = agent.deploy(game.get_player_by_id('p1'), rng)
        assert set(deployment.values()) == {1, 2, 3, 4, 5}
        apply_deployment(game, 'p1', deployment)

        # Deploy p2 with default
        p2 = game.get_player_by_id('p2')
        p2_deploy = {f.id: p for f, p in zip(p2.forces, [1, 2, 3, 4, 5])}
        apply_deployment(game, 'p2', p2_deploy)

        orders, report = agent.observe_and_plan('p1', game, rng)
        assert len(orders) > 0
        assert report.turn == game.turn
        assert report.player_id == 'p1'
        assert 'mock_llm' in report.strategy

    def test_mock_agent_generates_beliefs(self):
        """MockLLMAgent should generate belief distributions."""
        agent = MockLLMAgent(strategy_name='cautious')
        game = initialize_game(42)
        rng = random.Random(42)
        deployment = agent.deploy(game.get_player_by_id('p1'), rng)
        apply_deployment(game, 'p1', deployment)
        p2 = game.get_player_by_id('p2')
        p2_deploy = {f.id: p for f, p in zip(p2.forces, [1, 2, 3, 4, 5])}
        apply_deployment(game, 'p2', p2_deploy)

        _, report = agent.observe_and_plan('p1', game, rng)
        # Should have beliefs about alive enemy forces
        assert len(report.beliefs) > 0
        for belief in report.beliefs.values():
            assert abs(sum(belief.distribution.values()) - 1.0) < 0.01


# ===========================================================================
# Benchmark property tests (quick)
# ===========================================================================

class TestBenchmarkProperties:
    """quick — Properties that the benchmark must satisfy."""

    def test_noisy_scouting_produces_bands(self):
        """Noisy scouting should sometimes return bands instead of exact power."""
        from orders import resolve_scout
        rng = random.Random(42)
        exact_count = 0
        band_count = 0
        for _ in range(100):
            result = resolve_scout(3, scout_accuracy=0.7, rng=rng)
            if result['type'] == 'exact':
                exact_count += 1
            else:
                band_count += 1
        # With accuracy 0.7, roughly 70 exact and 30 band
        assert 50 < exact_count < 90, f"exact={exact_count}, expected ~70"
        assert 10 < band_count < 50, f"band={band_count}, expected ~30"

    def test_noisy_scouting_bands_are_truthful(self):
        """Band results should always contain the actual power."""
        from orders import resolve_scout
        rng = random.Random(42)
        for power in [1, 2, 3, 4, 5]:
            for _ in range(50):
                result = resolve_scout(power, scout_accuracy=0.0, rng=rng)
                assert result['type'] == 'band'
                assert power in result['power_range']

    def test_scout_accuracy_configurable(self):
        """scout_accuracy=1.0 should always return exact."""
        from orders import resolve_scout
        rng = random.Random(42)
        for _ in range(20):
            result = resolve_scout(3, scout_accuracy=1.0, rng=rng)
            assert result['type'] == 'exact'
            assert result['power'] == 3

    def test_charge_bonus_is_2(self):
        """v10: charge attack bonus should be 2."""
        from resolution import load_combat_config
        config = load_combat_config()
        assert config['charge_attack_bonus'] == 2

    def test_ambush_bonus_is_2(self):
        """v10: ambush bonus should be 2."""
        from resolution import load_combat_config
        config = load_combat_config()
        assert config['ambush_bonus'] == 2

    def test_sovereign_defense_is_1(self):
        """v10: sovereign defense bonus kept at 1 (balances charge+2)."""
        from resolution import load_combat_config
        config = load_combat_config()
        assert config['sovereign_defense_bonus'] == 1

    def test_domination_requires_4_turns(self):
        """v10: domination requires 4 consecutive turns."""
        from upkeep import load_upkeep_config
        config = load_upkeep_config()
        assert config['domination_turns_required'] == 4


# ===========================================================================
# Integration test: telemetry flows through a game
# ===========================================================================

class TestTelemetryIntegration:
    """quick"""

    def test_mock_agent_game_produces_telemetry(self):
        """Run a short game with MockLLMAgent and verify telemetry output."""
        agent_p1 = MockLLMAgent(strategy_name='aggressive')
        agent_p2 = MockLLMAgent(strategy_name='cautious')

        game = initialize_game(42)
        rng = random.Random(42)

        # Deploy
        d1 = agent_p1.deploy(game.get_player_by_id('p1'), rng)
        d2 = agent_p2.deploy(game.get_player_by_id('p2'), rng)
        apply_deployment(game, 'p1', d1)
        apply_deployment(game, 'p2', d2)

        telemetry = GameTelemetry(
            game_id='integration_test', p1_strategy=agent_p1.name,
            p2_strategy=agent_p2.name, seed=42,
        )

        max_turns = 10
        while game.phase != 'ended' and game.turn <= max_turns:
            if game.phase != 'plan':
                break

            p1_orders, p1_report = agent_p1.observe_and_plan('p1', game, rng)
            p2_orders, p2_report = agent_p2.observe_and_plan('p2', game, rng)
            telemetry.add_report(p1_report)
            telemetry.add_report(p2_report)

            event_log = EventLog(turn=game.turn)

            game.phase = 'resolve'
            result = resolve_orders(p1_orders, p2_orders, game)

            for combat in result.get('combats', []):
                event_log.add_combat(
                    combat.get('attacker_id', ''), combat.get('defender_id', ''),
                    combat.get('attacker_power', 0), combat.get('defender_power', 0),
                    combat.get('outcome', ''),
                )
            for scout in result.get('scouts', []):
                revealed = str(scout.get('revealed_power', scout.get('revealed_band', '')))
                event_log.add_scout_reveal(
                    scout.get('scouting_force', ''), scout.get('scouted_force', ''),
                    revealed, scout.get('actual_power', 0),
                )

            telemetry.add_event_log(event_log)

            sovereign_capture = result.get('sovereign_captured')
            upkeep = perform_upkeep(game, sovereign_capture)
            if upkeep.get('winner'):
                break

        telemetry.winner = game.winner
        telemetry.victory_type = game.victory_type
        telemetry.turns = game.turn

        # Verify telemetry was collected
        assert len(telemetry.agent_reports) > 0
        assert len(telemetry.event_logs) > 0

        # Verify JSONL output
        jsonl = telemetry.to_jsonl()
        lines = [l for l in jsonl.split('\n') if l.strip()]
        header = json.loads(lines[0])
        assert header['type'] == 'game_header'
        assert header['game_id'] == 'integration_test'

        # Verify metrics can be computed
        ground_truth = {}
        for pid in ['p1', 'p2']:
            p = game.get_player_by_id(pid)
            for f in p.forces:
                ground_truth[f.id] = f.power

        p1_reports = telemetry.get_reports_for_player('p1')
        if p1_reports and any(r.beliefs for r in p1_reports):
            metrics = compute_game_metrics(telemetry, ground_truth)
            assert 'p1_brier_score' in metrics
