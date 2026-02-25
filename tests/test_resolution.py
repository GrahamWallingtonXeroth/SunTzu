"""Tests for v5 combat resolution: power values + variance + ambush + charge + support + retreat."""

import pytest
import random
from resolution import resolve_combat, calculate_effective_power
from state import GameState
from orders import is_adjacent
from models import Force, Player, Hex


def make_combat_state():
    """Create a minimal game state for combat testing."""
    p1 = Player(id='p1', shih=6, max_shih=10)
    p2 = Player(id='p2', shih=6, max_shih=10)
    game = GameState(
        game_id='test', turn=1, phase='resolve',
        players=[p1, p2],
        map_data={
            (3, 3): Hex(q=3, r=3, terrain='Open'),
            (4, 3): Hex(q=4, r=3, terrain='Open'),
            (3, 4): Hex(q=3, r=4, terrain='Difficult'),
            (4, 4): Hex(q=4, r=4, terrain='Contentious'),
            (2, 3): Hex(q=2, r=3, terrain='Open'),
            (3, 2): Hex(q=3, r=2, terrain='Open'),
            (2, 4): Hex(q=2, r=4, terrain='Open'),
            (5, 3): Hex(q=5, r=3, terrain='Open'),
        },
    )
    return game


class TestEffectivePower:
    def test_base_power(self):
        game = make_combat_state()
        f = Force(id='p1_f1', position=(3, 3), power=5)
        game.players[0].add_force(f)
        # No variance for deterministic testing
        power = calculate_effective_power(f, game, apply_variance=False)
        assert power == 5

    def test_fortify_bonus(self):
        game = make_combat_state()
        f = Force(id='p1_f1', position=(3, 3), power=2, fortified=True)
        game.players[0].add_force(f)
        power = calculate_effective_power(f, game, apply_variance=False)
        assert power == 4  # 2 base + 2 fortify

    def test_ambush_bonus_for_defender(self):
        game = make_combat_state()
        f = Force(id='p1_f1', position=(3, 3), power=2, ambushing=True)
        game.players[0].add_force(f)
        power = calculate_effective_power(f, game, is_defender=True, apply_variance=False)
        assert power == 3  # 2 base + 1 ambush

    def test_ambush_no_bonus_for_attacker(self):
        game = make_combat_state()
        f = Force(id='p1_f1', position=(3, 3), power=2, ambushing=True)
        game.players[0].add_force(f)
        power = calculate_effective_power(f, game, is_defender=False, apply_variance=False)
        assert power == 2  # Ambush only works when defending

    def test_difficult_terrain_defense_bonus(self):
        game = make_combat_state()
        f = Force(id='p1_f1', position=(3, 4), power=2)
        game.players[0].add_force(f)
        power = calculate_effective_power(f, game, is_defender=True, hex_pos=(3, 4), apply_variance=False)
        assert power == 3  # 2 base + 1 difficult terrain

    def test_all_bonuses_stack(self):
        game = make_combat_state()
        f = Force(id='p1_f1', position=(3, 4), power=1, fortified=True, ambushing=True)
        game.players[0].add_force(f)
        power = calculate_effective_power(f, game, is_defender=True, hex_pos=(3, 4), apply_variance=False)
        # 1 base + 2 fortify + 1 ambush + 1 difficult = 5
        assert power == 5

    def test_variance_in_range(self):
        game = make_combat_state()
        f = Force(id='p1_f1', position=(3, 3), power=3)
        game.players[0].add_force(f)
        rng = random.Random(42)
        power = calculate_effective_power(f, game, apply_variance=True, rng=rng)
        assert power in [1, 2, 3, 4, 5]  # 3 + variance(-2..+2)


class TestCombatResolution:
    def test_higher_power_wins(self):
        """Power 5 vs 1 — attacker should always win (kill or retreat the defender)."""
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=5)
        dfd = Force(id='p2_f1', position=(4, 3), power=1)
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        rng = random.Random(100)
        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        assert 'attacker_wins' in result['outcome']
        assert att.position == (4, 3)

    def test_combat_reveals_both_powers(self):
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=5)
        dfd = Force(id='p2_f1', position=(4, 3), power=2)
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        rng = random.Random(42)
        resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        assert att.revealed is True
        assert dfd.revealed is True

    def test_both_players_learn_powers(self):
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=5)
        dfd = Force(id='p2_f1', position=(4, 3), power=3)
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        rng = random.Random(42)
        resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        assert p1.known_enemy_powers['p2_f1'] == 3
        assert p2.known_enemy_powers['p1_f1'] == 5

    def test_sovereign_capture(self):
        """Power 5 vs Sovereign (1): sovereign should be killable across trials."""
        captured = False
        for seed in range(20):
            game = make_combat_state()
            att = Force(id='p1_f1', position=(3, 3), power=5)
            dfd = Force(id='p2_f1', position=(4, 3), power=1)  # Sovereign
            game.players[0].add_force(att)
            game.players[1].add_force(dfd)
            rng = random.Random(seed)
            result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
            if result['sovereign_captured'] is not None:
                assert result['sovereign_captured']['winner'] == 'p1'
                assert result['sovereign_captured']['loser'] == 'p2'
                captured = True
                break
        assert captured, "Power 5 never captured Sovereign across 20 trials"

    def test_fortified_defender_wins(self):
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=1)
        dfd = Force(id='p2_f1', position=(4, 3), power=3, fortified=True)  # 3+2=5
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        # Base: att=1 vs def=5 (3+fortify). Diff=4. Defender wins even with worst variance swing.
        rng = random.Random(100)
        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        assert result['outcome'] in ('defender_wins', 'defender_wins_retreat')

    def test_ambush_defender_bonus(self):
        """Ambushing defender with power 2 gets +1, making effective 3 vs attacker power 1."""
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=1)
        dfd = Force(id='p2_f1', position=(4, 3), power=2, ambushing=True)  # 2+1=3
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        # Base: att=1 vs def=3 (2+ambush). Diff=2. Even with worst variance swing, defender favored.
        rng = random.Random(100)
        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        assert result['outcome'] in ('defender_wins', 'defender_wins_retreat')

    def test_variance_can_cause_upset(self):
        """Run many combats: a weaker force should sometimes beat a stronger one."""
        wins_for_weaker = 0
        trials = 100
        for i in range(trials):
            game = make_combat_state()
            att = Force(id='p1_f1', position=(3, 3), power=4)
            dfd = Force(id='p2_f1', position=(4, 3), power=3)
            game.players[0].add_force(att)
            game.players[1].add_force(dfd)
            rng = random.Random(i)
            result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
            if result['outcome'] in ('defender_wins', 'defender_wins_retreat'):
                wins_for_weaker += 1
        # The weaker side should win SOME of the time (not zero)
        assert wins_for_weaker > 0
        # But not most of the time
        assert wins_for_weaker < trials * 0.5


class TestSupportBonus:
    def test_support_bonus_from_adjacent_friendly(self):
        """Adjacent friendly force adds +1 support bonus."""
        game = make_combat_state()
        f1 = Force(id='p1_f1', position=(3, 3), power=3)
        f2 = Force(id='p1_f2', position=(2, 3), power=4)  # Adjacent to (3,3)
        game.players[0].add_force(f1)
        game.players[0].add_force(f2)
        friendly = game.players[0].get_alive_forces()
        power = calculate_effective_power(
            f1, game, apply_variance=False, friendly_forces=friendly
        )
        assert power == 4  # 3 base + 1 support

    def test_support_bonus_max_cap(self):
        """Support bonus is capped at +2 even with 3+ adjacent friendlies."""
        game = make_combat_state()
        f1 = Force(id='p1_f1', position=(3, 3), power=2)
        f2 = Force(id='p1_f2', position=(2, 3), power=4)  # Adjacent
        f3 = Force(id='p1_f3', position=(3, 2), power=5)  # Adjacent
        f4 = Force(id='p1_f4', position=(4, 3), power=3)  # Adjacent (3 friendlies)
        game.players[0].add_force(f1)
        game.players[0].add_force(f2)
        game.players[0].add_force(f3)
        game.players[0].add_force(f4)
        friendly = game.players[0].get_alive_forces()
        power = calculate_effective_power(
            f1, game, apply_variance=False, friendly_forces=friendly
        )
        assert power == 4  # 2 base + 2 max support (capped)

    def test_no_support_from_non_adjacent(self):
        """Friendly forces that are not adjacent don't give support bonus."""
        game = make_combat_state()
        f1 = Force(id='p1_f1', position=(3, 3), power=3)
        f2 = Force(id='p1_f2', position=(5, 3), power=4)  # Distance 2, not adjacent
        game.players[0].add_force(f1)
        game.players[0].add_force(f2)
        friendly = game.players[0].get_alive_forces()
        power = calculate_effective_power(
            f1, game, apply_variance=False, friendly_forces=friendly
        )
        assert power == 3  # No support bonus

    def test_no_support_when_no_friendly_forces_arg(self):
        """Without friendly_forces parameter, no support bonus is applied."""
        game = make_combat_state()
        f1 = Force(id='p1_f1', position=(3, 3), power=3)
        f2 = Force(id='p1_f2', position=(2, 3), power=4)
        game.players[0].add_force(f1)
        game.players[0].add_force(f2)
        power = calculate_effective_power(
            f1, game, apply_variance=False
        )
        assert power == 3  # No support bonus — friendly_forces not passed

    def test_dead_friendly_no_support(self):
        """Dead friendly forces don't provide support bonus."""
        game = make_combat_state()
        f1 = Force(id='p1_f1', position=(3, 3), power=3)
        f2 = Force(id='p1_f2', position=(2, 3), power=4, alive=False)
        game.players[0].add_force(f1)
        game.players[0].add_force(f2)
        friendly = game.players[0].get_alive_forces()
        power = calculate_effective_power(
            f1, game, apply_variance=False, friendly_forces=friendly
        )
        assert power == 3  # Dead ally doesn't count


class TestRetreatMechanic:
    def test_close_combat_defender_retreats_alive(self):
        """When power diff <= 1, losing defender retreats instead of dying."""
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=4)
        dfd = Force(id='p2_f1', position=(4, 3), power=3)
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        # Seed 0: both get +1 → 5 vs 4, diff=1 → attacker wins with retreat
        rng = random.Random(0)
        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        assert result['outcome'] == 'attacker_wins_retreat'
        assert dfd.alive is True
        assert dfd.position != (4, 3)  # Retreated away from combat hex

    def test_decisive_combat_kills_loser(self):
        """When power diff > retreat_threshold (2), loser is eliminated."""
        killed = False
        for seed in range(20):
            game = make_combat_state()
            att = Force(id='p1_f1', position=(3, 3), power=5)
            dfd = Force(id='p2_f1', position=(4, 3), power=1)
            game.players[0].add_force(att)
            game.players[1].add_force(dfd)
            rng = random.Random(seed)
            result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
            if result['outcome'] == 'attacker_wins' and not dfd.alive:
                killed = True
                break
        assert killed, "Power 5 vs 1 never produced a decisive kill across 20 trials"

    def test_close_combat_attacker_retreats_alive(self):
        """When defender wins by <= 1 power diff, attacker retreats alive."""
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=3)
        dfd = Force(id='p2_f1', position=(4, 3), power=4)
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        # Seed 0: both +1 → 4 vs 5, diff=1, defender wins with retreat
        rng = random.Random(0)
        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        assert result['outcome'] == 'defender_wins_retreat'
        assert att.alive is True

    def test_stalemate_both_survive(self):
        """Equal effective power results in stalemate — both survive."""
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=3)
        dfd = Force(id='p2_f1', position=(4, 3), power=3)
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        # Seed 0: both get +1 → 4 vs 4, stalemate
        rng = random.Random(0)
        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        assert result['outcome'] == 'stalemate'
        assert att.alive is True
        assert dfd.alive is True

    def test_retreated_sovereign_not_captured(self):
        """A Sovereign that retreats (power diff ≤ 1) is NOT captured."""
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=2)
        dfd = Force(id='p2_f1', position=(4, 3), power=1)  # Sovereign
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        # Seed 0: both +1 → 3 vs 2, diff=1 → retreat (not kill)
        rng = random.Random(0)
        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        assert result['outcome'] == 'attacker_wins_retreat'
        assert dfd.alive is True
        assert result['sovereign_captured'] is None
