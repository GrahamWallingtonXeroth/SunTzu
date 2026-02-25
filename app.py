"""
API for The Unfought Battle.

Every endpoint respects the fog of war. You never see more than your
player is supposed to know. The state endpoint requires a player_id
because there is no god-view in this game.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from state import initialize_game, GameState, get_player_view, apply_deployment
from orders import resolve_orders, Order, OrderType, OrderValidationError
from upkeep import perform_upkeep
from typing import Dict, Any
import uuid

app = Flask(__name__)
CORS(app)
games: Dict[str, GameState] = {}


@app.route('/api/game/new', methods=['POST'])
def new_game():
    """Create a new game. Returns game_id. Both players must deploy before play begins."""
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'error': 'Invalid JSON'}), 400

        seed = data.get('seed', 42)
        try:
            seed = int(seed)
        except (ValueError, TypeError):
            return jsonify({'error': 'Seed must be an integer'}), 400

        game_state = initialize_game(seed)
        game_id = game_state.game_id
        games[game_id] = game_state

        return jsonify({'game_id': game_id, 'phase': 'deploy'})

    except Exception as e:
        return jsonify({'error': f'Failed to create game: {str(e)}'}), 500


@app.route('/api/game/<game_id>/deploy', methods=['POST'])
def deploy_forces(game_id: str):
    """
    Assign roles to your forces.

    POST body:
    {
        "player_id": "p1",
        "assignments": {
            "p1_f1": "Sovereign",
            "p1_f2": "Vanguard",
            "p1_f3": "Vanguard",
            "p1_f4": "Scout",
            "p1_f5": "Shield"
        }
    }

    Must assign exactly: 1 Sovereign, 2 Vanguard, 1 Scout, 1 Shield.
    Both players must deploy before the game begins.
    """
    try:
        if game_id not in games:
            return jsonify({'error': 'Game not found'}), 404

        game_state = games[game_id]
        if game_state.phase != 'deploy':
            return jsonify({'error': f"Cannot deploy during '{game_state.phase}' phase"}), 400

        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'error': 'Invalid JSON'}), 400

        player_id = data.get('player_id')
        if not player_id:
            return jsonify({'error': 'player_id is required'}), 400

        assignments = data.get('assignments')
        if not assignments or not isinstance(assignments, dict):
            return jsonify({'error': 'assignments dict is required'}), 400

        error = apply_deployment(game_state, player_id, assignments)
        if error:
            return jsonify({'error': error}), 400

        return jsonify({
            'game_id': game_id,
            'phase': game_state.phase,
            'deployed': True,
        })

    except Exception as e:
        return jsonify({'error': f'Deployment failed: {str(e)}'}), 500


@app.route('/api/game/<game_id>/state', methods=['GET'])
def get_game_state(game_id: str):
    """
    Get game state from YOUR perspective.

    Requires ?player_id=p1 or ?player_id=p2.
    You see your own forces in full. Enemy forces show position only,
    plus any roles you've discovered through scouting or combat.
    """
    try:
        if game_id not in games:
            return jsonify({'error': 'Game not found'}), 404

        game_state = games[game_id]
        player_id = request.args.get('player_id')

        if not player_id:
            return jsonify({'error': 'player_id query parameter is required'}), 400

        if not game_state.get_player_by_id(player_id):
            return jsonify({'error': f'Player {player_id} not found'}), 400

        view = get_player_view(game_state, player_id)
        return jsonify(view)

    except Exception as e:
        return jsonify({'error': f'Failed to get state: {str(e)}'}), 500


@app.route('/api/game/<game_id>/action', methods=['POST'])
def submit_action(game_id: str):
    """
    Submit orders for your forces.

    POST body:
    {
        "player_id": "p1",
        "orders": [
            {"force_id": "p1_f1", "order": "Move", "target_hex": {"q": 1, "r": 0}},
            {"force_id": "p1_f2", "order": "Scout", "scout_target_id": "p2_f3"},
            {"force_id": "p1_f3", "order": "Fortify"},
            {"force_id": "p1_f4", "order": "Feint", "target_hex": {"q": 3, "r": 3}},
            {"force_id": "p1_f5", "order": "Move", "target_hex": {"q": 0, "r": 2}}
        ]
    }

    When both players have submitted, orders resolve simultaneously.
    """
    try:
        if game_id not in games:
            return jsonify({'error': 'Game not found'}), 404

        game_state = games[game_id]
        if game_state.phase != 'plan':
            return jsonify({'error': f"Cannot submit orders during '{game_state.phase}' phase"}), 400

        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'error': 'Invalid JSON'}), 400

        player_id = data.get('player_id')
        if not player_id:
            return jsonify({'error': 'player_id is required'}), 400

        player = game_state.get_player_by_id(player_id)
        if not player:
            return jsonify({'error': f'Player {player_id} not found'}), 400

        if game_state.orders_submitted.get(player_id, False):
            return jsonify({'error': f'{player_id} already submitted orders this turn'}), 400

        orders_data = data.get('orders', [])
        if not isinstance(orders_data, list):
            return jsonify({'error': 'orders must be an array'}), 400

        # Parse orders
        orders = []
        for od in orders_data:
            if not isinstance(od, dict) or 'force_id' not in od or 'order' not in od:
                return jsonify({'error': 'Each order needs force_id and order fields'}), 400

            force = player.get_force_by_id(od['force_id'])
            if not force:
                return jsonify({'error': f"Force {od['force_id']} not found"}), 400

            try:
                order_type = OrderType(od['order'])
            except ValueError:
                return jsonify({'error': f"Invalid order type: {od['order']}"}), 400

            target_hex = None
            if 'target_hex' in od and od['target_hex']:
                th = od['target_hex']
                if not isinstance(th, dict) or 'q' not in th or 'r' not in th:
                    return jsonify({'error': 'target_hex must have q and r'}), 400
                target_hex = (th['q'], th['r'])

            scout_target_id = od.get('scout_target_id')

            orders.append(Order(order_type, force, target_hex, scout_target_id))

        # Store orders, waiting for both players
        if not hasattr(game_state, '_pending_orders'):
            game_state._pending_orders = {}
        game_state._pending_orders[player_id] = orders
        game_state.orders_submitted[player_id] = True

        game_state.log.append({
            'turn': game_state.turn, 'phase': 'plan',
            'event': f'{player_id} submitted {len(orders)} orders',
        })

        # Check if both players have submitted
        both_submitted = all(
            game_state.orders_submitted.get(p.id, False)
            for p in game_state.players
        )

        if not both_submitted:
            # Return acknowledgment, wait for other player
            return jsonify({
                'game_id': game_id,
                'status': 'waiting',
                'orders_accepted': len(orders),
                'phase': game_state.phase,
            })

        # Both submitted — resolve simultaneously
        game_state.phase = 'resolve'
        p1_orders = game_state._pending_orders.get('p1', [])
        p2_orders = game_state._pending_orders.get('p2', [])

        resolve_result = resolve_orders(p1_orders, p2_orders, game_state)

        # Perform upkeep
        sovereign_capture = resolve_result.get('sovereign_captured')
        upkeep_result = perform_upkeep(game_state, sovereign_capture)

        # Clean up
        game_state._pending_orders = {}
        game_state.orders_submitted = {}

        # Return player-specific view
        view = get_player_view(game_state, player_id)
        view['resolve_result'] = {
            'combats': resolve_result.get('combats', []),
            'movements': resolve_result.get('movements', []),
            'feints': resolve_result.get('feints', []),
            # Only include scouts for this player
            'scouts': [
                s for s in resolve_result.get('scouts', [])
                if s['player'] == player_id
            ],
            'errors': resolve_result.get('errors', []),
        }
        view['upkeep'] = {
            'shih_income': upkeep_result.get('shih_income', {}),
            'winner': upkeep_result.get('winner'),
            'victory_type': upkeep_result.get('victory_type'),
            'domination_progress': upkeep_result.get('domination_progress', {}),
        }

        return jsonify(view)

    except Exception as e:
        return jsonify({'error': f'Action failed: {str(e)}'}), 500


@app.route('/api/game/<game_id>/concede', methods=['POST'])
def concede_game(game_id: str):
    """Surrender. The unfought battle — but not in the way Sun Tzu meant."""
    try:
        if game_id not in games:
            return jsonify({'error': 'Game not found'}), 404

        game_state = games[game_id]
        if game_state.phase == 'ended':
            return jsonify({'error': 'Game already ended'}), 400

        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'error': 'Invalid JSON'}), 400

        player_id = data.get('player_id')
        if not player_id:
            return jsonify({'error': 'player_id is required'}), 400

        opponent = game_state.get_opponent(player_id)
        if not opponent:
            return jsonify({'error': f'Player {player_id} not found'}), 400

        game_state.winner = opponent.id
        game_state.victory_type = 'concession'
        game_state.phase = 'ended'

        game_state.log.append({
            'turn': game_state.turn, 'phase': 'ended',
            'event': f'{player_id} concedes. {opponent.id} wins.',
        })

        return jsonify({
            'game_id': game_id,
            'winner': opponent.id,
            'victory_type': 'concession',
        })

    except Exception as e:
        return jsonify({'error': f'Concession failed: {str(e)}'}), 500


@app.route('/api/game/<game_id>/log', methods=['GET'])
def get_game_log(game_id: str):
    """Full game log. For post-game analysis only — reveals everything."""
    try:
        if game_id not in games:
            return jsonify({'error': 'Game not found'}), 404

        game_state = games[game_id]
        return jsonify({
            'game_id': game_id,
            'turn': game_state.turn,
            'phase': game_state.phase,
            'log': game_state.log,
        })

    except Exception as e:
        return jsonify({'error': f'Failed to get log: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=True)
