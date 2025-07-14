import pytest
from state import initialize_game, GameState, Player, Force
from models import Hex

def test_initialize_game_basic():
    """Test that initialize_game sets up the game state correctly."""
    game_state = initialize_game(seed=42)
    
    # Check game state basics
    assert isinstance(game_state, GameState), "GameState object not created"
    assert game_state.turn == 1, "Initial turn should be 1"
    assert game_state.phase == "plan", "Initial phase should be 'plan'"
    
    # Check players
    assert len(game_state.players) == 2, "Should have 2 players"
    p1, p2 = game_state.players
    
    # Player 1 checks
    assert p1.id == "p1", "Player 1 ID should be 'p1'"
    assert p1.chi == 100, "Player 1 Chi should be 100"
    assert p1.shih == 10, "Player 1 Shih should be 10"
    assert len(p1.forces) == 3, "Player 1 should have 3 forces"
    
    # Player 2 checks
    assert p2.id == "p2", "Player 2 ID should be 'p2'"
    assert p2.chi == 100, "Player 2 Chi should be 100"
    assert p2.shih == 10, "Player 2 Shih should be 10"
    assert len(p2.forces) == 3, "Player 2 should have 3 forces"
    
    # Check force positions for Player 1
    p1_positions = [f.position for f in p1.forces]
    expected_p1_positions = [(0, 0), (1, 0), (0, 1)]
    assert sorted(p1_positions) == sorted(expected_p1_positions), "Player 1 forces at wrong positions"
    
    # Check force positions for Player 2
    p2_positions = [f.position for f in p2.forces]
    expected_p2_positions = [(9, 9), (8, 9), (9, 8)]
    assert sorted(p2_positions) == sorted(expected_p2_positions), "Player 2 forces at wrong positions"


def test_initialize_game_map():
    """Test that the map is initialized in the game state."""
    game_state = initialize_game(seed=42)
    assert game_state.map_data is not None, "Map should not be None"
    assert len(game_state.map_data) == 10 * 10, "Map should have 100 hexes (10x10)"