from flask import Flask, request, jsonify
from flask_cors import CORS
from state import initialize_game, GameState, Player, Force
from typing import Dict
import uuid

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
games: Dict[str, GameState] = {}  # In-memory storage for game states

@app.route('/api/game/new', methods=['POST'])
def new_game():
    """Create a new game with the provided seed."""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        seed = data.get('seed', 42)  # Default seed if none provided
        
        # Validate seed is an integer
        try:
            seed = int(seed)
        except (ValueError, TypeError):
            return jsonify({'error': 'Seed must be an integer'}), 400
        
        game_state = initialize_game(seed)
        
        # Use UUID for unique game ID generation
        game_id = str(uuid.uuid4())
        games[game_id] = game_state
        
        return jsonify({'game_id': game_id})
    
    except Exception as e:
        return jsonify({'error': f'Failed to create game: {str(e)}'}), 500

@app.route('/api/game/<game_id>/state', methods=['GET'])
def get_game_state(game_id: str):
    """Retrieve the current game state for the given game ID."""
    try:
        if game_id not in games:
            return jsonify({'error': 'Game not found'}), 404
        
        game_state = games[game_id]
        
        # Serialize game state to JSON
        state_json = {
            'game_id': game_id,
            'turn': game_state.turn,
            'phase': game_state.phase,
            'players': [
                {
                    'id': player.id,
                    'chi': player.chi,
                    'shih': player.shih,
                    'forces': [
                        {
                            'position': {'q': force.position[0], 'r': force.position[1]},
                            'stance': force.stance
                        } for force in player.forces
                    ]
                } for player in game_state.players
            ],
            'map': [
                {
                    'q': hex_coord[0],
                    'r': hex_coord[1],
                    'terrain': hex_obj.terrain
                } for hex_coord, hex_obj in game_state.map_data.items()
            ]
        }
        
        return jsonify(state_json)
    
    except Exception as e:
        return jsonify({'error': f'Failed to retrieve game state: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)