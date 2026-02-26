# v10 Benchmark Design: Measuring Strategic Reasoning

## Objective

Build a benchmark that empirically measures strategic reasoning in LLM-based
agents under incomplete information, without relying on activation probing.

## Anti-Calculability: Noisy Scouting

Scout reveals the exact enemy power with probability `scout_accuracy` (default
0.7). Otherwise, it returns a truthful but less informative **band**:

| Band | Power Range | Values |
|------|-------------|--------|
| `band_low` | Low | 1, 2 |
| `band_mid` | Mid | 3 |
| `band_high` | High | 4, 5 |

**Why this mechanic:**
1. Agents must integrate noisy signals with prior beliefs
2. Perfect lookahead requires enumerating all possible configurations
3. Noisy signals create richer belief hierarchies
4. Testable via Brier score comparison

## Benchmark Metrics

### Per-Turn Metrics (in AgentReport)
| Metric | Formula | Purpose |
|--------|---------|---------|
| Power belief entropy | H = -Σ p·log(p) per enemy force | Uncertainty level |
| Prediction confidence | max(p) for predicted opponent action | Confidence calibration |
| Information gain | H_before - H_after for reveals | Scouting value |

### Per-Game Metrics (aggregated)
| Metric | Formula | Purpose |
|--------|---------|---------|
| Brier score | (1/N)·Σ(p_predicted - actual)² | Prediction accuracy |
| Log loss | -(1/N)·Σ log(p_actual_outcome) | Surprise / calibration |
| Calibration error | |predicted_conf - actual_freq| per bin | Over/under-confidence |
| ToM delta | accuracy_agent - accuracy_baseline | Theory-of-mind value |
| Uncertainty reduction | (H_turn1 - H_final) / H_turn1 | Info gathering efficiency |

### Benchmark-Level Metrics
| Metric | Purpose |
|--------|---------|
| Tier gradient | Does sophistication improve play? |
| Scouting value | Does noisy scouting still improve outcomes? |
| Belief quality | Do better beliefs correlate with winning? |
| Anti-calculability | Does Tier 4 lookahead have diminishing returns? |

## Logging Schema

### AgentReport (per turn per player)
```json
{
  "turn": 5,
  "player_id": "p1",
  "strategy": "bayesian_hunter",
  "beliefs": {
    "p2_f1": {"1": 0.1, "2": 0.2, "3": 0.3, "4": 0.2, "5": 0.2},
    "p2_f2": {"1": 0.05, "2": 0.05, "3": 0.1, "4": 0.4, "5": 0.4}
  },
  "action_predictions": {
    "p2_f1": {"Move": 0.4, "Charge": 0.3, "Scout": 0.1, "Fortify": 0.1, "Ambush": 0.1}
  },
  "objective_prediction": {"hunt_sovereign": 0.6, "dominate": 0.2, "defend": 0.2},
  "chosen_orders": ["Move p1_f1 (2,3)", "Charge p1_f3 (3,3)"],
  "confidence": 0.72
}
```

### EventLog (per turn)
```json
{
  "turn": 5,
  "events": [
    {"type": "combat", "attacker": "p1_f3", "defender": "p2_f1",
     "attacker_power": 4, "defender_power": 2, "result": "attacker_wins"},
    {"type": "scout_reveal", "scout": "p1_f2", "target": "p2_f4",
     "revealed": "band_high", "actual_power": 5},
    {"type": "noose_kill", "force": "p2_f5", "position": [0, 0],
     "was_sovereign": false}
  ]
}
```

## LLM Agent Interface

```python
from benchmark.llm_agent_interface import LLMAgent, MockLLMAgent

# For testing:
agent = MockLLMAgent(strategy_name='bayesian_hunter')

# For real LLM agents, subclass LLMAgent:
class MyLLMAgent(LLMAgent):
    def observe_and_plan(self, player_id, game_state, rng):
        # 1. Format game state for the LLM
        # 2. Call the LLM API
        # 3. Parse response into orders
        # 4. Return (orders, AgentReport)
        ...

    def deploy(self, player, rng):
        # Assign power values 1-5 to forces
        ...

    @property
    def name(self):
        return 'my_llm_agent'
```

## Files

| File | Purpose |
|------|---------|
| `benchmark/__init__.py` | Package init |
| `benchmark/telemetry.py` | AgentReport, EventLog, BeliefState, GameTelemetry |
| `benchmark/metrics.py` | Brier score, log loss, calibration, ToM delta |
| `benchmark/llm_agent_interface.py` | LLMAgent abstract class + MockLLMAgent |
| `tests/test_benchmark.py` | 30 benchmark property tests |

## How to Run

```bash
# Quick benchmark tests (~30s)
pytest tests/test_benchmark.py -k quick

# Full benchmark tests (~2min)
pytest tests/test_benchmark.py

# All tests (unit + gameplay + benchmark)
pytest
```
