import pytest
from orders import Order, OrderType, validate_order, is_adjacent, resolve_orders
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
            (24, 18): Hex(q=24, r=18, terrain="Open"),
            (23, 18): Hex(q=23, r=18, terrain="Open")
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
    sample_game_state.players[0].shih = 2
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.DECEIVE, force, target_hex=(1, 0))
    assert validate_order(order, sample_game_state) == False

def test_is_adjacent():
    """Test hex adjacency check."""
    assert is_adjacent((0, 0), (1, 0)) == True
    assert is_adjacent((0, 0), (0, 1)) == True
    assert is_adjacent((0, 0), (1, -1)) == True
    assert is_adjacent((0, 0), (2, 2)) == False
    assert is_adjacent((0, 0), (3, 0)) == False
    assert is_adjacent((0, 0), (0, 3)) == False
    assert is_adjacent((0, 0), (0, 0)) == False

def test_resolve_orders_advance_move(sample_game_state):
    """Test Advance order moves force to empty hex."""
    force = sample_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
    order = Order(OrderType.ADVANCE, force, target_hex=(1, 0), stance="Mountain")
    results = resolve_orders([order], sample_game_state)
    
    assert force.position == (1, 0)
    assert force.stance == "Mountain"
    assert sample_game_state.players[0].shih == 8  # 10 - 2
    assert len(results["confrontations"]) == 0
    assert len(results["revealed_orders"]) == 0
    assert len(results["errors"]) == 0

def test_resolve_orders_advance_confrontation(sample_game_state):
    """Test Advance order triggers confrontation."""
    force_p1 = sample_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
    force_p2 = sample_game_state.players[1].forces[0]  # p2_f1 at (24, 19)
    sample_game_state.players[1].forces[0].position = (1, 0)  # Move p2_f1 to (1, 0)
    order = Order(OrderType.ADVANCE, force_p1, target_hex=(1, 0), stance="Mountain")
    results = resolve_orders([order], sample_game_state)
    
    assert force_p1.position == (0, 0)  # No move due to confrontation
    assert len(results["confrontations"]) == 1
    assert results["confrontations"][0]["attacking_force"] == "p1_f1"
    assert results["confrontations"][0]["target_hex"] == (1, 0)
    assert results["confrontations"][0]["attacking_stance"] == "Mountain"
    assert results["confrontations"][0]["occupying_force"] == "p2_f1"
    assert sample_game_state.players[0].shih == 8  # 10 - 2
    assert len(results["revealed_orders"]) == 0
    assert len(results["errors"]) == 0

def test_resolve_orders_meditate(sample_game_state):
    """Test Meditate order queues Shih and reveals adjacent orders."""
    force_p1 = sample_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
    force_p2 = sample_game_state.players[1].forces[0]  # p2_f1 at (24, 19)
    sample_game_state.players[1].forces[0].position = (1, 0)  # Move p2_f1 adjacent
    order_p1 = Order(OrderType.MEDITATE, force_p1)
    # The order should be for the force at the adjacent position, not the original position
    # Use a target that doesn't conflict with existing forces
    order_p2 = Order(OrderType.ADVANCE, force_p2, target_hex=(2, 0), stance="River")
    results = resolve_orders([order_p1, order_p2], sample_game_state)
    
    assert sample_game_state.players[0].shih == 12  # 10 + 2
    assert ("p2_f1", "Advance") in results["revealed_orders"]
    assert len(results["confrontations"]) == 0
    assert len(results["errors"]) == 0

def test_resolve_orders_deceive(sample_game_state):
    """Test Deceive order creates ghost and deducts Shih."""
    force = sample_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
    order = Order(OrderType.DECEIVE, force, target_hex=(1, 0))
    results = resolve_orders([order], sample_game_state)
    
    assert sample_game_state.players[0].shih == 7  # 10 - 3
    # Ghosts are internal to resolve_orders and not exposed in results
    # We can only verify the Shih deduction and no errors
    assert len(results["confrontations"]) == 0
    assert len(results["revealed_orders"]) == 0
    assert len(results["errors"]) == 0

def test_resolve_orders_invalid_order(sample_game_state):
    """Test invalid order is skipped with error message."""
    force = sample_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
    sample_game_state.players[0].shih = 1
    order = Order(OrderType.ADVANCE, force, target_hex=(1, 0), stance="Mountain")
    results = resolve_orders([order], sample_game_state)
    
    assert sample_game_state.players[0].shih == 1  # No Shih deducted
    assert force.position == (0, 0)  # No move
    assert len(results["errors"]) == 1
    assert "Invalid order for force p1_f1: Advance" in results["errors"]
    assert len(results["confrontations"]) == 0
    assert len(results["revealed_orders"]) == 0

def test_validate_advance_river_on_difficult(sample_game_state):
    """Test Advance with River stance on Difficult terrain (should be valid)."""
    # Add Difficult terrain at an adjacent hex
    sample_game_state.map_data[(1, 0)] = Hex(q=1, r=0, terrain="Difficult")
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.ADVANCE, force, target_hex=(1, 0), stance="River")
    assert validate_order(order, sample_game_state) == True

def test_validate_advance_mountain_on_difficult(sample_game_state):
    """Test Advance with Mountain stance on Difficult terrain (should be valid)."""
    # Add Difficult terrain at an adjacent hex
    sample_game_state.map_data[(1, 0)] = Hex(q=1, r=0, terrain="Difficult")
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.ADVANCE, force, target_hex=(1, 0), stance="Mountain")
    assert validate_order(order, sample_game_state) == True

def test_resolve_orders_advance_into_ghost(sample_game_state):
    """Test Advance order triggers confrontation with ghost."""
    force_p1 = sample_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
    force_p2 = sample_game_state.players[1].forces[0]  # p2_f1 at (24, 19)
    
    # Move p2_f1 to an adjacent position to p1_f1 so DECEIVE can target (1, 0)
    sample_game_state.players[1].forces[0].position = (1, 0)
    
    # Create a ghost at (1, 0) from p2 (now valid since p2_f1 is at (1, 0))
    order_deceive = Order(OrderType.DECEIVE, force_p2, target_hex=(0, 1))
    order_advance = Order(OrderType.ADVANCE, force_p1, target_hex=(0, 1), stance="Mountain")
    
    # DECEIVE is processed before ADVANCE, so ghost exists when ADVANCE is processed
    results = resolve_orders([order_deceive, order_advance], sample_game_state)
    
    # The implementation processes DECEIVE before ADVANCE, so ghost exists
    # and should trigger confrontation
    assert force_p1.position == (0, 0)  # Force doesn't move due to confrontation
    assert len(results["confrontations"]) == 1
    assert results["confrontations"][0]["attacking_force"] == "p1_f1"
    assert results["confrontations"][0]["target_hex"] == (0, 1)
    assert results["confrontations"][0]["ghost_owner"] == "p2"
    assert sample_game_state.players[0].shih == 8  # 10 - 2
    assert sample_game_state.players[1].shih == 7  # 10 - 3

def test_resolve_orders_multiple_meditate_reveals(sample_game_state):
    """Test multiple Meditate orders reveal all adjacent enemy orders."""
    force_p1_1 = sample_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
    force_p1_2 = sample_game_state.players[0].forces[1]  # p1_f2 at (1, 0)
    force_p2_1 = sample_game_state.players[1].forces[0]  # p2_f1 at (24, 19)
    force_p2_2 = sample_game_state.players[1].forces[1]  # p2_f2 at (23, 19)
    
    # Move p2 forces adjacent to p1 forces, avoiding conflicts
    sample_game_state.players[1].forces[0].position = (1, 0)  # p2_f1 adjacent to p1_f1
    sample_game_state.players[1].forces[1].position = (1, 1)  # p2_f2 adjacent to p1_f2 (not conflicting with p1_f3)
    
    order_meditate_1 = Order(OrderType.MEDITATE, force_p1_1)
    order_meditate_2 = Order(OrderType.MEDITATE, force_p1_2)
    # Orders should be for forces at their current positions, use non-conflicting targets
    order_advance_1 = Order(OrderType.ADVANCE, force_p2_1, target_hex=(2, 0), stance="River")
    order_advance_2 = Order(OrderType.ADVANCE, force_p2_2, target_hex=(2, 1), stance="Thunder")
    
    results = resolve_orders([order_meditate_1, order_meditate_2, order_advance_1, order_advance_2], sample_game_state)
    
    assert sample_game_state.players[0].shih == 14  # 10 + 2 + 2
    # Both p2_f1 and p2_f2 should be revealed since they're adjacent to meditating forces
    assert len(results["revealed_orders"]) == 2
    revealed_force_ids = [force_id for force_id, _ in results["revealed_orders"]]
    assert "p2_f1" in revealed_force_ids
    assert "p2_f2" in revealed_force_ids
    assert len(results["confrontations"]) == 0
    assert len(results["errors"]) == 0

def test_resolve_orders_deceive_creates_ghost(sample_game_state):
    """Test Deceive order creates ghost and deducts Shih correctly."""
    force = sample_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
    order = Order(OrderType.DECEIVE, force, target_hex=(1, 0))
    results = resolve_orders([order], sample_game_state)
    
    assert sample_game_state.players[0].shih == 7  # 10 - 3
    assert len(results["confrontations"]) == 0
    assert len(results["revealed_orders"]) == 0
    assert len(results["errors"]) == 0
    
    # Verify ghost was created (this would be checked in a confrontation test)
    # The ghost creation is internal to resolve_orders and not directly exposed

def test_validate_deceive_with_stance(sample_game_state):
    """Test Deceive with invalid stance parameter."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.DECEIVE, force, target_hex=(1, 0), stance="Mountain")
    assert validate_order(order, sample_game_state) == False

def test_validate_advance_out_of_bounds(sample_game_state):
    """Test Advance with target hex outside map bounds."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.ADVANCE, force, target_hex=(25, 20), stance="Mountain")
    assert validate_order(order, sample_game_state) == False

def test_validate_deceive_out_of_bounds(sample_game_state):
    """Test Deceive with target hex outside map bounds."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.DECEIVE, force, target_hex=(-1, -1))
    assert validate_order(order, sample_game_state) == False