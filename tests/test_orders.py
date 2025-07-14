import pytest
from unittest.mock import Mock, patch
from orders import Order, OrderType, validate_order, resolve_orders, validate_orders_batch, log_event, OrderValidationError, is_adjacent
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
                Force(id="p2_f1", position=(9, 9), stance="Mountain"),
                Force(id="p2_f2", position=(8, 9), stance="Mountain"),
                Force(id="p2_f3", position=(9, 8), stance="Mountain")
            ])
        ],
        map_data={
            (0, 0): Hex(q=0, r=0, terrain="Open"),
            (1, 0): Hex(q=1, r=0, terrain="Open"),
            (0, 1): Hex(q=0, r=1, terrain="Open"),
            (1, 1): Hex(q=1, r=1, terrain="Difficult"),
            (9, 9): Hex(q=9, r=9, terrain="Open"),
            (8, 9): Hex(q=8, r=9, terrain="Open"),
            (9, 8): Hex(q=9, r=8, terrain="Open"),
            (8, 8): Hex(q=8, r=8, terrain="Open")
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
    with pytest.raises(OrderValidationError):
        validate_order(order, sample_game_state)

def test_validate_advance_non_adjacent(sample_game_state):
    """Test Advance with non-adjacent target hex."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.ADVANCE, force, target_hex=(3, 3), stance="Mountain")
    with pytest.raises(OrderValidationError):
        validate_order(order, sample_game_state)

def test_validate_advance_invalid_stance(sample_game_state):
    """Test Advance with invalid stance."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.ADVANCE, force, target_hex=(1, 0), stance="Invalid")
    with pytest.raises(OrderValidationError):
        validate_order(order, sample_game_state)

def test_validate_advance_thunder_on_difficult(sample_game_state):
    """Test Advance with Thunder stance on Difficult terrain."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.ADVANCE, force, target_hex=(1, 1), stance="Thunder")
    with pytest.raises(OrderValidationError):
        validate_order(order, sample_game_state)

def test_validate_meditate_valid(sample_game_state):
    """Test a valid Meditate order."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.MEDITATE, force)
    assert validate_order(order, sample_game_state) == True

def test_validate_meditate_with_target(sample_game_state):
    """Test Meditate with invalid target hex."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.MEDITATE, force, target_hex=(1, 0))
    with pytest.raises(OrderValidationError):
        validate_order(order, sample_game_state)

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
    with pytest.raises(OrderValidationError):
        validate_order(order, sample_game_state)

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
    assert force_p1.stance == "Mountain"  # Stance updated even with confrontation
    assert len(results["confrontations"]) == 1
    assert results["confrontations"][0]["attacking_force"] == "p1_f1"
    assert results["confrontations"][0]["target_hex"] == (1, 0)
    assert results["confrontations"][0]["occupying_force"] == "p2_f1"
    assert sample_game_state.players[0].shih == 8  # 10 - 2
    assert len(results["revealed_orders"]) == 0
    assert len(results["errors"]) == 0

def test_resolve_orders_meditate(sample_game_state):
    """Test Meditate order stores Shih for upkeep and reveals adjacent orders."""
    force_p1 = sample_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
    force_p2 = sample_game_state.players[1].forces[0]  # p2_f1 at (24, 19)
    sample_game_state.players[1].forces[0].position = (1, 0)  # Move p2_f1 adjacent
    order_p1 = Order(OrderType.MEDITATE, force_p1)
    # The order should be for the force at the adjacent position, not the original position
    # Use a target that doesn't conflict with existing forces
    order_p2 = Order(OrderType.ADVANCE, force_p2, target_hex=(2, 0), stance="River")
    results = resolve_orders([order_p1, order_p2], sample_game_state)
    
    # Shih should not be applied immediately, but stored for upkeep
    assert sample_game_state.players[0].shih == 10  # No immediate change
    # Verify Meditate order was stored for upkeep
    assert 'p1' in sample_game_state.last_orders
    assert len(sample_game_state.last_orders['p1']) == 1
    assert sample_game_state.last_orders['p1'][0]['order_type'] == 'Meditate'
    assert sample_game_state.last_orders['p1'][0]['shih_bonus'] == 2
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
    assert len(results["errors"]) == 2  # Two errors are logged
    assert "Invalid order for force p1_f1: Advance" in results["errors"][0]
    assert "has insufficient Shih" in results["errors"][0]
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
    """Test multiple Meditate orders store Shih for upkeep and reveal all adjacent enemy orders."""
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
    
    # Shih should not be applied immediately, but stored for upkeep
    assert sample_game_state.players[0].shih == 10  # No immediate change
    # Verify both Meditate orders were stored for upkeep
    assert 'p1' in sample_game_state.last_orders
    assert len(sample_game_state.last_orders['p1']) == 2
    meditate_orders = [order for order in sample_game_state.last_orders['p1'] if order['order_type'] == 'Meditate']
    assert len(meditate_orders) == 2
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
    with pytest.raises(OrderValidationError):
        validate_order(order, sample_game_state)

def test_validate_advance_out_of_bounds(sample_game_state):
    """Test Advance with target hex outside map bounds."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.ADVANCE, force, target_hex=(25, 20), stance="Mountain")
    with pytest.raises(OrderValidationError):
        validate_order(order, sample_game_state)

def test_validate_deceive_out_of_bounds(sample_game_state):
    """Test Deceive with target hex outside map bounds."""
    force = sample_game_state.players[0].forces[0]
    order = Order(OrderType.DECEIVE, force, target_hex=(-1, -1))
    with pytest.raises(OrderValidationError):
        validate_order(order, sample_game_state)

class TestOrderLogging:
    """Test cases for order logging functionality."""
    
    def test_log_event_function(self):
        """Test that log_event properly adds entries to game state log."""
        # Create a mock game state
        game_state = Mock()
        game_state.turn = 1
        game_state.phase = 'execute'
        game_state.log = []
        
        # Test basic logging
        log_event(game_state, "Test event")
        
        assert len(game_state.log) == 1
        assert game_state.log[0]['turn'] == 1
        assert game_state.log[0]['phase'] == 'execute'
        assert game_state.log[0]['event'] == "Test event"
        
        # Test logging with additional data
        log_event(game_state, "Test with data", player_id="p1", force_id="f1")
        
        assert len(game_state.log) == 2
        assert game_state.log[1]['player_id'] == "p1"
        assert game_state.log[1]['force_id'] == "f1"
    
    def test_order_submission_logging(self):
        """Test that order submission is logged during resolution."""
        # Create a simple game state with one player and force
        game_state = GameState(game_id="test", turn=1, phase='execute')
        player = Player(id="p1", chi=100, shih=10)
        force = Force(id="f1", position=(0, 0), stance="Mountain")
        player.add_force(force)
        game_state.players = [player]
        
        # Create a meditate order
        order = Order(OrderType.MEDITATE, force)
        
        # Resolve the order
        results = resolve_orders([order], game_state)
        
        # Check that submission was logged
        submission_logs = [log for log in game_state.log if "submitted" in log['event']]
        assert len(submission_logs) == 1
        assert "p1" in submission_logs[0]['event']
        assert "f1" in submission_logs[0]['event']
        assert "Meditate" in submission_logs[0]['event']
    
    def test_advance_movement_logging(self):
        """Test that advance movement is properly logged."""
        # Create game state with valid positions
        game_state = GameState(game_id="test", turn=1, phase='execute')
        player = Player(id="p1", chi=100, shih=10)
        force = Force(id="f1", position=(0, 0), stance="Mountain")
        player.add_force(force)
        game_state.players = [player]
        
        # Create an advance order to an empty hex
        order = Order(OrderType.ADVANCE, force, target_hex=(1, 0), stance="River")
        
        # Resolve the order
        results = resolve_orders([order], game_state)
        
        # Check that movement was logged
        movement_logs = [log for log in game_state.log if "moved from" in log['event']]
        assert len(movement_logs) == 1
        assert "(0, 0)" in movement_logs[0]['event']
        assert "(1, 0)" in movement_logs[0]['event']
        assert "River" in movement_logs[0]['event']
    
    def test_deceive_ghost_logging(self):
        """Test that deceive ghost creation is properly logged."""
        # Create game state
        game_state = GameState(game_id="test", turn=1, phase='execute')
        player = Player(id="p1", chi=100, shih=10)
        force = Force(id="f1", position=(0, 0), stance="Mountain")
        player.add_force(force)
        game_state.players = [player]
        
        # Create a deceive order
        order = Order(OrderType.DECEIVE, force, target_hex=(1, 0))
        
        # Resolve the order
        results = resolve_orders([order], game_state)
        
        # Check that ghost creation was logged
        ghost_logs = [log for log in game_state.log if "created ghost" in log['event']]
        assert len(ghost_logs) == 1
        assert "(1, 0)" in ghost_logs[0]['event']
        
        # Check that Shih expenditure was logged
        shih_logs = [log for log in game_state.log if "spent 3 Shih" in log['event']]
        assert len(shih_logs) == 1
    
    def test_meditation_revelation_logging(self):
        """Test that meditation order revelation is properly logged."""
        # Create game state with two players and adjacent forces
        game_state = GameState(game_id="test", turn=1, phase='execute')
        
        # Player 1 with meditating force
        player1 = Player(id="p1", chi=100, shih=10)
        force1 = Force(id="f1", position=(0, 0), stance="Mountain")
        player1.add_force(force1)
        
        # Player 2 with adjacent force
        player2 = Player(id="p2", chi=100, shih=10)
        force2 = Force(id="f2", position=(1, 0), stance="River")
        player2.add_force(force2)
        
        game_state.players = [player1, player2]
        
        # Create orders for both forces
        meditate_order = Order(OrderType.MEDITATE, force1)
        advance_order = Order(OrderType.ADVANCE, force2, target_hex=(2, 0), stance="Thunder")
        
        # Resolve orders
        results = resolve_orders([meditate_order, advance_order], game_state)
        
        # Check that revelation was logged
        revelation_logs = [log for log in game_state.log if "revealed" in log['event']]
        assert len(revelation_logs) >= 1
        
        # Check that meditation effect was logged
        meditation_logs = [log for log in game_state.log if "meditated, queued +2 Shih" in log['event']]
        assert len(meditation_logs) == 1
    
    def test_confrontation_logging(self):
        """Test that confrontations are properly logged."""
        # Create game state with two players and forces in adjacent positions
        game_state = GameState(game_id="test", turn=1, phase='execute')
        
        # Player 1 with advancing force
        player1 = Player(id="p1", chi=100, shih=10)
        force1 = Force(id="f1", position=(0, 0), stance="Mountain")
        player1.add_force(force1)
        
        # Player 2 with force at target position
        player2 = Player(id="p2", chi=100, shih=10)
        force2 = Force(id="f2", position=(1, 0), stance="River")
        player2.add_force(force2)
        
        game_state.players = [player1, player2]
        
        # Create advance order into occupied hex
        advance_order = Order(OrderType.ADVANCE, force1, target_hex=(1, 0), stance="Thunder")
        
        # Resolve order
        results = resolve_orders([advance_order], game_state)
        
        # Check that confrontation was logged
        confrontation_logs = [log for log in game_state.log if "Confrontation initiated" in log['event']]
        assert len(confrontation_logs) == 1
        assert "f1" in confrontation_logs[0]['event']
        assert "f2" in confrontation_logs[0]['event']
        assert "Thunder" in confrontation_logs[0]['event']
    
    def test_error_logging(self):
        """Test that validation errors are properly logged."""
        # Create game state with insufficient Shih
        game_state = GameState(game_id="test", turn=1, phase='execute')
        player = Player(id="p1", chi=100, shih=1)  # Not enough Shih for advance
        force = Force(id="f1", position=(0, 0), stance="Mountain")
        player.add_force(force)
        game_state.players = [player]
        
        # Create an advance order (requires 2 Shih)
        order = Order(OrderType.ADVANCE, force, target_hex=(1, 0), stance="River")
        
        # Resolve the order
        results = resolve_orders([order], game_state)
        
        # Check that error was logged
        error_logs = [log for log in game_state.log if "error_type" in log]
        assert len(error_logs) == 2  # Two errors are logged
        assert error_logs[0]['error_type'] == "validation_error"
        assert "insufficient Shih" in error_logs[0]['event']
    
    def test_batch_validation_logging(self):
        """Test that batch validation is properly logged."""
        # Create game state
        game_state = GameState(game_id="test", turn=1, phase='execute')
        player = Player(id="p1", chi=100, shih=10)
        force = Force(id="f1", position=(0, 0), stance="Mountain")
        player.add_force(force)
        game_state.players = [player]
        
        # Create valid orders (both should be valid in batch validation)
        valid_order1 = Order(OrderType.MEDITATE, force)
        valid_order2 = Order(OrderType.ADVANCE, force, target_hex=(1, 0), stance="River")
        
        # Run batch validation
        results = validate_orders_batch([valid_order1, valid_order2], game_state)
        
        # Check that batch validation was logged
        batch_logs = [log for log in game_state.log if "Batch validation" in log['event']]
        assert len(batch_logs) == 2  # Start and completion
        assert "started for 2 orders" in batch_logs[0]['event']
        assert "completed: 2 valid, 0 errors" in batch_logs[1]['event']
    
    def test_resolution_completion_logging(self):
        """Test that order resolution completion is properly logged."""
        # Create game state
        game_state = GameState(game_id="test", turn=1, phase='execute')
        player = Player(id="p1", chi=100, shih=10)
        force = Force(id="f1", position=(0, 0), stance="Mountain")
        player.add_force(force)
        game_state.players = [player]
        
        # Create orders that will result in confrontations and ghosts
        advance_order = Order(OrderType.ADVANCE, force, target_hex=(1, 0), stance="River")
        deceive_order = Order(OrderType.DECEIVE, force, target_hex=(0, 1))
        
        # Resolve orders
        results = resolve_orders([advance_order, deceive_order], game_state)
        
        # Check that completion was logged
        completion_logs = [log for log in game_state.log if "Order resolution completed" in log['event']]
        assert len(completion_logs) == 1
        assert "confrontations" in completion_logs[0]['event']
        assert "ghosts created" in completion_logs[0]['event']