# Sun Tzu: The Unfought Battle — Repository Analysis

## Executive Summary

This repository implements **The Unfought Battle**, a turn-based strategy game
built as a headless Python/Flask API. The game is currently at **version 9**
after 14 iterative design revisions on this branch. It features hidden
information, fog of war, a shrinking board, and five distinct order types —
designed to be a platform for both human gameplay and AI strategy research.

The codebase is ~10,000 lines of Python across 24 files: 10 source modules and
14 test/harness files. The test suite contains **238 tests** (182 unit + 56
gameplay) that all pass, plus 3 score harnesses (Fun Score, Narrative Score,
Depth Score) that measure game quality mathematically.

**Key finding:** The game has strong mechanical foundations but v9 introduced a
balance regression. The sovereign defense bonus shifted the meta toward
defensive/ambush strategies, collapsing the metagame in replicator dynamics to a
single dominant strategy. The test suite accommodated this by loosening
thresholds — tests pass, but the game is measurably less balanced than v7/v8.

---

## Architecture

### Core Engine (2,181 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `models.py` | 82 | Data classes: Force, Player, Hex. Hidden power values 1-5. |
| `state.py` | 282 | GameState management, fog of war filtering, deployment. |
| `orders.py` | 430 | Five order types (Move/Charge/Scout/Fortify/Ambush), supply chain validation. |
| `resolution.py` | 288 | Combat resolution with variance, support bonus, retreat mechanic. |
| `upkeep.py` | 277 | Turn finalization, Noose (shrinking board), victory conditions. |
| `map_gen.py` | 198 | 7x7 hex grid generation with terrain types (Open/Difficult/Contentious/Scorched). |
| `app.py` | 342 | Flask REST API: game creation, state queries, order submission. |
| `play_cli.py` | 492 | CLI play mode (v9 addition). |
| `config.json` | 27 | Tunable game parameters. |

### Test Infrastructure (7,288 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `simulate.py` | 1,528 | Game simulation engine + 9 Tier 1 strategies + adversarial variants. |
| `strategies_advanced.py` | 1,033 | Tiers 2-4: PatternReader, SupplyCutter, BayesianHunter, LookaheadPlayer. |
| `test_gameplay.py` | 1,054 | 56 gameplay tests across 17 test classes. |
| `test_fun_score.py` | 733 | 9-dimension Fun Score (0-10 per dimension). |
| `test_narrative_score.py` | 920 | 10-dimension Narrative Score (story richness + anti-calculability). |
| `test_depth_score.py` | 549 | 6-dimension Depth Score (strategy tier gradient). |
| Unit tests (6 files) | 1,471 | Unit tests for each core module. |

---

## Game Design

### Core Concept

Each player deploys 5 forces with **hidden power values** (1-5, each used
exactly once). Power 1 is the **Sovereign** — lose it, lose the game. Every
force looks identical to the opponent. The game is about information asymmetry:
what you know, what you don't, and what you can make your opponent believe.

### Mechanics

**Orders (5 types):**
- **Move** (free): Adjacent hex movement.
- **Charge** (2 Shih): Move up to 2 hexes, +1 attack bonus. Requires supply.
- **Scout** (2 Shih): Reveal one enemy's power within range 2. Requires supply.
- **Fortify** (2 Shih): +2 defense this turn. Requires supply.
- **Ambush** (3 Shih): +1 defense, hidden from opponent. Requires supply.

**Supply Chain:** Forces must chain back to the Sovereign (max 2 hops, range 2)
to use special orders. Broken supply = Move only.

**Combat:** `effective_power = base_power + modifiers + random(±2)`. Both power
values are permanently revealed after combat. Losers retreat if power difference
≤ 2, otherwise killed.

**The Noose:** Every 5 turns, the outermost ring of hexes becomes Scorched.
Forces on Scorched hexes die. Creates endgame pressure.

**Victory Conditions:**
1. Sovereign Capture — destroy the enemy's power-1 force
2. Domination — hold 2+ Contentious hexes for 3 consecutive turns
3. Elimination — destroy all enemy forces

### Configuration (v9)

```json
{
  "starting_shih": 6,   "max_shih": 8,
  "base_shih_income": 1, "contentious_shih_bonus": 2,
  "force_count": 5,      "board_size": 7,
  "visibility_range": 2, "shrink_interval": 5,
  "charge_attack_bonus": 1, "sovereign_defense_bonus": 1,
  "retreat_threshold": 2, "supply_range": 2, "max_supply_hops": 2
}
```

---

## Version History (Branch)

| Version | Commit | Key Changes |
|---------|--------|-------------|
| v3 | `e904906` | Complete redesign: hidden power values, fog of war, shrinking board, ambush. |
| v4 | `81fdef7` | Charge, support, retreat mechanics. |
| v5 | `286de2f` | Supply lines, charge bonus, wider combat variance, gentler Noose. |
| v6 | `b9fa69b` | Rigorous gameplay tests with game balance fixes. |
| v7 | `86d31e8` | Supply hop limits, tighter economy, intransitive metagame. |
| v8 | `3f1bd94` | Anti-Goodhart overhaul: ablation tests, smart passive, adversarial strategies, seed robustness. No rule changes. |
| v9 | `c8407c9` | Sovereign defense bonus, wider starting separation, CLI play mode. Strategy ladder (Tiers 2-4). |

The branch also includes the **Goodhart's Law analysis** (`462a295`) that
identified 10 structural problems in the test suite, leading to the v8 overhaul.

---

## Test Suite Analysis

### Unit Tests (182 tests, ~2 seconds)

Cover all core modules: models, state, orders, resolution, upkeep, map
generation, and API endpoints. These are deterministic and fast.

### Gameplay Tests (56 tests, ~3 minutes)

Run a full round-robin tournament between 9 strategies (40 games per matchup =
2,880 games) and measure 17 design properties:

1. **Combat is central** — majority of games involve fights
2. **Decisions matter** — no single order type monopolizes
3. **Information pays** — scouting correlates with combat/wins
4. **Aggression works** — aggressive strategies are competitive
5. **Passivity dies** — turtle is crushed; SmartPassive also loses
6. **No dominant strategy** — rock-paper-scissors among competitive strats
7. **Games have arcs** — opening/midgame/endgame phases exist
8. **Victory paths diverge** — all 3 victory types occur
9. **Forces die** — combat has consequences
10. **The Noose pressures** — shrinking board shapes play
11. **Skill gradient** — smarter strategies beat dumber ones
12. **Deployment matters** — power assignment changes outcomes
13. **Contentious hexes contested** — both players fight for territory
14. **Mechanics work** — every mechanic is used and affects outcomes
15. **Game theory** — intransitive cycles, replicator dynamics, no dominance
16. **Ablation** — removing scouting/charge/power-awareness degrades performance
17. **Seed robustness** — results stable across different map seeds

### Score Harnesses (3 files)

- **Fun Score** (9 dimensions): Decision density, deployment impact, combat
  skill, information depth, organic endings, metagame richness, spatial freedom,
  role emergence, supply relevance.
- **Narrative Score** (10 dimensions): Arc length, lead changes, decisive
  moments, story diversity, comeback viability, phase transitions, fog
  persistence, information-action coupling, outcome uncertainty, counter-strategy
  reward.
- **Depth Score** (6 dimensions): Planning gradient (T2 vs T1), reasoning
  gradient (T3 vs T2), computation gradient (T4 vs T3), narrative from depth,
  depth unlocks mechanics, cross-harness consistency.

---

## Strategy Tiers

### Tier 1 — Reactive Heuristics (simulate.py)

| Strategy | Approach |
|----------|----------|
| Aggressive | High-power forces charge; low-power scout |
| Cautious | Scout first, attack only when intel is favorable |
| Ambush | Set traps, fortify, wait for attackers |
| Blitzer | Charge-heavy, close distance fast |
| Sovereign Hunter | Prioritize finding and killing the Sovereign |
| Noose Dodger | Stay ahead of the shrinking board |
| Coordinator | Maintain formation for support bonuses |
| Turtle | Never move, only fortify (straw man) |
| Random | Random orders (baseline) |

**Adversarial variants (v8):** NeverScout, NoCharge, PowerBlind,
SmartPassive, DominationStaller.

### Tier 2 — Stateful Planners (strategies_advanced.py)

**PatternReader:** Tracks enemy movement patterns across turns to predict
behavior. **SupplyCutter:** Deliberately positions between enemy forces and
their Sovereign to break supply chains.

### Tier 3 — Information-Theoretic

**BayesianHunter:** Maintains probability distributions over hidden enemy
power values. Uses scouting and combat reveals to update beliefs. Makes
decisions under genuine uncertainty.

### Tier 4 — Search-Based

**LookaheadPlayer:** Forward simulation across multiple possible worlds
(belief states). Evaluates actions by predicting outcomes 1-2 turns ahead.
The anti-calculability test: if Tier 4 massively dominates, the game is
solvable by brute force.

---

## Known Issues (v9)

### 1. Metagame Collapse

The sovereign defense bonus (+1 when defending) combined with wider starting
separation created a meta where **ambush is overwhelmingly dominant** in
replicator dynamics. The competitive metagame collapses to a single survivor
in evolutionary simulation.

**Evidence in test thresholds:**
- `test_replicator_dynamics_sustain_diversity`: threshold lowered from 3
  survivors to 1
- `test_no_strategy_dominates_competitive_field`: ceiling raised from 62% to 68%
- `test_intransitive_cycles_exist`: made informational (`assert found or True`)
- `test_domination_staller_not_viable`: threshold raised from 40% to 65%

### 2. Threshold Inflation

Multiple v9 test thresholds were loosened to accommodate the balance shift
rather than fixing the underlying game balance:

| Test | v8 Threshold | v9 Threshold |
|------|-------------|-------------|
| Strategy dominance ceiling | 62% | 68% |
| Replicator survivors | ≥3 | ≥1 |
| Every-strategy-has-counter | 0 exceptions | 1 exception allowed |
| SmartPassive ceiling | 40% | 50% |
| DominationStaller ceiling | 40% | 65% |
| Charge ablation threshold | 55% | 40% |

### 3. Goodhart Residuals

The v8 anti-Goodhart overhaul addressed 10 structural problems (documented in
`docs/goodharts-law-analysis.md`). Key mitigations were implemented (ablation
tests, SmartPassive, adversarial strategies, seed robustness), but some
residual issues remain:

- **Strategies are both instrument and target:** All measurements still depend
  on hand-coded strategies co-evolved with the game rules.
- **Role emergence is programmed:** Power-level-specific behavior is hardcoded
  in strategy logic, not emergent from game mechanics.
- **Fun Score has no teeth:** `test_fun_score` asserts `overall >= 0` — a
  game scoring 1.0/10 would pass.

### 4. v10 Recommendations

The test comments themselves document what needs fixing:
- Rebalance Tier 1 strategies for sovereign defense bonus
- Tighten domination staller threshold once strategies adapt
- Restore replicator dynamics diversity requirement to ≥3
- Consider reducing sovereign defense bonus or adjusting ambush cost

---

## Codebase Patterns

### Design Strengths

- **Config-driven tuning:** All numeric constants live in `config.json` with
  sensible defaults in each module.
- **Measurement-rich:** Three independent score harnesses measure overlapping
  aspects of game quality from different angles.
- **Self-documenting tests:** Every test has a "Why" comment explaining the
  design goal it enforces.
- **Ablation methodology:** Tests prove causation (mechanic X matters) not
  just correlation (strategies that use X also do Y).
- **Adversarial testing:** Degenerate strategies specifically designed to
  exploit weaknesses, not just demonstrate features.

### Design Risks

- **Single-file simulation engine:** `simulate.py` at 1,528 lines handles
  strategy definitions, game simulation, and tournament infrastructure.
- **No persistent state:** Games exist only in memory. No database backing.
- **Heavy test runtime:** Gameplay tests run ~3 minutes (2,880 simulated
  games). Score harnesses add more.
- **Strategy-dependent measurements:** All game quality metrics depend on the
  behavior of hand-coded strategies, creating the closed feedback loop
  identified in the Goodhart analysis.

---

## File Dependency Graph

```
config.json
    ↓
models.py → map_gen.py → state.py → orders.py → resolution.py → upkeep.py
                                                                      ↓
                                                                   app.py
                                                                   play_cli.py
                                                                      ↓
                                                    tests/simulate.py (Tier 1)
                                                            ↓
                                              tests/strategies_advanced.py (Tiers 2-4)
                                                            ↓
                                              tests/test_gameplay.py (56 tests)
                                              tests/test_fun_score.py
                                              tests/test_narrative_score.py
                                              tests/test_depth_score.py
```

---

## How to Run

```bash
# Unit tests (~2 seconds)
pytest tests/test_models.py tests/test_state.py tests/test_orders.py \
       tests/test_resolution.py tests/test_upkeep.py tests/test_map_gen.py \
       tests/test_api.py

# Gameplay tests (~3 minutes)
pytest tests/test_gameplay.py

# All tests
pytest

# Score harnesses (long-running)
pytest tests/test_fun_score.py tests/test_narrative_score.py tests/test_depth_score.py

# API server
python app.py

# CLI play mode (v9)
python play_cli.py
```

---

*Analysis produced from branch `claude/explore-repo-overview-11H7s` at commit
`c8407c9` (The Unfought Battle v9).*
