# Goodhart's Law Analysis of the Test Suite

> "When a measure becomes a target, it ceases to be a good measure."

The test suite is sophisticated and self-aware — the docstrings even say
"fix the GAME, not the threshold." But several deep structural issues mean
the tests can pass while the game fails at what they're trying to measure.

---

## 1. THE STRATEGIES ARE BOTH INSTRUMENT AND TARGET

**The most fundamental problem.** Every gameplay and fun-score test measures
emergent properties of games played by 9 hand-coded strategies. But those
strategies were designed *by the same developer tuning the game rules*. This
creates a closed feedback loop:

- Developer writes strategy that scouts with power-2/3 forces
- `test_scouting_is_used_meaningfully` passes
- Developer concludes "the information system works"

But this proves the **strategies** use scouting, not that the **game** rewards
scouting. A human player might discover that charging blind is strictly
better — the test would never catch that because no strategy embodies it.

**Mitigation:** Add adversarial/degenerate strategies specifically designed to
exploit potential weaknesses — e.g., a "NeverScout" variant of Cautious that
skips all scouting, a "MassCharge" that spends all Shih on charges, a
"SupplyIgnorer" that deliberately spreads beyond supply range. If the game is
well-designed, these should lose. If they win, the metrics were being gamed.

---

## 2. ROLE EMERGENCE IS PROGRAMMED, NOT EMERGENT

`score_role_emergence` in `test_fun_score.py` measures whether different power
levels behave differently. It checks KL-divergence between power-level order
distributions and whether power-4/5 charge more than power-2/3.

But look at the strategies: `AggressiveStrategy` explicitly says
`if force.power >= 4: charge`. `BlitzerStrategy` does the same.
`CautiousStrategy` explicitly says `if force.power in (2, 3): scout`. Every
strategy hardcodes power-aware behavior.

The "role emergence" score measures **programmed** behavior, not emergent
behavior. The metric passes because the strategies were written to make it pass.

**Mitigation:** Test role emergence using ONLY `RandomStrategy` with a twist:
give it strategic but non-role-aware heuristics (e.g., "move toward enemies if
strong enough, flee otherwise" without power-specific thresholds). If power-1
forces naturally avoid combat because they lose, that's genuine emergence. If
power levels behave identically under non-coded heuristics, the "emergence" is
an illusion.

---

## 3. TURTLE IS A STRAW MAN

`test_turtle_is_crushed_by_every_active_strategy` asserts turtle wins <10%
against every active strategy. But `TurtleStrategy` literally *never moves*:

```python
def plan(self, ...):
    for force in alive:
        if can_order(force, player, FORTIFY):
            orders.append(Order(FORTIFY, force))
    # Never move
```

*Any* game with a shrinking board would crush this. A strategy that stays at
spawn and fortifies isn't testing whether the game punishes passivity — it's
testing whether standing still while the map burns kills you. The real danger
is a *smart* passive strategy: one that retreats from the Noose while avoiding
combat, wins by domination timeout, or forces stalemates.

**Mitigation:** Replace `TurtleStrategy` with `SmartPassive`: moves toward
center to dodge the Noose, fortifies at contentious hexes, never initiates
combat, retreats from attackers. If *that* strategy is crushed, passivity is
genuinely punished. If it's competitive, the game has a passivity problem that
the current turtle test obscures.

---

## 4. CURATED COMPETITIVE POOL MASKS DEGENERATE STRATEGIES

The `COMPETITIVE_STRATEGIES` filter excludes turtle and random, then tests
"no dominant strategy" within the remaining 7. But the 7 strategies were
hand-picked to be diverse. No strategy in the pool tries to:

- Stall for domination by holding 2 contentious hexes and running away
- Trade forces 1-for-1 regardless of power (attrition warfare)
- Mass-fortify at center and wait for the Noose to kill the opponent's sovereign
- Exploit supply chain hops by spreading forces thin to deny supply to the enemy

If any degenerate strategy dominates the competitive pool, the
rock-paper-scissors tests would fail — but those strategies were never
included in the pool.

**Mitigation:** Add a "strategy discovery" test that generates semi-random
strategy variants (e.g., random threshold values for when to attack vs.
scout vs. fortify) and checks whether any discovered strategy dominates the
competitive field. If the game is robust, random perturbations shouldn't
produce dominant strategies.

---

## 5. COMBAT CORRELATION TESTS ARE CONFOUNDED

`test_scouting_correlates_with_combat` asserts that games with scouting have
higher combat rates. But this correlation is spurious: strategies that scout
(cautious, hunter, dodger) are also strategies that advance toward enemies.
The correlation measures "strategies that do stuff → more stuff happens," not
"information → engagement."

Similarly, `test_charge_enables_combat` suffers the same confound:
charge-using strategies are aggressive strategies that would initiate combat
anyway.

**Mitigation:** Test causation, not correlation. Compare the *same strategy*
with and without scouting/charging enabled. Create a `CautiousNoScout` variant
that is identical to `CautiousStrategy` but skips all scout orders. If it
performs significantly worse, scouting genuinely matters. If it performs the
same, scouting is decorative.

---

## 6. THRESHOLDS ARE SUSPICIOUSLY ACHIEVABLE

The docstring claims "thresholds describe the game we WANT, not the game we
have." But consider:

| Test | Threshold | Effective constraint |
|------|-----------|---------------------|
| Aggressive wins | >40% | With 7 opponents, 40% is below average |
| Blitzer wins | >35% | Even weaker |
| No strategy >65% | Very generous ceiling |
| Tier gap <35% | Allows massive hierarchy |
| Viable strategies >35% win rate: ≥4 of 7 | Allows 3 dead strategies |
| Retreat rate 20-60% | Huge range |
| Midgame (7-14 turns) >20% | Very low bar |

These thresholds would pass even for a poorly balanced game. A game where one
strategy wins 64% would pass `test_no_strategy_dominates`. A game where 3 of 7
strategies are dead would pass `test_multiple_competitive_strategies_viable`.

**Mitigation:** Tighten thresholds or add statistical tests. Instead of
"no strategy >65%," test that the competitive win rate distribution has a
coefficient of variation < 0.15. Instead of "≥4 viable," test that all 7
competitive strategies have win rates in [40%, 60%].

---

## 7. FUN SCORE HAS NO TEETH

`test_fun_score` always passes:

```python
def test_fun_score():
    scores, overall = compute_fun_scores(verbose=True)
    assert overall >= 0, "Fun score computation failed"
```

This is an explicit anti-Goodhart decision ("this is a measurement, not a
gate"). But it means the most holistic quality metric has zero enforcement. A
game with fun score 1.0/10 passes the test suite.

**Mitigation:** Add minimum dimensional scores as gated assertions — not on the
overall average, but on each dimension. For example: every dimension must score
≥3.0/10 (below which the mechanic is clearly broken), and the overall must be
≥5.0. This preserves the "measurement" spirit while adding a safety net.

---

## 8. SUPPLY RELEVANCE IS SELF-FULFILLING

`score_supply_relevance` measures how often forces are cut from supply. But the
strategies are designed to keep forces in formation (CoordinatorStrategy
explicitly maintains adjacency). The `max_supply_hops` parameter was tuned
alongside strategy behavior.

The "Supply Relevance" sub-score B tries to check if supply loss correlates
with losing, but it explicitly acknowledges "We don't track per-player supply,
so use a proxy" — it then uses a proxy that doesn't actually measure what it
claims to measure.

**Mitigation:** Track per-player supply statistics in `GameRecord`. Measure the
actual question: "Does the player with more supply-cut force-turns lose more
often?" Also add a strategy that deliberately tries to cut enemy supply by
positioning between enemy forces and their sovereign.

---

## 9. FIXED SEEDS CREATE HIDDEN OVERFITTING

`GAMES_PER_MATCHUP = 40` with `MAP_SEEDS = list(range(40))` means every test
run uses the exact same 40 maps. The game rules, strategies, and thresholds may
have been unconsciously tuned to these specific maps. A different set of seeds
could produce different results.

**Mitigation:** Occasionally run tests with random seeds (e.g., a separate CI
job that uses `MAP_SEEDS = random.sample(range(10000), 40)`). If results are
stable across seed sets, the game is robust. If they fluctuate, the thresholds
are overfitted to the current seeds.

---

## 10. DEPLOYMENT IMPACT TESTS ONLY ONE STRATEGY

`score_deployment_impact` and `test_different_deployments_different_outcomes`
only test deployment variation using `AggressiveStrategy`. They don't test
whether deployment matters for cautious, ambush, or coordinator play. The
deployment phase might be meaningful for one archetype and irrelevant for
others.

**Mitigation:** Test deployment sensitivity across all competitive strategies.
For each strategy, run the same matchup with 10 different random deployments
and measure outcome variance. If deployment only matters for 1-2 strategies,
the deployment system is narrow, not deep.

---

## Summary

The core Goodhart pattern is: **the strategies, thresholds, and game rules form
a co-evolved system where each was adjusted to make the others look good.** The
tests prove the system is internally consistent, but not that it would produce
fun gameplay for real humans playing novel strategies.

The strongest mitigations are:

1. **Adversarial strategy generation** — strategies designed to exploit, not
   demonstrate
2. **Ablation testing** — disable mechanics and verify performance degrades
3. **Causation testing** — control for confounds in correlation tests
4. **Seed randomization** — break hidden overfitting to fixed map seeds
