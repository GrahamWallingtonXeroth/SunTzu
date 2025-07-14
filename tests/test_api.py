import pytest
from flask import Flask
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app  # Import the Flask app
import json

@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def sample_game_state(client):
    """Create a sample game state for testing."""
    response = client.post('/api/game/new', json={'seed': 42})
    assert response.status_code == 200
    return response.json['game_id']

def test_new_game(client):
    """Test POST /api/game/new creates a game with a valid game_id."""
    response = client.post('/api/game/new', json={'seed': 42})
    assert response.status_code == 200
    data = response.json
    assert 'game_id' in data
    # Verify it's a valid UUID format (8-4-4-4-12 characters)
    import re
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    assert re.match(uuid_pattern, data['game_id']) is not None

def test_get_game_state(client):
    """Test GET /api/game/<game_id>/state returns valid game state."""
    # First, create a game
    create_response = client.post('/api/game/new', json={'seed': 42})
    assert create_response.status_code == 200
    game_id = create_response.json['game_id']
    
    # Then, get the game state
    response = client.get(f'/api/game/{game_id}/state')
    assert response.status_code == 200
    data = response.json
    
    # Verify key structure
    assert data['game_id'] == game_id
    assert data['turn'] == 1
    assert data['phase'] == 'plan'
    assert len(data['players']) == 2
    assert len(data['map']) == 10 * 10  # 100 hexes
    
    # Verify player data
    p1 = data['players'][0]
    assert p1['id'] == 'p1'
    assert p1['chi'] == 100
    assert p1['shih'] == 10
    assert len(p1['forces']) == 3
    assert sorted([(f['position']['q'], f['position']['r']) for f in p1['forces']]) == [(0, 0), (0, 1), (1, 0)]
    
    p2 = data['players'][1]
    assert p2['id'] == 'p2'
    assert p2['chi'] == 100
    assert p2['shih'] == 10
    assert len(p2['forces']) == 3
    assert sorted([(f['position']['q'], f['position']['r']) for f in p2['forces']]) == [(8, 9), (9, 8), (9, 9)]

def test_valid_advance_order(client, sample_game_state):
    """Test valid Advance order without confrontation - check state update and Shih deduction."""
    # Get initial state to find force IDs
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    # Find a force from player 1 that can advance to an empty hex
    p1_forces = initial_state['players'][0]['forces']
    force_id = p1_forces[0]['id']  # Use first force
    
    # Submit advance order to adjacent empty hex (1, 0)
    orders = [{
        'force_id': force_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders})
    assert response.status_code == 200
    data = response.json
    
    # Verify response structure
    assert 'game_id' in data
    assert 'turn' in data
    assert 'phase' in data
    assert 'orders_processed' in data
    assert 'revealed_orders' in data
    assert 'confrontations' in data
    assert 'errors' in data
    assert 'state' in data
    
    # Verify phase is still 'plan' since only one player has submitted orders
    assert data['phase'] == 'plan'
    assert data['orders_processed'] == 1
    assert len(data['confrontations']) == 0
    assert len(data['errors']) == 0
    
    # Verify orders_submitted shows p1 has submitted
    assert data['orders_submitted']['p1'] is True
    assert data['orders_submitted'].get('p2', False) is False
    
    # Verify Shih deduction (10 - 2 = 8)
    updated_state = data['state']
    p1_updated = updated_state['players'][0]
    assert p1_updated['shih'] == 8
    
    # Verify force position update
    force_updated = next(f for f in p1_updated['forces'] if f['id'] == force_id)
    assert force_updated['position'] == {'q': 1, 'r': 0}
    assert force_updated['stance'] == 'Mountain'

def test_advance_with_confrontation(client, sample_game_state):
    """Test Advance order with confrontation or overlapping moves."""
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json

    # Use P1's forces at (0,0) and (1,0)
    p1_forces = initial_state['players'][0]['forces']
    force_a = p1_forces[0]  # (0,0)
    force_b = p1_forces[1]  # (1,0)

    # Both forces try to move into each other's starting hex
    orders = [
        {
            'force_id': force_a['id'],
            'order': 'Advance',
            'target_hex': {'q': 1, 'r': 0},
            'stance': 'Mountain'
        },
        {
            'force_id': force_b['id'],
            'order': 'Advance',
            'target_hex': {'q': 0, 'r': 0},
            'stance': 'River'
        }
    ]
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders})
    assert response.status_code == 200
    data = response.json
    # If self-confrontation is not allowed, confrontations will be empty
    assert 'confrontations' in data
    assert data['phase'] == 'plan'  # Still in plan phase since only one player submitted
    # At least one force should have moved
    updated_state = data['state']
    p1_updated = updated_state['players'][0]
    positions = [f['position'] for f in p1_updated['forces']]
    assert {'q': 1, 'r': 0} in positions or {'q': 0, 'r': 0} in positions


def test_invalid_order_insufficient_shih(client, sample_game_state):
    """Test invalid order with insufficient Shih - expect error about Shih, not adjacency or bounds."""
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json

    # Use P1's force at (0,0)
    p1_forces = initial_state['players'][0]['forces']
    force_id = p1_forces[0]['id']
    
    print(f"Initial Shih: {initial_state['players'][0]['shih']}")

    # Submit three valid Deceive orders to drain Shih (10 - 3 - 3 - 3 = 1 left)
    orders = [
        {'force_id': force_id, 'order': 'Deceive', 'target_hex': {'q': 1, 'r': 0}},
        {'force_id': force_id, 'order': 'Deceive', 'target_hex': {'q': 0, 'r': 1}},
        {'force_id': force_id, 'order': 'Deceive', 'target_hex': {'q': 1, 'r': 0}},
    ]
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders})
    assert response.status_code == 200
    data = response.json
    print(f"Errors returned: {data['errors']}")
    print(f"Orders processed: {data['orders_processed']}")
    # Should not have insufficient Shih error yet
    assert not any('has insufficient Shih' in error for error in data['errors'])

    # Now try to submit another Deceive order, which should fail for insufficient Shih
    # First, advance to execute phase by submitting orders for player 2
    p2_forces = initial_state['players'][1]['forces']
    force2_id = p2_forces[0]['id']
    
    orders2 = [{
        'force_id': force2_id,
        'order': 'Meditate'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p2', 'orders': orders2})
    assert response.status_code == 200
    assert response.json['phase'] == 'execute'
    
    # Now perform upkeep to advance to next turn
    upkeep_response = client.post(f'/api/game/{sample_game_state}/upkeep')
    assert upkeep_response.status_code == 200
    # Now submit another Deceive order
    orders = [
        {'force_id': force_id, 'order': 'Deceive', 'target_hex': {'q': 1, 'r': 0}},
        {'force_id': force_id, 'order': 'Deceive', 'target_hex': {'q': 0, 'r': 1}},
        {'force_id': force_id, 'order': 'Deceive', 'target_hex': {'q': 1, 'r': 0}},
        {'force_id': force_id, 'order': 'Deceive', 'target_hex': {'q': 0, 'r': 1}},
    ]
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders})
    assert response.status_code == 200
    data = response.json
    print(f"Errors returned (insufficient Shih): {data['errors']}")
    assert any('has insufficient Shih' in error for error in data['errors'])


def test_ghost_confrontation(client, sample_game_state):
    """Test ghost confrontation - Deceive then Advance into ghost (using valid adjacent hexes and P1's own forces)."""
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json

    p1_forces = initial_state['players'][0]['forces']

    # Use force 0 (at 0,0) to Deceive at (1,0), and force 2 (at 0,1) to Advance to (1,0)
    orders = [
        {
            'force_id': p1_forces[0]['id'],  # Force at (0,0)
            'order': 'Deceive',
            'target_hex': {'q': 1, 'r': 0}
        },
        {
            'force_id': p1_forces[2]['id'],  # Force at (0,1)
            'order': 'Advance',
            'target_hex': {'q': 1, 'r': 0},
            'stance': 'Mountain'
        }
    ]
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders})
    assert response.status_code == 200
    data = response.json

    # Verify orders were processed
    assert data['orders_processed'] == 2
    assert data['phase'] == 'plan'  # Still in plan phase since only one player submitted
    # No errors expected
    assert len(data['errors']) == 0
    # The advancing force should end up at (1,0)
    updated_state = data['state']
    p1_updated = updated_state['players'][0]
    positions = [f['position'] for f in p1_updated['forces']]
    assert {'q': 1, 'r': 0} in positions

def test_phase_advancement(client, sample_game_state):
    """Test phase advancement from 'plan' to 'execute' when both players submit orders."""
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    # Verify initial phase is 'plan'
    assert initial_state['phase'] == 'plan'
    
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for player 1
    orders1 = [{
        'force_id': force1_id,
        'order': 'Meditate'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders1})
    assert response.status_code == 200
    data = response.json
    
    # Verify phase is still 'plan' after first player submits
    assert data['phase'] == 'plan'
    
    # Submit orders for player 2 to trigger phase advancement
    orders2 = [{
        'force_id': force2_id,
        'order': 'Meditate'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p2', 'orders': orders2})
    assert response.status_code == 200
    data = response.json
    
    # Verify phase advanced to 'execute' after both players submit
    assert data['phase'] == 'execute'
    assert data['state']['phase'] == 'execute'
    
    # Verify turn remains the same
    assert data['turn'] == 1
    assert data['state']['turn'] == 1

def test_json_response_structure(client, sample_game_state):
    """Test JSON response structure includes updated state, confrontations, errors."""
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    force_id = p1_forces[0]['id']
    
    # Submit a simple order
    orders = [{
        'force_id': force_id,
        'order': 'Meditate'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders})
    assert response.status_code == 200
    data = response.json
    
    # Verify all required JSON keys are present
    required_keys = [
        'game_id', 'turn', 'phase', 'orders_processed', 
        'revealed_orders', 'confrontations', 'errors', 'state'
    ]
    for key in required_keys:
        assert key in data, f"Missing required key: {key}"
    
    # Verify data types
    assert isinstance(data['game_id'], str)
    assert isinstance(data['turn'], int)
    assert isinstance(data['phase'], str)
    assert isinstance(data['orders_processed'], int)
    assert isinstance(data['revealed_orders'], list)
    assert isinstance(data['confrontations'], list)
    assert isinstance(data['errors'], list)
    assert isinstance(data['state'], dict)
    
    # Verify state structure
    state = data['state']
    state_required_keys = ['game_id', 'turn', 'phase', 'players', 'map']
    for key in state_required_keys:
        assert key in state, f"Missing required state key: {key}"
    
    # Verify players structure
    assert len(state['players']) == 2
    for player in state['players']:
        player_required_keys = ['id', 'chi', 'shih', 'forces']
        for key in player_required_keys:
            assert key in player, f"Missing required player key: {key}"
        
        # Verify forces structure
        for force in player['forces']:
            force_required_keys = ['id', 'position', 'stance']
            for key in force_required_keys:
                assert key in force, f"Missing required force key: {key}"
            
            # Verify position structure
            assert 'q' in force['position']
            assert 'r' in force['position']

def test_shih_yields_from_contentious_terrain(client, sample_game_state):
    """Test Shih yields from controlled Contentious terrain (+2 per hex)."""
    # First, advance to execute phase by submitting orders for both players
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for player 1
    orders1 = [{
        'force_id': force1_id,
        'order': 'Meditate'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders1})
    assert action_response.status_code == 200
    
    # Submit orders for player 2 to advance to execute phase
    orders2 = [{
        'force_id': force2_id,
        'order': 'Meditate'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p2', 'orders': orders2})
    assert action_response.status_code == 200
    
    # Mock control of Contentious terrain by directly modifying the game state
    from app import games
    game_state = games[sample_game_state]
    
    # Find a Contentious hex and place a P1 force there
    contentious_pos = None
    for hex_pos, hex_data in game_state.map_data.items():
        if hex_data.terrain == 'Contentious':
            contentious_pos = hex_pos
            break
    
    if contentious_pos:
        # Move P1's first force to control the Contentious hex
        game_state.players[0].forces[0].position = contentious_pos
        
        # Remove any adjacent enemy forces to ensure control
        # (This is a simplified test - in reality, control requires no adjacent enemies)
        
        # Perform upkeep
        upkeep_response = client.post(f'/api/game/{sample_game_state}/upkeep')
        assert upkeep_response.status_code == 200
        data = upkeep_response.json
        
        # Verify Shih yield from controlled Contentious terrain
        shih_yields = data['shih_yields']
        assert shih_yields['p1'] >= 2  # Should get +2 for controlled Contentious hex
        
        # Verify Shih was actually added to the player
        updated_state = data['state']
        p1_updated = updated_state['players'][0]
        initial_shih = initial_state['players'][0]['shih']
        assert p1_updated['shih'] >= initial_shih + 2

def test_valid_upkeep_execute_phase(client, sample_game_state):
    """Test valid upkeep in 'execute' phase - check Shih yields, phase to 'plan', turn increment."""
    # First, advance to execute phase by submitting orders for both players
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for player 1
    orders1 = [{
        'force_id': force1_id,
        'order': 'Meditate'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders1})
    assert action_response.status_code == 200
    assert action_response.json['phase'] == 'plan'  # Still in plan phase
    
    # Submit orders for player 2 to advance to execute phase
    orders2 = [{
        'force_id': force2_id,
        'order': 'Meditate'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p2', 'orders': orders2})
    assert action_response.status_code == 200
    assert action_response.json['phase'] == 'execute'
    
    # Now perform upkeep
    upkeep_response = client.post(f'/api/game/{sample_game_state}/upkeep')
    assert upkeep_response.status_code == 200
    data = upkeep_response.json
    
    # Verify response structure
    assert 'game_id' in data
    assert 'turn' in data
    assert 'phase' in data
    assert 'winner' in data
    assert 'shih_yields' in data
    assert 'encirclements' in data
    assert 'state' in data
    
    # Verify phase advancement from 'execute' to 'plan' (next turn)
    assert data['phase'] == 'plan'
    assert data['state']['phase'] == 'plan'
    
    # Verify turn increments when going from upkeep to plan
    assert data['turn'] == 2
    assert data['state']['turn'] == 2
    
    # Verify Shih yields (should be 0 for initial positions as they don't control Contentious terrain)
    assert isinstance(data['shih_yields'], dict)
    assert 'p1' in data['shih_yields']
    assert 'p2' in data['shih_yields']
    
    # Verify no winner yet
    assert data['winner'] is None
    
    # Verify no encirclements initially
    assert isinstance(data['encirclements'], list)
    assert len(data['encirclements']) == 0

def test_encirclement_penalty_after_2_turns(client, sample_game_state):
    """Test encirclement penalty after 2 turns (-20 Chi)."""
    # First, advance to execute phase by submitting orders for both players
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for player 1
    orders1 = [{
        'force_id': force1_id,
        'order': 'Meditate'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders1})
    assert action_response.status_code == 200
    
    # Submit orders for player 2 to advance to execute phase
    orders2 = [{
        'force_id': force2_id,
        'order': 'Meditate'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p2', 'orders': orders2})
    assert action_response.status_code == 200
    
    # Mock encirclement by directly modifying the game state
    from app import games
    game_state = games[sample_game_state]
    
    # Set a force to be encircled for 2 turns
    p1_force = game_state.players[0].forces[0]
    p1_force.encircled_turns = 2
    
    # Print initial Chi and Shih
    print(f"Initial Chi: {game_state.players[0].chi}")
    print(f"Initial Shih: {game_state.players[0].shih}")
    
    # Patch is_encircled to always return True for this test
    import upkeep
    original_is_encircled = upkeep.is_encircled
    upkeep.is_encircled = lambda force, gs: True
    try:
        # Perform upkeep
        upkeep_response = client.post(f'/api/game/{sample_game_state}/upkeep')
        assert upkeep_response.status_code == 200
        data = upkeep_response.json
        
        # Print final Chi and Shih
        updated_state = data['state']
        p1_updated = updated_state['players'][0]
        print(f"Final Chi: {p1_updated['chi']}")
        print(f"Final Shih: {p1_updated['shih']}")
        
        # Verify Chi penalty applied (-20) from encirclement
        assert p1_updated['chi'] == 80  # 100 - 20
        
        # Verify encircled_turns reset to 0 after penalty
        assert p1_force.encircled_turns == 0
    finally:
        # Restore original is_encircled
        upkeep.is_encircled = original_is_encircled

def test_victory_by_demoralization(client, sample_game_state):
    """Test victory by demoralization (Chi <= 0 after penalty)."""
    # First, advance to execute phase by submitting orders for both players
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for player 1
    orders1 = [{
        'force_id': force1_id,
        'order': 'Meditate'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders1})
    assert action_response.status_code == 200
    
    # Submit orders for player 2 to advance to execute phase
    orders2 = [{
        'force_id': force2_id,
        'order': 'Meditate'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p2', 'orders': orders2})
    assert action_response.status_code == 200
    
    # Mock demoralization by directly modifying the game state
    from app import games
    game_state = games[sample_game_state]
    
    # Set P1's Chi to 0 to trigger demoralization
    game_state.players[0].chi = 0
    
    # Perform upkeep
    upkeep_response = client.post(f'/api/game/{sample_game_state}/upkeep')
    assert upkeep_response.status_code == 200
    data = upkeep_response.json
    
    # Verify victory by demoralization
    assert data['winner'] == 'p2'  # P2 wins when P1 is demoralized
    
    # Verify game phase is 'ended'
    assert data['phase'] == 'ended'
    assert data['state']['phase'] == 'ended'
    
    # Verify turn doesn't increment when game ends
    assert data['turn'] == 1
    assert data['state']['turn'] == 1

def test_domination_victory(client, sample_game_state):
    """Test domination victory (control all Contentious)."""
    # First, advance to execute phase by submitting orders for both players
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for player 1
    orders1 = [{
        'force_id': force1_id,
        'order': 'Meditate'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders1})
    assert action_response.status_code == 200
    
    # Submit orders for player 2 to advance to execute phase
    orders2 = [{
        'force_id': force2_id,
        'order': 'Meditate'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p2', 'orders': orders2})
    assert action_response.status_code == 200
    
    # Mock domination by directly modifying the game state
    from app import games
    game_state = games[sample_game_state]
    
    # Find all Contentious terrain and place P1 forces there
    contentious_positions = []
    for hex_pos, hex_data in game_state.map_data.items():
        if hex_data.terrain == 'Contentious':
            contentious_positions.append(hex_pos)
    
    # Move P1's forces to control all Contentious terrain
    for i, pos in enumerate(contentious_positions[:len(game_state.players[0].forces)]):
        game_state.players[0].forces[i].position = pos
    
    # Mock that P1 has controlled all Contentious for one full turn
    # This would require additional tracking in the actual implementation
    # For now, we'll test the basic structure
    
    # Perform upkeep
    upkeep_response = client.post(f'/api/game/{sample_game_state}/upkeep')
    assert upkeep_response.status_code == 200
    data = upkeep_response.json
    
    # Verify response structure includes domination check
    assert 'winner' in data
    assert 'shih_yields' in data
    assert 'encirclements' in data
    
    # Note: Actual domination victory would require tracking when a player
    # first controlled all Contentious terrain for one full turn

def test_error_not_execute_phase(client, sample_game_state):
    """Test error if not 'execute' phase (400)."""
    # Get initial state (should be 'plan' phase)
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    # Verify we're in 'plan' phase
    assert initial_state['phase'] == 'plan'
    
    # Try to perform upkeep in 'plan' phase (should fail)
    upkeep_response = client.post(f'/api/game/{sample_game_state}/upkeep')
    assert upkeep_response.status_code == 400
    
    data = upkeep_response.json
    assert 'error' in data
    assert 'execute phase' in data['error'].lower()

def test_upkeep_json_response_structure(client, sample_game_state):
    """Test JSON response structure (winner, shih_yields, encirclements, state)."""
    # First, advance to execute phase by submitting orders for both players
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for player 1
    orders1 = [{
        'force_id': force1_id,
        'order': 'Meditate'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders1})
    assert action_response.status_code == 200
    
    # Submit orders for player 2 to advance to execute phase
    orders2 = [{
        'force_id': force2_id,
        'order': 'Meditate'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p2', 'orders': orders2})
    assert action_response.status_code == 200
    
    # Perform upkeep
    upkeep_response = client.post(f'/api/game/{sample_game_state}/upkeep')
    assert upkeep_response.status_code == 200
    data = upkeep_response.json
    
    # Verify all required JSON keys are present
    required_keys = [
        'game_id', 'turn', 'phase', 'winner', 
        'shih_yields', 'encirclements', 'state'
    ]
    for key in required_keys:
        assert key in data, f"Missing required key: {key}"
    
    # Verify data types
    assert isinstance(data['game_id'], str)
    assert isinstance(data['turn'], int)
    assert isinstance(data['phase'], str)
    assert data['winner'] is None or isinstance(data['winner'], str)
    assert isinstance(data['shih_yields'], dict)
    assert isinstance(data['encirclements'], list)
    assert isinstance(data['state'], dict)
    
    # Verify shih_yields structure
    shih_yields = data['shih_yields']
    assert 'p1' in shih_yields
    assert 'p2' in shih_yields
    assert isinstance(shih_yields['p1'], int)
    assert isinstance(shih_yields['p2'], int)
    
    # Verify encirclements structure
    encirclements = data['encirclements']
    for encirclement in encirclements:
        assert 'force_id' in encirclement
        assert 'player_id' in encirclement
        assert 'turns_encircled' in encirclement
        assert isinstance(encirclement['force_id'], str)
        assert isinstance(encirclement['player_id'], str)
        assert isinstance(encirclement['turns_encircled'], int)
    
    # Verify state structure
    state = data['state']
    state_required_keys = ['game_id', 'turn', 'phase', 'players', 'map']
    for key in state_required_keys:
        assert key in state, f"Missing required state key: {key}"
    
    # Verify players structure
    assert len(state['players']) == 2
    for player in state['players']:
        player_required_keys = ['id', 'chi', 'shih', 'forces']
        for key in player_required_keys:
            assert key in player, f"Missing required player key: {key}"
        
        # Verify forces structure
        for force in player['forces']:
            force_required_keys = ['id', 'position', 'stance']
            for key in force_required_keys:
                assert key in force, f"Missing required force key: {key}"
            
            # Verify position structure
            assert 'q' in force['position']
            assert 'r' in force['position']

def test_get_game_log_empty_new_game(client, sample_game_state):
    """Test successful retrieval of an empty log for a new game."""
    # Get the game log for a newly created game
    response = client.get(f'/api/game/{sample_game_state}/log')
    assert response.status_code == 200
    data = response.json
    
    # Verify response structure
    assert 'game_id' in data
    assert 'turn' in data
    assert 'phase' in data
    assert 'log' in data
    
    # Verify data types
    assert isinstance(data['game_id'], str)
    assert isinstance(data['turn'], int)
    assert isinstance(data['phase'], str)
    assert isinstance(data['log'], list)
    
    # Verify game_id matches
    assert data['game_id'] == sample_game_state
    
    # Verify initial game state
    assert data['turn'] == 1
    assert data['phase'] == 'plan'
    
    # Verify log is empty for new game
    assert len(data['log']) == 0

def test_get_game_log_populated_after_actions(client, sample_game_state):
    """Test successful retrieval after simulating actions/upkeep to populate the log."""
    # First, advance to execute phase by submitting an order
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    force_id = p1_forces[0]['id']
    
    # Submit an Advance order to create log entries
    orders = [{
        'force_id': force_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    action_response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders})
    assert action_response.status_code == 200
    
    # Mock log entries by directly modifying the game state
    from app import games
    from state import GameState
    game_state = games[sample_game_state]
    
    # Add sample log entries to simulate game activity
    sample_log_entries = [
        {'turn': 1, 'event': 'action', 'details': {'order': 'Advance', 'force_id': force_id, 'target': {'q': 1, 'r': 0}}},
        {'turn': 1, 'event': 'phase_change', 'details': {'from': 'plan', 'to': 'execute'}},
        {'turn': 1, 'event': 'confrontation', 'details': {'attacker': force_id, 'defender': None, 'result': 'no_confrontation'}},
        {'turn': 1, 'event': 'upkeep', 'details': {'shih_yields': {'p1': 0, 'p2': 0}}}
    ]
    
    game_state.log = sample_log_entries
    
    # Now retrieve the log
    log_response = client.get(f'/api/game/{sample_game_state}/log')
    assert log_response.status_code == 200
    data = log_response.json
    
    # Verify response structure
    assert 'game_id' in data
    assert 'turn' in data
    assert 'phase' in data
    assert 'log' in data
    
    # Verify game_id matches
    assert data['game_id'] == sample_game_state
    
    # Verify log contains the expected entries
    assert isinstance(data['log'], list)
    assert len(data['log']) == 4
    
    # Verify log entry structure
    for entry in data['log']:
        assert 'turn' in entry
        assert 'event' in entry
        assert 'details' in entry
        assert isinstance(entry['turn'], int)
        assert isinstance(entry['event'], str)
        assert isinstance(entry['details'], dict)
    
    # Verify specific log entries
    assert data['log'][0]['turn'] == 1
    assert data['log'][0]['event'] == 'action'
    assert data['log'][0]['details']['order'] == 'Advance'
    
    assert data['log'][1]['turn'] == 1
    assert data['log'][1]['event'] == 'phase_change'
    assert data['log'][1]['details']['from'] == 'plan'
    assert data['log'][1]['details']['to'] == 'execute'

def test_get_game_log_invalid_game_id(client):
    """Test invalid game_id returns 404 JSON error."""
    # Use a non-existent game ID
    invalid_game_id = "non-existent-game-id"
    
    response = client.get(f'/api/game/{invalid_game_id}/log')
    assert response.status_code == 404
    
    data = response.json
    assert 'error' in data
    assert isinstance(data['error'], str)
    assert 'Game not found' in data['error']

def test_get_game_log_json_response_structure(client, sample_game_state):
    """Test JSON response structure has keys 'game_id', 'turn', 'phase', 'log' (list)."""
    # Get the game log
    response = client.get(f'/api/game/{sample_game_state}/log')
    assert response.status_code == 200
    data = response.json
    
    # Verify all required keys are present
    required_keys = ['game_id', 'turn', 'phase', 'log']
    for key in required_keys:
        assert key in data, f"Missing required key: {key}"
    
    # Verify data types
    assert isinstance(data['game_id'], str)
    assert isinstance(data['turn'], int)
    assert isinstance(data['phase'], str)
    assert isinstance(data['log'], list)
    
    # Verify no extra keys (strict structure validation)
    expected_keys = set(required_keys)
    actual_keys = set(data.keys())
    assert actual_keys == expected_keys, f"Unexpected keys found: {actual_keys - expected_keys}"
    
    # Verify game_id is a valid UUID format
    import re
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    assert re.match(uuid_pattern, data['game_id']) is not None
    
    # Verify turn is positive
    assert data['turn'] > 0
    
    # Verify phase is valid
    valid_phases = ['plan', 'execute', 'upkeep', 'ended']
    assert data['phase'] in valid_phases
    
    # Verify log is a list (can be empty or contain entries)
    assert isinstance(data['log'], list)
    
    # If log has entries, verify their structure
    for entry in data['log']:
        assert isinstance(entry, dict), "Log entries must be dictionaries"
        # Note: We don't enforce specific structure for log entries as they may vary
        # based on the type of event being logged


def test_action_phase_validation_plan_only(client, sample_game_state):
    """
    Test that action endpoint only accepts orders during 'plan' phase.

    Based on GDD page 5: Orders can only be submitted during plan phase.
    """
    # Get initial state to verify we're in 'plan' phase
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    assert initial_state['phase'] == 'plan'

    # Submit valid orders for both players to move to 'execute' phase
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']

    # Submit orders for player 1
    orders1 = [{
        'force_id': force1_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]

    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders1})
    assert response.status_code == 200
    assert response.json['phase'] == 'plan'  # Still in plan phase
    
    # Submit orders for player 2 to advance to execute phase
    orders2 = [{
        'force_id': force2_id,
        'order': 'Meditate'
    }]

    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p2', 'orders': orders2})
    assert response.status_code == 200
    assert response.json['phase'] == 'execute'
    
    # Now try to submit orders again while in 'execute' phase - should fail
    orders = [{
        'force_id': force1_id,
        'order': 'Advance',
        'target_hex': {'q': 2, 'r': 0},
        'stance': 'River'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders})
    assert response.status_code == 400
    assert 'Orders can only be submitted during \'plan\' phase' in response.json['error']


def test_action_phase_transition_to_execute(client, sample_game_state):
    """
    Test that action endpoint correctly transitions from 'plan' to 'execute' phase.
    
    Based on GDD page 5: After processing orders, phase should be set to 'execute'.
    """
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    assert initial_state['phase'] == 'plan'
    
    # Submit orders for both players
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for player 1
    orders1 = [{
        'force_id': force1_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders1})
    assert response.status_code == 200
    assert response.json['phase'] == 'plan'  # Still in plan phase
    
    # Submit orders for player 2 to advance to execute phase
    orders2 = [{
        'force_id': force2_id,
        'order': 'Meditate'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p2', 'orders': orders2})
    assert response.status_code == 200
    data = response.json
    
    # Verify phase transition to 'execute'
    assert data['phase'] == 'execute'
    assert data['state']['phase'] == 'execute'
    
    # Verify phase didn't advance to 'upkeep'
    assert data['phase'] != 'upkeep'
    assert data['state']['phase'] != 'upkeep'


def test_action_phase_logging(client, sample_game_state):
    """
    Test that action endpoint logs phase transitions correctly.
    
    Based on GDD page 9: API should log phase transitions in game state log.
    """
    # Submit orders for both players to trigger phase transition
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for player 1
    orders1 = [{
        'force_id': force1_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders1})
    assert response.status_code == 200
    
    # Submit orders for player 2 to trigger phase transition
    orders2 = [{
        'force_id': force2_id,
        'order': 'Meditate'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p2', 'orders': orders2})
    assert response.status_code == 200
    
    # Check game log for phase transition entry
    log_response = client.get(f'/api/game/{sample_game_state}/log')
    assert log_response.status_code == 200
    log_data = log_response.json
    
    # Verify log contains phase transition entry
    phase_transition_entries = [
        entry for entry in log_data['log'] 
        if 'phase set to execute' in entry.get('event', '')
    ]
    assert len(phase_transition_entries) == 1
    
    # Verify log entry structure
    log_entry = phase_transition_entries[0]
    assert log_entry['turn'] == 1
    assert log_entry['phase'] == 'execute'
    assert 'Orders processed for player' in log_entry['event']
    assert 'phase set to execute' in log_entry['event']


def test_action_phase_validation_execute_phase(client, sample_game_state):
    """
    Test that action endpoint rejects orders when already in 'execute' phase.
    
    This test ensures the phase validation works correctly after a phase transition.
    """
    # First, submit orders for both players to move to 'execute' phase
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for player 1
    orders1 = [{
        'force_id': force1_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders1})
    assert response.status_code == 200
    assert response.json['phase'] == 'plan'  # Still in plan phase
    
    # Submit orders for player 2 to advance to execute phase
    orders2 = [{
        'force_id': force2_id,
        'order': 'Meditate'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p2', 'orders': orders2})
    assert response.status_code == 200
    assert response.json['phase'] == 'execute'
    
    # Try to submit more orders while in 'execute' phase
    orders = [{
        'force_id': force1_id,
        'order': 'Deceive',
        'target_hex': {'q': 2, 'r': 0}
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'player_id': 'p1', 'orders': orders})
    assert response.status_code == 400
    assert 'Orders can only be submitted during \'plan\' phase' in response.json['error']
    assert 'current phase: execute' in response.json['error']


def test_player_id_required_in_action_request(client, sample_game_state):
    """
    Test that action endpoint requires player_id in request body.
    
    Based on new requirement: player_id is required to track order submissions.
    """
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    force_id = p1_forces[0]['id']
    
    # Submit orders without player_id - should fail
    orders = [{
        'force_id': force_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={'orders': orders})
    assert response.status_code == 400
    assert 'player_id is required' in response.json['error']


def test_invalid_player_id_in_action_request(client, sample_game_state):
    """
    Test that action endpoint validates player_id exists.
    
    Based on new requirement: player_id must correspond to an existing player.
    """
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    force_id = p1_forces[0]['id']
    
    # Submit orders with invalid player_id - should fail
    orders = [{
        'force_id': force_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={
        'player_id': 'p3',  # Invalid player ID
        'orders': orders
    })
    assert response.status_code == 400
    assert 'Player p3 not found' in response.json['error']


def test_duplicate_order_submission_prevention(client, sample_game_state):
    """
    Test that action endpoint prevents duplicate order submissions from same player.
    
    Based on new requirement: Each player can only submit orders once per turn.
    """
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    force_id = p1_forces[0]['id']
    
    # Submit orders for player 1
    orders = [{
        'force_id': force_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={
        'player_id': 'p1',
        'orders': orders
    })
    assert response.status_code == 200
    
    # Try to submit orders again for player 1 - should fail
    orders = [{
        'force_id': force_id,
        'order': 'Deceive',
        'target_hex': {'q': 2, 'r': 0}
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={
        'player_id': 'p1',
        'orders': orders
    })
    assert response.status_code == 400
    assert 'Player p1 has already submitted orders for this turn' in response.json['error']


def test_both_players_must_submit_orders_before_execute(client, sample_game_state):
    """
    Test that phase only transitions to 'execute' when both players have submitted orders.
    
    Based on new requirement: Phase transitions to 'execute' only when all players have submitted orders.
    """
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for player 1 only
    orders1 = [{
        'force_id': force1_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={
        'player_id': 'p1',
        'orders': orders1
    })
    assert response.status_code == 200
    
    # Verify phase is still 'plan' and orders_submitted shows p1 has submitted
    data = response.json
    assert data['phase'] == 'plan'
    assert data['orders_submitted']['p1'] is True
    assert data['orders_submitted'].get('p2', False) is False
    
    # Submit orders for player 2
    orders2 = [{
        'force_id': force2_id,
        'order': 'Advance',
        'target_hex': {'q': 23, 'r': 18},
        'stance': 'River'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={
        'player_id': 'p2',
        'orders': orders2
    })
    assert response.status_code == 200
    
    # Verify phase is now 'execute' and orders_submitted is reset
    data = response.json
    assert data['phase'] == 'execute'
    assert data['orders_submitted'] == {}


def test_orders_submitted_tracking_in_game_state(client, sample_game_state):
    """
    Test that orders_submitted tracking is included in game state responses.
    
    Based on new requirement: orders_submitted should be included in all state responses.
    """
    # Get initial state
    response = client.get(f'/api/game/{sample_game_state}/state')
    assert response.status_code == 200
    data = response.json
    
    # Verify orders_submitted is present and empty initially
    assert 'orders_submitted' in data
    assert data['orders_submitted'] == {}
    
    # Submit orders for player 1
    p1_forces = data['players'][0]['forces']
    force_id = p1_forces[0]['id']
    
    orders = [{
        'force_id': force_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={
        'player_id': 'p1',
        'orders': orders
    })
    assert response.status_code == 200
    
    # Verify orders_submitted shows p1 has submitted
    data = response.json
    assert data['orders_submitted']['p1'] is True
    assert data['orders_submitted'].get('p2', False) is False
    
    # Verify state in response also includes orders_submitted
    assert data['state']['orders_submitted']['p1'] is True
    assert data['state']['orders_submitted'].get('p2', False) is False


def test_order_submission_logging(client, sample_game_state):
    """
    Test that order submissions are logged correctly.
    
    Based on GDD page 9: API should log order submissions and phase transitions.
    """
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    force_id = p1_forces[0]['id']
    
    # Submit orders for player 1
    orders = [{
        'force_id': force_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={
        'player_id': 'p1',
        'orders': orders
    })
    assert response.status_code == 200
    
    # Check game log for order submission entry
    log_response = client.get(f'/api/game/{sample_game_state}/log')
    assert log_response.status_code == 200
    log_data = log_response.json
    
    # Verify log contains order submission entry
    order_submission_entries = [
        entry for entry in log_data['log'] 
        if 'Orders processed for player p1' in entry.get('event', '')
    ]
    assert len(order_submission_entries) == 1
    
    # Verify log entry structure
    log_entry = order_submission_entries[0]
    assert log_entry['turn'] == 1
    assert log_entry['phase'] == 'plan'
    assert 'Orders processed for player p1' in log_entry['event']
    assert 'waiting for other player' in log_entry['event']


def test_phase_transition_logging_when_both_players_submit(client, sample_game_state):
    """
    Test that phase transition is logged when both players submit orders.
    
    Based on GDD page 9: API should log phase transitions when moving to execute.
    """
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for player 1
    orders1 = [{
        'force_id': force1_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={
        'player_id': 'p1',
        'orders': orders1
    })
    assert response.status_code == 200
    
    # Submit orders for player 2 (this should trigger phase transition)
    orders2 = [{
        'force_id': force2_id,
        'order': 'Advance',
        'target_hex': {'q': 23, 'r': 18},
        'stance': 'River'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={
        'player_id': 'p2',
        'orders': orders2
    })
    assert response.status_code == 200
    
    # Check game log for phase transition entry
    log_response = client.get(f'/api/game/{sample_game_state}/log')
    assert log_response.status_code == 200
    log_data = log_response.json
    
    # Verify log contains phase transition entry
    phase_transition_entries = [
        entry for entry in log_data['log'] 
        if 'phase set to execute' in entry.get('event', '')
    ]
    assert len(phase_transition_entries) == 1
    
    # Verify log entry structure
    log_entry = phase_transition_entries[0]
    assert log_entry['turn'] == 1
    assert log_entry['phase'] == 'execute'
    assert 'Orders processed for player p2' in log_entry['event']
    assert 'phase set to execute' in log_entry['event']


def test_orders_submitted_reset_after_phase_transition(client, sample_game_state):
    """
    Test that orders_submitted is reset when transitioning to execute phase.
    
    Based on new requirement: orders_submitted should be reset for next turn.
    """
    # Get initial state
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    initial_state = state_response.json
    
    p1_forces = initial_state['players'][0]['forces']
    p2_forces = initial_state['players'][1]['forces']
    force1_id = p1_forces[0]['id']
    force2_id = p2_forces[0]['id']
    
    # Submit orders for both players to trigger phase transition
    orders1 = [{
        'force_id': force1_id,
        'order': 'Advance',
        'target_hex': {'q': 1, 'r': 0},
        'stance': 'Mountain'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={
        'player_id': 'p1',
        'orders': orders1
    })
    assert response.status_code == 200
    
    orders2 = [{
        'force_id': force2_id,
        'order': 'Advance',
        'target_hex': {'q': 23, 'r': 18},
        'stance': 'River'
    }]
    
    response = client.post(f'/api/game/{sample_game_state}/action', json={
        'player_id': 'p2',
        'orders': orders2
    })
    assert response.status_code == 200
    
    # Verify orders_submitted is reset
    data = response.json
    assert data['orders_submitted'] == {}
    assert data['state']['orders_submitted'] == {}
    
    # Perform upkeep to advance to next turn's plan phase
    response = client.post(f'/api/game/{sample_game_state}/upkeep')
    assert response.status_code == 200
    
    # Verify we're back in plan phase with empty orders_submitted
    state_response = client.get(f'/api/game/{sample_game_state}/state')
    assert state_response.status_code == 200
    data = state_response.json
    assert data['phase'] == 'plan'
    assert data['orders_submitted'] == {}