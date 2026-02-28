"""
Game Depth Score: Does sophistication find new depth?

The ultimate test of a great game: smarter players play differently AND better.
In chess, a grandmaster doesn't just play faster — they see things a beginner
can't. Sacrifices, prophylaxis, zugzwang, positional squeezes. Each level of
sophistication unlocks NEW STRATEGIES that didn't exist at lower levels.

This harness measures the DEPTH GRADIENT: how much does each tier of
strategic sophistication improve over the previous one?

=== THE TIERS ===

Tier 1 — Reactive Heuristics (existing 7 competitive strategies)
    Stateless, single-turn planners. "If enemy nearby, attack."

Tier 2 — Stateful Planners (PatternReader, SupplyCutter)
    Memory. Pattern recognition. Multi-turn intent.

Tier 3 — Information-Theoretic (BayesianHunter)
    Bayesian belief tracking. Probabilistic reasoning. Info-seeking.

Tier 4 — Search-Based (LookaheadPlayer)
    Forward simulation. Evaluate actions by predicting outcomes.

=== THE MEASUREMENTS ===

D1. PLANNING GRADIENT — Tier 2 vs Tier 1
    Does memory and pattern recognition beat reactive play?
    If yes: the game rewards planning.
    If no: the game is too simple for planning to matter.

D2. REASONING GRADIENT — Tier 3 vs Tier 2
    Does Bayesian reasoning beat pattern matching?
    If yes: hidden information creates genuine strategic depth.
    If no: hidden info is just noise — knowing it doesn't help.

D3. COMPUTATION GRADIENT — Tier 4 vs Tier 3
    Does forward search beat understanding?
    THIS IS THE KEY ANTI-CALCULABILITY TEST.
    If Tier 4 >> Tier 3: the game is calculable (search dominates).
    If Tier 4 ≈ Tier 3: the game resists calculation (understanding
    matters as much as computation — the human advantage).

D4. NARRATIVE FROM DEPTH — Do smarter players produce richer games?
    Longer games? More lead changes? More diverse outcomes?
    If yes: depth creates narrative. The game gets MORE interesting
    as players get better. That's what chess does.
    If no: depth just means faster kills. The game rewards
    optimization, not exploration.

D5. DEPTH UNLOCKS MECHANICS — Do advanced strategies use
    mechanics that Tier 1 ignores?
    Supply cutting, deceptive deployment, information-seeking,
    ambush traps. If advanced players find new uses for existing
    mechanics, the game has untapped depth.

D6. CROSS-HARNESS CONSISTENCY — Do the three harnesses agree?
    Fun Score, Narrative Score, and Depth Score should tell
    a coherent story. If they contradict, we're measuring wrong.

=== THE IDEAL SHAPE ===

The DEPTH GRADIENT should look like this:

    Tier 1 → Tier 2: Large improvement (~10-15% win rate gain)
    Tier 2 → Tier 3: Moderate improvement (~5-10%)
    Tier 3 → Tier 4: Small improvement (~2-5%)

This shape means:
- Understanding always helps (each tier beats the previous)
- But computation has diminishing returns (the improvement shrinks)
- Human skills (reading opponents, pattern recognition, understanding)
  matter more than brute-force search

If instead Tier 4 >> Tier 3 >> Tier 2 >> Tier 1 with equal gaps,
the game is calculable and AI will dominate humans.

If Tier 2 ≈ Tier 1, the game is too simple for planning to matter.
"""

import math
from collections import Counter

from tests.simulate import (
    AggressiveStrategy,
    BlitzerStrategy,
    CautiousStrategy,
    GameRecord,
    run_game,
)
from tests.strategies_advanced import (
    TIER2_STRATEGIES,
    TIER3_STRATEGIES,
    TIER4_STRATEGIES,
)
from tests.test_narrative_score import _advantage_series, _classify_game

# ---------------------------------------------------------------------------
# Tier 1 representatives (best 3 from existing competitive strategies)
# ---------------------------------------------------------------------------

TIER1_REPRESENTATIVES = [
    BlitzerStrategy(),
    CautiousStrategy(),
    AggressiveStrategy(),
]

N_GAMES = 40  # games per matchup (20 per side)


def _clamp(val, lo=0.0, hi=10.0):
    return max(lo, min(hi, val))


def _h2h(s1, s2, n=N_GAMES):
    """Head-to-head win rate for s1 vs s2, alternating sides."""
    wins = 0
    total = 0
    for i in range(n // 2):
        r = run_game(s1, s2, seed=i, rng_seed=i * 1000)
        total += 1
        if r.winner == "p1":
            wins += 1
        r = run_game(s2, s1, seed=i, rng_seed=i * 1000 + 500)
        total += 1
        if r.winner == "p2":
            wins += 1
    return wins / total if total > 0 else 0.5


def _tier_vs_tier(higher_tier, lower_tier, n=N_GAMES):
    """Average win rate of higher_tier strategies vs lower_tier strategies."""
    total_wins = 0
    total_games = 0
    matchup_details = []
    for h in higher_tier:
        for low in lower_tier:
            rate = _h2h(h, low, n=n)
            total_wins += rate * n
            total_games += n
            matchup_details.append((h.name, low.name, rate))
    avg = total_wins / total_games if total_games > 0 else 0.5
    return avg, matchup_details


def _collect_games(strategies_a, strategies_b, n=N_GAMES) -> list[GameRecord]:
    """Collect game records from all matchups between two strategy sets."""
    records = []
    for a in strategies_a:
        for b in strategies_b:
            for i in range(n // 2):
                records.append(run_game(a, b, seed=i, rng_seed=i * 1000))
                records.append(run_game(b, a, seed=i, rng_seed=i * 1000 + 500))
    return records


# ===================================================================
# D1. PLANNING GRADIENT — Does Tier 2 beat Tier 1?
# ===================================================================


def score_planning_gradient() -> tuple[float, str]:
    """
    If memory and pattern recognition beat reactive heuristics,
    the game rewards planning. The gradient should be 55-65%.
    Below 50%: planning doesn't help (game too simple or too chaotic).
    Above 70%: planning is mandatory (game punishes reactivity too hard).
    """
    rate, details = _tier_vs_tier(TIER2_STRATEGIES, TIER1_REPRESENTATIVES)
    gap = rate - 0.50

    if gap < -0.05:
        score = max(0.0, 2.0 + gap * 20.0)  # tier 2 loses = bad
    elif gap < 0.0:
        score = 2.0 + (gap + 0.05) / 0.05 * 2.0  # slight loss, still ok
    elif gap < 0.05:
        score = 4.0 + gap / 0.05 * 2.0  # marginal gain
    elif gap < 0.15:
        score = 6.0 + (gap - 0.05) / 0.10 * 3.0  # good gain
    elif gap <= 0.25:
        score = 9.0 + (gap - 0.15) / 0.10 * 1.0  # strong gain
    else:
        score = 10.0 - (gap - 0.25) / 0.15 * 2.0  # too much = reactive is useless

    detail_str = ", ".join(f"{h}v{lo}={r:.0%}" for h, lo, r in details)
    detail = f"T2_vs_T1={rate:.1%}, gap={gap:+.1%} [{detail_str}]"
    return _clamp(score), detail


# ===================================================================
# D2. REASONING GRADIENT — Does Tier 3 beat Tier 2?
# ===================================================================


def score_reasoning_gradient() -> tuple[float, str]:
    """
    If Bayesian reasoning beats pattern matching, hidden information
    creates genuine depth that rewards understanding uncertainty.
    """
    rate, details = _tier_vs_tier(TIER3_STRATEGIES, TIER2_STRATEGIES)
    gap = rate - 0.50

    if gap < -0.05:
        score = max(0.0, 2.0 + gap * 20.0)
    elif gap < 0.0:
        score = 2.0 + (gap + 0.05) / 0.05 * 2.0
    elif gap < 0.05:
        score = 4.0 + gap / 0.05 * 2.0
    elif gap < 0.15:
        score = 6.0 + (gap - 0.05) / 0.10 * 3.0
    elif gap <= 0.25:
        score = 9.0 + (gap - 0.15) / 0.10 * 1.0
    else:
        score = 10.0 - (gap - 0.25) / 0.15 * 2.0

    detail_str = ", ".join(f"{h}v{lo}={r:.0%}" for h, lo, r in details)
    detail = f"T3_vs_T2={rate:.1%}, gap={gap:+.1%} [{detail_str}]"
    return _clamp(score), detail


# ===================================================================
# D3. COMPUTATION GRADIENT — Does Tier 4 beat Tier 3?
# ===================================================================


def score_computation_gradient() -> tuple[float, str]:
    """
    THE ANTI-CALCULABILITY TEST.

    If forward search dominates Bayesian reasoning (>65%), the game
    is calculable. Brute force beats understanding. AI will dominate.

    If search barely helps (50-55%), the game resists calculation.
    Understanding and reading opponents matters more than looking
    ahead. Humans can compete with AI.

    Sweet spot: 50-58%. Search helps slightly (it should, it's more
    information) but doesn't dominate.
    """
    rate, details = _tier_vs_tier(TIER4_STRATEGIES, TIER3_STRATEGIES, n=N_GAMES)
    gap = rate - 0.50

    # INVERTED SCORING: smaller gap is BETTER (anti-calculability)
    if gap > 0.20:
        score = max(0.0, 3.0 - (gap - 0.20) * 15.0)  # very calculable
    elif gap > 0.15:
        score = 3.0 + (0.20 - gap) / 0.05 * 1.0
    elif gap > 0.08:
        score = 4.0 + (0.15 - gap) / 0.07 * 3.0  # moderately calculable
    elif gap > 0.0:
        score = 7.0 + (0.08 - gap) / 0.08 * 2.0  # slightly calculable — good
    elif gap > -0.05:
        score = 9.0 + (-gap) / 0.05 * 1.0  # search doesn't help — great
    else:
        score = 9.0  # search actually hurts — also fine (overhead > benefit)

    detail_str = ", ".join(f"{h}v{lo}={r:.0%}" for h, lo, r in details)
    detail = f"T4_vs_T3={rate:.1%}, gap={gap:+.1%} [{detail_str}]"
    return _clamp(score), detail


# ===================================================================
# D4. NARRATIVE FROM DEPTH — Do smarter players produce better games?
# ===================================================================


def score_narrative_from_depth() -> tuple[float, str]:
    """
    Chess between grandmasters produces more interesting games than
    chess between beginners. If our game has depth, smarter players
    should produce:
    - Longer games (more story beats)
    - More lead changes (more drama)
    - More diverse outcomes (more story types)

    We compare Tier 1-vs-Tier 1 games to Tier 3-vs-Tier 3 games.
    """
    # Collect games at different skill levels
    t1_games = _collect_games(TIER1_REPRESENTATIVES, TIER1_REPRESENTATIVES, n=20)
    t3_games = _collect_games(TIER3_STRATEGIES + TIER2_STRATEGIES, TIER3_STRATEGIES + TIER2_STRATEGIES, n=20)

    def _avg_turns(games):
        return sum(r.turns for r in games) / max(len(games), 1)

    def _avg_lead_changes(games):
        total = 0
        count = 0
        for r in games:
            series = _advantage_series(r)
            if len(series) < 2:
                continue
            changes = 0
            for i in range(1, len(series)):
                if series[i - 1] != 0 and series[i] != 0 and (series[i - 1] > 0) != (series[i] > 0):
                    changes += 1
            total += changes
            count += 1
        return total / max(count, 1)

    def _story_entropy(games):
        archetypes = [_classify_game(r) for r in games]
        counts = Counter(archetypes)
        total = len(archetypes)
        entropy = 0.0
        for c in counts.values():
            if c > 0:
                p = c / total
                entropy -= p * math.log2(p)
        return entropy

    t1_turns = _avg_turns(t1_games)
    t3_turns = _avg_turns(t3_games)
    t1_lc = _avg_lead_changes(t1_games)
    t3_lc = _avg_lead_changes(t3_games)
    t1_entropy = _story_entropy(t1_games)
    t3_entropy = _story_entropy(t3_games)

    # Score: do higher-tier games have more narrative?
    turn_improvement = t3_turns - t1_turns
    lc_improvement = t3_lc - t1_lc
    entropy_improvement = t3_entropy - t1_entropy

    # Each improvement scores 0-10, combined
    turn_score = _clamp(5.0 + turn_improvement * 1.0, 0, 10)  # +1 turn = +1 point
    lc_score = _clamp(5.0 + lc_improvement * 5.0, 0, 10)  # +0.2 lead changes = +1 point
    ent_score = _clamp(5.0 + entropy_improvement * 5.0, 0, 10)  # +0.2 bits = +1 point

    score = turn_score * 0.4 + lc_score * 0.3 + ent_score * 0.3

    detail = (
        f"T1_turns={t1_turns:.1f} T3_turns={t3_turns:.1f} (+{turn_improvement:.1f}), "
        f"T1_lc={t1_lc:.2f} T3_lc={t3_lc:.2f} (+{lc_improvement:.2f}), "
        f"T1_entropy={t1_entropy:.2f} T3_entropy={t3_entropy:.2f} (+{entropy_improvement:.2f})"
    )
    return _clamp(score), detail


# ===================================================================
# D5. DEPTH UNLOCKS MECHANICS — Do advanced strategies use more?
# ===================================================================


def score_depth_unlocks_mechanics() -> tuple[float, str]:
    """
    In chess, grandmasters use sacrifices, positional play, and endgame
    technique that beginners never touch. If our game has depth, advanced
    strategies should USE MECHANICS that Tier 1 ignores.

    Measures: Do Tier 2-4 strategies produce different order distributions
    than Tier 1? Do they use supply cutting, ambush, non-standard deployment?
    """
    t1_games = _collect_games(TIER1_REPRESENTATIVES, TIER1_REPRESENTATIVES, n=20)
    adv_games = _collect_games(TIER2_STRATEGIES + TIER3_STRATEGIES, TIER2_STRATEGIES + TIER3_STRATEGIES, n=20)

    def _order_profile(games):
        totals = Counter()
        for r in games:
            totals["scout"] += r.scouts_used
            totals["fortify"] += r.fortifies_used
            totals["ambush"] += r.ambushes_used
            totals["charge"] += r.charges_used
            totals["move"] += r.moves_used
        return totals

    t1_profile = _order_profile(t1_games)
    adv_profile = _order_profile(adv_games)

    # Normalize to distributions
    t1_total = sum(t1_profile.values()) or 1
    adv_total = sum(adv_profile.values()) or 1

    order_types = ["scout", "fortify", "ambush", "charge", "move"]

    # Measure divergence
    t1_dist = {ot: (t1_profile[ot] + 0.1) / (t1_total + 0.5) for ot in order_types}
    adv_dist = {ot: (adv_profile[ot] + 0.1) / (adv_total + 0.5) for ot in order_types}

    # Jensen-Shannon divergence
    kl_fwd = sum(t1_dist[ot] * math.log(t1_dist[ot] / adv_dist[ot]) for ot in order_types)
    kl_rev = sum(adv_dist[ot] * math.log(adv_dist[ot] / t1_dist[ot]) for ot in order_types)
    js_div = (kl_fwd + kl_rev) / 2.0

    # Also check: do advanced players cut supply more?
    t1_supply_cut = sum(r.supply_cut_forces for r in t1_games) / max(len(t1_games), 1)
    adv_supply_cut = sum(r.supply_cut_forces for r in adv_games) / max(len(adv_games), 1)

    # Score
    div_score = _clamp(js_div / 0.05 * 5.0, 0, 10)  # 0.1 div = 10/10
    supply_diff = adv_supply_cut - t1_supply_cut
    supply_score = _clamp(5.0 + supply_diff * 2.0, 0, 10)

    score = div_score * 0.7 + supply_score * 0.3

    t1_str = " ".join(f"{ot}={t1_profile[ot]}" for ot in order_types)
    adv_str = " ".join(f"{ot}={adv_profile[ot]}" for ot in order_types)
    detail = (
        f"JS_div={js_div:.3f}, T1_supply_cut={t1_supply_cut:.1f}/game "
        f"adv_supply_cut={adv_supply_cut:.1f}/game, "
        f"T1=[{t1_str}], Adv=[{adv_str}]"
    )
    return _clamp(score), detail


# ===================================================================
# D6. GRADIENT SHAPE — Does the improvement flatten with sophistication?
# ===================================================================


def score_gradient_shape() -> tuple[float, str]:
    """
    The ideal depth gradient flattens: each tier helps, but by less.

        Tier 1 → 2: big jump    (planning matters)
        Tier 2 → 3: medium jump (reasoning matters)
        Tier 3 → 4: small jump  (calculation has diminishing returns)

    This shape means human skills (reading, understanding, creativity)
    outweigh raw computation. It's what makes a game "for humans, not AIs."

    We measure the three gradients and check the shape.
    """
    # Compute all three tier-vs-tier rates
    t2_vs_t1, _ = _tier_vs_tier(TIER2_STRATEGIES, TIER1_REPRESENTATIVES, n=N_GAMES)
    t3_vs_t2, _ = _tier_vs_tier(TIER3_STRATEGIES, TIER2_STRATEGIES, n=N_GAMES)
    t4_vs_t3, _ = _tier_vs_tier(TIER4_STRATEGIES, TIER3_STRATEGIES, n=N_GAMES)

    gap1 = t2_vs_t1 - 0.50
    gap2 = t3_vs_t2 - 0.50
    gap3 = t4_vs_t3 - 0.50

    # Check shape: ideal is gap1 > gap2 > gap3 > 0 (diminishing returns)
    score = 5.0  # base

    # Each tier should beat the previous (all gaps positive)
    if gap1 > 0:
        score += 1.0
    if gap2 > 0:
        score += 1.0
    if gap3 >= 0:
        score += 0.5

    # Gaps should diminish
    if gap1 > gap2:
        score += 1.5  # planning > reasoning (good)
    if gap2 > gap3:
        score += 1.5  # reasoning > computation (great — anti-calculable)

    # Computation gap should be small
    if abs(gap3) < 0.08:
        score += 1.0  # search barely helps

    # Penalty: if computation dominates
    if gap3 > 0.15:
        score -= 3.0  # very calculable

    detail = (
        f"T2vT1={t2_vs_t1:.1%} (gap={gap1:+.1%}), "
        f"T3vT2={t3_vs_t2:.1%} (gap={gap2:+.1%}), "
        f"T4vT3={t4_vs_t3:.1%} (gap={gap3:+.1%}), "
        f"shape={'diminishing' if gap1 > gap2 > gap3 else 'NOT diminishing'}"
    )
    return _clamp(score), detail


# ===================================================================
# COMBINED SCORING
# ===================================================================


def compute_depth_scores(verbose=True):
    """Run all depth measurements and compute the Game Depth Score."""
    dims = [
        ("D1. Planning Gradient", score_planning_gradient),
        ("D2. Reasoning Gradient", score_reasoning_gradient),
        ("D3. Computation Gradient", score_computation_gradient),
        ("D4. Narrative from Depth", score_narrative_from_depth),
        ("D5. Depth Unlocks Mechanics", score_depth_unlocks_mechanics),
        ("D6. Gradient Shape", score_gradient_shape),
    ]

    scores = {}
    details = {}

    for name, scorer in dims:
        s, d = scorer()
        scores[name] = s
        details[name] = d

    overall = sum(scores.values()) / len(scores)

    if verbose:
        print("\n" + "=" * 70)
        print("GAME DEPTH SCORE — THE STRATEGY LADDER")
        print("=" * 70)

        for name, _ in dims:
            bar = "#" * int(scores[name]) + "." * (10 - int(scores[name]))
            print(f"\n  {name}")
            print(f"    [{bar}] {scores[name]:.1f}/10")
            print(f"    {details[name]}")

        print(f"\n{'=' * 70}")
        print(f"  OVERALL DEPTH SCORE: {overall:.1f}/10")
        print(f"{'=' * 70}")

        # The combined picture
        print("\n  THE THREE SCORES TOGETHER:")
        print("    Fun Score:       (run test_fun_score.py for current)")
        print("    Narrative Score: (run test_narrative_score.py for current)")
        print(f"    Depth Score:     {overall:.1f}/10")
        print()
        print("  For 'Chess for the AI Age' all three must be 7.5+:")
        print("    Fun ≥ 7.5       → The game is well-designed")
        print("    Narrative ≥ 7.5 → Every game tells a unique story")
        print("    Depth ≥ 7.5     → Smarter play finds deeper strategies")

    return scores, overall


# ===================================================================
# PYTEST ENTRY POINTS
# ===================================================================


def test_depth_score():
    """Compute and display the depth score. Informational."""
    _scores, overall = compute_depth_scores(verbose=True)
    assert overall >= 0, "Depth score computation failed"


def test_each_tier_can_win():
    """Every tier must be able to win games. Basic sanity."""
    for tier_name, strats in [("Tier2", TIER2_STRATEGIES), ("Tier3", TIER3_STRATEGIES), ("Tier4", TIER4_STRATEGIES)]:
        for s in strats:
            wins = 0
            for i in range(10):
                r = run_game(s, AggressiveStrategy(), seed=i, rng_seed=i)
                if r.winner == "p1":
                    wins += 1
                r = run_game(AggressiveStrategy(), s, seed=i, rng_seed=i + 100)
                if r.winner == "p2":
                    wins += 1
            assert wins > 0, f"{tier_name}/{s.name} never won in 20 games"


if __name__ == "__main__":
    compute_depth_scores()
