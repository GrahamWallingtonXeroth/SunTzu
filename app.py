from flask import Flask, request, jsonify
from state import initialize_game

app = Flask(__name__)
games = {}  # Temporary in-memory storage for game states

@app.route('/api/game/new', methods=['POST'])
def new_game():
    """Create a new game with the provided seed."""
    data = request.json
    seed = data.get('seed', 42)  # Default seed if none provided
    game_state = initialize_game(seed)
    
    game_id = str(len(games) + 1)
    games[game_id] = game_state
    
    return jsonify({'game_id': game_id})

if __name__ == '__main__':
    app.run(debug=True)