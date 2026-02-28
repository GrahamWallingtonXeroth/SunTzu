"""Tests for game state management, initialization, and deployment."""

import pytest

from models import Force, Player
from state import (
    apply_deployment,
    get_player_view,
    initialize_game,
    is_visible_to_player,
    validate_deployment,
)


@pytest.fixture
def game():
    return initialize_game(seed=42)


class TestInitialization:
    def test_creates_game(self, game):
        assert game.game_id is not None
        assert game.turn == 0
        assert game.phase == "deploy"
        assert len(game.players) == 2

    def test_players_have_5_forces(self, game):
        for player in game.players:
            assert len(player.forces) == 5

    def test_forces_start_without_power(self, game):
        for player in game.players:
            for force in player.forces:
                assert force.power is None

    def test_players_start_with_shih(self, game):
        for player in game.players:
            assert player.shih == 6

    def test_map_is_7x7(self, game):
        assert len(game.map_data) == 49  # 7x7

    def test_map_has_contentious_hexes(self, game):
        contentious = [h for h in game.map_data.values() if h.terrain == "Contentious"]
        assert len(contentious) == 3

    def test_players_start_at_opposite_sides(self, game):
        """P1 starts left cluster near (0,2), P2 starts right cluster near (6,4)."""
        p1 = game.get_player_by_id("p1")
        p2 = game.get_player_by_id("p2")
        p1_expected = {(0, 1), (0, 2), (0, 3), (1, 1), (1, 2)}
        p2_expected = {(6, 5), (6, 4), (6, 3), (5, 5), (5, 4)}
        p1_positions = {f.position for f in p1.forces}
        p2_positions = {f.position for f in p2.forces}
        assert p1_positions == p1_expected
        assert p2_positions == p2_expected

    def test_shrink_stage_starts_at_0(self, game):
        assert game.shrink_stage == 0


class TestDeployment:
    def test_valid_deployment(self, game):
        assignments = {
            "p1_f1": 1,
            "p1_f2": 2,
            "p1_f3": 3,
            "p1_f4": 4,
            "p1_f5": 5,
        }
        error = apply_deployment(game, "p1", assignments)
        assert error is None
        p1 = game.get_player_by_id("p1")
        assert p1.deployed is True

    def test_invalid_duplicate_power(self, game):
        assignments = {
            "p1_f1": 1,
            "p1_f2": 1,
            "p1_f3": 3,
            "p1_f4": 4,
            "p1_f5": 5,
        }
        error = apply_deployment(game, "p1", assignments)
        assert error is not None

    def test_invalid_missing_power(self, game):
        assignments = {
            "p1_f1": 1,
            "p1_f2": 2,
            "p1_f3": 3,
            "p1_f4": 4,
            "p1_f5": 6,
        }
        error = apply_deployment(game, "p1", assignments)
        assert error is not None

    def test_wrong_force_ids(self, game):
        assignments = {
            "p2_f1": 1,
            "p1_f2": 2,
            "p1_f3": 3,
            "p1_f4": 4,
            "p1_f5": 5,
        }
        error = apply_deployment(game, "p1", assignments)
        assert error is not None

    def test_double_deploy_rejected(self, game):
        assignments = {
            "p1_f1": 1,
            "p1_f2": 2,
            "p1_f3": 3,
            "p1_f4": 4,
            "p1_f5": 5,
        }
        apply_deployment(game, "p1", assignments)
        error = apply_deployment(game, "p1", assignments)
        assert error is not None
        assert "already deployed" in error

    def test_both_deploy_starts_game(self, game):
        p1_assign = {"p1_f1": 1, "p1_f2": 2, "p1_f3": 3, "p1_f4": 4, "p1_f5": 5}
        p2_assign = {"p2_f1": 1, "p2_f2": 2, "p2_f3": 3, "p2_f4": 4, "p2_f5": 5}
        apply_deployment(game, "p1", p1_assign)
        assert game.phase == "deploy"  # Still deploying
        apply_deployment(game, "p2", p2_assign)
        assert game.phase == "plan"
        assert game.turn == 1

    def test_incomplete_assignment_rejected(self, game):
        assignments = {"p1_f1": 1, "p1_f2": 2}
        error = apply_deployment(game, "p1", assignments)
        assert error is not None

    def test_validate_deployment_valid(self):
        assignments = {"f1": 1, "f2": 2, "f3": 3, "f4": 4, "f5": 5}
        assert validate_deployment(assignments) is None

    def test_validate_deployment_invalid(self):
        assignments = {"f1": 1, "f2": 2, "f3": 3, "f4": 4, "f5": 4}
        assert validate_deployment(assignments) is not None


class TestPlayerView:
    @pytest.fixture
    def deployed_game(self, game):
        p1_assign = {"p1_f1": 1, "p1_f2": 2, "p1_f3": 3, "p1_f4": 4, "p1_f5": 5}
        p2_assign = {"p2_f1": 1, "p2_f2": 2, "p2_f3": 3, "p2_f4": 4, "p2_f5": 5}
        apply_deployment(game, "p1", p1_assign)
        apply_deployment(game, "p2", p2_assign)
        return game

    def test_own_forces_show_power(self, deployed_game):
        view = get_player_view(deployed_game, "p1")
        for f in view["your_forces"]:
            assert "power" in f
            assert f["power"] is not None

    def test_enemy_forces_hidden_by_fog(self, deployed_game):
        """Enemy forces near (6,4) are far from p1 near (0,2) — fog of war hides them."""
        view = get_player_view(deployed_game, "p1")
        # p2 forces are at (5,4)-(6,5) cluster, p1 at (0,1)-(1,2) — far beyond visibility range
        assert len(view["enemy_forces"]) == 0

    def test_enemy_forces_visible_when_close(self, deployed_game):
        """Move an enemy force close to p1's forces — it becomes visible."""
        p2 = deployed_game.get_player_by_id("p2")
        p2.forces[0].position = (2, 1)  # Adjacent to p1_f4 at (1,1)
        view = get_player_view(deployed_game, "p1")
        visible_ids = [f["id"] for f in view["enemy_forces"]]
        assert p2.forces[0].id in visible_ids

    def test_visible_enemy_hides_power(self, deployed_game):
        """Visible enemy forces don't show power unless scouted/revealed."""
        p2 = deployed_game.get_player_by_id("p2")
        p2.forces[0].position = (2, 1)  # Within visibility of p1 forces
        view = get_player_view(deployed_game, "p1")
        enemy = view["enemy_forces"][0]
        assert "power" not in enemy

    def test_view_includes_map(self, deployed_game):
        view = get_player_view(deployed_game, "p1")
        assert "map" in view
        assert len(view["map"]) == 49

    def test_view_includes_shih(self, deployed_game):
        view = get_player_view(deployed_game, "p1")
        assert "your_shih" in view
        assert view["your_shih"] == 6

    def test_scouted_powers_visible(self, deployed_game):
        p1 = deployed_game.get_player_by_id("p1")
        p2 = deployed_game.get_player_by_id("p2")
        # Move enemy close to p1 cluster and scout it
        p2.forces[0].position = (2, 1)  # Within visibility of p1_f4 at (1,1)
        p1.known_enemy_powers[p2.forces[0].id] = 1
        view = get_player_view(deployed_game, "p1")
        scouted = [f for f in view["enemy_forces"] if f.get("scouted")]
        assert len(scouted) == 1
        assert scouted[0]["power"] == 1

    def test_revealed_powers_visible(self, deployed_game):
        p2 = deployed_game.get_player_by_id("p2")
        p2.forces[0].revealed = True
        p2.forces[0].position = (2, 1)  # Within visibility of p1_f4 at (1,1)
        view = get_player_view(deployed_game, "p1")
        revealed = [f for f in view["enemy_forces"] if f.get("revealed")]
        assert len(revealed) == 1

    def test_view_includes_shrink_stage(self, deployed_game):
        view = get_player_view(deployed_game, "p1")
        assert "shrink_stage" in view
        assert view["shrink_stage"] == 0


class TestVisibility:
    def test_visible_within_range(self):
        player = Player(id="p1")
        player.add_force(Force(id="p1_f1", position=(3, 3), power=5))
        assert is_visible_to_player((4, 3), player, visibility_range=2) is True
        assert is_visible_to_player((5, 3), player, visibility_range=2) is True

    def test_not_visible_beyond_range(self):
        player = Player(id="p1")
        player.add_force(Force(id="p1_f1", position=(0, 0), power=5))
        assert is_visible_to_player((6, 6), player, visibility_range=2) is False

    def test_multiple_forces_extend_visibility(self):
        player = Player(id="p1")
        player.add_force(Force(id="p1_f1", position=(0, 0), power=5))
        player.add_force(Force(id="p1_f2", position=(3, 3), power=4))
        # (5, 3) is within range 2 of (3,3)
        assert is_visible_to_player((5, 3), player, visibility_range=2) is True


class TestValidPosition:
    def test_valid_position(self):
        game = initialize_game(seed=42)
        assert game.is_valid_position((3, 3)) is True

    def test_invalid_off_board(self):
        game = initialize_game(seed=42)
        assert game.is_valid_position((-1, 0)) is False

    def test_scorched_is_invalid(self):
        game = initialize_game(seed=42)
        game.map_data[(3, 3)].terrain = "Scorched"
        assert game.is_valid_position((3, 3)) is False
