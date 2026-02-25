"""Tests for game state management, initialization, and deployment."""

import pytest
from state import initialize_game, apply_deployment, validate_deployment, get_player_view, GameState
from models import ForceRole


@pytest.fixture
def game():
    return initialize_game(seed=42)


class TestInitialization:
    def test_creates_game(self, game):
        assert game.game_id is not None
        assert game.turn == 0
        assert game.phase == 'deploy'
        assert len(game.players) == 2

    def test_players_have_5_forces(self, game):
        for player in game.players:
            assert len(player.forces) == 5

    def test_forces_start_without_roles(self, game):
        for player in game.players:
            for force in player.forces:
                assert force.role is None

    def test_players_start_with_shih(self, game):
        for player in game.players:
            assert player.shih == 8

    def test_map_is_7x7(self, game):
        assert len(game.map_data) == 49  # 7x7

    def test_map_has_contentious_hexes(self, game):
        contentious = [h for h in game.map_data.values() if h.terrain == 'Contentious']
        assert len(contentious) == 3

    def test_players_start_at_opposite_corners(self, game):
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        p1_positions = {f.position for f in p1.forces}
        p2_positions = {f.position for f in p2.forces}
        # P1 should be near (0,0), P2 near (6,6)
        assert any(q <= 2 and r <= 2 for q, r in p1_positions)
        assert any(q >= 4 and r >= 4 for q, r in p2_positions)


class TestDeployment:
    def test_valid_deployment(self, game):
        assignments = {
            'p1_f1': 'Sovereign',
            'p1_f2': 'Vanguard',
            'p1_f3': 'Vanguard',
            'p1_f4': 'Scout',
            'p1_f5': 'Shield',
        }
        error = apply_deployment(game, 'p1', assignments)
        assert error is None
        p1 = game.get_player_by_id('p1')
        assert p1.deployed is True

    def test_invalid_role_composition(self, game):
        assignments = {
            'p1_f1': 'Sovereign',
            'p1_f2': 'Sovereign',  # Two Sovereigns
            'p1_f3': 'Vanguard',
            'p1_f4': 'Scout',
            'p1_f5': 'Shield',
        }
        error = apply_deployment(game, 'p1', assignments)
        assert error is not None
        assert 'Sovereign' in error

    def test_wrong_force_ids(self, game):
        assignments = {
            'p2_f1': 'Sovereign',  # Wrong player's force
            'p1_f2': 'Vanguard',
            'p1_f3': 'Vanguard',
            'p1_f4': 'Scout',
            'p1_f5': 'Shield',
        }
        error = apply_deployment(game, 'p1', assignments)
        assert error is not None

    def test_double_deploy_rejected(self, game):
        assignments = {
            'p1_f1': 'Sovereign',
            'p1_f2': 'Vanguard',
            'p1_f3': 'Vanguard',
            'p1_f4': 'Scout',
            'p1_f5': 'Shield',
        }
        apply_deployment(game, 'p1', assignments)
        error = apply_deployment(game, 'p1', assignments)
        assert error is not None
        assert 'already deployed' in error

    def test_both_deploy_starts_game(self, game):
        p1_assign = {
            'p1_f1': 'Sovereign', 'p1_f2': 'Vanguard', 'p1_f3': 'Vanguard',
            'p1_f4': 'Scout', 'p1_f5': 'Shield',
        }
        p2_assign = {
            'p2_f1': 'Sovereign', 'p2_f2': 'Vanguard', 'p2_f3': 'Vanguard',
            'p2_f4': 'Scout', 'p2_f5': 'Shield',
        }
        apply_deployment(game, 'p1', p1_assign)
        assert game.phase == 'deploy'  # Still deploying
        apply_deployment(game, 'p2', p2_assign)
        assert game.phase == 'plan'
        assert game.turn == 1

    def test_incomplete_assignment_rejected(self, game):
        assignments = {
            'p1_f1': 'Sovereign',
            'p1_f2': 'Vanguard',
        }
        error = apply_deployment(game, 'p1', assignments)
        assert error is not None
        assert 'all' in error.lower() or '5' in error


class TestPlayerView:
    @pytest.fixture
    def deployed_game(self, game):
        p1_assign = {
            'p1_f1': 'Sovereign', 'p1_f2': 'Vanguard', 'p1_f3': 'Vanguard',
            'p1_f4': 'Scout', 'p1_f5': 'Shield',
        }
        p2_assign = {
            'p2_f1': 'Sovereign', 'p2_f2': 'Vanguard', 'p2_f3': 'Vanguard',
            'p2_f4': 'Scout', 'p2_f5': 'Shield',
        }
        apply_deployment(game, 'p1', p1_assign)
        apply_deployment(game, 'p2', p2_assign)
        return game

    def test_own_forces_show_roles(self, deployed_game):
        view = get_player_view(deployed_game, 'p1')
        for f in view['your_forces']:
            assert 'role' in f
            assert f['role'] is not None

    def test_enemy_forces_hide_roles(self, deployed_game):
        view = get_player_view(deployed_game, 'p1')
        for f in view['enemy_forces']:
            assert 'role' not in f or f.get('revealed') or f.get('scouted')

    def test_view_includes_map(self, deployed_game):
        view = get_player_view(deployed_game, 'p1')
        assert 'map' in view
        assert len(view['map']) == 49

    def test_view_includes_shih(self, deployed_game):
        view = get_player_view(deployed_game, 'p1')
        assert 'your_shih' in view
        assert view['your_shih'] == 8

    def test_scouted_roles_visible(self, deployed_game):
        p1 = deployed_game.get_player_by_id('p1')
        p1.known_enemy_roles['p2_f1'] = 'Sovereign'
        view = get_player_view(deployed_game, 'p1')
        scouted = [f for f in view['enemy_forces'] if f.get('scouted')]
        assert len(scouted) == 1
        assert scouted[0]['role'] == 'Sovereign'

    def test_revealed_roles_visible(self, deployed_game):
        p2 = deployed_game.get_player_by_id('p2')
        p2.forces[0].revealed = True
        view = get_player_view(deployed_game, 'p1')
        revealed = [f for f in view['enemy_forces'] if f.get('revealed')]
        assert len(revealed) == 1
