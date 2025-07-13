import pytest
from flask import Flask
from app import app  # Import the Flask app

@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_new_game(client):
    """Test POST /api/game/new creates a game with a valid game_id."""
    response = client.post('/api/game/new', json={'seed': 42})
    assert response.status_code == 200
    assert response.json == {'game_id': '1'}

def test_get_game_state(client):
    """Test GET /api/game/<game_id>/state returns valid game state."""
    # First, create a game
    client.post('/api/game/new', json={'seed': 42})
    
    # Then, get the game state
    response = client.get('/api/game/1/state')
    assert response.status_code == 200
    data = response.json
    
    # Verify key structure
    assert data['game_id'] == '1'
    assert data['turn'] == 1
    assert data['phase'] == 'plan'
    assert len(data['players']) == 2
    assert len(data['map']) == 25 * 20  # 500 hexes
    
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
    assert sorted([(f['position']['q'], f['position']['r']) for f in p2['forces']]) == [(23, 19), (24, 18), (24, 19)]