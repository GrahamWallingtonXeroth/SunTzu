"""
Fun Score: Measuring game quality mathematically.

Each of the 9 dimensions scores 0-10, representing a specific aspect of
game quality derived from a critical analysis of the game's weaknesses.
The overall score is the average.

Dimensions:
1. DECISION DENSITY — How many meaningful choices per turn?
2. DEPLOYMENT IMPACT — Does the one-time power assignment matter?
3. COMBAT SKILL — Does the better player win fights, or is it dice?
4. INFORMATION DEPTH — How long does meaningful uncertainty last?
5. ORGANIC ENDINGS — Do games end from player action, not the timer?
6. METAGAME RICHNESS — Are the strategic interactions deep?
7. SPATIAL FREEDOM — Is there room to maneuver?
8. ROLE EMERGENCE — Do different power levels play differently?
9. SUPPLY RELEVANCE — Does the supply mechanic actually matter?

The goal: iterate on game design until every dimension scores well.
When a dimension scores low, fix the GAME, not the metric.
"""

import itertools
import math
import random
from collections import Counter, defaultdict

from tests.simulate import (
    ALL_STRATEGIES,
    AggressiveStrategy,
    CautiousStrategy,
    GameRecord,
    run_game,
    run_tournament,
)

# ---------------------------------------------------------------------------
# Shared tournament data (computed once)
# ---------------------------------------------------------------------------

GAMES_PER_MATCHUP = 40
MAP_SEEDS = list(range(GAMES_PER_MATCHUP))
COMPETITIVE_NAMES = {s.name for s in ALL_STRATEGIES if s.name not in ("turtle", "random")}


def _run_competitive_tournament():
    """Run tournament and return competitive-only records."""
    all_records = run_tournament(ALL_STRATEGIES, games_per_matchup=GAMES_PER_MATCHUP, map_seeds=MAP_SEEDS)
    competitive = [r for r in all_records if r.p1_strategy in COMPETITIVE_NAMES and r.p2_strategy in COMPETITIVE_NAMES]
    return all_records, competitive


def _clamp(val, lo=0.0, hi=10.0):
    return max(lo, min(hi, val))


# ---------------------------------------------------------------------------
# 1. DECISION DENSITY
# ---------------------------------------------------------------------------


def score_decision_density(records: list[GameRecord]) -> tuple[float, str]:
    """
    How many meaningful choices does a player face per turn?

    Measures:
    - What fraction of force-turns involve a special order (not just Move)?
    - How diverse are the special orders used? (entropy)

    A game where everyone just walks is boring. A game where every force
    does something interesting every turn has high decision density.
    """
    total_specials = 0
    total_moves = 0
    order_counts = Counter()

    for r in records:
        total_specials += r.scouts_used + r.fortifies_used + r.ambushes_used + r.charges_used
        total_moves += r.moves_used
        order_counts["scout"] += r.scouts_used
        order_counts["fortify"] += r.fortifies_used
        order_counts["ambush"] += r.ambushes_used
        order_counts["charge"] += r.charges_used

    total_orders = total_specials + total_moves
    if total_orders == 0:
        return 0.0, "No orders issued"

    # Sub-score A: Special order rate (what fraction of orders are special?)
    # Target: 30-50% special. Below 15% = boring. Above 70% = no constraint.
    special_rate = total_specials / total_orders
    if special_rate < 0.05:
        rate_score = 0.0
    elif special_rate < 0.30:
        rate_score = (special_rate - 0.05) / 0.25 * 7.0  # 0-7 for 5%-30%
    elif special_rate <= 0.50:
        rate_score = 7.0 + (special_rate - 0.30) / 0.20 * 3.0  # 7-10 for 30%-50%
    else:
        rate_score = 10.0 - (special_rate - 0.50) / 0.30 * 5.0  # drops above 50%

    # Sub-score B: Order diversity (Shannon entropy of special order distribution)
    total_sp = sum(order_counts.values())
    if total_sp > 0:
        probs = [order_counts[k] / total_sp for k in ["scout", "fortify", "ambush", "charge"] if order_counts[k] > 0]
        entropy = -sum(p * math.log2(p) for p in probs)
        max_entropy = math.log2(4)  # 4 special types
        diversity_score = (entropy / max_entropy) * 10.0
    else:
        diversity_score = 0.0

    score = (rate_score + diversity_score) / 2.0
    detail = (
        f"special_rate={special_rate:.1%}, entropy={entropy:.2f}/{max_entropy:.2f}, "
        f"scout={order_counts['scout']}, fort={order_counts['fortify']}, "
        f"ambush={order_counts['ambush']}, charge={order_counts['charge']}"
    )
    return _clamp(score), detail


# ---------------------------------------------------------------------------
# 2. DEPLOYMENT IMPACT
# ---------------------------------------------------------------------------


def score_deployment_impact(competitive_records: list[GameRecord]) -> tuple[float, str]:
    """
    Does the one-time power assignment actually matter?

    Test: run the same strategies against each other with randomized
    deployments. If different deployments produce different winners,
    deployment matters.
    """

    class RandomDeploy(AggressiveStrategy):
        name = "agg_rand"

        def __init__(self, seed):
            self._rng = random.Random(seed)

        def deploy(self, player, rng):
            powers = [1, 2, 3, 4, 5]
            self._rng.shuffle(powers)
            return {f.id: p for f, p in zip(player.forces, powers, strict=False)}

    # Run 60 games: same map, different deployments
    winners = []
    for i in range(60):
        r = run_game(RandomDeploy(i), RandomDeploy(i + 1000), seed=42, rng_seed=i)
        winners.append(r.winner)

    p1_wins = winners.count("p1")
    p2_wins = winners.count("p2")
    draws = winners.count(None)
    total_decided = p1_wins + p2_wins

    if total_decided == 0:
        return 0.0, "All draws — deployment irrelevant"

    # Deployment matters if neither side dominates (both win ~30-70%)
    balance = min(p1_wins, p2_wins) / total_decided if total_decided > 0 else 0
    # Perfect balance = 0.5, terrible = 0.0
    # Also check that SOME games flip: if one side always wins, deployment doesn't matter
    flip_rate = balance * 2  # 0 = one side always wins, 1 = perfectly balanced

    # Also measure: do sovereign-front vs sovereign-back produce different results?
    class SovFront(AggressiveStrategy):
        name = "sov_front"

        def deploy(self, player, rng):
            return dict(zip([f.id for f in player.forces], [1, 5, 4, 3, 2], strict=False))

    class SovBack(AggressiveStrategy):
        name = "sov_back"

        def deploy(self, player, rng):
            return dict(zip([f.id for f in player.forces], [5, 4, 3, 2, 1], strict=False))

    sov_results = []
    for i in range(30):
        r1 = run_game(SovFront(), CautiousStrategy(), seed=i, rng_seed=i)
        r2 = run_game(SovBack(), CautiousStrategy(), seed=i, rng_seed=i)
        sov_results.append(r1.winner != r2.winner)
    sov_flip_rate = sum(sov_results) / len(sov_results)

    score = flip_rate * 6.0 + sov_flip_rate * 4.0
    detail = f"deploy_flip={flip_rate:.1%}, sov_flip={sov_flip_rate:.1%}, p1={p1_wins}/p2={p2_wins}/draw={draws}"
    return _clamp(score), detail


# ---------------------------------------------------------------------------
# 3. COMBAT SKILL
# ---------------------------------------------------------------------------


def score_combat_skill(records: list[GameRecord]) -> tuple[float, str]:
    """
    Does the better-prepared side win fights, or is combat pure dice?

    Measures:
    - How often does higher base power win?
    - How often do bonuses (fortify/charge/ambush) swing the outcome?
    - What's the variance dominance ratio?

    Combat should reward preparation (bonuses) and power advantage,
    not just lucky dice rolls.
    """
    all_combats = []
    for r in records:
        all_combats.extend(r.combat_details)

    if not all_combats:
        return 0.0, "No combats"

    # Sub-score A: Higher base power win rate
    higher_wins = 0
    lower_wins = 0
    ties_base = 0
    for c in all_combats:
        ab = c.get("attacker_base", 0)
        db = c.get("defender_base", 0)
        outcome = c.get("outcome", "")
        att_won = "attacker_wins" in outcome
        def_won = "defender_wins" in outcome
        if ab > db:
            if att_won:
                higher_wins += 1
            elif def_won:
                lower_wins += 1
        elif db > ab:
            if def_won:
                higher_wins += 1
            elif att_won:
                lower_wins += 1
        else:
            ties_base += 1

    decided = higher_wins + lower_wins
    if decided > 0:
        higher_rate = higher_wins / decided
    else:
        higher_rate = 0.5

    # Target: 60-80% higher wins. Below 55% = dice game. Above 90% = too deterministic.
    if higher_rate < 0.50:
        power_score = 0.0
    elif higher_rate < 0.60:
        power_score = (higher_rate - 0.50) / 0.10 * 4.0
    elif higher_rate <= 0.80:
        power_score = 4.0 + (higher_rate - 0.60) / 0.20 * 6.0
    else:
        power_score = 10.0 - (higher_rate - 0.80) / 0.20 * 5.0

    # Sub-score B: Bonus effectiveness — compare effective vs base power gaps
    bonus_swings = 0
    for c in all_combats:
        ab = c.get("attacker_base", 0)
        db = c.get("defender_base", 0)
        ae = c.get("attacker_eff", 0)
        de = c.get("defender_eff", 0)
        # Did bonuses change who had the advantage?
        base_advantage = ab - db  # positive = attacker favored
        eff_advantage = ae - de
        if (base_advantage > 0 and eff_advantage < 0) or (base_advantage < 0 and eff_advantage > 0):
            bonus_swings += 1
    swing_rate = bonus_swings / len(all_combats) if all_combats else 0
    # Target: 15-35% swing rate. Bonuses should matter but not dominate.
    if swing_rate < 0.05:
        bonus_score = swing_rate / 0.05 * 3.0
    elif swing_rate <= 0.35:
        bonus_score = 3.0 + (swing_rate - 0.05) / 0.30 * 7.0
    else:
        bonus_score = 10.0 - (swing_rate - 0.35) / 0.30 * 5.0

    score = power_score * 0.6 + bonus_score * 0.4
    detail = (
        f"higher_base_wins={higher_rate:.1%} ({higher_wins}/{decided}), "
        f"bonus_swings={swing_rate:.1%} ({bonus_swings}/{len(all_combats)}), "
        f"stalemates_base_equal={ties_base}"
    )
    return _clamp(score), detail


# ---------------------------------------------------------------------------
# 4. INFORMATION DEPTH
# ---------------------------------------------------------------------------


def score_information_depth(records: list[GameRecord]) -> tuple[float, str]:
    """
    How long does meaningful uncertainty last?

    Measures:
    - Average turn when sovereign is first revealed
    - Fraction of games where sovereign stays hidden past midgame
    - Whether information advantage correlates with winning

    A game where everything is known by turn 3 has no information game.
    """
    reveal_turns = []
    games_with_late_reveal = 0  # sovereign hidden past turn 6
    games_with_never_reveal = 0  # sovereign never found (game ends first)

    for r in records:
        if r.turns == 0:
            continue
        # Check both players' sovereign reveals
        for pid in ["p1", "p2"]:
            if pid in r.sovereign_revealed_turn:
                turn = r.sovereign_revealed_turn[pid]
                reveal_turns.append(turn)
                if turn > 6:
                    games_with_late_reveal += 1
            else:
                games_with_never_reveal += 1

    total_sovereign_instances = len(records) * 2  # 2 sovereigns per game
    if not reveal_turns and total_sovereign_instances == 0:
        return 0.0, "No data"

    # Sub-score A: Average reveal turn (later = more mystery)
    avg_reveal = sum(reveal_turns) / len(reveal_turns) if reveal_turns else 0
    # Target: reveal around turn 5-8 (mid-game). Before turn 3 = too easy.
    if avg_reveal < 2:
        timing_score = avg_reveal / 2 * 3.0
    elif avg_reveal <= 8:
        timing_score = 3.0 + (avg_reveal - 2) / 6 * 7.0
    else:
        timing_score = 10.0  # Late reveals are always good

    # Sub-score B: Late reveal rate (sovereigns hidden past midgame)
    late_rate = (
        (games_with_late_reveal + games_with_never_reveal) / total_sovereign_instances
        if total_sovereign_instances > 0
        else 0
    )
    # Target: 30-60% of sovereigns stay hidden past midgame
    late_score = min(late_rate / 0.50 * 10.0, 10.0)

    score = timing_score * 0.6 + late_score * 0.4
    detail = (
        f"avg_reveal_turn={avg_reveal:.1f}, late_reveals={games_with_late_reveal}, "
        f"never_revealed={games_with_never_reveal}, total_instances={total_sovereign_instances}"
    )
    return _clamp(score), detail


# ---------------------------------------------------------------------------
# 5. ORGANIC ENDINGS
# ---------------------------------------------------------------------------


def score_organic_endings(all_records: list[GameRecord]) -> tuple[float, str]:
    """
    Do games end because of player action, or because the timer ran out?

    The Noose (shrinking board) should create urgency, not decide games.
    Games should end from sovereign capture, domination, or elimination —
    not from forces being scorched.
    """
    competitive = [r for r in all_records if r.p1_strategy in COMPETITIVE_NAMES and r.p2_strategy in COMPETITIVE_NAMES]
    if not competitive:
        return 0.0, "No competitive games"

    total = len(competitive)
    noose_decided = sum(1 for r in competitive if r.sovereign_killed_by_noose)
    timeouts = sum(1 for r in competitive if r.victory_type == "timeout")
    player_decided = total - noose_decided - timeouts

    # Sub-score A: Player-decided rate
    player_rate = player_decided / total
    # Target: >85% player-decided. <60% = Noose dominates.
    player_score = min(player_rate / 0.85 * 10.0, 10.0)

    # Sub-score B: Noose as pressure vs decision-maker
    # Noose should KILL forces (pressure) but not kill SOVEREIGNS (deciding games)
    games_with_noose_kills = sum(1 for r in competitive if r.noose_kills > 0)
    noose_pressure_rate = games_with_noose_kills / total
    # Good: Noose kills forces in 20-40% of games (pressure) but decides <10% (not dominant)
    noose_decide_rate = noose_decided / total
    pressure_not_deciding = noose_pressure_rate - noose_decide_rate
    pressure_score = min(pressure_not_deciding / 0.20 * 10.0, 10.0) if pressure_not_deciding > 0 else 0.0

    score = player_score * 0.7 + pressure_score * 0.3
    detail = (
        f"player_decided={player_rate:.1%}, noose_decided={noose_decide_rate:.1%}, "
        f"noose_pressure={noose_pressure_rate:.1%}, timeouts={timeouts}"
    )
    return _clamp(score), detail


# ---------------------------------------------------------------------------
# 6. METAGAME RICHNESS
# ---------------------------------------------------------------------------


def score_metagame_richness(all_records: list[GameRecord]) -> tuple[float, str]:
    """
    Are the strategic interactions deep?

    Measures:
    - Number of intransitive cycles (A>B>C>A)
    - Replicator dynamics diversity (how many strategies survive?)
    - Payoff matrix variance (are matchups different or all 50/50?)
    """
    competitive = [r for r in all_records if r.p1_strategy in COMPETITIVE_NAMES and r.p2_strategy in COMPETITIVE_NAMES]
    names = sorted(COMPETITIVE_NAMES)
    n = len(names)
    idx = {name: i for i, name in enumerate(names)}

    # Build payoff matrix
    wins = [[0] * n for _ in range(n)]
    games = [[0] * n for _ in range(n)]
    for r in competitive:
        i, j = idx.get(r.p1_strategy), idx.get(r.p2_strategy)
        if i is None or j is None:
            continue
        games[i][j] += 1
        games[j][i] += 1
        if r.winner == "p1":
            wins[i][j] += 1
        elif r.winner == "p2":
            wins[j][i] += 1

    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i][j] = 0.5
            elif games[i][j] > 0:
                matrix[i][j] = wins[i][j] / games[i][j]

    # Sub-score A: Intransitive cycles (A>B>C>A at >55%)
    beats = {i: set() for i in range(n)}
    for i in range(n):
        for j in range(n):
            if i != j and matrix[i][j] > 0.55:
                beats[i].add(j)
    cycle_count = 0
    for a in range(n):
        for b in beats[a]:
            for c in beats[b]:
                if a in beats[c]:
                    cycle_count += 1
    # Each cycle counted 3 times (a->b->c->a, b->c->a->b, c->a->b->c)
    unique_cycles = cycle_count // 3
    cycle_score = min(unique_cycles / 3 * 10.0, 10.0)  # 3+ cycles = perfect

    # Sub-score B: Replicator dynamics survivors
    freqs = [1.0 / n] * n
    for _ in range(2000):
        fitness = [sum(matrix[i][j] * freqs[j] for j in range(n)) for i in range(n)]
        avg_fitness = sum(fitness[i] * freqs[i] for i in range(n))
        new_freqs = [max(0.0, freqs[i] + 0.05 * freqs[i] * (fitness[i] - avg_fitness)) for i in range(n)]
        total = sum(new_freqs)
        freqs = [f / total for f in new_freqs] if total > 0 else new_freqs
    survivors = sum(1 for f in freqs if f > 0.01)
    # Target: 4+ survivors out of 7 competitive strategies
    survivor_score = min(survivors / 4 * 10.0, 10.0)

    # Sub-score C: Payoff variance (matchups should be different, not all 50/50)
    rates = [matrix[i][j] for i in range(n) for j in range(n) if i != j]
    if rates:
        mean = sum(rates) / len(rates)
        var = sum((x - mean) ** 2 for x in rates) / len(rates)
        std = var**0.5
        # Target: std > 0.10 (diverse matchups)
        variance_score = min(std / 0.12 * 10.0, 10.0)
    else:
        variance_score = 0.0

    score = cycle_score * 0.4 + survivor_score * 0.3 + variance_score * 0.3
    survivor_names = [(names[i], f"{freqs[i]:.1%}") for i in range(n) if freqs[i] > 0.01]
    detail = f"cycles={unique_cycles}, survivors={survivors} {survivor_names}, payoff_std={std:.3f}"
    return _clamp(score), detail


# ---------------------------------------------------------------------------
# 7. SPATIAL FREEDOM
# ---------------------------------------------------------------------------


def score_spatial_freedom(records: list[GameRecord]) -> tuple[float, str]:
    """
    Is there room to maneuver, or do forces collide immediately?

    Measures:
    - How many unique hexes are used across the game?
    - How many turns of maneuver before first combat?
    - Average game length (proxy for positional play duration)
    """
    board_hexes = 49  # 7x7

    # Sub-score A: Board utilization
    total_unique = sum(r.unique_positions for r in records)
    avg_unique = total_unique / len(records) if records else 0
    # Target: 25-35 hexes used per game (50-70% of board)
    utilization = avg_unique / board_hexes
    if utilization < 0.20:
        util_score = utilization / 0.20 * 3.0
    elif utilization <= 0.70:
        util_score = 3.0 + (utilization - 0.20) / 0.50 * 7.0
    else:
        util_score = 10.0

    # Sub-score B: Maneuver turns before first contact
    maneuver_turns = [r.first_combat_turn for r in records if r.first_combat_turn > 0]
    avg_maneuver = sum(maneuver_turns) / len(maneuver_turns) if maneuver_turns else 0
    # Target: 3-5 turns of setup before first fight
    if avg_maneuver < 1:
        maneuver_score = 0.0
    elif avg_maneuver < 3:
        maneuver_score = (avg_maneuver - 1) / 2 * 5.0
    elif avg_maneuver <= 6:
        maneuver_score = 5.0 + (avg_maneuver - 3) / 3 * 5.0
    else:
        maneuver_score = 10.0 - (avg_maneuver - 6) / 4 * 5.0  # Too long = cold war

    # Sub-score C: Game length spread (variety in game arcs)
    turns = [r.turns for r in records if r.turns > 0]
    if turns:
        avg_len = sum(turns) / len(turns)
        std_len = (sum((t - avg_len) ** 2 for t in turns) / len(turns)) ** 0.5
        # Target: std of 3-6 turns (diverse game lengths)
        spread_score = min(std_len / 5 * 10.0, 10.0)
    else:
        spread_score = 0.0

    score = util_score * 0.4 + maneuver_score * 0.4 + spread_score * 0.2
    detail = (
        f"avg_hexes={avg_unique:.0f}/{board_hexes} ({utilization:.0%}), "
        f"avg_maneuver={avg_maneuver:.1f} turns, game_len_std={std_len:.1f}"
    )
    return _clamp(score), detail


# ---------------------------------------------------------------------------
# 8. ROLE EMERGENCE
# ---------------------------------------------------------------------------


def score_role_emergence(records: list[GameRecord]) -> tuple[float, str]:
    """
    Do different power levels play differently?

    Even though all forces have the same abilities, different power levels
    should develop emergent roles: power-5 as shock troops, power-1 as
    protected VIP, power-2/3 as scouts/support.
    """
    # Aggregate per-power order distributions
    power_orders = defaultdict(Counter)
    for r in records:
        for pw, orders in r.per_power_orders.items():
            for order_type, count in orders.items():
                power_orders[pw][order_type] += count

    if not power_orders:
        return 0.0, "No per-power data"

    # Compute normalized distributions per power level
    distributions = {}
    order_types = ["move", "scout", "fortify", "ambush", "charge"]
    for pw in sorted(power_orders.keys()):
        total = sum(power_orders[pw].values())
        if total > 0:
            distributions[pw] = {ot: power_orders[pw].get(ot, 0) / total for ot in order_types}

    if len(distributions) < 3:
        return 0.0, "Too few power levels observed"

    # Sub-score A: Behavioral differentiation (KL divergence between power levels)
    # Compare each pair of power levels
    divergences = []
    for p1, p2 in itertools.combinations(sorted(distributions.keys()), 2):
        kl = 0
        for ot in order_types:
            q = distributions[p1].get(ot, 0.001)
            p = distributions[p2].get(ot, 0.001)
            # Symmetrized KL
            if q > 0 and p > 0:
                kl += 0.5 * (p * math.log(p / q) + q * math.log(q / p))
        divergences.append(kl)

    avg_divergence = sum(divergences) / len(divergences) if divergences else 0
    # Target: avg divergence > 0.15 (meaningful behavioral differences)
    div_score = min(avg_divergence / 0.20 * 10.0, 10.0)

    # Sub-score B: Sovereign plays differently (power-1 should fortify/flee more, charge less)
    sov_dist = distributions.get(1, {})
    avg_dist = {
        ot: sum(distributions[pw].get(ot, 0) for pw in distributions) / len(distributions) for ot in order_types
    }
    sov_diff = sum(abs(sov_dist.get(ot, 0) - avg_dist.get(ot, 0)) for ot in order_types) / 2
    # Target: sovereign behaves 30%+ differently from average
    sov_score = min(sov_diff / 0.30 * 10.0, 10.0)

    # Sub-score C: Strong forces attack more (power-4/5 should charge more)
    strong_charge = sum(distributions.get(pw, {}).get("charge", 0) for pw in [4, 5]) / 2
    weak_charge = sum(distributions.get(pw, {}).get("charge", 0) for pw in [2, 3]) / 2
    charge_diff = strong_charge - weak_charge
    # Target: power-4/5 charge 10%+ more than power-2/3
    charge_score = min(max(charge_diff / 0.10 * 10.0, 0), 10.0)

    score = div_score * 0.4 + sov_score * 0.3 + charge_score * 0.3
    dist_summary = {pw: {k: f"{v:.0%}" for k, v in d.items() if v > 0.01} for pw, d in sorted(distributions.items())}
    detail = f"avg_kl={avg_divergence:.3f}, sov_diff={sov_diff:.1%}, charge_gap={charge_diff:.1%}, dists={dist_summary}"
    return _clamp(score), detail


# ---------------------------------------------------------------------------
# 9. SUPPLY RELEVANCE
# ---------------------------------------------------------------------------


def score_supply_relevance(records: list[GameRecord]) -> tuple[float, str]:
    """
    Does the supply mechanic actually matter?

    Measures:
    - How often are forces cut off from supply?
    - Does supply loss correlate with losing?

    A supply mechanic that never activates is dead weight.
    """
    total_cut = sum(r.supply_cut_forces for r in records)
    total_ft = sum(r.total_force_turns for r in records)

    if total_ft == 0:
        return 0.0, "No data"

    cut_rate = total_cut / total_ft

    # Sub-score A: Supply cut frequency
    # Target: 5-20% of force-turns involve supply loss
    if cut_rate < 0.01:
        freq_score = cut_rate / 0.01 * 2.0
    elif cut_rate < 0.05:
        freq_score = 2.0 + (cut_rate - 0.01) / 0.04 * 3.0
    elif cut_rate <= 0.20:
        freq_score = 5.0 + (cut_rate - 0.05) / 0.15 * 5.0
    else:
        freq_score = 10.0 - (cut_rate - 0.20) / 0.30 * 5.0

    # Sub-score B: Supply loss correlates with losing (v8: uses per-player data)
    games_with_cuts = [r for r in records if r.supply_cut_forces > 0]
    if games_with_cuts:
        # Now using real per-player supply data instead of a proxy
        correlated = 0
        counted = 0
        for r in games_with_cuts:
            if r.winner and r.winner in ("p1", "p2"):
                loser = "p1" if r.winner == "p2" else "p2"
                loser_cuts = r.supply_cut_p1 if loser == "p1" else r.supply_cut_p2
                winner_cuts = r.supply_cut_p1 if r.winner == "p1" else r.supply_cut_p2
                counted += 1
                if loser_cuts > winner_cuts:
                    correlated += 1
        if counted > 0:
            correlation_rate = correlated / counted
            # Target: >50% means supply cuts genuinely predict losing
            impact_score = min(correlation_rate / 0.60 * 10.0, 10.0)
        else:
            impact_score = 5.0  # Neutral if no decided games with cuts
    else:
        impact_score = 0.0

    score = freq_score * 0.6 + impact_score * 0.4
    detail = (
        f"supply_cut_rate={cut_rate:.1%} ({total_cut}/{total_ft}), "
        f"games_with_cuts={len(games_with_cuts)}/{len(records)}"
    )
    return _clamp(score), detail


# ===========================================================================
# MAIN SCORING FUNCTION
# ===========================================================================


def compute_fun_scores(verbose=True):
    """Run tournament and compute all 9 fun scores."""
    all_records, competitive = _run_competitive_tournament()

    scores = {}
    details = {}

    dimensions = [
        ("1. Decision Density", lambda: score_decision_density(competitive)),
        ("2. Deployment Impact", lambda: score_deployment_impact(competitive)),
        ("3. Combat Skill", lambda: score_combat_skill(competitive)),
        ("4. Information Depth", lambda: score_information_depth(competitive)),
        ("5. Organic Endings", lambda: score_organic_endings(all_records)),
        ("6. Metagame Richness", lambda: score_metagame_richness(all_records)),
        ("7. Spatial Freedom", lambda: score_spatial_freedom(competitive)),
        ("8. Role Emergence", lambda: score_role_emergence(competitive)),
        ("9. Supply Relevance", lambda: score_supply_relevance(competitive)),
    ]

    for name, scorer in dimensions:
        s, d = scorer()
        scores[name] = s
        details[name] = d

    overall = sum(scores.values()) / len(scores)

    if verbose:
        print("\n" + "=" * 70)
        print("FUN SCORE REPORT")
        print("=" * 70)
        for name in scores:
            bar = "#" * int(scores[name]) + "." * (10 - int(scores[name]))
            print(f"\n  {name}")
            print(f"    Score: [{bar}] {scores[name]:.1f}/10")
            print(f"    {details[name]}")
        print(f"\n{'=' * 70}")
        print(f"  OVERALL FUN SCORE: {overall:.1f}/10")
        print(f"{'=' * 70}\n")

    return scores, overall


# ===========================================================================
# PYTEST ENTRY POINT
# ===========================================================================


def test_fun_score():
    """Compute and display the fun score. This test always passes — it's informational."""
    _scores, overall = compute_fun_scores(verbose=True)
    # Store for reference but don't assert — this is a measurement, not a gate
    assert overall >= 0, "Fun score computation failed"


def test_fun_score_minimum_dimensions():
    """Every fun dimension must score at least 3.0/10.
    Why: Below 3.0 means a mechanic is clearly broken. This is the safety net
    that gives the fun score real teeth without over-constraining the overall score.
    Addresses Goodhart problem #7: fun score with no enforcement."""
    scores, _ = compute_fun_scores(verbose=False)
    for name, score in scores.items():
        assert score >= 3.0, (
            f"Fun dimension '{name}' scored {score:.1f}/10 — below minimum of 3.0. This mechanic needs attention."
        )


def test_fun_score_overall_minimum():
    """Overall fun score must be at least 5.0/10.
    Why: An overall score below 5 means the game is failing at more dimensions
    than it's succeeding at. Addresses Goodhart problem #7."""
    _, overall = compute_fun_scores(verbose=False)
    assert overall >= 5.0, (
        f"Overall fun score is {overall:.1f}/10 — below minimum of 5.0. Multiple dimensions need improvement."
    )


if __name__ == "__main__":
    compute_fun_scores()
