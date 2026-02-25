"""Tests for upkeep: victory conditions, Shih income, domination tracking."""

import pytest
from upkeep import perform_upkeep, check_victory, get_controlled_contentious
from state import GameState
from models import Player, Force, Hex, ForceRole


def make_upkeep_state():
    """Create a game state ready for upkeep testing."""
    p1 = Player(id='p1', shih=8, max_shih=15)
    p2 = Player(id='p2', shih=8, max_shih=15)

    # P1 forces
    p1.add_force(Force(id='p1_f1', position=(3, 3), role=ForceRole.SOVEREIGN))
    p1.add_force(Force(id='p1_f2', position=(3, 4), role=ForceRole.VANGUARD))

    # P2 forces
    p2.add_force(Force(id='p2_f1', position=(5, 5), role=ForceRole.SOVEREIGN))
    p2.add_force(Force(id='p2_f2', position=(5, 4), role=ForceRole.VANGUARD))

    game = GameState(
        game_id='test', turn=1, phase='resolve',
        players=[p1, p2],
        map_data={
            (3, 3): Hex(q=3, r=3, terrain='Contentious'),
            (3, 4): Hex(q=3, r=4, terrain='Open'),
            (4, 3): Hex(q=4, r=3, terrain='Contentious'),
            (4, 4): Hex(q=4, r=4, terrain='Contentious'),
            (5, 5): Hex(q=5, r=5, terrain='Open'),
            (5, 4): Hex(q=5, r=4, terrain='Open'),
        },
    )
    return game


class TestShihIncome:
    def test_base_income(self):
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        old_shih = p1.shih
        results = perform_upkeep(game)
        # Base 2 + 1 contentious (p1 has force at (3,3) which is Contentious)
        assert p1.shih > old_shih

    def test_contentious_bonus(self):
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        controlled = get_controlled_contentious(p1, game)
        # p1_f1 at (3,3) is Contentious
        assert (3, 3) in controlled

    def test_shih_caps_at_max(self):
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        p1.shih = 14  # Near max of 15
        perform_upkeep(game)
        assert p1.shih <= 15


class TestVictoryConditions:
    def test_sovereign_capture_wins(self):
        game = make_upkeep_state()
        capture = {'winner': 'p1', 'loser': 'p2', 'capturing_force': 'p1_f2'}
        result = check_victory(game, capture)
        assert result is not None
        assert result['winner'] == 'p1'
        assert result['type'] == 'sovereign_capture'

    def test_elimination_wins(self):
        game = make_upkeep_state()
        p2 = game.get_player_by_id('p2')
        for f in p2.forces:
            f.alive = False
        result = check_victory(game)
        assert result is not None
        assert result['winner'] == 'p1'
        assert result['type'] == 'elimination'

    def test_no_winner_normally(self):
        game = make_upkeep_state()
        result = check_victory(game)
        assert result is None

    def test_domination_requires_consecutive_turns(self):
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        # Place p1 forces on ALL contentious hexes
        p1.forces[0].position = (3, 3)
        p1.forces[1].position = (4, 3)
        p1.add_force(Force(id='p1_f3', position=(4, 4), role=ForceRole.SHIELD))

        results = perform_upkeep(game)
        assert results['winner'] is None  # Only 1 turn, need 2
        assert p1.domination_turns == 1

    def test_domination_victory_after_2_turns(self):
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        p1.domination_turns = 1  # Already held for 1 turn
        # Place on all contentious hexes
        p1.forces[0].position = (3, 3)
        p1.forces[1].position = (4, 3)
        p1.add_force(Force(id='p1_f3', position=(4, 4), role=ForceRole.SHIELD))

        results = perform_upkeep(game)
        assert results['winner'] == 'p1'
        assert results['victory_type'] == 'domination'

    def test_domination_resets_when_lost(self):
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        p1.domination_turns = 1
        # p1 does NOT control all contentious hexes (missing some)
        results = perform_upkeep(game)
        assert p1.domination_turns == 0  # Reset


class TestUpkeepPhaseTransition:
    def test_advances_turn(self):
        game = make_upkeep_state()
        assert game.turn == 1
        perform_upkeep(game)
        assert game.turn == 2
        assert game.phase == 'plan'

    def test_game_ends_on_victory(self):
        game = make_upkeep_state()
        p2 = game.get_player_by_id('p2')
        for f in p2.forces:
            f.alive = False
        perform_upkeep(game)
        assert game.phase == 'ended'
        assert game.winner == 'p1'

    def test_clears_feints(self):
        game = make_upkeep_state()
        game.feints = [{'force_id': 'p1_f1', 'toward': (4, 3)}]
        perform_upkeep(game)
        assert game.feints == []
