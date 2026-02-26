# v10 Plan: Strategic Reasoning Benchmark

## Objective

Build a benchmark that empirically measures strategic reasoning in LLM-based
agents under incomplete information, without relying on activation probing.

## Objective Mapping

| Change | Measurability | Anti-Calculability | Metagame Diversity |
|--------|:---:|:---:|:---:|
| Balance fix (config + strategies) | | | X |
| Benchmark telemetry (belief/prediction logging) | X | | |
| Noisy scouting mechanic | | X | X |
| LLM agent harness skeleton | X | | |
| v10 test module | X | X | X |

## Chosen Anti-Calculability Mechanic: Noisy Scouting

**Option 3: Scout returns probabilistic intel.**

Scout reveals the exact enemy power with probability `scout_accuracy` (config,
default 0.7). Otherwise, it returns a **band**: low (1-2), mid (3), high (4-5).
The band is always truthful but less informative.

**Why this mechanic:**
1. **Increases inference requirements**: Agents must integrate noisy signals
   with prior beliefs. A single scout no longer perfectly resolves a force's
   power — you may need to scout again or infer from context.
2. **Reduces brute-force advantage**: Perfect lookahead requires enumerating
   all possible power configurations. With noisy scouting, the belief space
   remains partially ambiguous even after observation, increasing the number
   of possible worlds to evaluate.
3. **Increases theory-of-mind value**: If I only know an enemy is "high power
   (4-5)", my optimal action depends on whether the opponent KNOWS that I
   know this. Noisy signals create richer belief hierarchies.
4. **Testable**: We can measure Brier score improvement from scouting, compare
   calibration between noisy and perfect scouting, and test whether Tier 3
   (BayesianHunter) gains a larger advantage under noisy scouting.
5. **Config-driven**: `scout_accuracy` in config.json, default 0.7.

## Balance Changes

### Config (config.json)
```json
{
  "charge_attack_bonus": 2,    // was 1 — stronger charges counter defense
  "ambush_bonus": 2,           // was 1 — stronger ambush counters charges
  "sovereign_defense_bonus": 0, // was 1 — removed, caused defensive meta
  "domination_turns_required": 4, // was 3 — harder domination
  "scout_accuracy": 0.7        // NEW — noisy scouting
}
```

### Strategy Updates
- **AggressiveV10**: Charge-first sovereign rush (no scout-before-charge)
- **BlitzerV10**: Charge-first blitz (scouts with low-power only)
- **Other Tier 1**: Minimal changes
- **Tier 2-3**: Included in competitive pool; no strategy changes

### Expected Metagame
- Replicator survivors: 3+ (bayesian_hunter, supply_cutter, pattern_reader)
- Dominance ceiling: <67%
- Tier 1 strategies viable (>35% win rate)
- Intransitive cycles present among competitive strategies

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
    "p2_f1": {"Move": 0.4, "Charge": 0.3, "Scout": 0.1, "Fortify": 0.1, "Ambush": 0.1},
    "p2_f2": {"Move": 0.2, "Charge": 0.5, "Scout": 0.1, "Fortify": 0.1, "Ambush": 0.1}
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
    {"type": "noose_shrink", "stage": 2, "kills": ["p2_f5"]}
  ]
}
```

## Files Changed/Added

### Modified
- `config.json` — new parameters
- `models.py` — v10 version string
- `state.py` — v10 version string
- `orders.py` — noisy scouting implementation, v10 version string
- `resolution.py` — v10 version string, updated defaults
- `upkeep.py` — v10 version string, updated defaults
- `tests/simulate.py` — v10 strategies, telemetry hooks, refactored
- `tests/strategies_advanced.py` — belief reporting interface
- `tests/test_gameplay.py` — restored strict thresholds, multi-tier pool
- `README.md` — updated for v10

### Added
- `benchmark/` — new package
- `benchmark/__init__.py`
- `benchmark/telemetry.py` — AgentReport, EventLog, BeliefState schemas
- `benchmark/metrics.py` — Brier score, log loss, calibration, ToM delta
- `benchmark/llm_agent_interface.py` — LLM agent skeleton + MockLLMAgent
- `tests/test_benchmark.py` — benchmark property tests
- `docs/v10-balance-diagnosis.md` — metagame diagnosis
- `docs/v10-plan.md` — this file
- `docs/v10-benchmark-design.md` — full benchmark documentation

## How to Run

```bash
# Unit tests (~2s)
pytest tests/test_models.py tests/test_state.py tests/test_orders.py \
       tests/test_resolution.py tests/test_upkeep.py tests/test_map_gen.py

# Gameplay tests (~3min)
pytest tests/test_gameplay.py

# Benchmark tests (~2min)
pytest tests/test_benchmark.py

# Quick benchmark mode (PR iteration, ~30s)
pytest tests/test_benchmark.py -k quick

# Full benchmark tournament with JSONL output
python -m benchmark.telemetry --output tests/artifacts/

# All tests
pytest
```
