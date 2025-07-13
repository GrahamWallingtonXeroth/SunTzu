import pytest
from orders import Order, OrderType, validate_order, is_adjacent
from state import GameState, Player
from models import Force, Hex
from typing import Dict, Tuple

@pytest.fixture
def sample_game_state():
    """Create a sample game state for testing."""
    game_state = GameState(
        game_id="test_game_123",
        turn=1,
        phase="plan",
        players=[
            Player(id="p1", chi=100, shih=10, forces=[
                Force(id="p1_f1", position=(0, 0), stance="Mountain"),
                Force(id="p1_f2", position=(1, 0), stance="Mountain"),
                Force(id="p1_f3", position=(0, 1), stance="Mountain")
            ]),
            Player(id="p2", chi=100, shih=10, forces=[
                Force(id="p2_f1", position=(24, 19), stance="Mountain"),
                Force(id="p2_f2", position=(23, 19), stance="Mountain"),
                Force(id="p2_f3", position=(24, 18), stance="Mountain")
            ])
        ],
        map_data={
            (0, 0): Hex(q=0, r=0, terrain="Open"),
            (1, 0): Hex(q=1, r=0, terrain="Open"),
            (0, 1): Hex(q=0, r=1, terrain="Open"),
            (1, 1): Hex(q=1, r=1, terrain="Difficult"),
            (24, 19): Hex(q=24, r=19, terrain="Open"),
            (23, 19): Hex(q=23, r=19, terrain="Open"),
            (24, 18): Hex(q=24, r=18, terrain="Open")
        }
    )
    return game_state

def test_validate_advance_valid(sample_game_state):
    """Test a valid Advance order."""
    force = sample_game_state.players[0].forces[0]  # Force at (0, 0)
    order = Order(OrderType.ADVANCE, force, target_hex=(1, 0), stance="Mountain")
    assert validate_order(order, sample_game_state) == True

def test_validate_advance_insufficient_shih(sample_game_state):
    """Test Advance with insufficient Shih."""
    # Reduce player's Shih below 2
    sample_game_state.players[0].shih = 1
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.ADVANCE, force, target_hex=(1, 0), stance="Mountain")
    assert validate_order(order, sample_game_state) == False

def test_validate_advance_non_adjacent(sample_game_state):
    """Test Advance with non-adjacent target hex."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.ADVANCE, force, target_hex=(3, 3), stance="Mountain")
    assert validate_order(order, sample_game_state) == False

def test_validate_advance_invalid_stance(sample_game_state):
    """Test Advance with invalid stance."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.ADVANCE, force, target_hex=(1, 0), stance="Invalid")
    assert validate_order(order, sample_game_state) == False

def test_validate_advance_thunder_on_difficult(sample_game_state):
    """Test Advance with Thunder stance on Difficult terrain."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.ADVANCE, force, target_hex=(1, 1), stance="Thunder")
    assert validate_order(order, sample_game_state) == False

def test_validate_meditate_valid(sample_game_state):
    """Test a valid Meditate order."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.MEDITATE, force)
    assert validate_order(order, sample_game_state) == True

def test_validate_meditate_with_target(sample_game_state):
    """Test Meditate with invalid target hex."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.MEDITATE, force, target_hex=(1, 0))
    assert validate_order(order, sample_game_state) == False

def test_validate_deceive_valid(sample_game_state):
    """Test a valid Deceive order."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.DECEIVE, force, target_hex=(1, 0))
    assert validate_order(order, sample_game_state) == True

def test_validate_deceive_insufficient_shih(sample_game_state):
    """Test Deceive with insufficient Shih."""
    # Reduce player's Shih below 3
    sample_game_state.players[0].shih = 2
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.DECEIVE, force, target_hex=(1, 0))
    assert validate_order(order, sample_game_state) == False

def test_is_adjacent():
    """Test hex adjacency check."""
    # Test adjacent hexes
    assert is_adjacent((0, 0), (1, 0)) == True
    assert is_adjacent((0, 0), (0, 1)) == True
    assert is_adjacent((0, 0), (1, -1)) == True
    
    # Test non-adjacent hexes
    assert is_adjacent((0, 0), (2, 2)) == False
    assert is_adjacent((0, 0), (3, 0)) == False
    assert is_adjacent((0, 0), (0, 3)) == False
    
    # Test same hex
    assert is_adjacent((0, 0), (0, 0)) == False