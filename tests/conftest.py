"""Shared test fixtures and helpers."""

import random

import pytest

from models import Force, Hex, Player
from state import GameState, apply_deployment, initialize_game

# --- Standard power assignments ---

STANDARD_P1_POWERS = {"p1_f1": 1, "p1_f2": 5, "p1_f3": 4, "p1_f4": 2, "p1_f5": 3}
STANDARD_P2_POWERS = {"p2_f1": 1, "p2_f2": 5, "p2_f3": 4, "p2_f4": 2, "p2_f5": 3}

SEQUENTIAL_P1_POWERS = {"p1_f1": 1, "p1_f2": 2, "p1_f3": 3, "p1_f4": 4, "p1_f5": 5}
SEQUENTIAL_P2_POWERS = {"p2_f1": 1, "p2_f2": 2, "p2_f3": 3, "p2_f4": 4, "p2_f5": 5}


# --- Fixtures ---


@pytest.fixture
def game():
    """Fresh game in deploy phase (seed=42)."""
    return initialize_game(seed=42)


@pytest.fixture
def deployed_game(game):
    """Game with both players deployed using sequential power assignments."""
    apply_deployment(game, "p1", SEQUENTIAL_P1_POWERS)
    apply_deployment(game, "p2", SEQUENTIAL_P2_POWERS)
    return game


@pytest.fixture
def rng():
    """Deterministic RNG seeded at 42."""
    return random.Random(42)


@pytest.fixture
def api_client():
    """Flask test client."""
    from app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# --- Helper functions ---


def make_deployed_game(seed=42):
    """Create a fully deployed game with standard power assignments."""
    game = initialize_game(seed)
    apply_deployment(game, "p1", STANDARD_P1_POWERS)
    apply_deployment(game, "p2", STANDARD_P2_POWERS)
    return game


def make_combat_state():
    """Create a minimal game state for combat testing."""
    p1 = Player(id="p1", shih=6, max_shih=10)
    p2 = Player(id="p2", shih=6, max_shih=10)
    return GameState(
        game_id="test",
        turn=1,
        phase="resolve",
        players=[p1, p2],
        map_data={
            (3, 3): Hex(q=3, r=3, terrain="Open"),
            (4, 3): Hex(q=4, r=3, terrain="Open"),
            (3, 4): Hex(q=3, r=4, terrain="Difficult"),
            (4, 4): Hex(q=4, r=4, terrain="Contentious"),
            (2, 3): Hex(q=2, r=3, terrain="Open"),
            (3, 2): Hex(q=3, r=2, terrain="Open"),
            (2, 4): Hex(q=2, r=4, terrain="Open"),
            (5, 3): Hex(q=5, r=3, terrain="Open"),
        },
    )


def make_upkeep_state():
    """Create a game state ready for upkeep testing."""
    p1 = Player(id="p1", shih=6, max_shih=10)
    p2 = Player(id="p2", shih=6, max_shih=10)

    p1.add_force(Force(id="p1_f1", position=(3, 3), power=1))
    p1.add_force(Force(id="p1_f2", position=(3, 4), power=5))

    p2.add_force(Force(id="p2_f1", position=(5, 5), power=1))
    p2.add_force(Force(id="p2_f2", position=(5, 4), power=5))

    p1.deployed = True
    p2.deployed = True

    return GameState(
        game_id="test",
        turn=1,
        phase="resolve",
        players=[p1, p2],
        map_data={
            (3, 3): Hex(q=3, r=3, terrain="Contentious"),
            (3, 4): Hex(q=3, r=4, terrain="Open"),
            (4, 3): Hex(q=4, r=3, terrain="Contentious"),
            (4, 4): Hex(q=4, r=4, terrain="Contentious"),
            (5, 5): Hex(q=5, r=5, terrain="Open"),
            (5, 4): Hex(q=5, r=4, terrain="Open"),
            (0, 0): Hex(q=0, r=0, terrain="Open"),
            (6, 6): Hex(q=6, r=6, terrain="Open"),
        },
    )


def create_api_game(client, seed=42):
    """Create a new game via API, return game_id."""
    resp = client.post("/api/game/new", json={"seed": seed})
    assert resp.status_code == 200
    return resp.json["game_id"]


def deploy_both_api(client, game_id):
    """Deploy both players via API with standard assignments."""
    for player_id, assignments in [("p1", STANDARD_P1_POWERS), ("p2", STANDARD_P2_POWERS)]:
        resp = client.post(
            f"/api/game/{game_id}/deploy",
            json={"player_id": player_id, "assignments": assignments},
        )
        assert resp.status_code == 200
    return resp.json
