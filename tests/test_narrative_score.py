"""
Narrative Score: Steering toward "Chess for the AI Age."

Chess is the greatest strategy game ever made because every game tells a unique
story — the Immortal Game, the Opera Game, Kasparov-Deep Blue Game 6. But chess
has a fatal weakness: it's calculable. Perfect information + deterministic
outcomes = a game AI can solve.

This harness measures two things:
1. NARRATIVE RICHNESS — Does each game tell a unique, dramatic story?
2. ANTI-CALCULABILITY — Does the game resist being "solved" by brute-force
   computation?

The goal: build a game with chess's strength (infinite narrative diversity)
but not its weakness (vulnerability to calculation).

=== THE THEORY ===

Narrative emerges from the INTERACTION OF CONSEQUENTIAL DECISIONS OVER TIME.
A game with 7 turns and one dominant strategy tells one story. A game with
20 turns, multiple viable plans, and hidden information tells thousands.

Chess's narrative comes from:
  - Enough moves for a plot to develop (avg 40 moves/side)
  - Phase transitions (opening → middlegame → endgame) that change the
    character of play, creating "chapters"
  - Advantage oscillation — the lead changes, creating dramatic tension
  - Decisive moments that bifurcate the game tree — "if he'd played Nf6
    instead..." creates the sense that THIS game is unique
  - Comeback potential — being behind doesn't mean it's over

Anti-calculability comes from:
  - Hidden information that changes the optimal decision (not just noise)
  - Opponent modeling that matters more than raw search depth
  - Strategic uncertainty — even with perfect play, outcomes aren't certain
  - Diminishing returns from deeper computation

We measure each of these as a 0-10 score, just like the Fun Score.
The Narrative Score is the compass. The Fun Score is the checklist.

=== DIMENSIONS ===

NARRATIVE RICHNESS:
  N1. Arc Length — Enough turns for a story to develop?
  N2. Lead Changes — Does the advantage oscillate (drama)?
  N3. Decisive Moments — Are kills spread across the game (multiple crises)?
  N4. Story Diversity — Do games fall into many different archetypes?
  N5. Comeback Viability — Can the losing side still win?
  N6. Phase Transitions — Does the character of play change over time?

ANTI-CALCULABILITY:
  A1. Fog Persistence — How much stays hidden throughout the game?
  A2. Information-Action Coupling — Does hidden info change decisions?
  A3. Outcome Uncertainty — Given same strategies, how unpredictable is the winner?
  A4. Counter-Strategy Reward — Does reading the opponent matter?
"""

import math
import random
import itertools
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.simulate import (
    run_game, run_tournament, GameRecord, Strategy,
    RandomStrategy, AggressiveStrategy, CautiousStrategy,
    AmbushStrategy, TurtleStrategy, SovereignHunterStrategy,
    NooseDodgerStrategy, CoordinatorStrategy, BlitzerStrategy,
    ALL_STRATEGIES, STRATEGY_MAP,
)


# ---------------------------------------------------------------------------
# Shared data
# ---------------------------------------------------------------------------

GAMES_PER_MATCHUP = 40
MAP_SEEDS = list(range(GAMES_PER_MATCHUP))
COMPETITIVE_NAMES = {s.name for s in ALL_STRATEGIES if s.name not in ('turtle', 'random')}


def _run_competitive_tournament():
    all_records = run_tournament(ALL_STRATEGIES, games_per_matchup=GAMES_PER_MATCHUP, map_seeds=MAP_SEEDS)
    competitive = [r for r in all_records
                   if r.p1_strategy in COMPETITIVE_NAMES and r.p2_strategy in COMPETITIVE_NAMES]
    return all_records, competitive


def _clamp(val, lo=0.0, hi=10.0):
    return max(lo, min(hi, val))


# ---------------------------------------------------------------------------
# Advantage estimation (the "who's winning" heuristic)
# ---------------------------------------------------------------------------

def _advantage(snap: Dict) -> float:
    """
    Estimate P1's advantage from a turn snapshot. Positive = P1 ahead.

    Combines:
    - Force count (each force worth 2 points)
    - Power sum (raw combat potential)
    - Contentious hex control (positional advantage)

    This is deliberately rough. The point isn't perfect evaluation — it's
    detecting CHANGES in who's ahead, which is what creates narrative.
    """
    force_adv = (snap['p1_alive'] - snap['p2_alive']) * 2.0
    power_adv = (snap['p1_power_sum'] - snap['p2_power_sum']) * 0.5
    territory_adv = (snap['p1_contentious'] - snap['p2_contentious']) * 1.5
    return force_adv + power_adv + territory_adv


def _advantage_series(record: GameRecord) -> List[float]:
    """Return the advantage at each turn. Positive = P1 ahead."""
    return [_advantage(s) for s in record.turn_snapshots]


# ===================================================================
# N1. ARC LENGTH — Enough turns for a story to develop?
# ===================================================================

def score_arc_length(records: List[GameRecord]) -> Tuple[float, str]:
    """
    Chess averages ~80 half-moves. That's enough for opening, middlegame,
    endgame — three distinct acts. Our game needs enough turns for at least
    two phase transitions.

    Measures:
    - Average game length (target: 12-18 turns)
    - % of games reaching "midgame" (turn 8+, target: >60%)
    - % of games reaching "late game" (turn 14+, target: >25%)

    Current v8 reality: 7.2 turns avg, 27% midgame, 8% late. This is the
    single biggest problem. You can't tell a story in 7 turns.
    """
    if not records:
        return 0.0, "No data"

    turns = [r.turns for r in records]
    avg = sum(turns) / len(turns)
    midgame_pct = sum(1 for t in turns if t >= 8) / len(turns)
    lategame_pct = sum(1 for t in turns if t >= 14) / len(turns)

    # Average length score: peak at 12-18 turns
    if avg < 5:
        len_score = avg / 5.0 * 2.0  # 0-2 for very short games
    elif avg < 8:
        len_score = 2.0 + (avg - 5) / 3.0 * 3.0  # 2-5 for short games
    elif avg < 12:
        len_score = 5.0 + (avg - 8) / 4.0 * 3.0  # 5-8 for approaching target
    elif avg <= 18:
        len_score = 8.0 + (avg - 12) / 6.0 * 2.0  # 8-10 for sweet spot
    else:
        len_score = 10.0 - (avg - 18) / 7.0 * 3.0  # decay if too long

    # Midgame reach score
    mid_score = min(midgame_pct / 0.60 * 10.0, 10.0)

    # Late game score
    late_score = min(lategame_pct / 0.25 * 10.0, 10.0)

    score = len_score * 0.4 + mid_score * 0.35 + late_score * 0.25
    detail = (f"avg_turns={avg:.1f}, midgame_reach={midgame_pct:.1%}, "
              f"lategame_reach={lategame_pct:.1%}")
    return _clamp(score), detail


# ===================================================================
# N2. LEAD CHANGES — Does the advantage oscillate?
# ===================================================================

def score_lead_changes(records: List[GameRecord]) -> Tuple[float, str]:
    """
    A game where P1 is ahead from turn 1 to the end is a boring story.
    "He was winning, then he won." Great games have reversals: "She was
    losing, then she found the key weakness and turned it around."

    Measures: average number of lead changes per game.
    A "lead change" = advantage flips sign between consecutive turns.

    Target: 1.0-3.0 lead changes per game on average.
    Below 0.5 = the game is decided too early (monotonic advantage).
    Above 4.0 = advantage is just noise, not meaningful.
    """
    if not records:
        return 0.0, "No data"

    changes_list = []
    for r in records:
        series = _advantage_series(r)
        if len(series) < 2:
            changes_list.append(0)
            continue
        changes = 0
        for i in range(1, len(series)):
            # Lead change: sign flip (ignore 0 = tied)
            if series[i - 1] != 0 and series[i] != 0:
                if (series[i - 1] > 0) != (series[i] > 0):
                    changes += 1
        changes_list.append(changes)

    avg_changes = sum(changes_list) / len(changes_list)
    pct_with_change = sum(1 for c in changes_list if c > 0) / len(changes_list)

    # Score: peak at 1.5-3.0 lead changes
    if avg_changes < 0.3:
        change_score = avg_changes / 0.3 * 2.0
    elif avg_changes < 1.0:
        change_score = 2.0 + (avg_changes - 0.3) / 0.7 * 4.0
    elif avg_changes <= 3.0:
        change_score = 6.0 + (avg_changes - 1.0) / 2.0 * 4.0
    else:
        change_score = 10.0 - (avg_changes - 3.0) / 3.0 * 4.0

    # Bonus for breadth: what % of games have at least one lead change?
    breadth_score = min(pct_with_change / 0.50 * 10.0, 10.0)

    score = change_score * 0.7 + breadth_score * 0.3
    detail = (f"avg_lead_changes={avg_changes:.2f}, "
              f"games_with_changes={pct_with_change:.1%}")
    return _clamp(score), detail


# ===================================================================
# N3. DECISIVE MOMENTS — Are kills spread across the game?
# ===================================================================

def score_decisive_moments(records: List[GameRecord]) -> Tuple[float, str]:
    """
    A game where all 3 kills happen on turn 5 has one crisis. A game where
    forces die on turns 4, 8, and 12 has three crises — three moments where
    the narrative could have gone differently. Spread = more story beats.

    Measures: what fraction of turns in each game have at least one kill?
    Target: kills spread across 30-50% of turns (not clustered).
    """
    if not records:
        return 0.0, "No data"

    spreads = []
    for r in records:
        if not r.turn_snapshots or r.turns <= 1:
            continue
        turns_with_kills = sum(
            1 for s in r.turn_snapshots
            if s.get('p1_killed_this_turn', 0) + s.get('p2_killed_this_turn', 0) > 0
        )
        total_turns = len(r.turn_snapshots)
        if total_turns > 0:
            spreads.append(turns_with_kills / total_turns)

    if not spreads:
        return 0.0, "No games with snapshots"

    avg_spread = sum(spreads) / len(spreads)

    # Also measure: how many distinct "crisis turns" per game on average?
    total_kills_per_game = [
        (r.p1_forces_lost + r.p2_forces_lost) for r in records
    ]
    avg_kills = sum(total_kills_per_game) / len(total_kills_per_game)
    crisis_per_game = avg_spread * sum(r.turns for r in records) / len(records)

    # Score: peak at 30-50% spread
    if avg_spread < 0.10:
        spread_score = avg_spread / 0.10 * 3.0
    elif avg_spread < 0.30:
        spread_score = 3.0 + (avg_spread - 0.10) / 0.20 * 4.0
    elif avg_spread <= 0.50:
        spread_score = 7.0 + (avg_spread - 0.30) / 0.20 * 3.0
    else:
        spread_score = 10.0 - (avg_spread - 0.50) / 0.30 * 3.0

    # Bonus: games with 2+ distinct kill turns
    multi_crisis = sum(1 for r in records
                       if r.turn_snapshots and
                       sum(1 for s in r.turn_snapshots
                           if s.get('p1_killed_this_turn', 0) + s.get('p2_killed_this_turn', 0) > 0
                           ) >= 2) / max(len(records), 1)
    crisis_score = min(multi_crisis / 0.40 * 10.0, 10.0)

    score = spread_score * 0.6 + crisis_score * 0.4
    detail = (f"kill_spread={avg_spread:.1%}, avg_kills={avg_kills:.1f}/game, "
              f"multi_crisis_games={multi_crisis:.1%}")
    return _clamp(score), detail


# ===================================================================
# N4. STORY DIVERSITY — Do games fall into distinct archetypes?
# ===================================================================

def _classify_game(r: GameRecord) -> str:
    """
    Classify a game into a narrative archetype based on its features.

    Archetypes:
    - "blitz": Short game (<=5 turns), sovereign captured
    - "assassination": Sovereign captured after scouting (turns 6+)
    - "siege": Domination victory (positional stranglehold)
    - "attrition": Elimination victory or 3+ forces killed
    - "reversal": The player who was behind early won
    - "noose_drama": Noose killed forces or nearly ended the game
    - "stalemate": Timeout or mutual destruction
    """
    if r.victory_type == 'timeout' or r.victory_type == 'mutual_destruction':
        return 'stalemate'

    if r.noose_kills > 0 or r.sovereign_killed_by_noose:
        return 'noose_drama'

    if r.victory_type == 'domination':
        return 'siege'

    if r.victory_type == 'elimination':
        return 'attrition'

    # Check for reversal: was the winner behind at the midpoint?
    series = _advantage_series(r)
    if len(series) >= 3:
        mid = len(series) // 2
        mid_adv = series[mid]
        winner_is_p1 = r.winner == 'p1'
        if (winner_is_p1 and mid_adv < -1.5) or (not winner_is_p1 and mid_adv > 1.5):
            return 'reversal'

    # Short sovereign capture = blitz
    if r.victory_type == 'sovereign_capture' and r.turns <= 5:
        return 'blitz'

    # Longer sovereign capture = assassination
    if r.victory_type == 'sovereign_capture':
        return 'assassination'

    # Fallback: high-attrition games
    if r.p1_forces_lost + r.p2_forces_lost >= 3:
        return 'attrition'

    return 'blitz'


def score_story_diversity(records: List[GameRecord]) -> Tuple[float, str]:
    """
    If every game is "rush sovereign, kill on turn 5," there's one story.
    If games split across blitz, assassination, siege, reversal, attrition,
    and noose_drama, there are six stories. Players will retell the unusual
    ones — "remember that game where the Noose forced us both into the center?"

    Measures: Shannon entropy of archetype distribution.
    Target: >2.0 bits (at least 4 roughly-equal archetypes).
    """
    if not records:
        return 0.0, "No data"

    archetypes = [_classify_game(r) for r in records]
    counts = Counter(archetypes)
    total = len(archetypes)

    # Shannon entropy
    entropy = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)

    # Max possible entropy for 7 archetypes = log2(7) ≈ 2.81
    max_entropy = math.log2(7)

    # Score: peak at >2.0 bits
    if entropy < 0.5:
        ent_score = entropy / 0.5 * 2.0
    elif entropy < 1.5:
        ent_score = 2.0 + (entropy - 0.5) / 1.0 * 4.0
    elif entropy <= 2.5:
        ent_score = 6.0 + (entropy - 1.5) / 1.0 * 4.0
    else:
        ent_score = 10.0

    # Bonus: number of archetypes that appear in >5% of games
    active_types = sum(1 for c in counts.values() if c / total > 0.05)
    type_score = min(active_types / 5.0 * 10.0, 10.0)

    score = ent_score * 0.6 + type_score * 0.4
    dist_str = ", ".join(f"{k}={v}" for k, v in counts.most_common())
    detail = (f"entropy={entropy:.2f}/{max_entropy:.2f} bits, "
              f"active_types={active_types}, dist=[{dist_str}]")
    return _clamp(score), detail


# ===================================================================
# N5. COMEBACK VIABILITY — Can the losing side still win?
# ===================================================================

def score_comeback_viability(records: List[GameRecord]) -> Tuple[float, str]:
    """
    If the player who's ahead at the midpoint always wins, the game is
    decided too early. The second half is just going through the motions.
    But if the player who's behind has ~25% chance of winning, every game
    stays tense until the end.

    Chess: a player who's a pawn down still wins ~35% of GM games.
    That's the sweet spot — being behind matters, but isn't fatal.

    Target: 15-35% comeback rate (behind at midpoint but wins).
    """
    if not records:
        return 0.0, "No data"

    behind_wins = 0
    behind_total = 0

    for r in records:
        series = _advantage_series(r)
        if len(series) < 3 or not r.winner or r.winner not in ('p1', 'p2'):
            continue

        mid = len(series) // 2
        mid_adv = series[mid]

        # Skip tied games at midpoint
        if abs(mid_adv) < 0.5:
            continue

        behind_total += 1
        # P1 ahead at mid (positive advantage) but P2 wins = comeback
        # P2 ahead at mid (negative advantage) but P1 wins = comeback
        if (mid_adv > 0 and r.winner == 'p2') or (mid_adv < 0 and r.winner == 'p1'):
            behind_wins += 1

    if behind_total == 0:
        return 5.0, "No games with clear midpoint leader"

    comeback_rate = behind_wins / behind_total

    # Score: peak at 20-35%
    if comeback_rate < 0.05:
        rate_score = comeback_rate / 0.05 * 2.0
    elif comeback_rate < 0.15:
        rate_score = 2.0 + (comeback_rate - 0.05) / 0.10 * 3.0
    elif comeback_rate <= 0.35:
        rate_score = 5.0 + (comeback_rate - 0.15) / 0.20 * 5.0
    elif comeback_rate <= 0.50:
        rate_score = 10.0 - (comeback_rate - 0.35) / 0.15 * 3.0
    else:
        rate_score = 7.0 - (comeback_rate - 0.50) / 0.20 * 4.0  # too swingy

    detail = (f"comeback_rate={comeback_rate:.1%} "
              f"({behind_wins}/{behind_total} games with clear leader at midpoint)")
    return _clamp(rate_score), detail


# ===================================================================
# N6. PHASE TRANSITIONS — Does the character of play change?
# ===================================================================

def score_phase_transitions(records: List[GameRecord]) -> Tuple[float, str]:
    """
    Chess has opening (development), middlegame (tactics), endgame (technique).
    Each phase has different concerns — that's what makes a game feel like a
    journey, not a sprint.

    Measures: KL divergence of order distributions between game thirds.
    If early-game orders look like late-game orders, there are no phases.
    If they're dramatically different, the game has distinct chapters.

    Target: KL divergence > 0.3 between early and late thirds.
    """
    if not records:
        return 0.0, "No data"

    # Only analyze games long enough to have phases (8+ turns)
    long_games = [r for r in records if len(r.turn_snapshots) >= 6]
    if len(long_games) < 20:
        # Not enough long games to measure phases — that's a problem in itself
        pct = len(long_games) / max(len(records), 1)
        return _clamp(pct * 3.0), f"only {len(long_games)} games with 6+ turns ({pct:.1%})"

    order_types = ['move', 'scout', 'fortify', 'ambush', 'charge']

    early_dist = Counter()
    late_dist = Counter()

    for r in long_games:
        snaps = r.turn_snapshots
        third = len(snaps) // 3
        if third == 0:
            continue

        # Early third
        for s in snaps[:third]:
            for ot in order_types:
                for pid in ['p1', 'p2']:
                    early_dist[ot] += s.get(f'{pid}_orders', {}).get(ot, 0)

        # Late third
        for s in snaps[-third:]:
            for ot in order_types:
                for pid in ['p1', 'p2']:
                    late_dist[ot] += s.get(f'{pid}_orders', {}).get(ot, 0)

    # Normalize to probability distributions
    early_total = sum(early_dist.values()) or 1
    late_total = sum(late_dist.values()) or 1

    early_p = {ot: (early_dist[ot] + 0.1) / (early_total + 0.5) for ot in order_types}
    late_p = {ot: (late_dist[ot] + 0.1) / (late_total + 0.5) for ot in order_types}

    # KL divergence: D(early || late)
    kl = sum(early_p[ot] * math.log(early_p[ot] / late_p[ot]) for ot in order_types)
    # Symmetric KL (Jensen-Shannon-like)
    kl_rev = sum(late_p[ot] * math.log(late_p[ot] / early_p[ot]) for ot in order_types)
    js_div = (kl + kl_rev) / 2.0

    # Score: higher divergence = more distinct phases
    if js_div < 0.05:
        div_score = js_div / 0.05 * 2.0
    elif js_div < 0.15:
        div_score = 2.0 + (js_div - 0.05) / 0.10 * 3.0
    elif js_div < 0.30:
        div_score = 5.0 + (js_div - 0.15) / 0.15 * 3.0
    elif js_div <= 0.60:
        div_score = 8.0 + (js_div - 0.30) / 0.30 * 2.0
    else:
        div_score = 10.0

    # Detail: show the actual distributions
    early_str = " ".join(f"{ot}={early_dist[ot]}" for ot in order_types)
    late_str = " ".join(f"{ot}={late_dist[ot]}" for ot in order_types)
    detail = (f"JS_divergence={js_div:.3f}, long_games={len(long_games)}, "
              f"early=[{early_str}], late=[{late_str}]")
    return _clamp(div_score), detail


# ===================================================================
# A1. FOG PERSISTENCE — How much stays hidden throughout the game?
# ===================================================================

def score_fog_persistence(records: List[GameRecord]) -> Tuple[float, str]:
    """
    Hidden information is the foundation of anti-calculability. But it only
    matters if it PERSISTS — if everything is revealed by turn 3, the rest
    of the game is calculable.

    Measures: average fraction of enemy forces whose power is still unknown
    to the opponent, tracked across all turns.

    Target: >30% of enemy forces hidden throughout the average game.
    At game end: >15% still hidden (not everything revealed).
    """
    if not records:
        return 0.0, "No data"

    game_avg_hidden = []
    endgame_hidden = []

    for r in records:
        if not r.turn_snapshots:
            continue

        per_turn_hidden = []
        for s in r.turn_snapshots:
            # Average hidden fraction across both players
            p1_total = s.get('p2_alive', 0)  # forces p1 is trying to read
            p2_total = s.get('p1_alive', 0)  # forces p2 is trying to read
            p1_hidden = s.get('p1_hidden_to_opp', 0)  # p1 forces hidden from p2
            p2_hidden = s.get('p2_hidden_to_opp', 0)  # p2 forces hidden from p1

            # What fraction of the opponent's forces does each player NOT know?
            if p1_total > 0 and p2_total > 0:
                # p2_hidden = forces of p2 that p1 doesn't know
                # p1_hidden = forces of p1 that p2 doesn't know
                frac = (p1_hidden + p2_hidden) / (p1_total + p2_total)
                per_turn_hidden.append(frac)

        if per_turn_hidden:
            game_avg_hidden.append(sum(per_turn_hidden) / len(per_turn_hidden))
            endgame_hidden.append(per_turn_hidden[-1])

    if not game_avg_hidden:
        return 0.0, "No games with hidden info tracking"

    avg_hidden = sum(game_avg_hidden) / len(game_avg_hidden)
    avg_endgame_hidden = sum(endgame_hidden) / len(endgame_hidden)

    # Score: persistent fog
    if avg_hidden < 0.10:
        fog_score = avg_hidden / 0.10 * 2.0
    elif avg_hidden < 0.30:
        fog_score = 2.0 + (avg_hidden - 0.10) / 0.20 * 4.0
    elif avg_hidden <= 0.60:
        fog_score = 6.0 + (avg_hidden - 0.30) / 0.30 * 4.0
    else:
        fog_score = 10.0

    # Endgame hidden bonus
    if avg_endgame_hidden < 0.05:
        end_score = avg_endgame_hidden / 0.05 * 3.0
    elif avg_endgame_hidden < 0.15:
        end_score = 3.0 + (avg_endgame_hidden - 0.05) / 0.10 * 4.0
    elif avg_endgame_hidden <= 0.40:
        end_score = 7.0 + (avg_endgame_hidden - 0.15) / 0.25 * 3.0
    else:
        end_score = 10.0

    score = fog_score * 0.6 + end_score * 0.4
    detail = (f"avg_hidden={avg_hidden:.1%}, endgame_hidden={avg_endgame_hidden:.1%}")
    return _clamp(score), detail


# ===================================================================
# A2. INFORMATION-ACTION COUPLING — Does hidden info change decisions?
# ===================================================================

def score_info_action_coupling(records: List[GameRecord]) -> Tuple[float, str]:
    """
    Hidden information only matters if it changes what players DO. If the
    optimal play is "rush forward regardless," then fog of war is just
    decoration.

    Measures (via ablation): how much worse does NeverScout perform vs
    the full scouting strategy? The bigger the gap, the more hidden
    information is driving decisions.

    Also measures: per-game, do scout results correlate with changed behavior
    in the following turn?

    Target: >15% win rate gap between scout and no-scout strategies.
    """
    # Use the ablation data: Cautious vs NeverScout
    from tests.simulate import NeverScoutVariant

    scout_wins = 0
    total = 0
    n_games = 60

    for i in range(n_games // 2):
        r1 = run_game(CautiousStrategy(), NeverScoutVariant(), seed=i, rng_seed=i * 1000)
        total += 1
        if r1.winner == 'p1':
            scout_wins += 1
        r2 = run_game(NeverScoutVariant(), CautiousStrategy(), seed=i, rng_seed=i * 1000 + 500)
        total += 1
        if r2.winner == 'p2':
            scout_wins += 1

    scout_advantage = scout_wins / total if total > 0 else 0.5

    # The gap above 50% represents how much scouting matters
    gap = scout_advantage - 0.50

    # Score: bigger gap = information drives action more
    if gap < 0.05:
        gap_score = gap / 0.05 * 2.0
    elif gap < 0.15:
        gap_score = 2.0 + (gap - 0.05) / 0.10 * 4.0
    elif gap < 0.30:
        gap_score = 6.0 + (gap - 0.15) / 0.15 * 3.0
    elif gap <= 0.45:
        gap_score = 9.0 + (gap - 0.30) / 0.15 * 1.0
    else:
        gap_score = 10.0

    detail = (f"scout_win_rate={scout_advantage:.1%} vs no_scout, "
              f"gap={gap:.1%}")
    return _clamp(gap_score), detail


# ===================================================================
# A3. OUTCOME UNCERTAINTY — How unpredictable is the winner?
# ===================================================================

def score_outcome_uncertainty(records: List[GameRecord]) -> Tuple[float, str]:
    """
    If the same two strategies play 40 times, what's the split? 30-10 means
    the outcome is 75% predictable — there's some uncertainty but not much.
    20-20 means pure coin flip — too random. 25-15 (62.5%) is the sweet spot.

    This is the ANTI-chess measure. In chess, the better player wins 85%+
    of games. In a game with genuine hidden information and strategic
    uncertainty, even the favored strategy should lose 30-40% of the time.

    Measures: average predictability across all matchups.
    Predictability = max(p1_win%, p2_win%) for each matchup.
    Target: 55-65% average predictability.
    """
    if not records:
        return 0.0, "No data"

    # Group by matchup
    matchups = defaultdict(list)
    for r in records:
        key = tuple(sorted([r.p1_strategy, r.p2_strategy]))
        matchups[key].append(r)

    predictabilities = []
    for key, games in matchups.items():
        decided = [g for g in games if g.winner in ('p1', 'p2')]
        if len(decided) < 4:
            continue

        # Count wins for each strategy
        s1, s2 = key
        s1_wins = sum(1 for g in decided
                      if (g.winner == 'p1' and g.p1_strategy == s1) or
                      (g.winner == 'p2' and g.p2_strategy == s1))
        s1_rate = s1_wins / len(decided)
        predictability = max(s1_rate, 1 - s1_rate)
        predictabilities.append(predictability)

    if not predictabilities:
        return 5.0, "Insufficient matchup data"

    avg_pred = sum(predictabilities) / len(predictabilities)

    # Score: peak at 55-65% predictability
    # Below 52% = too random (coin flip)
    # Above 75% = too deterministic (calculable)
    if avg_pred < 0.52:
        pred_score = 5.0 + (avg_pred - 0.50) / 0.02 * 2.0  # slight penalty for pure chaos
    elif avg_pred < 0.55:
        pred_score = 7.0 + (avg_pred - 0.52) / 0.03 * 1.0
    elif avg_pred <= 0.65:
        pred_score = 8.0 + (avg_pred - 0.55) / 0.10 * 2.0  # sweet spot
    elif avg_pred <= 0.75:
        pred_score = 10.0 - (avg_pred - 0.65) / 0.10 * 4.0
    else:
        pred_score = 6.0 - (avg_pred - 0.75) / 0.15 * 4.0

    # Also measure: upset rate (weaker strategy winning)
    upset_rates = [1 - p for p in predictabilities]
    avg_upset = sum(upset_rates) / len(upset_rates)

    detail = (f"avg_predictability={avg_pred:.1%}, avg_upset_rate={avg_upset:.1%}, "
              f"matchups={len(predictabilities)}")
    return _clamp(pred_score), detail


# ===================================================================
# A4. COUNTER-STRATEGY REWARD — Does reading opponents matter?
# ===================================================================

def score_counter_strategy(records: List[GameRecord]) -> Tuple[float, str]:
    """
    In chess, the best move is (theoretically) the same regardless of who
    you're playing. But in poker, the best play depends on your read of the
    opponent. Games that reward opponent-modeling resist AI because reading
    humans is what humans do best.

    Measures: matchup variance. If strategy A beats B 70% but loses to C 70%,
    then knowing you're facing B vs C completely changes optimal play. High
    variance = opponent modeling matters.

    Target: >12% standard deviation in per-matchup win rates.
    """
    if not records:
        return 0.0, "No data"

    # For each strategy, compute its win rate against each opponent
    strategy_matchup_rates = defaultdict(list)

    matchups = defaultdict(list)
    for r in records:
        key = (r.p1_strategy, r.p2_strategy)
        matchups[key].append(r)

    for (s1, s2), games in matchups.items():
        if s1 == s2:
            continue
        decided = [g for g in games if g.winner in ('p1', 'p2')]
        if len(decided) < 4:
            continue
        s1_wins = sum(1 for g in decided if g.winner == 'p1')
        s1_rate = s1_wins / len(decided)
        strategy_matchup_rates[s1].append(s1_rate)
        strategy_matchup_rates[s2].append(1 - s1_rate)

    # Compute per-strategy variance in matchup win rates
    variances = []
    for strat, rates in strategy_matchup_rates.items():
        if len(rates) >= 3:
            mean = sum(rates) / len(rates)
            var = sum((r - mean) ** 2 for r in rates) / len(rates)
            variances.append(math.sqrt(var))

    if not variances:
        return 5.0, "Insufficient matchup data"

    avg_std = sum(variances) / len(variances)

    # Score: higher std = more matchup-dependent = more opponent-reading
    if avg_std < 0.04:
        std_score = avg_std / 0.04 * 2.0
    elif avg_std < 0.08:
        std_score = 2.0 + (avg_std - 0.04) / 0.04 * 3.0
    elif avg_std < 0.12:
        std_score = 5.0 + (avg_std - 0.08) / 0.04 * 3.0
    elif avg_std <= 0.20:
        std_score = 8.0 + (avg_std - 0.12) / 0.08 * 2.0
    else:
        std_score = 10.0

    detail = (f"avg_matchup_std={avg_std:.3f}, strategies={len(variances)}")
    return _clamp(std_score), detail


# ===================================================================
# COMBINED SCORING
# ===================================================================

def compute_narrative_scores(verbose=True):
    """Run tournament and compute all narrative + anti-calculability scores."""
    all_records, competitive = _run_competitive_tournament()

    scores = {}
    details = {}

    narrative_dims = [
        ("N1. Arc Length", lambda: score_arc_length(competitive)),
        ("N2. Lead Changes", lambda: score_lead_changes(competitive)),
        ("N3. Decisive Moments", lambda: score_decisive_moments(competitive)),
        ("N4. Story Diversity", lambda: score_story_diversity(competitive)),
        ("N5. Comeback Viability", lambda: score_comeback_viability(competitive)),
        ("N6. Phase Transitions", lambda: score_phase_transitions(competitive)),
    ]

    calc_dims = [
        ("A1. Fog Persistence", lambda: score_fog_persistence(competitive)),
        ("A2. Info-Action Coupling", lambda: score_info_action_coupling(competitive)),
        ("A3. Outcome Uncertainty", lambda: score_outcome_uncertainty(competitive)),
        ("A4. Counter-Strategy Reward", lambda: score_counter_strategy(competitive)),
    ]

    for name, scorer in narrative_dims + calc_dims:
        s, d = scorer()
        scores[name] = s
        details[name] = d

    narrative_score = sum(scores[n] for n, _ in narrative_dims) / len(narrative_dims)
    calc_score = sum(scores[n] for n, _ in calc_dims) / len(calc_dims)
    overall = (narrative_score * 0.6 + calc_score * 0.4)

    if verbose:
        print("\n" + "=" * 70)
        print("NARRATIVE SCORE — CHESS FOR THE AI AGE")
        print("=" * 70)

        print("\n  NARRATIVE RICHNESS — Does each game tell a unique story?")
        print("  " + "-" * 60)
        for name, _ in narrative_dims:
            bar = "#" * int(scores[name]) + "." * (10 - int(scores[name]))
            print(f"\n    {name}")
            print(f"      [{bar}] {scores[name]:.1f}/10")
            print(f"      {details[name]}")

        print(f"\n    >>> NARRATIVE RICHNESS: {narrative_score:.1f}/10")

        print("\n  ANTI-CALCULABILITY — Does the game resist being solved?")
        print("  " + "-" * 60)
        for name, _ in calc_dims:
            bar = "#" * int(scores[name]) + "." * (10 - int(scores[name]))
            print(f"\n    {name}")
            print(f"      [{bar}] {scores[name]:.1f}/10")
            print(f"      {details[name]}")

        print(f"\n    >>> ANTI-CALCULABILITY: {calc_score:.1f}/10")

        print(f"\n{'=' * 70}")
        print(f"  OVERALL NARRATIVE SCORE: {overall:.1f}/10")
        print(f"  (Narrative {narrative_score:.1f} x 0.6 + Anti-Calc {calc_score:.1f} x 0.4)")
        print(f"{'=' * 70}")

        # Chess comparison
        print("\n  CHESS COMPARISON (estimated):")
        print("    Chess narrative richness:  ~9.0/10 (40+ moves, deep phases, reversals)")
        print("    Chess anti-calculability:  ~3.0/10 (perfect info, deterministic, solvable)")
        print(f"    Chess overall:             ~6.6/10")
        print(f"    SunTzu overall:            {overall:.1f}/10")
        print(f"    Gap to close:              {max(0, 7.5 - overall):.1f} points to target 7.5")

    return scores, overall, narrative_score, calc_score


# ===================================================================
# PYTEST ENTRY POINTS
# ===================================================================

def test_narrative_score():
    """Compute and display the narrative score. Informational."""
    scores, overall, narrative, calc = compute_narrative_scores(verbose=True)
    assert overall >= 0, "Narrative score computation failed"


def test_narrative_minimum_dimensions():
    """Every narrative dimension must score at least 2.0/10.
    Below 2.0 means the game fundamentally lacks this quality."""
    scores, _, _, _ = compute_narrative_scores(verbose=False)
    for name, score in scores.items():
        assert score >= 2.0, (
            f"Narrative dimension '{name}' scored {score:.1f}/10 — "
            f"below minimum of 2.0. This is a fundamental weakness."
        )


def test_anti_calculability_floor():
    """Anti-calculability must average at least 5.0/10.
    Below 5 means the game is too calculable — AI will dominate humans."""
    scores, _, _, calc = compute_narrative_scores(verbose=False)
    assert calc >= 5.0, (
        f"Anti-calculability score is {calc:.1f}/10 — below minimum of 5.0. "
        f"The game is too solvable by brute-force computation."
    )


if __name__ == "__main__":
    compute_narrative_scores()
