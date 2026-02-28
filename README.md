# Sun Tzu: The Unfought Battle

A turn-based strategy game built as a headless Python/Flask API, designed as a
benchmark for measuring strategic reasoning in LLM-based agents under
incomplete information.

Each player deploys 5 forces with **hidden power values** (1-5, each used
exactly once). Power 1 is the **Sovereign** — lose it, lose the game. Every
force looks identical to the opponent. The game is about information asymmetry:
what you know, what you don't, and what you can make your opponent believe.

## Getting Started

```bash
# Create a virtual environment
python -m venv .venv && source .venv/bin/activate

# Install production dependencies
pip install -r requirements.txt

# Install dev dependencies (testing, linting)
pip install -e ".[dev]"

# Run the API server
python app.py

# Play via CLI
python play_cli.py
```

## Running Tests

```bash
# All tests
pytest

# Unit tests only (~2s)
pytest tests/test_models.py tests/test_state.py tests/test_orders.py \
       tests/test_resolution.py tests/test_upkeep.py tests/test_map_gen.py

# Benchmark tests (~30s)
pytest tests/test_benchmark.py

# Gameplay tests (~3min)
pytest tests/test_gameplay.py
```

## Linting

```bash
ruff check .        # lint
ruff format .       # format
```

## Game Mechanics

### Orders

| Order | Cost | Effect |
|-------|------|--------|
| Move | 0 Shih | Adjacent hex movement |
| Charge | 2 Shih | Move up to 2 hexes, +2 attack bonus |
| Scout | 2 Shih | Noisy intel on one enemy within 2 hexes |
| Fortify | 2 Shih | +2 defense this turn |
| Ambush | 3 Shih | +2 defense, hidden from opponent |

All orders except Move require supply chain to the Sovereign.

### Supply Chain

Forces must chain back to the Sovereign (max 2 hops, range 2) to use
special orders. Broken supply = Move only.

### Combat

`effective_power = base_power + modifiers + random(+-2)`. Both power values are
permanently revealed after combat. Losers retreat if power difference <= 2,
otherwise eliminated.

### The Noose

Every 5 turns, the outermost ring of hexes becomes Scorched. Forces on
Scorched hexes die.

### Victory Conditions

1. **Sovereign Capture** — destroy the enemy's power-1 force
2. **Domination** — hold 2+ Contentious hexes for 4 consecutive turns
3. **Elimination** — destroy all enemy forces

## Project Structure

```
app.py                  Flask REST API
models.py               Force, Player, Hex data classes
state.py                Game state management, fog of war
orders.py               Order processing, noisy scouting
resolution.py           Combat resolution with variance
upkeep.py               Turn finalization, Noose, victory conditions
map_gen.py              7x7 hex grid generation
config.json             Tunable game parameters
play_cli.py             CLI play mode
benchmark/
  telemetry.py          AgentReport, EventLog, BeliefState schemas
  metrics.py            Brier score, log loss, calibration, ToM delta
  llm_agent_interface.py  LLM agent abstract class + MockLLMAgent
tests/
  conftest.py           Shared fixtures and helpers
  simulate.py           Game simulation + Tier 1 strategies
  strategies_advanced.py  Tiers 2-4 strategies
  test_*.py             Unit and integration tests
```

## Benchmark

The benchmark instrumentation measures LLM strategic reasoning via:

- **Noisy scouting**: Scout reveals exact power with probability 0.7, otherwise
  returns a band (low 1-2, mid 3, high 4-5)
- **Per-turn telemetry**: Belief distributions, action predictions, confidence
- **Metrics**: Brier score, log loss, calibration error, information gain,
  theory-of-mind delta
- **LLM agent interface**: Abstract `LLMAgent` class + `MockLLMAgent` for
  testing the harness without API calls

## Strategy Tiers

| Tier | Strategy | Approach |
|------|----------|----------|
| 1 | Aggressive | Charge-first sovereign rush |
| 1 | Cautious | Scout first, attack with intel advantage |
| 1 | Ambush | Set traps, fortify, wait for attackers |
| 1 | Blitzer | Charge-first blitz |
| 1 | Sovereign Hunter | Prioritize finding and killing the Sovereign |
| 1 | Coordinator | Maintain formation for support bonuses |
| 1 | Noose Dodger | Stay ahead of the shrinking board |
| 2 | Pattern Reader | Track enemy movement patterns |
| 2 | Supply Cutter | Break enemy supply chains |
| 3 | Bayesian Hunter | Bayesian inference over hidden powers |
| 4 | Lookahead | Forward simulation across belief states |

## Deployment

Deployed to Google Cloud App Engine. See `app.yaml` for configuration.

```bash
gcloud app deploy
```
