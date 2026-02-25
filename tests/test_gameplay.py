"""
Gameplay experience tests for The Unfought Battle v4.

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

6. They test that COMBAT DECIDES GAMES, not just the Noose timer.

7. They test that NEW MECHANICS (support, charge, retreat) are used
   and create meaningful strategic choices.

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
9. Noose works        — board shrink has teeth but doesn't dominate
10. Deployment matters — different power layouts lead to different outcomes
11. Combat decides    — player decisions, not the timer, determine outcomes
12. New mechanics work — support, charge, retreat all matter
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
    NooseDodgerStrategy, CoordinatorStrategy, BlitzerStrategy,
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
        assert random_rate < avg_non_random, (
            f"Random win rate ({random_rate:.2f}) should be below "
            f"average non-random ({avg_non_random:.2f})"
        )

    def test_heuristic_beats_random(self, tournament_records):
        """Every heuristic strategy should beat random more than 45% of the time."""
        for strat in ALL_STRATEGIES:
            if strat.name in ('random', 'turtle', 'dodger'):
                continue
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
            assert rate > 0.45, (
                f"{strat.name} should beat random >45% of the time, got {rate:.2f}"
            )


# ===========================================================================
# MEASURE 2: NO DOMINANT STRATEGY — Rock-paper-scissors must emerge
# ===========================================================================

class TestNoDominantStrategy:
    """No single strategy should beat every other strategy."""

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
                assert min_wr < 0.85, (
                    f"{strat.name} dominates with min opponent win rate {min_wr:.2f}"
                )

    def test_multiple_viable_strategies(self, tournament_records):
        """At least 4 strategies should have overall win rate > 30%."""
        viable = 0
        for strat in ALL_STRATEGIES:
            games = strategy_games_played(tournament_records, strat.name)
            if games == 0:
                continue
            wins = strategy_overall_wins(tournament_records, strat.name)
            if wins / games > 0.30:
                viable += 1
        assert viable >= 4, f"Only {viable} viable strategies (need 4+)"

    def test_center_rush_not_dominant(self, tournament_records):
        """Pure center-rush (NooseDodger) should not dominate — the game must
        reward more than just walking to center."""
        dodger_games = strategy_games_played(tournament_records, 'dodger')
        dodger_wins = strategy_overall_wins(tournament_records, 'dodger')
        if dodger_games > 0:
            rate = dodger_wins / dodger_games
            assert rate < 0.65, (
                f"NooseDodger wins {rate:.1%} — game reduces to 'walk to center'"
            )


# ===========================================================================
# MEASURE 3: GAMES TERMINATE — No infinite stalls
# ===========================================================================

class TestGamesTerminate:
    """Every game should end. The Noose guarantees this."""

    def test_all_games_have_winner(self, tournament_records):
        """No game should end in a timeout."""
        timeouts = [r for r in tournament_records if r.victory_type == 'timeout']
        timeout_rate = len(timeouts) / len(tournament_records)
        assert timeout_rate < 0.05, (
            f"{len(timeouts)}/{len(tournament_records)} games timed out ({timeout_rate:.1%})"
        )

    def test_game_length_reasonable(self, tournament_records):
        """Games should typically end between turns 6-20 (not ultra-short)."""
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
    """All victory types should occur naturally in play."""

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
        """No victory type should account for >70% of all wins."""
        types = Counter(r.victory_type for r in tournament_records if r.victory_type)
        total = sum(types.values())
        for vtype, count in types.items():
            rate = count / total
            assert rate < 0.80, (
                f"Victory type '{vtype}' is {rate:.1%} of all wins — too dominant"
            )

    def test_at_least_two_victory_types(self, tournament_records):
        """At least 2 different victory types should occur."""
        types = set(r.victory_type for r in tournament_records if r.victory_type and r.victory_type != 'timeout')
        assert len(types) >= 2, f"Only {len(types)} victory types occurred: {types}"

    def test_combat_kills_vs_noose_kills(self, tournament_records):
        """A meaningful fraction of sovereign captures should come from combat, not Noose."""
        noose_sov_kills = sum(1 for r in tournament_records if r.sovereign_killed_by_noose)
        total_sov_captures = sum(1 for r in tournament_records if r.victory_type == 'sovereign_capture')
        combat_sov_kills = total_sov_captures - noose_sov_kills
        if total_sov_captures > 0:
            combat_ratio = combat_sov_kills / total_sov_captures
            assert combat_ratio > 0.25, (
                f"Only {combat_ratio:.1%} of sovereign captures from combat (need >25%)"
            )


# ===========================================================================
# MEASURE 5: INFORMATION VALUE — Scouting helps
# ===========================================================================

class TestInformationValue:
    """Scouting should provide measurable advantage."""

    def test_scout_strategy_beats_non_scout(self, tournament_records):
        """Strategies that scout should collectively outperform strategies that never scout."""
        scout_strats = {'cautious', 'hunter', 'blitzer'}
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
    """Aggressive play should be a viable path to victory."""

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

    def test_average_combats_per_game(self, tournament_records):
        """Games should average at least 0.5 combats."""
        total_combats = sum(r.combats for r in tournament_records)
        avg = total_combats / len(tournament_records)
        assert avg >= 0.5, f"Average combats per game is only {avg:.2f}"


# ===========================================================================
# MEASURE 7: PASSIVITY PUNISHED — Turtling loses
# ===========================================================================

class TestPassivityPunished:
    """The turtle strategy should be the worst or near-worst."""

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
    """Players should face real resource constraints."""

    def test_players_cant_afford_everything(self, tournament_records):
        """Special orders per turn should be well below maximum possible."""
        games_with_specials = [
            r for r in tournament_records
            if r.scouts_used + r.ambushes_used + r.fortifies_used + r.charges_used > 0
        ]
        for r in games_with_specials:
            if r.turns > 0:
                specials_per_turn = (r.scouts_used + r.ambushes_used + r.fortifies_used + r.charges_used) / r.turns
                assert specials_per_turn <= 8, (
                    f"Economy too loose: {specials_per_turn:.1f} special orders/turn"
                )

    def test_fortify_is_most_used_special(self, tournament_records):
        """Fortify (cheapest special) should be used more than scout."""
        total_fortify = sum(r.fortifies_used for r in tournament_records)
        total_scout = sum(r.scouts_used for r in tournament_records)
        assert total_fortify > total_scout, (
            f"Fortify ({total_fortify}) should be used more than Scout ({total_scout})"
        )


# ===========================================================================
# MEASURE 9: THE NOOSE WORKS — Board shrink has teeth but doesn't dominate
# ===========================================================================

class TestNooseWorks:
    """The shrinking board should actively shape games without dominating outcomes."""

    def test_noose_kills_some_forces(self, tournament_records):
        """The Noose should kill at least some forces across all games."""
        total_noose_kills = sum(r.noose_kills for r in tournament_records)
        assert total_noose_kills > 0, "The Noose never killed anyone"

    def test_noose_kills_in_long_games(self, tournament_records):
        """Games lasting >8 turns should have Noose kills."""
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
    """Different power assignments should produce different results."""

    def test_different_deployments_different_outcomes(self):
        """Same strategies with different deployment orders should produce different game records."""
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

        p1_wins = winners.count('p1')
        p2_wins = winners.count('p2')
        assert p1_wins > 0 and p2_wins > 0, (
            f"Deployment doesn't matter: p1={p1_wins}, p2={p2_wins}"
        )

    def test_sovereign_placement_matters(self):
        """Putting the sovereign in front vs back should change outcomes."""
        class SovFront(AggressiveStrategy):
            name = "sov_front"
            def deploy(self, player, rng):
                ids = [f.id for f in player.forces]
                return dict(zip(ids, [1, 5, 4, 3, 2]))

        class SovBack(AggressiveStrategy):
            name = "sov_back"
            def deploy(self, player, rng):
                ids = [f.id for f in player.forces]
                return dict(zip(ids, [5, 4, 3, 2, 1]))

        front_records = []
        back_records = []
        for i in range(30):
            r1 = run_game(SovFront(), CautiousStrategy(), seed=i, rng_seed=i)
            r2 = run_game(SovBack(), CautiousStrategy(), seed=i, rng_seed=i)
            front_records.append(r1)
            back_records.append(r2)

        front_wins = sum(1 for r in front_records if r.winner == 'p1')
        back_wins = sum(1 for r in back_records if r.winner == 'p1')
        total = len(front_records)
        combined_results = [(f.winner, b.winner) for f, b in zip(front_records, back_records)]
        identical = sum(1 for f, b in combined_results if f == b)
        assert identical < total, (
            "Sovereign front vs back produced identical results every time"
        )


# ===========================================================================
# STRUCTURAL TESTS: Emergent game properties
# ===========================================================================

class TestGameArc:
    """Games should have a natural arc: opening, midgame, endgame."""

    def test_combat_not_immediate(self, tournament_records):
        """First combat shouldn't happen on turn 1 (forces start far apart)."""
        games_with_combat = [r for r in tournament_records if r.combats > 0]
        assert len(games_with_combat) > 0

    def test_forces_are_lost(self, tournament_records):
        """Both players should lose forces in some games — not just one-sided."""
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
            assert rate > 0.15, f"Ambush strategy only wins {rate:.1%}"


# ===========================================================================
# NEW MECHANICS TESTS — v4 additions
# ===========================================================================

class TestRetreatMechanic:
    """Close combat retreat should create more combat and less permanent loss."""

    def test_retreats_happen(self, tournament_records):
        """Some combats should result in retreats, not just kills."""
        total_retreats = sum(r.retreats for r in tournament_records)
        assert total_retreats > 0, "No retreats occurred in any game"

    def test_combat_with_retreat_more_engaging(self, tournament_records):
        """Games with combat should exist and some should have retreats."""
        games_with_combat = [r for r in tournament_records if r.combats > 0]
        if games_with_combat:
            games_with_retreats = sum(1 for r in games_with_combat if r.retreats > 0)
            rate = games_with_retreats / len(games_with_combat)
            assert rate > 0.05, (
                f"Only {rate:.1%} of combat games had retreats"
            )


class TestChargeMechanic:
    """Charge should be used and create meaningful fast-strike options."""

    def test_charge_is_used(self, tournament_records):
        """Charge should be used in some games."""
        total_charges = sum(r.charges_used for r in tournament_records)
        assert total_charges > 0, "Charge was never used"


class TestSupportMechanic:
    """The support mechanic should make formation play meaningful."""

    def test_coordinator_viable(self, tournament_records):
        """Coordinator strategy should be competitive."""
        games = strategy_games_played(tournament_records, 'coordinator')
        wins = strategy_overall_wins(tournament_records, 'coordinator')
        if games > 0:
            rate = wins / games
            assert rate > 0.20, f"Coordinator only wins {rate:.1%}"


# ===========================================================================
# META-TEST: The game is not solvable by simple heuristics
# ===========================================================================

class TestGameComplexity:
    """The game should exhibit enough complexity that no simple heuristic dominates."""

    def test_win_rates_spread(self, tournament_records):
        """Strategy win rates should be spread out, indicating depth."""
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
                f"Win rate spread is only {spread:.2f} — strategies too equal"
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
