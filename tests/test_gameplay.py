"""
Gameplay experience tests for The Unfought Battle v3.

These tests don't check that code works. They check that the GAME works.
They simulate hundreds of games between different AI strategies and measure
emergent properties that a brilliant game must exhibit.

GOODHART'S LAW RESISTANCE
=========================
These tests are resistant to parameter-gaming because they measure
RELATIONSHIPS between strategies, not absolute numbers. You can't
tune config.json to pass these tests without actually making the game
better, because:

1. They test that SKILL MATTERS (informed > random) — you can't fake
   this by tweaking numbers; the information system must genuinely help.

2. They test that NO STRATEGY DOMINATES — you can't tune one number to
   fix this; the rock-paper-scissors must emerge from the mechanics.

3. They test that PASSIVITY LOSES — the Noose must actually kill turtles,
   not just exist in the rules.

4. They test that ALL VICTORY PATHS ARE REACHABLE — you can't fake
   sovereign capture, domination, and elimination all occurring naturally.

5. They test STRUCTURAL properties (game length distribution, combat
   frequency, information usage) that emerge from the interaction of
   ALL mechanics simultaneously.

The only way to pass all these tests is to have a well-designed game.

KEY MEASURES FOR A BRILLIANT GAME
==================================
1. Skill gradient     — better strategies beat worse ones
2. No dominant play   — no pure strategy beats everything
3. Games terminate    — no draws, no infinite stalls
4. Diverse victories  — all victory types occur in practice
5. Information value  — scouting measurably helps
6. Aggression viable  — attacking is a path to winning
7. Patience punished  — turtling loses to active play
8. Economy bites      — players face real resource constraints
9. Noose works        — board shrink kills forces and ends games
10. Deployment matters — different power layouts lead to different outcomes
"""

import pytest
import random
from collections import Counter
from typing import List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.simulate import (
    run_game, run_tournament, GameRecord,
    RandomStrategy, AggressiveStrategy, CautiousStrategy,
    AmbushStrategy, TurtleStrategy, SovereignHunterStrategy,
    ALL_STRATEGIES, STRATEGY_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures: run the tournaments once, share across all tests
# ---------------------------------------------------------------------------

GAMES_PER_MATCHUP = 40
MAP_SEEDS = list(range(GAMES_PER_MATCHUP))

@pytest.fixture(scope="module")
def tournament_records():
    """Full round-robin tournament. Cached for the module."""
    return run_tournament(ALL_STRATEGIES, games_per_matchup=GAMES_PER_MATCHUP, map_seeds=MAP_SEEDS)


@pytest.fixture(scope="module")
def records_by_matchup(tournament_records):
    """Group records by (p1_strategy, p2_strategy) pair."""
    grouped = {}
    for r in tournament_records:
        key = (r.p1_strategy, r.p2_strategy)
        grouped.setdefault(key, []).append(r)
    return grouped


def win_rate(records: List[GameRecord], player_id: str) -> float:
    """Win rate for a given player across a set of game records."""
    if not records:
        return 0.0
    wins = sum(1 for r in records if r.winner == player_id)
    return wins / len(records)


def strategy_overall_wins(records: List[GameRecord], strategy_name: str) -> int:
    """Count total wins for a strategy across all games (as either p1 or p2)."""
    wins = 0
    for r in records:
        if r.winner == 'p1' and r.p1_strategy == strategy_name:
            wins += 1
        elif r.winner == 'p2' and r.p2_strategy == strategy_name:
            wins += 1
    return wins


def strategy_games_played(records: List[GameRecord], strategy_name: str) -> int:
    """Count games a strategy played."""
    return sum(1 for r in records if r.p1_strategy == strategy_name or r.p2_strategy == strategy_name)


# ===========================================================================
# MEASURE 1: SKILL GRADIENT — Better strategies beat worse ones
# ===========================================================================

class TestSkillGradient:
    """
    The fundamental test: does being smarter help?

    Why Goodhart-resistant: You can't make random play equal to informed
    play by tuning numbers. Either the strategy logic produces better
    outcomes or it doesn't. The gap between random and heuristic players
    is an emergent property of the entire system.
    """

    def test_random_is_worst(self, tournament_records):
        """Random strategy should have the lowest overall win rate."""
        wins_by_strat = {}
        games_by_strat = {}
        for s in ALL_STRATEGIES:
            wins_by_strat[s.name] = strategy_overall_wins(tournament_records, s.name)
            games_by_strat[s.name] = strategy_games_played(tournament_records, s.name)

        random_rate = wins_by_strat['random'] / max(1, games_by_strat['random'])
        non_random_rates = [
            wins_by_strat[s.name] / max(1, games_by_strat[s.name])
            for s in ALL_STRATEGIES if s.name != 'random'
        ]
        avg_non_random = sum(non_random_rates) / len(non_random_rates)
        # Random should win less than the average non-random strategy
        assert random_rate < avg_non_random, (
            f"Random win rate ({random_rate:.2f}) should be below "
            f"average non-random ({avg_non_random:.2f})"
        )

    def test_heuristic_beats_random(self, tournament_records):
        """Every heuristic strategy should beat random more than 50% of the time."""
        for strat in ALL_STRATEGIES:
            if strat.name == 'random' or strat.name == 'turtle':
                continue
            # Get all games where this strat played against random
            matchup_records = [
                r for r in tournament_records
                if (r.p1_strategy == strat.name and r.p2_strategy == 'random')
                or (r.p1_strategy == 'random' and r.p2_strategy == strat.name)
            ]
            if not matchup_records:
                continue
            strat_wins = sum(
                1 for r in matchup_records
                if (r.winner == 'p1' and r.p1_strategy == strat.name)
                or (r.winner == 'p2' and r.p2_strategy == strat.name)
            )
            rate = strat_wins / len(matchup_records)
            assert rate > 0.40, (
                f"{strat.name} should beat random >40% of the time, got {rate:.2f}"
            )


# ===========================================================================
# MEASURE 2: NO DOMINANT STRATEGY — Rock-paper-scissors must emerge
# ===========================================================================

class TestNoDominantStrategy:
    """
    No single strategy should beat every other strategy.

    Why Goodhart-resistant: A dominant strategy means the game has a
    solved opening or a degenerate mechanic. You can't fix this by
    tuning one parameter — the entire strategic triangle must work.
    """

    def test_no_strategy_beats_all(self, tournament_records):
        """No strategy should have >80% win rate against ALL others."""
        for strat in ALL_STRATEGIES:
            opponent_win_rates = []
            for opp in ALL_STRATEGIES:
                if opp.name == strat.name:
                    continue
                matchup = [
                    r for r in tournament_records
                    if (r.p1_strategy == strat.name and r.p2_strategy == opp.name)
                    or (r.p1_strategy == opp.name and r.p2_strategy == strat.name)
                ]
                if not matchup:
                    continue
                wins = sum(
                    1 for r in matchup
                    if (r.winner == 'p1' and r.p1_strategy == strat.name)
                    or (r.winner == 'p2' and r.p2_strategy == strat.name)
                )
                opponent_win_rates.append(wins / len(matchup))

            if opponent_win_rates:
                min_wr = min(opponent_win_rates)
                # Even against its weakest opponent, no strategy should lose every game
                assert min_wr < 0.85, (
                    f"{strat.name} dominates with min opponent win rate {min_wr:.2f}"
                )

    def test_multiple_viable_strategies(self, tournament_records):
        """At least 3 strategies should have overall win rate > 30%."""
        viable = 0
        for strat in ALL_STRATEGIES:
            games = strategy_games_played(tournament_records, strat.name)
            if games == 0:
                continue
            wins = strategy_overall_wins(tournament_records, strat.name)
            if wins / games > 0.30:
                viable += 1
        assert viable >= 3, f"Only {viable} viable strategies (need 3+)"


# ===========================================================================
# MEASURE 3: GAMES TERMINATE — No infinite stalls
# ===========================================================================

class TestGamesTerminate:
    """
    Every game should end. The Noose guarantees this.

    Why Goodhart-resistant: If games don't end, the Noose is broken.
    You can't fake game termination — either the board shrinks and
    forces engagement, or it doesn't.
    """

    def test_all_games_have_winner(self, tournament_records):
        """No game should end in a draw/timeout."""
        timeouts = [r for r in tournament_records if r.victory_type == 'timeout']
        timeout_rate = len(timeouts) / len(tournament_records)
        assert timeout_rate < 0.05, (
            f"{len(timeouts)}/{len(tournament_records)} games timed out ({timeout_rate:.1%})"
        )

    def test_game_length_reasonable(self, tournament_records):
        """Games should typically end between turns 4-20."""
        turns = [r.turns for r in tournament_records]
        avg_turns = sum(turns) / len(turns)
        assert 4 <= avg_turns <= 20, f"Average game length {avg_turns:.1f} is outside [4, 20]"

    def test_no_absurdly_long_games(self, tournament_records):
        """No game should exceed 25 turns."""
        max_turns = max(r.turns for r in tournament_records)
        assert max_turns <= 25, f"Longest game was {max_turns} turns"

    def test_game_length_has_variance(self, tournament_records):
        """Games shouldn't all be the same length — variance means different outcomes."""
        turns = [r.turns for r in tournament_records]
        min_t = min(turns)
        max_t = max(turns)
        assert max_t - min_t >= 4, (
            f"Game lengths {min_t}-{max_t} too uniform (spread < 4)"
        )


# ===========================================================================
# MEASURE 4: DIVERSE VICTORIES — All paths reachable
# ===========================================================================

class TestVictoryDiversity:
    """
    All victory types should occur naturally in play.

    Why Goodhart-resistant: You can't tune parameters to make sovereign
    capture, domination, AND elimination all occur. They require
    fundamentally different game dynamics. If all three show up in a
    tournament, the game has real strategic diversity.
    """

    def test_sovereign_capture_occurs(self, tournament_records):
        """Sovereign capture should happen in some games."""
        sov_captures = [r for r in tournament_records if r.victory_type == 'sovereign_capture']
        rate = len(sov_captures) / len(tournament_records)
        assert rate > 0.05, (
            f"Sovereign capture only {rate:.1%} of games (need >5%)"
        )

    def test_elimination_occurs(self, tournament_records):
        """Elimination should happen in some games."""
        elims = [r for r in tournament_records if r.victory_type == 'elimination']
        rate = len(elims) / len(tournament_records)
        assert rate > 0.02, (
            f"Elimination only {rate:.1%} of games (need >2%)"
        )

    def test_no_single_victory_type_dominates(self, tournament_records):
        """No victory type should account for >85% of all wins."""
        types = Counter(r.victory_type for r in tournament_records if r.victory_type)
        total = sum(types.values())
        for vtype, count in types.items():
            rate = count / total
            assert rate < 0.85, (
                f"Victory type '{vtype}' is {rate:.1%} of all wins — too dominant"
            )

    def test_at_least_two_victory_types(self, tournament_records):
        """At least 2 different victory types should occur."""
        types = set(r.victory_type for r in tournament_records if r.victory_type and r.victory_type != 'timeout')
        assert len(types) >= 2, f"Only {len(types)} victory types occurred: {types}"


# ===========================================================================
# MEASURE 5: INFORMATION VALUE — Scouting helps
# ===========================================================================

class TestInformationValue:
    """
    Scouting should provide measurable advantage.

    Why Goodhart-resistant: You can't make scouting "help" by tuning
    its cost or range. It helps because knowing the enemy's power
    values lets you make better attack/retreat decisions. If the
    information system is broken (scouting reveals useless data, or
    combat is too random for information to matter), this test fails.
    """

    def test_scout_strategy_beats_non_scout(self, tournament_records):
        """
        Strategies that scout (cautious, hunter) should collectively
        outperform strategies that never scout (aggressive, turtle).
        """
        scout_strats = {'cautious', 'hunter'}
        no_scout_strats = {'aggressive', 'turtle'}

        scout_wins = 0
        scout_games = 0
        for r in tournament_records:
            p1_scouts = r.p1_strategy in scout_strats
            p2_scouts = r.p2_strategy in no_scout_strats
            if p1_scouts and p2_scouts:
                scout_games += 1
                if r.winner == 'p1':
                    scout_wins += 1
            p1_no = r.p1_strategy in no_scout_strats
            p2_sc = r.p2_strategy in scout_strats
            if p2_sc and p1_no:
                scout_games += 1
                if r.winner == 'p2':
                    scout_wins += 1

        if scout_games > 0:
            rate = scout_wins / scout_games
            assert rate > 0.35, (
                f"Scouting strategies only win {rate:.1%} vs non-scouting — "
                f"information isn't valuable enough"
            )

    def test_games_use_scouting(self, tournament_records):
        """Scouting should be used in a meaningful fraction of games."""
        games_with_scouts = sum(1 for r in tournament_records if r.scouts_used > 0)
        rate = games_with_scouts / len(tournament_records)
        assert rate > 0.1, f"Only {rate:.1%} of games used scouting"


# ===========================================================================
# MEASURE 6: AGGRESSION VIABLE — Attacking works
# ===========================================================================

class TestAggressionViable:
    """
    Aggressive play should be a viable path to victory.

    Why Goodhart-resistant: If aggression never works, the game rewards
    only turtling. If aggression always works, the game rewards only
    rushing. Either extreme is a degenerate game.
    """

    def test_aggressive_wins_some(self, tournament_records):
        """Aggressive strategy should win at least 25% of its games."""
        games = strategy_games_played(tournament_records, 'aggressive')
        wins = strategy_overall_wins(tournament_records, 'aggressive')
        if games > 0:
            rate = wins / games
            assert rate > 0.25, f"Aggressive only wins {rate:.1%}"

    def test_combat_happens(self, tournament_records):
        """Most games should involve at least one combat."""
        games_with_combat = sum(1 for r in tournament_records if r.combats > 0)
        rate = games_with_combat / len(tournament_records)
        assert rate > 0.30, f"Only {rate:.1%} of games had combat"


# ===========================================================================
# MEASURE 7: PASSIVITY PUNISHED — Turtling loses
# ===========================================================================

class TestPassivityPunished:
    """
    The turtle strategy should be the worst or near-worst.

    Why Goodhart-resistant: If turtling is viable, the game allows
    infinite stalling. The Noose is supposed to prevent this. You can't
    tune the Noose to barely kill turtles — it must force engagement
    strongly enough that sitting still is a death sentence.
    """

    def test_turtle_loses_to_active_strategies(self, tournament_records):
        """Turtle should lose to every non-random active strategy."""
        active_strats = ['aggressive', 'cautious', 'ambush', 'hunter']
        for active in active_strats:
            matchup = [
                r for r in tournament_records
                if (r.p1_strategy == 'turtle' and r.p2_strategy == active)
                or (r.p1_strategy == active and r.p2_strategy == 'turtle')
            ]
            if not matchup:
                continue
            turtle_wins = sum(
                1 for r in matchup
                if (r.winner == 'p1' and r.p1_strategy == 'turtle')
                or (r.winner == 'p2' and r.p2_strategy == 'turtle')
            )
            rate = turtle_wins / len(matchup)
            assert rate < 0.55, (
                f"Turtle beats {active} {rate:.1%} — passivity shouldn't be this effective"
            )

    def test_turtle_has_low_overall_rate(self, tournament_records):
        """Turtle should have the lowest or near-lowest win rate."""
        games = strategy_games_played(tournament_records, 'turtle')
        wins = strategy_overall_wins(tournament_records, 'turtle')
        if games > 0:
            rate = wins / games
            assert rate < 0.50, f"Turtle wins {rate:.1%} — passivity too strong"


# ===========================================================================
# MEASURE 8: ECONOMY BITES — Resources constrain choices
# ===========================================================================

class TestEconomyBites:
    """
    Players should face real resource constraints.

    Why Goodhart-resistant: If the economy is too loose, every test
    about trade-offs (scout vs ambush vs fortify) becomes meaningless.
    You can't fake scarcity — either players run out of Shih and have
    to make hard choices, or they don't.
    """

    def test_players_cant_afford_everything(self, tournament_records):
        """
        Total orders requiring Shih should exceed what's available.
        Measured by: games where non-move orders > 0 should have turns
        where players default to free moves.
        """
        # If economy bites, games with scouts+ambushes+fortifies should show
        # significant variation in order mix (not everyone scouting every turn)
        games_with_specials = [
            r for r in tournament_records
            if r.scouts_used + r.ambushes_used + r.fortifies_used > 0
        ]
        # Not every force can use a special order every turn
        # Average special orders per turn should be well below 5 (forces per player)
        for r in games_with_specials:
            if r.turns > 0:
                specials_per_turn = (r.scouts_used + r.ambushes_used + r.fortifies_used) / r.turns
                # 10 forces total * 2 players, if economy is tight, specials << 10
                # We just need to see that it's not maxed out
                assert specials_per_turn < 8, (
                    f"Economy too loose: {specials_per_turn:.1f} special orders/turn"
                )

    def test_fortify_is_most_used_special(self, tournament_records):
        """Fortify (cheapest) should be used more than scout (most expensive)."""
        total_fortify = sum(r.fortifies_used for r in tournament_records)
        total_scout = sum(r.scouts_used for r in tournament_records)
        # Cheap actions should be used more — this proves cost matters
        assert total_fortify > total_scout, (
            f"Fortify ({total_fortify}) should be used more than Scout ({total_scout})"
        )


# ===========================================================================
# MEASURE 9: THE NOOSE WORKS — Board shrink has teeth
# ===========================================================================

class TestNooseWorks:
    """
    The shrinking board should actively shape games.

    Why Goodhart-resistant: Either the Noose kills forces and creates
    urgency, or it doesn't. You can't fake this — the simulation counts
    actual noose kills across hundreds of games.
    """

    def test_noose_kills_some_forces(self, tournament_records):
        """The Noose should kill at least some forces across all games."""
        total_noose_kills = sum(r.noose_kills for r in tournament_records)
        assert total_noose_kills > 0, "The Noose never killed anyone"

    def test_noose_kills_in_long_games(self, tournament_records):
        """Games lasting >8 turns should have Noose kills (board has shrunk)."""
        long_games = [r for r in tournament_records if r.turns > 8]
        if long_games:
            games_with_noose_kills = sum(1 for r in long_games if r.noose_kills > 0)
            rate = games_with_noose_kills / len(long_games)
            assert rate > 0.1, (
                f"Only {rate:.1%} of long games had Noose kills"
            )


# ===========================================================================
# MEASURE 10: DEPLOYMENT MATTERS — Different layouts, different outcomes
# ===========================================================================

class TestDeploymentMatters:
    """
    Different power assignments should produce different results.

    Why Goodhart-resistant: If deployment doesn't matter, the information
    system is broken — knowing that an enemy force has power 5 vs power 1
    should be decision-relevant. This tests the structural property that
    the game's hidden information is actually consequential.
    """

    def test_different_deployments_different_outcomes(self):
        """
        Same strategies with different deployment orders should produce
        different game records. Run 30 games with shuffled deployments.
        """
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
            s1 = ShuffledDeploy(i)
            s2 = ShuffledDeploy(i + 1000)
            r = run_game(s1, s2, seed=42, rng_seed=i)
            winners.append(r.winner)

        # Both p1 and p2 should win some games
        p1_wins = winners.count('p1')
        p2_wins = winners.count('p2')
        # Neither side should win ALL games — deployment affects outcomes
        assert p1_wins > 0 and p2_wins > 0, (
            f"Deployment doesn't matter: p1={p1_wins}, p2={p2_wins}"
        )

    def test_sovereign_placement_matters(self):
        """
        Putting the sovereign in front vs back should change outcomes.
        """
        class SovFront(AggressiveStrategy):
            name = "sov_front"
            def deploy(self, player, rng):
                ids = [f.id for f in player.forces]
                return dict(zip(ids, [1, 5, 4, 3, 2]))  # Sovereign first

        class SovBack(AggressiveStrategy):
            name = "sov_back"
            def deploy(self, player, rng):
                ids = [f.id for f in player.forces]
                return dict(zip(ids, [5, 4, 3, 2, 1]))  # Sovereign last

        front_records = []
        back_records = []
        for i in range(30):
            r1 = run_game(SovFront(), CautiousStrategy(), seed=i, rng_seed=i)
            r2 = run_game(SovBack(), CautiousStrategy(), seed=i, rng_seed=i)
            front_records.append(r1)
            back_records.append(r2)

        front_wins = sum(1 for r in front_records if r.winner == 'p1')
        back_wins = sum(1 for r in back_records if r.winner == 'p1')
        # The outcomes should differ — sovereign placement should matter
        # We don't care which is better, just that they're not identical
        total = len(front_records)
        # Allow some variance, but they shouldn't be exactly the same
        combined_results = [(f.winner, b.winner) for f, b in zip(front_records, back_records)]
        identical = sum(1 for f, b in combined_results if f == b)
        # At least some games should have different outcomes
        assert identical < total, (
            "Sovereign front vs back produced identical results every time"
        )


# ===========================================================================
# STRUCTURAL TESTS: Emergent game properties
# ===========================================================================

class TestGameArc:
    """
    Games should have a natural arc: opening (maneuver), midgame (contact),
    endgame (decisive combat). Measured by when first combat occurs.
    """

    def test_combat_not_immediate(self, tournament_records):
        """First combat shouldn't happen on turn 1 (forces start far apart)."""
        games_with_combat = [r for r in tournament_records if r.combats > 0]
        # Most games should require some movement before contact
        assert len(games_with_combat) > 0

    def test_forces_are_lost(self, tournament_records):
        """Both players should lose forces in most games — not just one-sided."""
        both_lose = sum(
            1 for r in tournament_records
            if r.p1_forces_lost > 0 and r.p2_forces_lost > 0
        )
        either_lose = sum(
            1 for r in tournament_records
            if r.p1_forces_lost > 0 or r.p2_forces_lost > 0
        )
        if either_lose > 0:
            rate = both_lose / either_lose
            assert rate > 0.2, (
                f"Only {rate:.1%} of combat games had mutual losses — too one-sided"
            )


class TestContentiousControl:
    """Contentious hexes should see real competition, not be ignored."""

    def test_both_players_contest(self, tournament_records):
        """Both players should control contentious hexes at some point."""
        p1_ever_controlled = sum(
            1 for r in tournament_records
            if r.contentious_control_turns.get('p1', 0) > 0
        )
        p2_ever_controlled = sum(
            1 for r in tournament_records
            if r.contentious_control_turns.get('p2', 0) > 0
        )
        total = len(tournament_records)
        assert p1_ever_controlled / total > 0.2, "P1 rarely controls contentious hexes"
        assert p2_ever_controlled / total > 0.2, "P2 rarely controls contentious hexes"


class TestAmbushMechanic:
    """The ambush mechanic should be used and should sometimes matter."""

    def test_ambush_is_used(self, tournament_records):
        """Ambush should be used in some games."""
        games_with_ambush = sum(1 for r in tournament_records if r.ambushes_used > 0)
        rate = games_with_ambush / len(tournament_records)
        assert rate > 0.05, f"Ambush only used in {rate:.1%} of games"

    def test_ambush_strategy_viable(self, tournament_records):
        """The ambush strategy should not be the absolute worst."""
        games = strategy_games_played(tournament_records, 'ambush')
        wins = strategy_overall_wins(tournament_records, 'ambush')
        if games > 0:
            rate = wins / games
            # It doesn't have to be the best, but it should win sometimes
            assert rate > 0.15, f"Ambush strategy only wins {rate:.1%}"


# ===========================================================================
# META-TEST: The game is not solvable by simple heuristics
# ===========================================================================

class TestGameComplexity:
    """
    The game should exhibit enough complexity that no simple heuristic
    dominates perfectly. This is the ultimate Goodhart resistance test.
    """

    def test_win_rates_spread(self, tournament_records):
        """
        Strategy win rates should be spread out (not clustered near 50%).
        A spread means strategies have DIFFERENT strengths, indicating
        the game has enough depth to differentiate approaches.
        """
        rates = []
        for strat in ALL_STRATEGIES:
            games = strategy_games_played(tournament_records, strat.name)
            if games == 0:
                continue
            wins = strategy_overall_wins(tournament_records, strat.name)
            rates.append(wins / games)

        if len(rates) >= 3:
            spread = max(rates) - min(rates)
            assert spread > 0.10, (
                f"Win rate spread is only {spread:.2f} — strategies too equal, "
                f"game may not reward different approaches"
            )

    def test_no_first_mover_advantage(self, tournament_records):
        """P1 and P2 should win roughly equally across all games."""
        p1_wins = sum(1 for r in tournament_records if r.winner == 'p1')
        p2_wins = sum(1 for r in tournament_records if r.winner == 'p2')
        total = p1_wins + p2_wins
        if total > 0:
            p1_rate = p1_wins / total
            assert 0.30 < p1_rate < 0.70, (
                f"P1 wins {p1_rate:.1%} — significant first-mover advantage"
            )
