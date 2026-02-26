# Evaluation Harness Analysis: Evolving Toward Dual Optimization

## Executive Summary

The v10 evaluation harness is architecturally strong — three independent scoring
systems (Fun, Narrative, Depth) plus a benchmark telemetry layer and 238+ tests.
But under scrutiny, there are **13 structural gaps** that prevent the harness from
being certain it optimizes both the game AND the LLM reasoning benchmark simultaneously.

This analysis identifies where the two objectives diverge, where Goodhart's Law
still lurks, and proposes concrete evolutions to close the gaps.

---

## Part 1: What the Harness Gets Right

**Orthogonal measurement axes.** Fun (is it well-designed?), Narrative (does it
tell stories?), and Depth (does skill matter?) measure genuinely different things.
A game that scores high on all three is likely good; gaming one doesn't
automatically game the others.

**Anti-Goodhart awareness.** The v8 adversarial variants (NeverScout, NoCharge,
PowerBlind, SmartPassive, DominationStaller) are well-conceived ablation probes.
They test that metrics reflect real game properties rather than artifacts of
strategy implementation.

**Tiered strategy ladder.** The Tier 1-4 architecture with diminishing returns
is the correct shape for measuring depth. The Depth Score's inverted scoring
for D3 (Computation Gradient) directly encodes the anti-calculability thesis.

**Benchmark telemetry primitives.** BeliefState, AgentReport, and EventLog form
a clean, extensible schema. The metrics (Brier, log loss, calibration error,
ToM delta) are the right ones for measuring strategic reasoning.

---

## Part 2: The 13 Structural Gaps

### Gap 1: The Two Objectives Are Never Jointly Tested

**The problem.** The Fun/Narrative/Depth scores optimize the *game*. The
benchmark metrics (Brier score, calibration, ToM delta) optimize the *LLM
measurement platform*. But no test asks: "Does improving the game also make it
a better benchmark?" or vice versa.

**Why it matters.** Consider: you could make the game more "fun" by adding more
combat variance (more dice, less prediction). But that would *degrade* the
benchmark by making beliefs less useful — Brier scores wouldn't improve
with better reasoning because randomness dominates outcomes.

Conversely, you could make the benchmark sharper by reducing variance to zero
(deterministic combat). That would improve belief quality measurement but
make the game boring and calculable.

**The fix.** Add a **Dual Optimization Score** (see Part 3, Proposal A) that
measures the *correlation* between belief quality and game outcomes.
The game is optimized for both purposes when: (a) better beliefs lead to
more wins, AND (b) the belief-to-win correlation has a ceiling (not 1.0)
because variance prevents brute-force solving.

### Gap 2: MockLLMAgent Generates Fake Beliefs, Never Tests Real Ones

**The problem.** MockLLMAgent (llm_agent_interface.py:129-152) builds beliefs
by reading `known_enemy_powers` directly from the game state — the very data
structure that encodes perfect knowledge. Its "beliefs" are trivially correct
wherever information exists and trivially uniform where it doesn't.

No agent in the test suite actually performs *inference* — combining partial
observations, tracking which powers have been revealed, updating priors from
position behavior. The mock just queries the answer key.

**Why it matters.** The benchmark claims to measure "strategic reasoning quality"
via Brier score and calibration. But these metrics have only been tested against
a mock that reads ground truth. The pipeline from "observe game state" →
"form belief" → "make decision based on belief" has never been exercised end-to-end
with a non-trivial reasoner.

**The fix.** Build at least one **InferenceAgent** (see Proposal B) that
actually maintains a constraint-based belief model: "I've seen powers 3 and 5 on
two forces; therefore the other three are drawn from {1, 2, 4}." This agent
doesn't need an LLM — just logic. Use it to validate that the telemetry
pipeline produces meaningful metric differentiation.

### Gap 3: Action Predictions Are Never Scored

**The problem.** AgentReport includes `action_predictions` (per-force predicted
opponent orders) and `objective_prediction` (high-level opponent intent). The
EventLog captures what actually happened. But `benchmark/metrics.py` computes
metrics *only* for power beliefs — never for action or objective predictions.

**Why it matters.** Theory-of-mind isn't just "what power does that force have?"
It's "what will that force DO next turn?" and "what is the opponent TRYING to
accomplish?" These are the predictions that separate strategic reasoning from
static inference. By not scoring them, the benchmark misses its most
interesting measurement opportunity.

**The fix.** Add **action prediction accuracy** and **objective prediction
accuracy** to the metrics module (see Proposal C). Compare predicted action
distributions against actual orders each turn.

### Gap 4: No Measurement of Belief → Decision Coupling

**The problem.** The benchmark measures belief quality (Brier score) and
game outcomes (win/loss) separately. But it doesn't measure whether agents
*use* their beliefs to make *better decisions*. An agent could have perfect
beliefs but still play randomly.

**Why it matters.** The fundamental question is: "Does reasoning about hidden
information lead to better play?" Not: "Can the agent track hidden information?"
(that's a memory test) or "Does the agent win?" (that's confounded by everything
else). The specific causal link — beliefs → decisions → outcomes — is unmeasured.

**The fix.** Add a **Belief-Decision Coherence** metric (see Proposal D): for
each order chosen, compute how well it aligns with the agent's stated beliefs.
For example, if the agent believes force X is the Sovereign (power 1) and
charges it with power 5, that's coherent. If it believes X is power 5 and
charges it with power 2, that's incoherent.

### Gap 5: Fun Score Dimensions Measure Strategies, Not Game Rules

**The problem.** Seven of nine Fun Score dimensions are computed from tournament
data using specific strategy implementations. Decision Density depends on
whether strategies happen to use special orders. Role Emergence depends on
whether strategies assign different behaviors to different power levels. Supply
Relevance depends on whether strategies position forces to cut supply.

**Why it matters.** This is the deepest Goodhart problem in the harness. If a
Fun Score dimension is low, the "correct" response is to improve the GAME RULES.
But the temptation — and the easy path — is to improve the STRATEGIES to
produce better numbers. The test_fun_score.py header says "fix the GAME, not
the metric" but the measurement itself can't distinguish the two.

**The fix.** For each Fun Score dimension, add a **rule-sensitivity ablation**
(see Proposal E): compute the dimension with the mechanic disabled in game
rules, and verify the score drops. If Role Emergence is 8/10 but stays 8/10
when all powers are replaced with 3s (no hidden values), the dimension is
measuring strategy behavior, not game design.

### Gap 6: Narrative Score's Advantage Function Is Too Coarse

**The problem.** The `_advantage()` function (test_narrative_score.py:101-116)
uses a simple linear combination: `force_count * 2 + power_sum * 0.5 +
contentious_hexes * 1.5`. Lead Changes (N2) and Comeback Viability (N5) depend
entirely on this estimate.

**Why it matters.** If the advantage function is miscalibrated — say it
overweights force count — then "lead changes" might actually be noise from
force losses that don't change who's truly winning. The narrative dimensions
would be measuring advantage-function artifacts, not game drama.

**The fix.** Validate the advantage function against actual outcomes (see
Proposal F): does the player with higher advantage at turn T actually win more
often? If the correlation is weak, the function is noise. If it's too strong,
lead changes are meaningful but rare. Tune the weights empirically.

### Gap 7: Depth Score Recomputes Tier-vs-Tier Matchups Redundantly

**The problem.** D1 (Planning Gradient), D2 (Reasoning Gradient), D3
(Computation Gradient), and D6 (Gradient Shape) all call `_tier_vs_tier()`
independently. D6 recomputes all three gradients that D1-D3 already computed.
Each call runs hundreds of games.

**Why it matters.** This is a correctness risk, not just a performance issue.
If game state has any seed-dependent variance, D6's gradient values will differ
from D1-D3's. The "shape" check could contradict the individual gradients.
Also, the redundant computation means the Depth Score runs ~3x more games
than necessary, which makes it prohibitively slow for rapid iteration.

**The fix.** Cache tier-vs-tier results (see Proposal G). Compute each matchup
once and share across all dimensions.

### Gap 8: No Test That the Evaluation Harnesses Agree With Each Other

**The problem.** D6 (Cross-Harness Consistency) is described in the Depth Score
docstring but the actual implementation (score_gradient_shape) only measures
the tier gradient's shape. It doesn't compute or compare Fun/Narrative scores.

**Why it matters.** The three-harness architecture was specifically designed to
resist Goodhart's Law via independent corroboration. But that defense is
meaningless if the harnesses are never compared. You could have Fun=9, Narrative=3,
Depth=8 — and the game would "pass" all individual tests despite having a
fundamental narrative weakness.

**The fix.** Implement a real cross-harness consistency test (see Proposal H):
run all three scores and verify they tell a coherent story. Specifically:
games produced by higher-tier strategies should score better on Fun and Narrative
dimensions than games produced by lower-tier strategies.

### Gap 9: Noisy Scouting's Anti-Calculability Claim Is Untested

**The problem.** The v10 design document claims noisy scouting (70% exact, 30%
band) "increases inference requirements" and "prevents brute-force lookahead."
The test suite verifies that noisy scouting *produces* bands
(test_benchmark.py:272-286) and that bands are *truthful* (287-297). But no
test measures whether noisy scouting actually *increases inference difficulty*
or *reduces Tier 4's advantage*.

**Why it matters.** The anti-calculability claim is the core thesis of v10.
If noisy scouting doesn't actually change the tier gradient, the entire v10
rationale is unfounded. The game would be equally calculable with or without it.

**The fix.** Run the Depth Score's D3 (Computation Gradient) with
`scout_accuracy=1.0` and `scout_accuracy=0.7` (see Proposal I). If the Tier 4
advantage is smaller under noisy scouting, the claim holds. If it's unchanged,
noisy scouting is cosmetic.

### Gap 10: Tournament Sample Sizes Create Noisy Estimates

**The problem.** GAMES_PER_MATCHUP is 40 across all harnesses. With 10
strategies in the competitive pool, that's 90 matchups × 40 games = 3,600 games.
But each individual matchup has only 40 games. At a 60-40 split, the 95%
confidence interval for a binomial with n=40 is ±15%. Many assertions check
thresholds within that interval (e.g., "win rate > 55%").

**Why it matters.** The harness may pass or fail based on random fluctuation,
not game quality. A test that checks "Cautious beats NeverScout at >50%" with
n=60 games has a ~10% chance of failing even if the true rate is 55%.

**The fix.** Two options (see Proposal J): (1) Increase sample size to 100+
per matchup for critical thresholds. (2) Use statistical tests (binomial CI,
chi-squared) instead of raw threshold checks, and require p<0.05 rather than
point estimates.

### Gap 11: The Benchmark Has No Adversarial Agents

**The problem.** The game-quality harness has 5 adversarial strategies
(NeverScout, NoCharge, PowerBlind, SmartPassive, DominationStaller) designed
to expose weaknesses. The benchmark layer has zero. There are no agents
designed to produce misleading telemetry — good Brier scores from bad play,
or bad Brier scores from good play.

**Why it matters.** If the benchmark can be gamed — e.g., an agent that
reports confident but arbitrary beliefs yet wins by ignoring them — the metrics
don't measure strategic reasoning. An agent that memorizes a lookup table of
"if position X, play Y" would have uniform beliefs (Brier score = 0.16) but
might win consistently.

**The fix.** Create adversarial benchmark agents (see Proposal K):
(1) **FakeBeliefAgent** — reports confident beliefs it doesn't use for decisions.
(2) **LookupAgent** — ignores beliefs entirely, plays from a hardcoded table.
Verify the benchmark detects these as lower-quality reasoners despite potentially
good win rates.

### Gap 12: No Temporal Structure in Metrics

**The problem.** `compute_game_metrics()` averages Brier score and calibration
across all turns of a game. But strategic reasoning quality should *improve*
over a game as more information is gathered. An agent that starts with Brier
0.16 (uniform) and ends with 0.02 (near-certain) is reasoning well. An agent
that stays at 0.10 throughout is not improving. Both might average to 0.09.

**Why it matters.** The benchmark should reward agents that *learn* — that
update beliefs in response to evidence and get sharper over time. Averaging
destroys this signal.

**The fix.** Add per-phase metrics (see Proposal L): early-game (turns 1-5),
mid-game (turns 6-10), late-game (turns 11+) Brier scores. Measure the
*improvement trajectory*, not just the average. A good agent's Brier score
should monotonically decrease.

### Gap 13: No Measurement of Deception

**The problem.** The game explicitly supports deception: ambush is hidden from
opponents, deployment is secret, and movement into fog creates uncertainty.
But no metric measures whether agents *exploit* deception — or whether the
game rewards it. A bluffing agent that deploys its Sovereign in a non-standard
position to confuse an opponent's belief model is engaging in the highest form
of strategic reasoning. The benchmark can't detect this.

**Why it matters.** Deception is the pinnacle of theory-of-mind. If the benchmark
can't measure it, it's measuring inference (what do I know?) rather than
strategy (how do I manipulate what my opponent knows?). The gap between these
is the gap between a calculator and a chess grandmaster.

**The fix.** Add a **Deception Efficacy** metric (see Proposal M): measure
how often an agent's actions cause the opponent's beliefs to become *less*
accurate. Compare this against a baseline of agents that always play
straightforwardly. If deceptive agents win more, deception is rewarded;
if the opponent's Brier score worsens when facing a deceptive agent, deception
is measurably effective.

---

## Part 3: Evolution Proposals

### Proposal A: Dual Optimization Score

Add a new test file `tests/test_dual_optimization.py` that measures the
correlation between belief quality and game outcomes:

```
belief_win_correlation:
  For each game in the benchmark tournament:
    1. Compute average Brier score for each player
    2. Record who won
    3. Compute: does the player with better Brier score win more often?

  Target: correlation between 0.3 and 0.7
    Below 0.3: beliefs don't help (game too random for reasoning to matter)
    Above 0.7: beliefs are everything (game too deterministic, brute-force solves it)
    Sweet spot: beliefs help, but aren't sufficient

belief_ceiling:
  Even with perfect beliefs (Brier = 0), what's the win rate?
  Target: 60-75% (beliefs help but variance preserves uncertainty)
```

### Proposal B: InferenceAgent

Build a `ConstraintInferenceAgent` in `benchmark/inference_agent.py` that:
- Tracks which powers have been revealed (via combat or scouting)
- Maintains a constraint set: {force_X: not power 3, not power 5}
- Distributes probability uniformly over remaining possibilities
- Updates via Bayesian inference on noisy scout results
- Does NOT read `known_enemy_powers` directly

This agent validates the full telemetry pipeline with real inference,
not mocked beliefs.

### Proposal C: Action Prediction Metrics

Add to `benchmark/metrics.py`:

```
action_brier_score(reports, event_logs):
  For each turn:
    Compare agent's predicted action distribution for each enemy force
    against the actual order issued
  Return: average Brier score across all force-turns

objective_accuracy(reports, event_logs, outcomes):
  For each game:
    Compare agent's objective_prediction against the actual victory type
  Return: fraction of correct high-level predictions
```

### Proposal D: Belief-Decision Coherence

Add to `benchmark/metrics.py`:

```
belief_decision_coherence(reports, game_states):
  For each order the agent issues:
    Given the agent's beliefs about enemy forces:
      - If attacking a force believed to be weak: coherent (+1)
      - If retreating from a force believed to be strong: coherent (+1)
      - If attacking a force believed to be strong with a weak force: incoherent (-1)
      - If scouting a force with high entropy belief: coherent (+1)
      - If scouting a force with low entropy (already known): incoherent (-1)
  Return: average coherence score (higher = agent acts on its beliefs)
```

### Proposal E: Rule-Sensitivity Ablations for Fun Score

For each Fun Score dimension, run a parallel measurement with the relevant
game mechanic disabled. Verify score drops by at least 30%:

- Decision Density: disable all specials (Move only) → score should drop to <3
- Role Emergence: all forces have power 3 → score should drop to <3
- Supply Relevance: disable supply check → score should drop to <3
- Combat Skill: set variance to 0 → score should change character
- Information Depth: set visibility to infinite → score should drop to <3

### Proposal F: Advantage Function Validation

Add a test that validates the `_advantage()` function:

```
For each game:
  At each turn T:
    Record advantage(T) and who eventually wins
  Compute: P(p1 wins | advantage > 0) should be > 0.55 and < 0.85

  If < 0.55: advantage function doesn't predict outcomes (miscalibrated)
  If > 0.85: advantage function is too accurate (no drama possible)
```

### Proposal G: Shared Tournament Cache for Depth Score

Refactor `test_depth_score.py` to compute all tier-vs-tier matchups once
at module scope and pass results to each dimension scorer. This eliminates
redundant game simulation and ensures consistency across dimensions.

### Proposal H: Cross-Harness Consistency Test

Add a real implementation of D6 that:
1. Runs Fun Score on Tier 1-vs-Tier 1 games and Tier 3-vs-Tier 3 games
2. Runs Narrative Score on both sets
3. Verifies: higher-tier games score >= on at least 6/9 Fun dimensions
4. Verifies: higher-tier games score >= on at least 7/10 Narrative dimensions

### Proposal I: Anti-Calculability Ablation

Run D3 (Computation Gradient) under two configurations:
- `scout_accuracy=1.0` (perfect scouting — v9 behavior)
- `scout_accuracy=0.7` (noisy scouting — v10)

Verify: Tier 4's advantage over Tier 3 is smaller under noisy scouting.
This is the empirical test of the v10 anti-calculability thesis.

### Proposal J: Statistical Rigor

Replace threshold assertions with statistical tests:

```python
# Instead of:
assert win_rate > 0.55

# Use:
from scipy.stats import binom_test
p_value = binom_test(wins, total, 0.50, alternative='greater')
assert p_value < 0.05, f"Cannot reject H0 (win_rate=50%) at p<0.05: {win_rate:.1%}, p={p_value:.3f}"
```

### Proposal K: Adversarial Benchmark Agents

Create agents that try to game the benchmark metrics:

1. **FakeBeliefAgent**: Reports peaked beliefs (Brier → 0) but plays
   identically to AggressiveStrategy regardless of beliefs.
2. **LookupAgent**: Plays from a table of "if position X, order Y" with
   no belief tracking at all (Brier = 0.16 always).
3. **OverfitAgent**: Memorizes outcomes from training seeds, produces
   perfect beliefs on those seeds but fails on new seeds.

### Proposal L: Temporal Metric Structure

Add phase-segmented metrics:

```
early_brier (turns 1-5): Starting uncertainty
mid_brier (turns 6-10): Active learning
late_brier (turns 11+): Refined knowledge
learning_rate = (early_brier - late_brier) / early_brier

Target: learning_rate > 0.3 for a good agent
```

### Proposal M: Deception Efficacy Metric

Measure deception as the *increase in opponent's Brier score* caused by
non-standard play:

```
For agent A playing against agent B:
  deception_effect = B.brier_score(vs_A) - B.brier_score(vs_straightforward)

  If positive: A's play makes B's beliefs worse (A is deceptive)
  If negative: A's play actually helps B form better beliefs (A is transparent)

  Score: correlate deception_effect with A's win rate
  If positive correlation: the game rewards deception (good for benchmark)
```

---

## Part 4: Priority Order

Ranked by impact on dual optimization certainty:

| Priority | Proposal | Impact | Effort |
|----------|----------|--------|--------|
| 1 | A (Dual Optimization Score) | Directly addresses the core question | Medium |
| 2 | B (InferenceAgent) | Validates the entire benchmark pipeline | Medium |
| 3 | D (Belief-Decision Coherence) | Connects beliefs to outcomes | Low |
| 4 | C (Action Prediction Metrics) | Completes the metric suite | Low |
| 5 | E (Rule-Sensitivity Ablations) | Validates Fun Score measures rules, not strategies | Medium |
| 6 | I (Anti-Calculability Ablation) | Tests the v10 thesis directly | Low |
| 7 | L (Temporal Metrics) | Measures learning, not just knowledge | Low |
| 8 | K (Adversarial Benchmark Agents) | Prevents benchmark gaming | Medium |
| 9 | M (Deception Efficacy) | Measures highest-order reasoning | High |
| 10 | H (Cross-Harness Consistency) | Delivers on the multi-harness promise | Medium |
| 11 | G (Shared Cache) | Correctness + performance fix | Low |
| 12 | J (Statistical Rigor) | Reduces false pass/fail rates | Medium |
| 13 | F (Advantage Validation) | Validates a specific measurement | Low |

---

## Part 5: The Unifying Insight

The evaluation harness currently answers two separate questions well:
- "Is this a good game?" (Fun + Narrative)
- "Is this a measurement platform?" (Benchmark + Depth)

But it doesn't answer the *combined* question:
**"Does making the game better also make it a better benchmark,
and does making the benchmark sharper also make the game better?"**

The answer should be yes. A game where beliefs matter is both more fun (information
depth, role emergence, decision density) and a better benchmark (Brier scores
differentiate, calibration is meaningful, ToM delta is positive). A game with
narrative richness (lead changes, comebacks, diverse arcs) is one where
reasoning agents play differently than heuristic ones — exactly what the
benchmark needs to measure.

The proposals above converge on measuring this *joint optimality*. Proposal A
measures it directly. Proposals B-D validate the measurement pipeline. Proposals
E-I ensure the measurements aren't Goodharted. Proposals J-M add rigor and
completeness.

The end state: an evaluation harness where you can change a game rule, re-run
the suite, and get a single answer: "Did this change make the game better
*and* the benchmark sharper?" If both improve, ship it. If they diverge,
investigate why — because divergence means the harness has a blind spot.
