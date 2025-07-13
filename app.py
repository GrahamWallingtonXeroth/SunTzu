from flask import Flask, request, jsonify
from state import initialize_game, GameState, Player, Force
from models import Hex
from typing import Dict, Tuple

app = Flask(__name__)
games: Dict[str, GameState] = {}  # In-memory storage for game states

@app.route('/api/game/new', methods=['POST'])
def new_game():
    """Create a new game with the provided seed."""
    data = request.json
    seed = data.get('seed', 42)  # Default seed if none provided
    game_state = initialize_game(seed)
    
    game_id = str(len(games) + 1)
    games[game_id] = game_state
    
    return jsonify({'game_id': game_id})

@app.route('/api/game/<game_id>/state', methods=['GET'])
def get_game_state(game_id: str):
    """Retrieve the current game state for the given game ID."""
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

if __name__ == '__main__':
    app.run(debug=True)