# Sun Tzu: The Unfought Battle v10

## Overview

A turn-based strategy game built as a headless Python/Flask API, designed as a
**benchmark for measuring strategic reasoning in LLM-based agents** under
incomplete information.

Each player deploys 5 forces with **hidden power values** (1-5, each used
exactly once). Power 1 is the **Sovereign** — lose it, lose the game. Every
force looks identical to the opponent. The game is about information asymmetry:
what you know, what you don't, and what you can make your opponent believe.

## v10: Strategic Reasoning Benchmark

v10 transforms the game into a measurement platform for LLM strategic reasoning:

- **Noisy scouting**: Scout reveals exact power with probability 0.7, otherwise
  returns a band (low 1-2, mid 3, high 4-5). Increases inference requirements.
- **Benchmark telemetry**: Per-turn belief distributions, action predictions,
  Brier score, log loss, calibration error, information gain, theory-of-mind delta.
- **Balance restored**: 3+ replicator survivors, multi-tier competitive pool,
  intransitive cycles enforced. Charge bonus +2, ambush bonus +2, sovereign
  defense removed, domination requires 4 turns.
- **LLM agent interface**: Abstract `LLMAgent` class + `MockLLMAgent` for
  testing the harness without API calls.

## Game Mechanics

### Orders (5 types)
- **Move** (free): Adjacent hex movement. Always available.
- **Charge** (2 Shih): Move up to 2 hexes, +2 attack bonus. Requires supply.
- **Scout** (2 Shih): Noisy intel on one enemy within 2 hexes. Requires supply.
- **Fortify** (2 Shih): +2 defense this turn. Requires supply.
- **Ambush** (3 Shih): +2 defense, hidden from opponent. Requires supply.

### Supply Chain
Forces must chain back to the Sovereign (max 2 hops, range 2) to use
special orders. Broken supply = Move only.

### Combat
`effective_power = base_power + modifiers + random(±2)`. Both power values are
permanently revealed after combat. Losers retreat if power difference ≤ 2,
otherwise eliminated.

### The Noose
Every 5 turns, the outermost ring of hexes becomes Scorched. Forces on
Scorched hexes die. Creates endgame pressure.

### Victory Conditions
1. **Sovereign Capture** — destroy the enemy's power-1 force
2. **Domination** — hold 2+ Contentious hexes for 4 consecutive turns
3. **Elimination** — destroy all enemy forces

## Project Structure

```
SunTzu/
├── app.py                 # Flask REST API
├── models.py              # Force, Player, Hex data classes
├── state.py               # Game state management, fog of war
├── orders.py              # Order processing, noisy scouting
├── resolution.py          # Combat resolution with variance
├── upkeep.py              # Turn finalization, Noose, victory conditions
├── map_gen.py             # 7x7 hex grid generation
├── config.json            # Tunable game parameters
├── play_cli.py            # CLI play mode
├── benchmark/             # Benchmark instrumentation (v10)
│   ├── __init__.py
│   ├── telemetry.py       # AgentReport, EventLog, BeliefState schemas
│   ├── metrics.py         # Brier score, log loss, calibration, ToM delta
│   └── llm_agent_interface.py  # LLM agent skeleton + MockLLMAgent
├── tests/
│   ├── simulate.py        # Game simulation + 9 Tier 1 strategies
│   ├── strategies_advanced.py  # Tiers 2-4 strategies
│   ├── test_gameplay.py   # 56 gameplay tests (multi-tier pool)
│   ├── test_benchmark.py  # 30 benchmark property tests
│   ├── test_fun_score.py  # Fun Score harness (9 dimensions)
│   ├── test_narrative_score.py  # Narrative Score harness (10 dimensions)
│   ├── test_depth_score.py     # Depth Score harness (6 dimensions)
│   └── test_*.py          # Unit tests for each core module
└── docs/
    ├── v10-plan.md         # v10 design document
    ├── v10-balance-diagnosis.md  # Metagame analysis
    └── repo-analysis.md    # Full repository analysis
```

## How to Run

```bash
# Unit tests (~2s)
pytest tests/test_models.py tests/test_state.py tests/test_orders.py \
       tests/test_resolution.py tests/test_upkeep.py tests/test_map_gen.py

# Benchmark tests (~30s)
pytest tests/test_benchmark.py

# Gameplay tests (~3min)
pytest tests/test_gameplay.py

# All tests
pytest

# API server
python app.py

# CLI play mode
python play_cli.py
```

## Strategy Tiers

| Tier | Strategy | Approach |
|------|----------|----------|
| 1 | Aggressive | Charge-first sovereign rush (v10) |
| 1 | Cautious | Scout first, attack with intel advantage |
| 1 | Ambush | Set traps, fortify, wait for attackers |
| 1 | Blitzer | Charge-first blitz (v10) |
| 1 | Sovereign Hunter | Prioritize finding and killing the Sovereign |
| 1 | Coordinator | Maintain formation for support bonuses |
| 1 | Noose Dodger | Stay ahead of the shrinking board |
| 2 | Pattern Reader | Track enemy movement patterns |
| 2 | Supply Cutter | Break enemy supply chains |
| 3 | Bayesian Hunter | Bayesian inference over hidden powers |
| 4 | Lookahead | Forward simulation across belief states |

## Configuration (v10)

```json
{
  "charge_attack_bonus": 2,
  "ambush_bonus": 2,
  "sovereign_defense_bonus": 0,
  "domination_turns_required": 4,
  "scout_accuracy": 0.7,
  "retreat_threshold": 2,
  "shrink_interval": 5
}
```

## Version History

| Version | Key Changes |
|---------|-------------|
| v10 | Strategic reasoning benchmark. Noisy scouting, telemetry, multi-tier pool. |
| v9 | Sovereign defense bonus, wider starting separation, CLI play mode. |
| v8 | Anti-Goodhart overhaul: ablation tests, adversarial strategies. |
| v7 | Supply hop limits, tighter economy, intransitive metagame. |
| v6 | Rigorous gameplay tests with game balance fixes. |
| v5 | Supply lines, charge bonus, wider combat variance, gentler Noose. |
| v4 | Charge, support, retreat mechanics. |
| v3 | Complete redesign: hidden power values, fog of war, shrinking board. |
