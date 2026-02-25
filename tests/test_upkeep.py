"""Tests for v5 upkeep: shrinking board, victory conditions, Shih income, domination, mutual destruction."""

import pytest
from upkeep import perform_upkeep, check_victory, get_controlled_contentious, apply_board_shrink
from state import GameState
from models import Player, Force, Hex, SOVEREIGN_POWER


def make_upkeep_state():
    """Create a game state ready for upkeep testing."""
    p1 = Player(id='p1', shih=6, max_shih=10)
    p2 = Player(id='p2', shih=6, max_shih=10)

    # P1 forces with power values
    p1.add_force(Force(id='p1_f1', position=(3, 3), power=1))  # Sovereign
    p1.add_force(Force(id='p1_f2', position=(3, 4), power=5))

    # P2 forces with power values
    p2.add_force(Force(id='p2_f1', position=(5, 5), power=1))  # Sovereign
    p2.add_force(Force(id='p2_f2', position=(5, 4), power=5))

    # Mark both as deployed
    p1.deployed = True
    p2.deployed = True

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
            (0, 0): Hex(q=0, r=0, terrain='Open'),
            (6, 6): Hex(q=6, r=6, terrain='Open'),
        },
    )
    return game


class TestShihIncome:
    def test_base_income(self):
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        old_shih = p1.shih
        results = perform_upkeep(game)
        # Base 1 + 1 contentious hex * 2 = 3 income
        assert p1.shih > old_shih

    def test_contentious_bonus(self):
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        controlled = get_controlled_contentious(p1, game)
        assert (3, 3) in controlled

    def test_shih_caps_at_max(self):
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        p1.shih = 9  # Near max of 10
        perform_upkeep(game)
        assert p1.shih <= 10

    def test_higher_contentious_bonus(self):
        """In v3, each contentious hex gives +2 Shih."""
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        # Put p1 on 2 contentious hexes
        p1.forces[1].position = (4, 3)
        p1.shih = 0
        perform_upkeep(game)
        # Base 1 + 2 contentious * 2 = 5
        assert p1.shih == 5


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

    def test_no_winner_normally(self):
        game = make_upkeep_state()
        result = check_victory(game)
        assert result is None

    def test_sovereign_death_from_noose(self):
        """If the Sovereign (power 1) dies from board shrink, that player loses."""
        game = make_upkeep_state()
        p2 = game.get_player_by_id('p2')
        # Kill p2's sovereign
        for f in p2.forces:
            if f.is_sovereign:
                f.alive = False
        result = check_victory(game)
        assert result is not None
        assert result['winner'] == 'p1'
        assert result['type'] == 'sovereign_capture'

    def test_domination_requires_2_of_3(self):
        """v3: need 2 of 3 contentious hexes, not all 3."""
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        # p1 controls 1 contentious (3,3) via p1_f1, put p1_f2 on another
        p1.forces[1].position = (4, 3)
        results = perform_upkeep(game)
        assert results['winner'] is None  # Only 1 turn, need 3
        assert p1.domination_turns == 1

    def test_domination_victory_after_3_turns(self):
        """v3: need 3 consecutive turns of holding 2+ contentious hexes."""
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        p1.domination_turns = 2  # Already held for 2 turns
        p1.forces[0].position = (3, 3)
        p1.forces[1].position = (4, 3)

        results = perform_upkeep(game)
        assert results['winner'] == 'p1'
        assert results['victory_type'] == 'domination'

    def test_domination_resets_when_lost(self):
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        p1.domination_turns = 2
        # p1 only controls 1 contentious hex (need 2)
        results = perform_upkeep(game)
        assert p1.domination_turns == 0  # Reset

    def test_simultaneous_sovereign_death_is_draw(self):
        """If both Sovereigns die at the same time (e.g., from Noose), result is a draw."""
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        # Kill both sovereigns
        for f in p1.forces:
            if f.is_sovereign:
                f.alive = False
        for f in p2.forces:
            if f.is_sovereign:
                f.alive = False
        result = check_victory(game)
        assert result is not None
        assert result['winner'] == 'draw'
        assert result['type'] == 'mutual_destruction'

    def test_simultaneous_elimination_is_draw(self):
        """If all forces of both players die simultaneously, result is a draw."""
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        for f in p1.forces:
            f.alive = False
        for f in p2.forces:
            f.alive = False
        result = check_victory(game)
        assert result is not None
        assert result['winner'] == 'draw'
        assert result['type'] == 'mutual_destruction'

    def test_simultaneous_sovereign_death_by_noose(self):
        """Both Sovereigns on far edges die from Noose shrink -- game ends as draw."""
        game = make_upkeep_state()
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        # Place both sovereigns at far corners
        p1.forces[0].position = (0, 0)  # Distance 6 from center
        p2.forces[0].position = (6, 6)  # Distance 6 from center
        # Place other forces safely near center
        p1.forces[1].position = (3, 2)
        p2.forces[1].position = (3, 4)
        game.turn = 6  # shrink_interval = 6
        results = perform_upkeep(game)
        assert results['winner'] == 'draw'
        assert results['victory_type'] == 'mutual_destruction'


class TestBoardShrink:
    def test_shrink_at_interval(self):
        """Board shrinks at turn multiples of shrink_interval."""
        game = make_upkeep_state()
        game.turn = 6  # shrink_interval = 6
        assert game.shrink_stage == 0
        perform_upkeep(game)
        assert game.shrink_stage == 1

    def test_no_shrink_before_interval(self):
        game = make_upkeep_state()
        game.turn = 5  # Before shrink_interval of 6
        perform_upkeep(game)
        assert game.shrink_stage == 0

    def test_scorched_hexes_after_shrink(self):
        game = make_upkeep_state()
        game.shrink_stage = 1
        events = apply_board_shrink(game)
        # (0,0) is distance 6 from center — should be scorched at stage 1 (max dist 5)
        assert game.map_data[(0, 0)].terrain == 'Scorched'

    def test_center_never_scorched(self):
        game = make_upkeep_state()
        game.shrink_stage = 3
        apply_board_shrink(game)
        assert game.map_data[(3, 3)].terrain != 'Scorched'

    def test_force_killed_on_scorched_hex(self):
        game = make_upkeep_state()
        # Move p2's sovereign to the edge
        p2 = game.get_player_by_id('p2')
        p2.forces[0].position = (0, 0)  # Far corner
        game.shrink_stage = 1
        events = apply_board_shrink(game)
        force_deaths = [e for e in events if e['type'] == 'force_scorched']
        assert len(force_deaths) >= 1
        assert not p2.forces[0].alive

    def test_sovereign_death_by_noose_ends_game(self):
        """If Sovereign is on a hex that gets Scorched, that player loses."""
        game = make_upkeep_state()
        p2 = game.get_player_by_id('p2')
        p2.forces[0].position = (0, 0)  # Sovereign at far corner
        p2.forces[1].position = (3, 2)  # Other force safe
        game.turn = 6  # shrink_interval = 6
        results = perform_upkeep(game)
        assert results['winner'] == 'p1'
        assert results['victory_type'] == 'sovereign_capture'


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
