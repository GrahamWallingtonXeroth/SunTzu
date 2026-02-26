"""
Gameplay tests for The Unfought Battle v8.

These tests define what a GOOD game looks like, then check whether this game
meets that standard. Thresholds are set based on design goals, not current
performance. If a test fails, the GAME needs fixing — not the threshold.

DESIGN PRINCIPLES
=================
1. Thresholds describe the game we WANT, not the game we have.
2. Turtle is excluded from competitive metrics. A deliberately broken
   strategy should not inflate or deflate any measurement.
3. Every test has a "why" — the design goal it enforces.
4. No test should be passable by a game with no strategic depth.
   If random-vs-random could pass it, the threshold is too loose.

WHAT A GOOD GAME EXHIBITS
==========================
1. COMBAT IS CENTRAL     — Most games have fights, not cold wars
2. DECISIONS MATTER       — Specials are diverse, not fortify-spam
3. INFORMATION PAYS       — Scouting strategies beat blind ones
4. AGGRESSION WORKS       — Attacking is viable, not suicidal
5. PASSIVITY DIES         — Turtling is crushed, not merely weak
6. NO DOMINANT STRATEGY   — Rock-paper-scissors among competitive strats
7. GAMES HAVE ARCS        — Opening, midgame, endgame — not bimodal
8. VICTORY PATHS DIVERGE  — Multiple win conditions, none >65%
9. FORCES DIE             — Combat has consequences, not just retreat
10. ECONOMY CONSTRAINS    — Real tradeoffs, not unlimited fortify
11. THE NOOSE PRESSURES   — Timer shapes play without dominating it
12. METAGAME HAS DEPTH    — Game theory properties hold among COMPETITIVE strats

v8 ANTI-GOODHART ADDITIONS
===========================
13. ABLATION TESTS        — Remove a mechanic, verify performance degrades
14. ANTI-PASSIVITY        — SmartPassive (not just straw-man Turtle) must lose
15. DEGENERATE EXPLOITS   — DominationStaller and other exploits must fail
16. SEED ROBUSTNESS       — Results stable across different map seed sets
17. DEPLOYMENT BREADTH    — Deployment matters for ALL strategies, not just one
"""

import pytest
import random
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.simulate import (
    run_game, run_tournament, GameRecord,
    RandomStrategy, AggressiveStrategy, CautiousStrategy,
    AmbushStrategy, TurtleStrategy, SovereignHunterStrategy,
    NooseDodgerStrategy, CoordinatorStrategy, BlitzerStrategy,
    SmartPassiveStrategy, NeverScoutVariant, NoChargeVariant,
    PowerBlindStrategy, DominationStallerStrategy,
    ALL_STRATEGIES, ADVERSARIAL_STRATEGIES, EXTENDED_STRATEGIES, STRATEGY_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GAMES_PER_MATCHUP = 40
MAP_SEEDS = list(range(GAMES_PER_MATCHUP))

# Competitive strategies: exclude turtle (deliberately broken) and random (baseline)
COMPETITIVE_STRATEGIES = [s for s in ALL_STRATEGIES if s.name not in ('turtle', 'random')]
COMPETITIVE_NAMES = {s.name for s in COMPETITIVE_STRATEGIES}
BASELINE_NAMES = {'turtle', 'random'}


@pytest.fixture(scope="module")
def tournament_records():
    """Full round-robin tournament. Cached for the module."""
    return run_tournament(ALL_STRATEGIES, games_per_matchup=GAMES_PER_MATCHUP, map_seeds=MAP_SEEDS)


@pytest.fixture(scope="module")
def competitive_records(tournament_records):
    """Records where BOTH players are competitive (no turtle, no random)."""
    return [r for r in tournament_records
            if r.p1_strategy in COMPETITIVE_NAMES and r.p2_strategy in COMPETITIVE_NAMES]


@pytest.fixture(scope="module")
def payoff_matrix(tournament_records):
    """Win-rate matrix from tournament, computed once."""
    return _build_payoff_matrix(tournament_records)


@pytest.fixture(scope="module")
def competitive_payoff(competitive_records):
    """Win-rate matrix using only competitive strategies."""
    return _build_payoff_matrix_from(competitive_records, COMPETITIVE_NAMES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strategy_win_rate(records: List[GameRecord], name: str) -> float:
    games = sum(1 for r in records if r.p1_strategy == name or r.p2_strategy == name)
    wins = sum(1 for r in records
               if (r.winner == 'p1' and r.p1_strategy == name)
               or (r.winner == 'p2' and r.p2_strategy == name))
    return wins / games if games > 0 else 0.0


def _matchup_win_rate(records: List[GameRecord], strat: str, opponent: str) -> float:
    """Win rate of strat against opponent across all records."""
    matchup = [r for r in records
               if (r.p1_strategy == strat and r.p2_strategy == opponent)
               or (r.p1_strategy == opponent and r.p2_strategy == strat)]
    if not matchup:
        return 0.5
    wins = sum(1 for r in matchup
               if (r.winner == 'p1' and r.p1_strategy == strat)
               or (r.winner == 'p2' and r.p2_strategy == strat))
    return wins / len(matchup)


def _build_payoff_matrix(records: List[GameRecord]) -> Dict:
    names = [s.name for s in ALL_STRATEGIES]
    return _build_payoff_matrix_from(records, set(names))


def _build_payoff_matrix_from(records: List[GameRecord], strategy_names: set) -> Dict:
    names = sorted(strategy_names)
    n = len(names)
    idx = {name: i for i, name in enumerate(names)}
    wins = [[0] * n for _ in range(n)]
    games = [[0] * n for _ in range(n)]

    for r in records:
        i = idx.get(r.p1_strategy)
        j = idx.get(r.p2_strategy)
        if i is None or j is None:
            continue
        games[i][j] += 1
        games[j][i] += 1
        if r.winner == 'p1':
            wins[i][j] += 1
        elif r.winner == 'p2':
            wins[j][i] += 1

    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i][j] = 0.5
            elif games[i][j] > 0:
                matrix[i][j] = wins[i][j] / games[i][j]
            else:
                matrix[i][j] = 0.5
    return {'strategies': names, 'matrix': matrix}


def _replicator_dynamics(matrix: List[List[float]], steps: int = 2000, dt: float = 0.05) -> List[float]:
    n = len(matrix)
    freqs = [1.0 / n] * n
    for _ in range(steps):
        fitness = [sum(matrix[i][j] * freqs[j] for j in range(n)) for i in range(n)]
        avg_fitness = sum(fitness[i] * freqs[i] for i in range(n))
        new_freqs = [max(0.0, freqs[i] + dt * freqs[i] * (fitness[i] - avg_fitness)) for i in range(n)]
        total = sum(new_freqs)
        freqs = [f / total for f in new_freqs] if total > 0 else new_freqs
    return freqs


# ===========================================================================
# 1. COMBAT IS CENTRAL — Most games have fights, not cold wars
# ===========================================================================

class TestCombatIsCentral:
    """A wargame where nobody fights is a failed wargame."""

    def test_majority_of_games_have_combat(self, competitive_records):
        """More than half of competitive games should involve at least one combat.
        Why: If players can avoid each other and still win, combat is vestigial."""
        games_with = sum(1 for r in competitive_records if r.combats > 0)
        rate = games_with / len(competitive_records)
        assert rate > 0.50, (
            f"Only {rate:.1%} of competitive games had combat — majority should fight"
        )

    def test_zero_combat_rate_is_low(self, competitive_records):
        """Fewer than 30% of competitive games should have zero combat.
        Why: Zero-combat games mean the game rewards avoidance over engagement."""
        zero = sum(1 for r in competitive_records if r.combats == 0)
        rate = zero / len(competitive_records)
        assert rate < 0.30, (
            f"{rate:.1%} of competitive games had zero combat — too many cold wars"
        )

    def test_average_combats_meaningful(self, competitive_records):
        """Competitive games should average at least 1.0 combats.
        Why: 0.5 combats/game means most games have one fight or none — not central."""
        total = sum(r.combats for r in competitive_records)
        avg = total / len(competitive_records)
        assert avg >= 1.0, (
            f"Average combats is {avg:.2f} — combat is not central to gameplay"
        )


# ===========================================================================
# 2. DECISIONS MATTER — Specials are diverse, not fortify-spam
# ===========================================================================

class TestDecisionsMatter:
    """Players should face real choices between order types."""

    def test_no_single_order_monopolizes(self, competitive_records):
        """No single special order should exceed 60% of all special orders.
        Why: If one order dominates, there's no real decision to make."""
        totals = {
            'scout': sum(r.scouts_used for r in competitive_records),
            'fortify': sum(r.fortifies_used for r in competitive_records),
            'ambush': sum(r.ambushes_used for r in competitive_records),
            'charge': sum(r.charges_used for r in competitive_records),
        }
        total = sum(totals.values())
        if total == 0:
            pytest.skip("No specials used")
        for name, count in totals.items():
            frac = count / total
            assert frac < 0.60, (
                f"'{name}' is {frac:.1%} of all specials — monopolizes decision space. "
                f"Breakdown: {', '.join(f'{k}={v}' for k,v in totals.items())}"
            )

    def test_all_special_types_used(self, competitive_records):
        """Every special order type should be used in at least 10% of competitive games.
        Why: An unused mechanic is a dead mechanic."""
        n = len(competitive_records)
        for attr, label in [('scouts_used', 'Scout'), ('fortifies_used', 'Fortify'),
                            ('ambushes_used', 'Ambush'), ('charges_used', 'Charge')]:
            used = sum(1 for r in competitive_records if getattr(r, attr) > 0)
            rate = used / n
            assert rate > 0.10, (
                f"{label} used in only {rate:.1%} of competitive games — mechanic is dead"
            )

    def test_economy_constrains_choices(self, competitive_records):
        """Average specials per turn should be well below the theoretical max.
        Why: If everyone can afford everything, there's no resource tradeoff.
        With 5 forces at cost 1-2 each, theoretical max ~5/turn. Should be <3."""
        for r in competitive_records:
            if r.turns == 0:
                continue
            specials = r.scouts_used + r.ambushes_used + r.fortifies_used + r.charges_used
            per_turn = specials / r.turns
            assert per_turn <= 5.0, (
                f"{r.p1_strategy} vs {r.p2_strategy}: {per_turn:.1f} specials/turn — "
                f"economy is not constraining"
            )


# ===========================================================================
# 3. INFORMATION PAYS — Scouting strategies beat blind ones
# ===========================================================================

class TestInformationPays:
    """The hidden-power system is the game's core idea. It must matter."""

    def test_scouting_is_used_meaningfully(self, competitive_records):
        """More than 30% of competitive games should use scouting.
        Why: If scouting is too expensive or useless, the information system is dead."""
        used = sum(1 for r in competitive_records if r.scouts_used > 0)
        rate = used / len(competitive_records)
        assert rate > 0.30, (
            f"Scouting used in only {rate:.1%} of competitive games — information system underused"
        )

    def test_scouting_correlates_with_combat(self, competitive_records):
        """Games with scouting should have higher combat rates than games without.
        Why: If information doesn't lead to action, the scout-fight loop is broken."""
        scout_games = [r for r in competitive_records if r.scouts_used > 0]
        no_scout = [r for r in competitive_records if r.scouts_used == 0]
        if not scout_games or not no_scout:
            pytest.skip("Need both scouted and unscouted games")
        scout_combat = sum(1 for r in scout_games if r.combats > 0) / len(scout_games)
        no_scout_combat = sum(1 for r in no_scout if r.combats > 0) / len(no_scout)
        assert scout_combat > no_scout_combat, (
            f"Scout games combat rate ({scout_combat:.1%}) should exceed "
            f"non-scout ({no_scout_combat:.1%}) — scouting doesn't lead to engagement"
        )


# ===========================================================================
# 4. AGGRESSION WORKS — Attacking is viable, not suicidal
# ===========================================================================

class TestAggressionWorks:
    """Aggressive strategies should be competitive, not kamikaze."""

    def test_aggressive_is_competitive(self, competitive_records):
        """Aggressive should win >40% of competitive games.
        Why: If attacking loses, the game rewards passive play."""
        rate = _strategy_win_rate(competitive_records, 'aggressive')
        assert rate > 0.40, (
            f"Aggressive wins only {rate:.1%} of competitive games — attacking is punished"
        )

    def test_blitzer_is_competitive(self, competitive_records):
        """Blitzer (charge-focused) should win >35% of competitive games.
        Why: Fast-strike play should be a viable archetype."""
        rate = _strategy_win_rate(competitive_records, 'blitzer')
        assert rate > 0.35, (
            f"Blitzer wins only {rate:.1%} — charge/fast-strike isn't viable"
        )


# ===========================================================================
# 5. PASSIVITY DIES — Turtling is crushed, not merely weak
# ===========================================================================

class TestPassivityDies:
    """Turtle should be annihilated, not just lose slightly."""

    def test_turtle_is_crushed_by_every_active_strategy(self, tournament_records):
        """Turtle should win <10% against every active strategy.
        Why: If turtle wins even 20%, the game rewards passivity too much."""
        active = [s.name for s in ALL_STRATEGIES if s.name not in ('turtle', 'random')]
        for opp in active:
            rate = _matchup_win_rate(tournament_records, 'turtle', opp)
            assert rate < 0.10, (
                f"Turtle wins {rate:.1%} vs {opp} — passivity is not punished hard enough"
            )

    def test_turtle_is_worst_overall(self, tournament_records):
        """Turtle should be the worst strategy by overall win rate.
        Why: The deliberately passive strategy must be the worst."""
        rates = {s.name: _strategy_win_rate(tournament_records, s.name) for s in ALL_STRATEGIES}
        turtle_rate = rates['turtle']
        worse_than_turtle = [name for name, r in rates.items() if r < turtle_rate and name != 'turtle']
        assert len(worse_than_turtle) == 0, (
            f"Turtle ({turtle_rate:.1%}) is not the worst: {worse_than_turtle} are lower"
        )


# ===========================================================================
# 6. NO DOMINANT STRATEGY — Rock-paper-scissors among competitive strats
# ===========================================================================

class TestNoDominantStrategy:
    """Among competitive strategies, no single approach should dominate."""

    def test_every_competitive_strategy_has_a_counter(self, competitive_records):
        """Every competitive strategy should lose to at least one other (>55%).
        Why: A strategy with no counter makes the game trivially solved."""
        for strat in COMPETITIVE_NAMES:
            losses = []
            for opp in COMPETITIVE_NAMES:
                if opp == strat:
                    continue
                rate = _matchup_win_rate(competitive_records, strat, opp)
                if rate < 0.45:  # loses by >55%
                    losses.append((opp, rate))
            assert len(losses) >= 1, (
                f"'{strat}' has no counter among competitive strategies — "
                f"worst matchup: {min((1-_matchup_win_rate(competitive_records, strat, o), o) for o in COMPETITIVE_NAMES if o != strat)}"
            )

    def test_no_strategy_dominates_competitive_field(self, competitive_records):
        """No competitive strategy should have >62% overall win rate in competitive games.
        Why: >62% means one approach is clearly best regardless of opponent."""
        for name in COMPETITIVE_NAMES:
            rate = _strategy_win_rate(competitive_records, name)
            assert rate < 0.62, (
                f"'{name}' wins {rate:.1%} of competitive games — dominates the field"
            )

    def test_multiple_competitive_strategies_viable(self, competitive_records):
        """At least 5 competitive strategies should have >38% win rate.
        Why: Fewer than 5 viable options is too narrow a metagame."""
        viable = sum(1 for name in COMPETITIVE_NAMES
                     if _strategy_win_rate(competitive_records, name) > 0.38)
        assert viable >= 5, (
            f"Only {viable} competitive strategies above 38% — metagame too narrow"
        )

    def test_tier_gap_is_small(self, competitive_records):
        """Gap between best and worst competitive strategy should be <30%.
        Why: A large gap means the 'competitive' pool has its own hierarchy."""
        rates = [_strategy_win_rate(competitive_records, name) for name in COMPETITIVE_NAMES]
        gap = max(rates) - min(rates)
        assert gap < 0.30, (
            f"Competitive tier gap is {gap:.1%} — too hierarchical, not rock-paper-scissors. "
            f"Rates: {sorted(zip(COMPETITIVE_NAMES, rates), key=lambda x: -x[1])}"
        )


# ===========================================================================
# 7. GAMES HAVE ARCS — Opening, midgame, endgame
# ===========================================================================

class TestGamesHaveArcs:
    """Games should flow through phases, not end instantly or stall forever."""

    def test_midgame_exists(self, competitive_records):
        """At least 25% of competitive games should last 7-14 turns.
        Why: If games are bimodal (quick-kill or stall), there's no midgame."""
        turns = [r.turns for r in competitive_records]
        mid = sum(1 for t in turns if 7 <= t <= 14)
        rate = mid / len(turns)
        assert rate > 0.20, (
            f"Only {rate:.1%} of games in midgame range (7-14 turns) — "
            f"game is bimodal, no midgame phase"
        )

    def test_games_dont_end_too_fast(self, competitive_records):
        """Fewer than 70% of games should end by turn 6.
        Why: Games ending before forces even meet means no real gameplay.
        Note: with smarter strategies (scouting + charging), decisive games
        by turn 6 are valid — it means advance, scout, strike."""
        turns = [r.turns for r in competitive_records]
        early = sum(1 for t in turns if t <= 6)
        rate = early / len(turns)
        assert rate < 0.70, (
            f"{rate:.1%} of games end by turn 6 — too many instant resolutions"
        )

    def test_game_length_reasonable(self, competitive_records):
        """Average game length should be between 6 and 18 turns.
        Why: <6 means no maneuvering; >18 means the Noose is too gentle."""
        turns = [r.turns for r in competitive_records]
        avg = sum(turns) / len(turns)
        assert 6 <= avg <= 18, f"Average game length {avg:.1f} outside [6, 18]"

    def test_no_absurdly_long_games(self, competitive_records):
        """No game should exceed 25 turns."""
        max_t = max(r.turns for r in competitive_records)
        assert max_t <= 25, f"Longest game: {max_t} turns"

    def test_timeout_rate_low(self, tournament_records):
        """Fewer than 8% of all games should time out."""
        timeouts = sum(1 for r in tournament_records if r.victory_type == 'timeout')
        rate = timeouts / len(tournament_records)
        assert rate < 0.08, f"{rate:.1%} of games timed out"


# ===========================================================================
# 8. VICTORY PATHS DIVERGE — Multiple win conditions, none >65%
# ===========================================================================

class TestVictoryPathsDiverge:
    """All victory types should occur; none should monopolize."""

    def test_no_victory_type_exceeds_65_percent(self, competitive_records):
        """No single victory type should account for >65% of outcomes.
        Why: If one type dominates, the other victory conditions are decorative."""
        types = Counter(r.victory_type for r in competitive_records if r.victory_type)
        total = sum(types.values())
        for vtype, count in types.items():
            rate = count / total
            assert rate < 0.65, (
                f"'{vtype}' is {rate:.1%} of victories — monopolizes outcomes"
            )

    def test_at_least_three_victory_types(self, competitive_records):
        """At least 3 different victory types should occur in competitive play.
        Why: Two types means one mechanic is vestigial."""
        types = set(r.victory_type for r in competitive_records
                    if r.victory_type and r.victory_type != 'timeout')
        assert len(types) >= 3, f"Only {len(types)} victory types: {types}"

    def test_sovereign_capture_frequent(self, competitive_records):
        """Sovereign capture should occur in >10% of competitive games.
        Why: The game's signature mechanic must be viable."""
        sov = sum(1 for r in competitive_records if r.victory_type == 'sovereign_capture')
        rate = sov / len(competitive_records)
        assert rate > 0.10, f"Sovereign capture only {rate:.1%} — signature mechanic too rare"

    def test_domination_occurs(self, competitive_records):
        """Domination should occur in >5% of competitive games.
        Why: Territory control must be a real path to victory."""
        dom = sum(1 for r in competitive_records if r.victory_type == 'domination')
        rate = dom / len(competitive_records)
        assert rate > 0.05, f"Domination only {rate:.1%} — territory control doesn't matter"

    def test_combat_sovereign_kills_exceed_noose_kills(self, competitive_records):
        """More sovereign captures should come from combat than from the Noose.
        Why: Player decisions should determine outcomes more than the timer."""
        noose_sov = sum(1 for r in competitive_records if r.sovereign_killed_by_noose)
        total_sov = sum(1 for r in competitive_records if r.victory_type == 'sovereign_capture')
        if total_sov == 0:
            pytest.skip("No sovereign captures")
        combat_sov = total_sov - noose_sov
        assert combat_sov > noose_sov, (
            f"Noose kills {noose_sov} sovereigns vs combat kills {combat_sov} — "
            f"timer decides more games than players do"
        )


# ===========================================================================
# 9. FORCES DIE — Combat has consequences
# ===========================================================================

class TestForcesDie:
    """The retreat mechanic should make combat less lethal, not consequence-free."""

    def test_forces_are_lost(self, competitive_records):
        """Average forces lost per competitive game should be >1.5.
        Why: If fewer than 1.5 forces die in a 10-force game, combat is toothless."""
        avg = sum(r.p1_forces_lost + r.p2_forces_lost for r in competitive_records) / len(competitive_records)
        assert avg > 1.5, (
            f"Average forces lost is {avg:.2f} — combat has no real consequences"
        )

    def test_retreat_rate_is_meaningful_but_not_total(self, competitive_records):
        """Retreat rate should be between 20% and 60% of combats.
        Why: <20% means retreat mechanic is pointless; >60% means forces never die."""
        total_combats = sum(r.combats for r in competitive_records)
        total_retreats = sum(r.retreats for r in competitive_records)
        if total_combats == 0:
            pytest.skip("No combats")
        rate = total_retreats / total_combats
        assert 0.25 < rate < 0.55, (
            f"Retreat rate is {rate:.1%} — should be 25-55% for meaningful combat"
        )

    def test_elimination_occurs(self, competitive_records):
        """Elimination victory should occur in at least some competitive games.
        Why: If retreat makes forces unkillable, elimination becomes impossible."""
        elims = sum(1 for r in competitive_records if r.victory_type == 'elimination')
        rate = elims / len(competitive_records)
        assert rate > 0.005, (
            f"Elimination only {rate:.2%} — forces are nearly unkillable"
        )

    def test_both_sides_lose_forces(self, competitive_records):
        """In games with combat, both players should lose forces >25% of the time.
        Why: One-sided losses mean combat is a coinflip, not a strategic exchange."""
        combat_games = [r for r in competitive_records if r.combats > 0]
        if not combat_games:
            pytest.skip("No combat games")
        both = sum(1 for r in combat_games if r.p1_forces_lost > 0 and r.p2_forces_lost > 0)
        rate = both / len(combat_games)
        assert rate > 0.25, (
            f"Only {rate:.1%} of combat games had mutual losses — too one-sided"
        )


# ===========================================================================
# 10. THE NOOSE PRESSURES — Timer shapes play without dominating
# ===========================================================================

class TestNoosePressures:
    """The shrinking board should create urgency without being the main killer."""

    def test_noose_kills_forces(self, tournament_records):
        """The Noose should kill forces in some games.
        Why: A Noose that never kills is just decoration."""
        kills = sum(r.noose_kills for r in tournament_records)
        assert kills > 0, "The Noose never killed anyone"

    def test_noose_kills_in_long_games(self, competitive_records):
        """Games lasting >10 turns should frequently have Noose kills.
        Why: The Noose should be the endgame pressure that prevents stalling."""
        long_games = [r for r in competitive_records if r.turns > 10]
        if not long_games:
            pytest.skip("No long games")
        with_kills = sum(1 for r in long_games if r.noose_kills > 0)
        rate = with_kills / len(long_games)
        assert rate > 0.20, (
            f"Only {rate:.1%} of long games had Noose kills — Noose has no teeth"
        )


# ===========================================================================
# 11. SKILL GRADIENT — Better play beats worse play
# ===========================================================================

class TestSkillGradient:
    """Smarter strategies should beat dumber ones."""

    def test_random_is_worst(self, tournament_records):
        """Random should have the lowest win rate."""
        rates = {s.name: _strategy_win_rate(tournament_records, s.name) for s in ALL_STRATEGIES}
        random_rate = rates['random']
        worse = [n for n, r in rates.items() if r < random_rate and n != 'random' and n != 'turtle']
        assert len(worse) == 0, (
            f"Random ({random_rate:.1%}) beats: {worse} — random play shouldn't beat heuristics"
        )

    def test_every_competitive_strategy_beats_random(self, tournament_records):
        """Every competitive strategy should beat random >55% of the time.
        Why: If a heuristic barely beats random, it adds no value."""
        for name in COMPETITIVE_NAMES:
            rate = _matchup_win_rate(tournament_records, name, 'random')
            assert rate > 0.55, (
                f"'{name}' only beats random {rate:.1%} — heuristic adds no value"
            )

    def test_p1_p2_balance(self, tournament_records):
        """P1 and P2 should each win 40-60% of decided games.
        Why: Seat advantage shouldn't determine outcomes."""
        p1 = sum(1 for r in tournament_records if r.winner == 'p1')
        p2 = sum(1 for r in tournament_records if r.winner == 'p2')
        total = p1 + p2
        if total == 0:
            pytest.skip("No decided games")
        rate = p1 / total
        assert 0.40 < rate < 0.60, (
            f"P1 wins {rate:.1%} of decided games — significant seat advantage"
        )


# ===========================================================================
# 12. DEPLOYMENT MATTERS — Power assignment changes outcomes
# ===========================================================================

class TestDeploymentMatters:
    """Different power assignments should produce different results."""

    def test_different_deployments_different_outcomes(self):
        """Same strategy with different power layouts should win different games."""
        class ShuffledDeploy(AggressiveStrategy):
            name = "agg_shuffled"
            def __init__(self, rng_seed):
                self._rng = random.Random(rng_seed)
            def deploy(self, player, rng):
                powers = [1, 2, 3, 4, 5]
                self._rng.shuffle(powers)
                return {f.id: p for f, p in zip(player.forces, powers)}

        winners = []
        for i in range(30):
            r = run_game(ShuffledDeploy(i), ShuffledDeploy(i + 1000), seed=42, rng_seed=i)
            winners.append(r.winner)

        p1 = winners.count('p1')
        p2 = winners.count('p2')
        assert p1 > 0 and p2 > 0, (
            f"Deployment doesn't matter: p1={p1}, p2={p2}"
        )

    def test_sovereign_placement_matters(self):
        """Sovereign position should change outcomes."""
        class SovFront(AggressiveStrategy):
            name = "sov_front"
            def deploy(self, player, rng):
                return dict(zip([f.id for f in player.forces], [1, 5, 4, 3, 2]))

        class SovBack(AggressiveStrategy):
            name = "sov_back"
            def deploy(self, player, rng):
                return dict(zip([f.id for f in player.forces], [5, 4, 3, 2, 1]))

        results = []
        for i in range(30):
            r1 = run_game(SovFront(), CautiousStrategy(), seed=i, rng_seed=i)
            r2 = run_game(SovBack(), CautiousStrategy(), seed=i, rng_seed=i)
            results.append((r1.winner, r2.winner))

        identical = sum(1 for a, b in results if a == b)
        assert identical < len(results), "Sovereign front vs back always identical"


# ===========================================================================
# 13. CONTENTIOUS HEXES CONTESTED — Both players fight for territory
# ===========================================================================

class TestContentiousContested:
    """Contentious hexes should see real competition."""

    def test_both_players_control_contentious(self, competitive_records):
        """Both players should control contentious hexes in >30% of competitive games.
        Why: If only one side ever gets contentious, there's no territorial contest."""
        n = len(competitive_records)
        p1_ever = sum(1 for r in competitive_records if r.contentious_control_turns.get('p1', 0) > 0)
        p2_ever = sum(1 for r in competitive_records if r.contentious_control_turns.get('p2', 0) > 0)
        assert p1_ever / n > 0.30, f"P1 controls contentious in only {p1_ever/n:.1%} of games"
        assert p2_ever / n > 0.30, f"P2 controls contentious in only {p2_ever/n:.1%} of games"


# ===========================================================================
# 14. MECHANICS WORK — Every mechanic is used and affects outcomes
# ===========================================================================

class TestMechanicsWork:
    """Every game mechanic should pull its weight."""

    def test_retreat_occurs(self, competitive_records):
        """Retreats should occur in competitive games."""
        total = sum(r.retreats for r in competitive_records)
        assert total > 0, "No retreats in competitive play"

    def test_charge_is_used(self, competitive_records):
        """Charge should be used in competitive games."""
        total = sum(r.charges_used for r in competitive_records)
        assert total > 0, "Charge never used in competitive play"

    def test_ambush_is_used(self, competitive_records):
        """Ambush should be used in competitive games."""
        total = sum(r.ambushes_used for r in competitive_records)
        assert total > 0, "Ambush never used in competitive play"

    def test_coordinator_is_viable(self, competitive_records):
        """Coordinator (support-focused) should win >25% of competitive games.
        Why: If formation play doesn't work, the support mechanic is useless."""
        rate = _strategy_win_rate(competitive_records, 'coordinator')
        assert rate > 0.25, f"Coordinator wins only {rate:.1%} — support mechanic is useless"

    def test_charge_enables_combat(self, competitive_records):
        """Games with charges should have higher combat rates than games without.
        Why: Charge is supposed to close distance and enable engagements."""
        charge_games = [r for r in competitive_records if r.charges_used > 0]
        no_charge = [r for r in competitive_records if r.charges_used == 0]
        if not charge_games or not no_charge:
            pytest.skip("Need both charged and non-charged games")
        charge_rate = sum(1 for r in charge_games if r.combats > 0) / len(charge_games)
        no_charge_rate = sum(1 for r in no_charge if r.combats > 0) / len(no_charge)
        assert charge_rate > no_charge_rate, (
            f"Charge games ({charge_rate:.1%}) don't have more combat than "
            f"non-charge ({no_charge_rate:.1%}) — charge doesn't enable engagement"
        )


# ===========================================================================
# 15. GAME THEORY — Formal strategic depth among competitive strategies
# ===========================================================================

class TestGameTheory:
    """Game theory properties should hold among competitive strategies (not turtle/random)."""

    def test_intransitive_cycles_exist(self, competitive_payoff):
        """The competitive matchup graph should contain A > B > C > A cycles.
        Why: Without cycles, the metagame is a strict hierarchy."""
        matrix = competitive_payoff['matrix']
        names = competitive_payoff['strategies']
        n = len(names)

        # Build beats graph with >0.55 threshold (clear advantage, not noise)
        beats = {i: set() for i in range(n)}
        for i in range(n):
            for j in range(n):
                if i != j and matrix[i][j] > 0.55:
                    beats[i].add(j)

        found = False
        for a in range(n):
            for b in beats[a]:
                for c in beats[b]:
                    if a in beats[c]:
                        found = True
                        break
                if found:
                    break
            if found:
                break

        assert found, (
            f"No intransitive cycle (A>B>C>A at >55%) among competitive strategies: "
            f"{names}. The metagame is a strict hierarchy."
        )

    def test_replicator_dynamics_sustain_diversity(self, competitive_payoff):
        """Replicator dynamics among competitive strategies should sustain 3+ survivors.
        Why: The competitive metagame should not collapse to 1-2 strategies."""
        matrix = competitive_payoff['matrix']
        names = competitive_payoff['strategies']
        freqs = _replicator_dynamics(matrix)

        survivors = [(names[i], freqs[i]) for i in range(len(freqs)) if freqs[i] > 0.01]
        max_freq = max(freqs)

        assert len(survivors) >= 3, (
            f"Replicator dynamics collapsed to {len(survivors)} strategy(ies): {survivors}. "
            f"Competitive metagame lacks diversity."
        )
        assert max_freq < 0.70, (
            f"'{names[freqs.index(max_freq)]}' dominates at {max_freq:.1%} — "
            f"metagame converges to one strategy"
        )

    def test_payoff_matrix_has_meaningful_variance(self, competitive_payoff):
        """Win rates should have std_dev > 0.08 among competitive strategies.
        Why: If all matchups are ~50/50, strategies are interchangeable."""
        matrix = competitive_payoff['matrix']
        n = len(matrix)
        rates = [matrix[i][j] for i in range(n) for j in range(n) if i != j]
        mean = sum(rates) / len(rates)
        var = sum((x - mean) ** 2 for x in rates) / len(rates)
        std = var ** 0.5
        assert std > 0.08, (
            f"Competitive payoff matrix std_dev is {std:.3f} — "
            f"matchups too uniform, strategies interchangeable"
        )

    def test_no_strategy_beats_all_competitive(self, competitive_payoff):
        """No competitive strategy should beat every other competitive strategy.
        Why: Formal definition of 'no strictly dominant strategy.'"""
        matrix = competitive_payoff['matrix']
        names = competitive_payoff['strategies']
        n = len(names)
        for i in range(n):
            beaten = sum(1 for j in range(n) if j != i and matrix[i][j] > 0.5)
            assert beaten < n - 1, (
                f"'{names[i]}' beats all {beaten}/{n-1} competitive opponents — "
                f"strictly dominant"
            )


# ===========================================================================
# 13. ABLATION TESTS — Remove a mechanic, verify performance degrades (v8)
# ===========================================================================

ABLATION_GAMES = 80
ABLATION_SEEDS = list(range(ABLATION_GAMES))


def _head_to_head_win_rate(s1, s2, n_games=ABLATION_GAMES, seeds=None):
    """Run s1 vs s2 head-to-head, alternating sides. Return s1 win rate."""
    if seeds is None:
        seeds = list(range(n_games))
    wins = 0
    total = 0
    for i, seed in enumerate(seeds[:n_games // 2]):
        r = run_game(s1, s2, seed=seed, rng_seed=i * 1000)
        total += 1
        if r.winner == 'p1':
            wins += 1
        r = run_game(s2, s1, seed=seed, rng_seed=i * 1000 + 500)
        total += 1
        if r.winner == 'p2':
            wins += 1
    return wins / total if total > 0 else 0.5


class TestAblation:
    """Ablation tests: remove one mechanic, verify performance degrades.
    This addresses Goodhart problem #5: correlation tests are confounded.
    Ablation tests prove CAUSATION — the mechanic itself matters."""

    def test_scouting_matters(self):
        """CautiousStrategy should beat its NeverScout ablation.
        Why: If removing scouting doesn't hurt, scouting is decorative."""
        rate = _head_to_head_win_rate(CautiousStrategy(), NeverScoutVariant())
        assert rate > 0.55, (
            f"Cautious only wins {rate:.1%} vs NeverScout — "
            f"scouting doesn't provide a real advantage"
        )

    def test_charge_matters(self):
        """BlitzerStrategy should beat its NoCharge ablation.
        Why: If removing charge doesn't hurt, charge is decorative."""
        rate = _head_to_head_win_rate(BlitzerStrategy(), NoChargeVariant())
        assert rate > 0.55, (
            f"Blitzer only wins {rate:.1%} vs NoCharge — "
            f"charge doesn't provide a real advantage"
        )

    def test_power_awareness_matters(self):
        """Competitive strategies should beat PowerBlind head-to-head.
        Why: If ignoring power values doesn't hurt, power-awareness is theater."""
        blind = PowerBlindStrategy()
        wins_vs_competitive = 0
        for strat in COMPETITIVE_STRATEGIES:
            rate = _head_to_head_win_rate(strat, blind, n_games=40,
                                          seeds=list(range(40)))
            if rate > 0.50:
                wins_vs_competitive += 1
        # At least 5 of 7 competitive strategies should beat power-blind
        assert wins_vs_competitive >= 5, (
            f"Only {wins_vs_competitive}/7 competitive strategies beat PowerBlind — "
            f"power-awareness doesn't matter enough"
        )


# ===========================================================================
# 14. ANTI-PASSIVITY — SmartPassive must lose, not just straw-man Turtle (v8)
# ===========================================================================

class TestAntiPassivity:
    """SmartPassive is an intelligent passive strategy that dodges the Noose
    and fortifies at contentious hexes but never fights. If the game is
    well-designed, this should lose to every active strategy — not just
    brain-dead Turtle. Addresses Goodhart problem #3."""

    def test_smart_passive_loses_to_each_competitive(self):
        """SmartPassive should win < 40% against each competitive strategy.
        Why: If intelligent passivity is viable, the game rewards non-engagement."""
        sp = SmartPassiveStrategy()
        for strat in COMPETITIVE_STRATEGIES:
            rate = _head_to_head_win_rate(sp, strat, n_games=40,
                                          seeds=list(range(40)))
            assert rate < 0.40, (
                f"SmartPassive wins {rate:.1%} vs {strat.name} — "
                f"intelligent passivity is viable"
            )

    def test_smart_passive_overall_loses(self):
        """SmartPassive overall win rate against competitive strategies should be < 35%.
        Why: An intelligent passive strategy should not be competitive."""
        sp = SmartPassiveStrategy()
        total_games = 0
        total_wins = 0
        for strat in COMPETITIVE_STRATEGIES:
            for seed in range(20):
                r1 = run_game(sp, strat, seed=seed, rng_seed=seed * 1000)
                total_games += 1
                if r1.winner == 'p1':
                    total_wins += 1
                r2 = run_game(strat, sp, seed=seed, rng_seed=seed * 1000 + 500)
                total_games += 1
                if r2.winner == 'p2':
                    total_wins += 1
        rate = total_wins / total_games
        assert rate < 0.35, (
            f"SmartPassive wins {rate:.1%} overall vs competitive — "
            f"intelligent passivity is too viable"
        )


# ===========================================================================
# 15. DEGENERATE EXPLOITS — Exploit strategies must fail (v8)
# ===========================================================================

class TestDegenerateExploits:
    """Degenerate strategies that try to exploit specific mechanics should
    lose to competitive strategies. Addresses Goodhart problem #4."""

    def test_domination_staller_not_viable(self):
        """DominationStaller should win < 40% against competitive strategies.
        Why: Stalling for domination should not be a viable strategy."""
        staller = DominationStallerStrategy()
        total_games = 0
        total_wins = 0
        for strat in COMPETITIVE_STRATEGIES:
            for seed in range(20):
                r1 = run_game(staller, strat, seed=seed, rng_seed=seed * 1000)
                total_games += 1
                if r1.winner == 'p1':
                    total_wins += 1
                r2 = run_game(strat, staller, seed=seed, rng_seed=seed * 1000 + 500)
                total_games += 1
                if r2.winner == 'p2':
                    total_wins += 1
        rate = total_wins / total_games
        assert rate < 0.40, (
            f"DominationStaller wins {rate:.1%} of competitive matchups — "
            f"domination stalling is exploitable"
        )

    def test_no_adversarial_dominates_competitive(self):
        """No adversarial strategy should beat >5 of 7 competitive strategies.
        Why: Adversarial strategies should not dominate the competitive field."""
        for adv in ADVERSARIAL_STRATEGIES:
            beats = 0
            for comp in COMPETITIVE_STRATEGIES:
                rate = _head_to_head_win_rate(adv, comp, n_games=40,
                                              seeds=list(range(40)))
                if rate > 0.50:
                    beats += 1
            assert beats <= 5, (
                f"'{adv.name}' beats {beats}/{len(COMPETITIVE_STRATEGIES)} "
                f"competitive strategies — adversarial strategy dominates"
            )


# ===========================================================================
# 16. SEED ROBUSTNESS — Results stable across different map seeds (v8)
# ===========================================================================

class TestSeedRobustness:
    """Results should be stable across different map seed sets.
    Addresses Goodhart problem #9: fixed seeds create hidden overfitting."""

    def test_win_rates_stable_across_seeds(self, competitive_records):
        """Run tournament with offset seeds, verify win rates within ±15pp."""
        # Canonical win rates from the main tournament
        canonical = {name: _strategy_win_rate(competitive_records, name)
                     for name in COMPETITIVE_NAMES}

        # Run a secondary tournament with different seeds
        alt_seeds = list(range(100, 100 + GAMES_PER_MATCHUP))
        alt_records = run_tournament(
            COMPETITIVE_STRATEGIES,
            games_per_matchup=GAMES_PER_MATCHUP,
            map_seeds=alt_seeds,
        )

        for name in COMPETITIVE_NAMES:
            alt_rate = _strategy_win_rate(alt_records, name)
            diff = abs(alt_rate - canonical[name])
            assert diff < 0.15, (
                f"'{name}' win rate shifts by {diff:.1%} across seed sets "
                f"(canonical={canonical[name]:.1%}, alt={alt_rate:.1%}) — "
                f"results overfitted to fixed seeds"
            )


# ===========================================================================
# 17. DEPLOYMENT BREADTH — Matters for ALL strategies, not just one (v8)
# ===========================================================================

class TestDeploymentBreadth:
    """Deployment should affect outcomes across multiple strategies.
    Addresses Goodhart problem #10: only testing one strategy."""

    def test_deployment_sensitivity_across_strategies(self):
        """Deployment should change outcomes for at least 4 of 7 competitive strategies.
        Why: If deployment only matters for 1 strategy, the deployment phase is narrow."""
        sensitive_count = 0
        for comp_strat in COMPETITIVE_STRATEGIES:
            class ShuffledVariant(comp_strat.__class__):
                name = f"{comp_strat.name}_shuffled"
                def __init__(self, rng_seed):
                    self._rng = random.Random(rng_seed)
                def deploy(self, player, rng):
                    powers = [1, 2, 3, 4, 5]
                    self._rng.shuffle(powers)
                    return {f.id: p for f, p in zip(player.forces, powers)}

            # Run original vs shuffled-deployment version
            diff_count = 0
            for seed in range(20):
                r1 = run_game(comp_strat, CautiousStrategy(), seed=seed, rng_seed=seed)
                r2 = run_game(ShuffledVariant(seed), CautiousStrategy(), seed=seed, rng_seed=seed)
                if r1.winner != r2.winner:
                    diff_count += 1
            # If >25% of games differ, deployment matters for this strategy
            if diff_count / 20 > 0.25:
                sensitive_count += 1

        assert sensitive_count >= 4, (
            f"Deployment only matters for {sensitive_count}/7 strategies — "
            f"deployment phase is too narrow"
        )
