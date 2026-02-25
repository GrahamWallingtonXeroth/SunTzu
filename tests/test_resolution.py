"""Tests for v3 combat resolution: power values + variance + ambush."""

import pytest
import random
from resolution import resolve_combat, calculate_effective_power
from state import GameState
from models import Force, Player, Hex


def make_combat_state():
    """Create a minimal game state for combat testing."""
    p1 = Player(id='p1', shih=5, max_shih=10)
    p2 = Player(id='p2', shih=5, max_shih=10)
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
        assert power == 5  # 2 base + 3 ambush

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
        # 1 base + 2 fortify + 3 ambush + 1 difficult = 7
        assert power == 7

    def test_variance_adds_plus_or_minus_1(self):
        game = make_combat_state()
        f = Force(id='p1_f1', position=(3, 3), power=3)
        game.players[0].add_force(f)
        rng = random.Random(42)
        power = calculate_effective_power(f, game, apply_variance=True, rng=rng)
        assert power in [2, 4]  # 3 +/- 1


class TestCombatResolution:
    def test_higher_power_wins(self):
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=5)
        dfd = Force(id='p2_f1', position=(4, 3), power=1)
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        # Use a fixed RNG where both get +1, so 6 vs 2
        rng = random.Random(100)
        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        # With big power difference, attacker should win regardless of variance
        assert result['outcome'] == 'attacker_wins'
        assert dfd.alive is False
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
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=5)
        dfd = Force(id='p2_f1', position=(4, 3), power=1)  # Sovereign
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        # Use RNG that gives both +1 — 6 vs 2, attacker wins
        rng = random.Random(100)
        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        assert result['sovereign_captured'] is not None
        assert result['sovereign_captured']['winner'] == 'p1'
        assert result['sovereign_captured']['loser'] == 'p2'

    def test_fortified_defender_wins(self):
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=2)
        dfd = Force(id='p2_f1', position=(4, 3), power=2, fortified=True)  # 2+2=4
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        # Use RNG that gives both +1 — 3 vs 5, defender wins
        rng = random.Random(100)
        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        assert result['outcome'] == 'defender_wins'

    def test_ambush_defender_bonus(self):
        """Ambushing defender with power 1 gets +3, making effective 4 vs attacker power 3."""
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), power=3)
        dfd = Force(id='p2_f1', position=(4, 3), power=1, ambushing=True)  # 1+3=4
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        # Use RNG that gives both +1 — 4 vs 5, defender wins
        rng = random.Random(100)
        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game, rng=rng)
        assert result['outcome'] == 'defender_wins'

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
            if result['outcome'] == 'defender_wins':
                wins_for_weaker += 1
        # The weaker side should win SOME of the time (not zero)
        assert wins_for_weaker > 0
        # But not most of the time
        assert wins_for_weaker < trials * 0.5
