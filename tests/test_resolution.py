"""Tests for combat resolution: power-based combat with information revelation."""

import pytest
from resolution import resolve_combat, calculate_effective_power
from state import GameState, initialize_game, apply_deployment
from models import Force, Player, Hex, ForceRole


def make_combat_state():
    """Create a minimal game state for combat testing."""
    p1 = Player(id='p1', shih=8, max_shih=15)
    p2 = Player(id='p2', shih=8, max_shih=15)
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
        f = Force(id='p1_f1', position=(3, 3), role=ForceRole.VANGUARD)
        game.players[0].add_force(f)
        assert calculate_effective_power(f, game) == 4

    def test_fortify_bonus(self):
        game = make_combat_state()
        f = Force(id='p1_f1', position=(3, 3), role=ForceRole.SCOUT, fortified=True)
        game.players[0].add_force(f)
        power = calculate_effective_power(f, game)
        assert power == 4  # 2 base + 2 fortify

    def test_shield_adjacency_bonus(self):
        game = make_combat_state()
        shield = Force(id='p1_f2', position=(4, 3), role=ForceRole.SHIELD)
        target = Force(id='p1_f1', position=(3, 3), role=ForceRole.SOVEREIGN)
        game.players[0].add_force(shield)
        game.players[0].add_force(target)
        power = calculate_effective_power(target, game)
        assert power == 3  # 1 base + 2 shield

    def test_difficult_terrain_defense_bonus(self):
        game = make_combat_state()
        f = Force(id='p1_f1', position=(3, 4), role=ForceRole.SCOUT)
        game.players[0].add_force(f)
        power = calculate_effective_power(f, game, is_defender=True, hex_pos=(3, 4))
        assert power == 3  # 2 base + 1 difficult terrain

    def test_all_bonuses_stack(self):
        game = make_combat_state()
        shield = Force(id='p1_f2', position=(2, 4), role=ForceRole.SHIELD)
        f = Force(id='p1_f1', position=(3, 4), role=ForceRole.SOVEREIGN, fortified=True)
        game.players[0].add_force(shield)
        game.players[0].add_force(f)
        power = calculate_effective_power(f, game, is_defender=True, hex_pos=(3, 4))
        # 1 base + 2 fortify + 2 shield + 1 difficult = 6
        assert power == 6


class TestCombatResolution:
    def test_vanguard_beats_sovereign(self):
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), role=ForceRole.VANGUARD)
        dfd = Force(id='p2_f1', position=(4, 3), role=ForceRole.SOVEREIGN)
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game)
        assert result['outcome'] == 'attacker_wins'
        assert dfd.alive is False
        assert att.position == (4, 3)

    def test_combat_reveals_both_roles(self):
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), role=ForceRole.VANGUARD)
        dfd = Force(id='p2_f1', position=(4, 3), role=ForceRole.SCOUT)
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game)
        assert att.revealed is True
        assert dfd.revealed is True

    def test_both_players_learn_roles(self):
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), role=ForceRole.VANGUARD)
        dfd = Force(id='p2_f1', position=(4, 3), role=ForceRole.SHIELD)
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game)
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        assert p1.known_enemy_roles['p2_f1'] == 'Shield'
        assert p2.known_enemy_roles['p1_f1'] == 'Vanguard'

    def test_equal_power_stalemate(self):
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), role=ForceRole.VANGUARD)
        dfd = Force(id='p2_f1', position=(4, 3), role=ForceRole.VANGUARD)
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game)
        assert result['outcome'] == 'stalemate'
        assert att.alive is True
        assert dfd.alive is True

    def test_defender_wins(self):
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), role=ForceRole.SCOUT)  # power 2
        dfd = Force(id='p2_f1', position=(4, 3), role=ForceRole.SHIELD)  # power 3
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game)
        assert result['outcome'] == 'defender_wins'
        assert att.alive is False
        assert dfd.alive is True

    def test_sovereign_capture_sets_winner(self):
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), role=ForceRole.VANGUARD)
        dfd = Force(id='p2_f1', position=(4, 3), role=ForceRole.SOVEREIGN)
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game)
        assert result['sovereign_captured'] is not None
        assert result['sovereign_captured']['winner'] == 'p1'
        assert result['sovereign_captured']['loser'] == 'p2'

    def test_fortified_scout_beats_scout(self):
        game = make_combat_state()
        att = Force(id='p1_f1', position=(3, 3), role=ForceRole.SCOUT)  # power 2
        dfd = Force(id='p2_f1', position=(4, 3), role=ForceRole.SCOUT, fortified=True)  # 2+2=4
        game.players[0].add_force(att)
        game.players[1].add_force(dfd)

        result = resolve_combat(att, 'p1', dfd, 'p2', (4, 3), game)
        assert result['outcome'] == 'defender_wins'

    def test_shielded_sovereign_survives_scout(self):
        """Shield adjacent to Sovereign gives +2, making Sovereign power 3 vs Scout power 2."""
        game = make_combat_state()
        shield = Force(id='p2_f2', position=(5, 3), role=ForceRole.SHIELD)
        sovereign = Force(id='p2_f1', position=(4, 3), role=ForceRole.SOVEREIGN)  # 1+2=3
        att = Force(id='p1_f1', position=(3, 3), role=ForceRole.SCOUT)  # power 2
        game.players[0].add_force(att)
        game.players[1].add_force(shield)
        game.players[1].add_force(sovereign)

        result = resolve_combat(att, 'p1', sovereign, 'p2', (4, 3), game)
        assert result['outcome'] == 'defender_wins'
        assert sovereign.alive is True

    def test_vanguard_still_kills_shielded_sovereign(self):
        """Vanguard (4) beats Sovereign+Shield (1+2=3)."""
        game = make_combat_state()
        shield = Force(id='p2_f2', position=(5, 3), role=ForceRole.SHIELD)
        sovereign = Force(id='p2_f1', position=(4, 3), role=ForceRole.SOVEREIGN)
        att = Force(id='p1_f1', position=(3, 3), role=ForceRole.VANGUARD)
        game.players[0].add_force(att)
        game.players[1].add_force(shield)
        game.players[1].add_force(sovereign)

        result = resolve_combat(att, 'p1', sovereign, 'p2', (4, 3), game)
        assert result['outcome'] == 'attacker_wins'
        assert result['sovereign_captured'] is not None
