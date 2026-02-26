"""
Benchmark metrics for measuring strategic reasoning quality.

Computes per-game and aggregate metrics from telemetry data:
- Brier score: prediction accuracy for power beliefs
- Log loss: surprise / calibration
- Calibration error: over/under-confidence per bin
- Information gain: entropy reduction from scouting
- Theory-of-mind delta: accuracy improvement from modeling opponent
"""

import math
from typing import Dict, List, Optional, Tuple
from benchmark.telemetry import AgentReport, EventLog, GameTelemetry, BeliefState


def brier_score(reports: List[AgentReport], ground_truth: Dict[str, int]) -> float:
    """
    Compute Brier score for power beliefs.

    Brier = (1/N) * sum((p_predicted - actual)^2)
    where actual is 1 for the true power, 0 for others.

    Lower is better. Perfect = 0.0, random uniform = 0.32.

    Args:
        reports: Agent reports with belief distributions
        ground_truth: force_id -> actual power mapping

    Returns:
        Average Brier score across all belief-force pairs.
    """
    total_score = 0.0
    n = 0

    for report in reports:
        for force_id, belief in report.beliefs.items():
            actual = ground_truth.get(force_id)
            if actual is None:
                continue
            for power in range(1, 6):
                predicted = belief.distribution.get(power, 0.0)
                actual_indicator = 1.0 if power == actual else 0.0
                total_score += (predicted - actual_indicator) ** 2
            n += 1

    if n == 0:
        return 0.0
    return total_score / (n * 5)  # normalize by n beliefs * 5 power values


def log_loss(reports: List[AgentReport], ground_truth: Dict[str, int],
             epsilon: float = 1e-10) -> float:
    """
    Compute log loss for power beliefs.

    LogLoss = -(1/N) * sum(log(p_actual_power))
    Lower is better. Perfect = 0.0, random uniform = log(5) ≈ 1.61.

    Args:
        reports: Agent reports with belief distributions
        ground_truth: force_id -> actual power mapping
        epsilon: small value to avoid log(0)

    Returns:
        Average log loss across all belief-force pairs.
    """
    total = 0.0
    n = 0

    for report in reports:
        for force_id, belief in report.beliefs.items():
            actual = ground_truth.get(force_id)
            if actual is None:
                continue
            p = belief.distribution.get(actual, 0.0)
            p = max(p, epsilon)
            total -= math.log(p)
            n += 1

    if n == 0:
        return 0.0
    return total / n


def calibration_error(reports: List[AgentReport], ground_truth: Dict[str, int],
                      n_bins: int = 5) -> float:
    """
    Compute expected calibration error (ECE).

    Groups predictions by confidence bin, then measures
    |predicted_confidence - actual_frequency| per bin.

    Lower is better. Perfect = 0.0.

    Args:
        reports: Agent reports with belief distributions
        ground_truth: force_id -> actual power mapping
        n_bins: number of calibration bins

    Returns:
        Weighted average calibration error.
    """
    bins = [[] for _ in range(n_bins)]

    for report in reports:
        for force_id, belief in report.beliefs.items():
            actual = ground_truth.get(force_id)
            if actual is None:
                continue
            for power in range(1, 6):
                predicted = belief.distribution.get(power, 0.0)
                actual_indicator = 1.0 if power == actual else 0.0
                bin_idx = min(int(predicted * n_bins), n_bins - 1)
                bins[bin_idx].append((predicted, actual_indicator))

    total_error = 0.0
    total_samples = sum(len(b) for b in bins)
    if total_samples == 0:
        return 0.0

    for b in bins:
        if not b:
            continue
        avg_predicted = sum(p for p, _ in b) / len(b)
        avg_actual = sum(a for _, a in b) / len(b)
        total_error += len(b) * abs(avg_predicted - avg_actual)

    return total_error / total_samples


def information_gain(reports: List[AgentReport]) -> List[float]:
    """
    Compute information gain per turn: H_before - H_after.

    Measures how much uncertainty was reduced each turn through
    scouting and combat reveals.

    Returns:
        List of information gain values per consecutive report pair.
    """
    gains = []
    for i in range(1, len(reports)):
        h_before = reports[i - 1].belief_entropy()
        h_after = reports[i].belief_entropy()
        gains.append(h_before - h_after)
    return gains


def uncertainty_reduction(reports: List[AgentReport]) -> float:
    """
    Compute overall uncertainty reduction: (H_turn1 - H_final) / H_turn1.

    Measures information gathering efficiency across the game.
    1.0 = complete certainty achieved. 0.0 = no learning.

    Returns:
        Uncertainty reduction ratio (0-1).
    """
    if len(reports) < 2:
        return 0.0
    h_first = reports[0].belief_entropy()
    h_last = reports[-1].belief_entropy()
    if h_first == 0:
        return 0.0
    return (h_first - h_last) / h_first


def tom_delta(agent_reports: List[AgentReport],
              baseline_reports: List[AgentReport],
              ground_truth: Dict[str, int]) -> float:
    """
    Compute theory-of-mind delta: accuracy_agent - accuracy_baseline.

    Measures how much a theory-of-mind model improves prediction accuracy
    beyond a baseline model (e.g., uniform beliefs).

    Positive = ToM helps. Negative = ToM hurts.

    Args:
        agent_reports: Reports from the theory-of-mind agent
        baseline_reports: Reports from a baseline (e.g., uniform beliefs)
        ground_truth: force_id -> actual power mapping

    Returns:
        Brier score difference (baseline - agent, so positive = better).
    """
    agent_brier = brier_score(agent_reports, ground_truth)
    baseline_brier = brier_score(baseline_reports, ground_truth)
    return baseline_brier - agent_brier  # positive = agent is better


def compute_game_metrics(telemetry: GameTelemetry,
                         ground_truth: Dict[str, int]) -> Dict[str, float]:
    """
    Compute all per-game metrics from telemetry.

    Args:
        telemetry: Complete game telemetry record
        ground_truth: force_id -> actual power for all forces

    Returns:
        Dictionary of metric name -> value.
    """
    metrics = {}

    for pid in ['p1', 'p2']:
        reports = telemetry.get_reports_for_player(pid)
        if not reports:
            continue

        prefix = f'{pid}_'
        metrics[f'{prefix}brier_score'] = brier_score(reports, ground_truth)
        metrics[f'{prefix}log_loss'] = log_loss(reports, ground_truth)
        metrics[f'{prefix}calibration_error'] = calibration_error(reports, ground_truth)
        metrics[f'{prefix}uncertainty_reduction'] = uncertainty_reduction(reports)

        ig = information_gain(reports)
        metrics[f'{prefix}avg_info_gain'] = sum(ig) / len(ig) if ig else 0.0
        metrics[f'{prefix}total_info_gain'] = sum(ig)

        metrics[f'{prefix}avg_belief_entropy'] = (
            sum(r.belief_entropy() for r in reports) / len(reports)
        )
        metrics[f'{prefix}avg_prediction_confidence'] = (
            sum(r.prediction_confidence() for r in reports) / len(reports)
        )

    return metrics
