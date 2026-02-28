"""Tests for the Flask API: endpoints, fog of war, game flow."""

import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def create_game(client, seed=42):
    resp = client.post("/api/game/new", json={"seed": seed})
    assert resp.status_code == 200
    return resp.json["game_id"]


def deploy_both(client, game_id):
    p1 = {
        "player_id": "p1",
        "assignments": {
            "p1_f1": 1,
            "p1_f2": 5,
            "p1_f3": 4,
            "p1_f4": 2,
            "p1_f5": 3,
        },
    }
    p2 = {
        "player_id": "p2",
        "assignments": {
            "p2_f1": 1,
            "p2_f2": 5,
            "p2_f3": 4,
            "p2_f4": 2,
            "p2_f5": 3,
        },
    }
    r1 = client.post(f"/api/game/{game_id}/deploy", json=p1)
    assert r1.status_code == 200
    r2 = client.post(f"/api/game/{game_id}/deploy", json=p2)
    assert r2.status_code == 200
    return r2.json


class TestNewGame:
    def test_creates_game(self, client):
        resp = client.post("/api/game/new", json={"seed": 42})
        assert resp.status_code == 200
        assert "game_id" in resp.json

    def test_starts_in_deploy_phase(self, client):
        resp = client.post("/api/game/new", json={"seed": 42})
        assert resp.json["phase"] == "deploy"

    def test_invalid_json(self, client):
        resp = client.post("/api/game/new", data="not json", content_type="application/json")
        assert resp.status_code == 400


class TestDeployment:
    def test_deploy_player(self, client):
        gid = create_game(client)
        resp = client.post(
            f"/api/game/{gid}/deploy",
            json={
                "player_id": "p1",
                "assignments": {
                    "p1_f1": 1,
                    "p1_f2": 2,
                    "p1_f3": 3,
                    "p1_f4": 4,
                    "p1_f5": 5,
                },
            },
        )
        assert resp.status_code == 200
        assert resp.json["deployed"] is True

    def test_both_deploy_starts_game(self, client):
        gid = create_game(client)
        result = deploy_both(client, gid)
        assert result["phase"] == "plan"

    def test_invalid_composition_rejected(self, client):
        gid = create_game(client)
        resp = client.post(
            f"/api/game/{gid}/deploy",
            json={
                "player_id": "p1",
                "assignments": {
                    "p1_f1": 1,
                    "p1_f2": 1,
                    "p1_f3": 3,
                    "p1_f4": 4,
                    "p1_f5": 5,
                },
            },
        )
        assert resp.status_code == 400

    def test_deploy_wrong_phase(self, client):
        gid = create_game(client)
        deploy_both(client, gid)
        resp = client.post(
            f"/api/game/{gid}/deploy",
            json={
                "player_id": "p1",
                "assignments": {
                    "p1_f1": 1,
                    "p1_f2": 2,
                    "p1_f3": 3,
                    "p1_f4": 4,
                    "p1_f5": 5,
                },
            },
        )
        assert resp.status_code == 400

    def test_deploy_with_out_of_range_values(self, client):
        gid = create_game(client)
        resp = client.post(
            f"/api/game/{gid}/deploy",
            json={
                "player_id": "p1",
                "assignments": {
                    "p1_f1": 0,
                    "p1_f2": 2,
                    "p1_f3": 3,
                    "p1_f4": 4,
                    "p1_f5": 5,
                },
            },
        )
        assert resp.status_code == 400


class TestState:
    def test_requires_player_id(self, client):
        gid = create_game(client)
        resp = client.get(f"/api/game/{gid}/state")
        assert resp.status_code == 400

    def test_shows_own_power(self, client):
        gid = create_game(client)
        deploy_both(client, gid)
        resp = client.get(f"/api/game/{gid}/state?player_id=p1")
        assert resp.status_code == 200
        for f in resp.json["your_forces"]:
            assert f["power"] is not None

    def test_fog_hides_distant_enemies(self, client):
        """Enemies at (6,6) corner are beyond visibility of p1 at (0,0)."""
        gid = create_game(client)
        deploy_both(client, gid)
        resp = client.get(f"/api/game/{gid}/state?player_id=p1")
        # All p2 forces are at far corner, should be hidden
        assert len(resp.json["enemy_forces"]) == 0

    def test_includes_shrink_stage(self, client):
        gid = create_game(client)
        deploy_both(client, gid)
        resp = client.get(f"/api/game/{gid}/state?player_id=p1")
        assert "shrink_stage" in resp.json

    def test_game_not_found(self, client):
        resp = client.get("/api/game/nonexistent/state?player_id=p1")
        assert resp.status_code == 404


class TestAction:
    def test_submit_orders(self, client):
        gid = create_game(client)
        deploy_both(client, gid)
        resp = client.post(
            f"/api/game/{gid}/action",
            json={
                "player_id": "p1",
                "orders": [
                    {"force_id": "p1_f1", "order": "Fortify"},
                    {"force_id": "p1_f2", "order": "Fortify"},
                    {"force_id": "p1_f3", "order": "Fortify"},
                    {"force_id": "p1_f4", "order": "Fortify"},
                    {"force_id": "p1_f5", "order": "Fortify"},
                ],
            },
        )
        assert resp.status_code == 200
        assert resp.json["status"] == "waiting"

    def test_both_submit_resolves(self, client):
        gid = create_game(client)
        deploy_both(client, gid)
        # P1 fortifies
        client.post(
            f"/api/game/{gid}/action",
            json={
                "player_id": "p1",
                "orders": [
                    {"force_id": "p1_f1", "order": "Fortify"},
                    {"force_id": "p1_f2", "order": "Fortify"},
                    {"force_id": "p1_f3", "order": "Fortify"},
                    {"force_id": "p1_f4", "order": "Fortify"},
                    {"force_id": "p1_f5", "order": "Fortify"},
                ],
            },
        )
        # P2 fortifies
        resp = client.post(
            f"/api/game/{gid}/action",
            json={
                "player_id": "p2",
                "orders": [
                    {"force_id": "p2_f1", "order": "Fortify"},
                    {"force_id": "p2_f2", "order": "Fortify"},
                    {"force_id": "p2_f3", "order": "Fortify"},
                    {"force_id": "p2_f4", "order": "Fortify"},
                    {"force_id": "p2_f5", "order": "Fortify"},
                ],
            },
        )
        assert resp.status_code == 200
        assert resp.json["phase"] == "plan"  # Advanced to next turn
        assert resp.json["turn"] == 2

    def test_ambush_order_accepted(self, client):
        gid = create_game(client)
        deploy_both(client, gid)
        resp = client.post(
            f"/api/game/{gid}/action",
            json={
                "player_id": "p1",
                "orders": [
                    {"force_id": "p1_f1", "order": "Ambush"},
                    {"force_id": "p1_f2", "order": "Fortify"},
                    {"force_id": "p1_f3", "order": "Fortify"},
                    {"force_id": "p1_f4", "order": "Fortify"},
                    {"force_id": "p1_f5", "order": "Fortify"},
                ],
            },
        )
        assert resp.status_code == 200

    def test_wrong_phase_rejected(self, client):
        gid = create_game(client)
        resp = client.post(
            f"/api/game/{gid}/action",
            json={
                "player_id": "p1",
                "orders": [{"force_id": "p1_f1", "order": "Fortify"}],
            },
        )
        assert resp.status_code == 400

    def test_invalid_order_type(self, client):
        gid = create_game(client)
        deploy_both(client, gid)
        resp = client.post(
            f"/api/game/{gid}/action",
            json={
                "player_id": "p1",
                "orders": [{"force_id": "p1_f1", "order": "Feint"}],
            },
        )
        assert resp.status_code == 400

    def test_feint_no_longer_valid(self, client):
        """Feint was removed in v3, replaced by Ambush."""
        gid = create_game(client)
        deploy_both(client, gid)
        resp = client.post(
            f"/api/game/{gid}/action",
            json={
                "player_id": "p1",
                "orders": [{"force_id": "p1_f1", "order": "Feint"}],
            },
        )
        assert resp.status_code == 400


class TestConcession:
    def test_concede(self, client):
        gid = create_game(client)
        deploy_both(client, gid)
        resp = client.post(f"/api/game/{gid}/concede", json={"player_id": "p1"})
        assert resp.status_code == 200
        assert resp.json["winner"] == "p2"
        assert resp.json["victory_type"] == "concession"


class TestLog:
    def test_get_log(self, client):
        gid = create_game(client)
        deploy_both(client, gid)
        resp = client.get(f"/api/game/{gid}/log")
        assert resp.status_code == 200
        assert "log" in resp.json
        assert len(resp.json["log"]) > 0
