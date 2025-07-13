from flask import Flask, request, jsonify
from flask_cors import CORS
from state import initialize_game, GameState, Player, Force
from orders import resolve_orders, Order, OrderType, OrderValidationError
from resolution import resolve_confrontation
from upkeep import perform_upkeep
from typing import Dict, List, Any
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
                            'id': force.id,
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

@app.route('/api/game/<game_id>/action', methods=['POST'])
def submit_action(game_id: str):
    """Submit orders for the current player and process the action phase."""
    try:
        # Validate game_id exists
        if game_id not in games:
            return jsonify({'error': 'Game not found'}), 404
        
        game_state = games[game_id]
        
        # Validate request body
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        orders_data = data.get('orders', [])
        if not isinstance(orders_data, list):
            return jsonify({'error': 'Orders must be an array'}), 400
        
        # Parse and validate orders
        orders: List[Order] = []
        for order_data in orders_data:
            try:
                # Validate required fields
                if not all(key in order_data for key in ['force_id', 'order']):
                    return jsonify({'error': 'Each order must have force_id and order fields'}), 400
                
                force_id = order_data['force_id']
                order_type_str = order_data['order']
                target_hex_data = order_data.get('target_hex')
                stance = order_data.get('stance')
                
                # Find the force
                force = None
                for player in game_state.players:
                    for f in player.forces:
                        if f.id == force_id:
                            force = f
                            break
                    if force:
                        break
                
                if not force:
                    return jsonify({'error': f'Force with id {force_id} not found'}), 400
                
                # Parse order type
                try:
                    order_type = OrderType(order_type_str)
                except ValueError:
                    return jsonify({'error': f'Invalid order type: {order_type_str}'}), 400
                
                # Parse target hex if provided
                target_hex = None
                if target_hex_data:
                    if not isinstance(target_hex_data, dict) or 'q' not in target_hex_data or 'r' not in target_hex_data:
                        return jsonify({'error': 'target_hex must be an object with q and r coordinates'}), 400
                    target_hex = (target_hex_data['q'], target_hex_data['r'])
                
                # Create order object
                order = Order(order_type, force, target_hex, stance)
                orders.append(order)
                
            except Exception as e:
                return jsonify({'error': f'Invalid order data: {str(e)}'}), 400
        
        # Process orders using resolve_orders
        # This updates force stances and positions, and queues confrontations
        results = resolve_orders(orders, game_state)
        
        # Handle confrontations if any occurred
        # Stances are now taken from the forces themselves (updated by resolve_orders)
        confrontation_results = []
        for confrontation in results.get('confrontations', []):
            try:
                # Find the attacking force
                attacking_force = None
                for player in game_state.players:
                    for force in player.forces:
                        if force.id == confrontation['attacking_force']:
                            attacking_force = force
                            break
                    if attacking_force:
                        break
                
                if not attacking_force:
                    continue
                
                # Find the defending force if it exists
                defending_force = None
                if confrontation['occupying_force']:
                    for player in game_state.players:
                        for force in player.forces:
                            if force.id == confrontation['occupying_force']:
                                defending_force = force
                                break
                        if defending_force:
                            break
                
                # Resolve the confrontation
                # Stances come from the forces themselves after orders are resolved (GDD page 5)
                confrontation_result = resolve_confrontation(
                    attacking_force,
                    defending_force,
                    confrontation['target_hex'],
                    game_state
                )
                confrontation_results.append(confrontation_result)
                
            except Exception as e:
                results['errors'].append(f'Failed to resolve confrontation: {str(e)}')
        
        # Advance game phase to 'execute' if we're in 'plan' phase
        if game_state.phase == 'plan':
            game_state.advance_phase()
        
        # Prepare response
        response_data = {
            'game_id': game_id,
            'turn': game_state.turn,
            'phase': game_state.phase,
            'orders_processed': len(orders),
            'revealed_orders': results.get('revealed_orders', []),
            'confrontations': confrontation_results,
            'errors': results.get('errors', [])
        }
        
        # Include updated game state
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
                            'id': force.id,
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
        response_data['state'] = state_json
        
        return jsonify(response_data)
    
    except Exception as e:
        return jsonify({'error': f'Failed to process action: {str(e)}'}), 500

@app.route('/api/game/<game_id>/upkeep', methods=['POST'])
def perform_upkeep_phase(game_id: str):
    """Perform upkeep phase operations for turn finalization."""
    try:
        # Validate game_id exists
        if game_id not in games:
            return jsonify({'error': 'Game not found'}), 404
        
        game_state = games[game_id]
        
        # Validate phase is 'execute'
        if game_state.phase != 'execute':
            return jsonify({'error': 'Upkeep can only be performed during execute phase'}), 400
        
        # Perform upkeep operations
        upkeep_results = perform_upkeep(game_state)
        
        # Check if there's a winner
        winner = upkeep_results.get('winner')
        if winner:
            # Game is over, set phase to 'ended'
            game_state.phase = 'ended'
        else:
            # No winner, advance to 'plan' phase and increment turn
            # Note: perform_upkeep already calls advance_phase() which handles this
            pass
        
        # Prepare response
        response_data = {
            'game_id': game_id,
            'turn': game_state.turn,
            'phase': game_state.phase,
            'winner': winner,
            'shih_yields': upkeep_results.get('shih_yields', {}),
            'encirclements': upkeep_results.get('encirclements', [])
        }
        
        # Include updated game state
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
                            'id': force.id,
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
        response_data['state'] = state_json
        
        return jsonify(response_data)
    
    except Exception as e:
        return jsonify({'error': f'Failed to perform upkeep: {str(e)}'}), 500

@app.route('/api/game/<game_id>/log', methods=['GET'])
def get_game_log(game_id: str):
    """Retrieve the full game log for analysis."""
    try:
        # Validate game_id exists
        if game_id not in games:
            return jsonify({'error': 'Game not found'}), 404
        
        game_state = games[game_id]
        
        # Prepare response with game log
        log_response = {
            'game_id': game_id,
            'turn': game_state.turn,
            'phase': game_state.phase,
            'log': game_state.log
        }
        
        return jsonify(log_response)
    
    except Exception as e:
        return jsonify({'error': f'Failed to retrieve game log: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)