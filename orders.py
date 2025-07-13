from enum import Enum
from typing import Optional, Tuple, List, Dict, Any
from models import Force, Hex
from state import GameState, Player

class OrderType(Enum):
    ADVANCE = "Advance"
    MEDITATE = "Meditate"
    DECEIVE = "Deceive"

class Order:
    def __init__(self, order_type: OrderType, force: Force, target_hex: Optional[Tuple[int, int]] = None, stance: Optional[str] = None):
        """Initialize an order for a force."""
        self.order_type = order_type
        self.force = force
        self.target_hex = target_hex  # For Advance or Deceive; None for Meditate
        self.stance = stance  # For Advance; None for others

class OrderValidationError(Exception):
    """Exception raised when an order fails validation."""
    pass

def log_event(game_state: GameState, event: str, **kwargs) -> None:
    """
    Add an event to the game state log.
    
    Args:
        game_state: Current game state
        event: Description of the event
        **kwargs: Additional event data to include
    """
    log_entry = {
        'turn': game_state.turn,
        'phase': game_state.phase,
        'event': event,
        **kwargs
    }
    game_state.log.append(log_entry)

def validate_order(order: Order, game_state: GameState) -> bool:
    """Validate if an order is legal based on game state and GDD rules."""
    try:
        # Find the player that owns this force
        player = None
        for p in game_state.players:
            if order.force in p.forces:
                player = p
                break
        
        if not player:
            raise OrderValidationError(f"Force {order.force.id} doesn't belong to any player")
        
        if order.order_type == OrderType.ADVANCE:
            # Validate Shih requirement
            if player.shih < 2:
                raise OrderValidationError(f"Player {player.id} has insufficient Shih (has {player.shih}, needs 2)")
            
            # Validate target hex
            if not order.target_hex:
                raise OrderValidationError("Advance order requires a target hex")
            
            if not game_state.is_valid_position(order.target_hex):
                raise OrderValidationError(f"Target hex {order.target_hex} is outside map bounds")
            
            if not is_adjacent(order.force.position, order.target_hex):
                raise OrderValidationError(f"Target hex {order.target_hex} is not adjacent to force position {order.force.position}")
            
            # Validate stance
            if not order.stance:
                raise OrderValidationError("Advance order requires a stance")
            
            if order.stance not in ["Mountain", "River", "Thunder"]:
                raise OrderValidationError(f"Invalid stance: {order.stance}")
            
            # Check terrain restrictions
            if order.target_hex in game_state.map_data:
                terrain = game_state.map_data[order.target_hex].terrain
                if terrain == "Difficult" and order.stance == "Thunder":
                    raise OrderValidationError("Thunder stance not allowed on Difficult terrain")
        
        elif order.order_type == OrderType.MEDITATE:
            # Meditate takes no target or stance
            if order.target_hex or order.stance:
                raise OrderValidationError("Meditate order should not have target hex or stance")
        
        elif order.order_type == OrderType.DECEIVE:
            # Validate Shih requirement
            if player.shih < 3:
                raise OrderValidationError(f"Player {player.id} has insufficient Shih (has {player.shih}, needs 3)")
            
            # Validate target hex
            if not order.target_hex:
                raise OrderValidationError("Deceive order requires a target hex")
            
            if not game_state.is_valid_position(order.target_hex):
                raise OrderValidationError(f"Target hex {order.target_hex} is outside map bounds")
            
            if not is_adjacent(order.force.position, order.target_hex):
                raise OrderValidationError(f"Target hex {order.target_hex} is not adjacent to force position {order.force.position}")
            
            # Deceive takes no stance
            if order.stance:
                raise OrderValidationError("Deceive order should not have a stance")
        
        return True
        
    except OrderValidationError as e:
        # Re-raise the exception to preserve the error message
        raise e

def is_adjacent(current: Tuple[int, int], target: Tuple[int, int]) -> bool:
    """Check if target hex is adjacent to current hex in axial coordinates."""
    q1, r1 = current
    q2, r2 = target
    # Hex grid adjacency: difference in q, r, and q+r must be -1, 0, or 1
    return (q2 - q1, r2 - r1, (q1 + r1) - (q2 + r2)) in [
        (1, 0, -1), (1, -1, 0), (0, -1, 1),
        (-1, 0, 1), (-1, 1, 0), (0, 1, -1)
    ]

def resolve_orders(orders: List[Order], game_state: GameState) -> Dict[str, List[Any]]:
    """Resolve all orders for a turn, returning revealed orders and confrontations."""
    results = {"revealed_orders": [], "confrontations": [], "errors": []}
    ghosts: List[Tuple[Tuple[int, int], str]] = []  # Track ghost positions: (position, owner_id)
    
    # Track forces that have already moved to prevent conflicts
    moved_forces: set = set()
    
    # Initialize last_orders for this turn if not exists
    if not hasattr(game_state, 'last_orders'):
        game_state.last_orders = {}
    
    # Log order resolution start
    log_event(game_state, f"Order resolution phase started with {len(orders)} orders")
    
    # Process orders one at a time to ensure proper Shih validation
    for order in orders:
        try:
            # Find the player that owns this force
            player = next(p for p in game_state.players if order.force in p.forces)
            
            # Log order submission
            target_info = f" to {order.target_hex}" if order.target_hex else ""
            stance_info = f" with {order.stance} stance" if order.stance else ""
            log_event(game_state, f"Player {player.id} submitted {order.order_type.value} for force {order.force.id}{target_info}{stance_info}")
            
            # Validate the order
            if validate_order(order, game_state):
                # Log successful validation
                log_event(game_state, f"Order validated successfully for force {order.force.id}")
                
                # Process the order based on its type
                if order.order_type == OrderType.MEDITATE:
                    # Store Meditate order for next turn's upkeep (GDD: +2 Shih next turn)
                    if player.id not in game_state.last_orders:
                        game_state.last_orders[player.id] = []
                    
                    game_state.last_orders[player.id].append({
                        'order_type': 'Meditate',
                        'force_id': order.force.id,
                        'shih_bonus': 2
                    })
                    
                    # Add order to tendency (GDD page 6-7: Strategic Tendency)
                    order.force.add_order_to_tendency(order.order_type.name)
                    
                    # Log meditation effect
                    log_event(game_state, f"Force {order.force.id} meditated, queued +2 Shih for next turn's upkeep")
                    
                    # Reveal adjacent enemy orders
                    revealed_count = 0
                    for p in game_state.players:
                        if p != player:
                            for f in p.forces:
                                if is_adjacent(order.force.position, f.position):
                                    # Find the order for this force, if any
                                    for o in orders:
                                        if o.force == f:
                                            results["revealed_orders"].append((f.id, o.order_type.value))
                                            revealed_count += 1
                                            log_event(game_state, f"Meditation revealed {o.order_type.value} order for force {f.id}")
                                            break
                    
                    if revealed_count > 0:
                        log_event(game_state, f"Meditation revealed {revealed_count} adjacent enemy orders")
                
                elif order.order_type == OrderType.DECEIVE:
                    # Deduct Shih
                    player.update_shih(-3)
                    
                    # Add order to tendency (GDD page 6-7: Strategic Tendency)
                    order.force.add_order_to_tendency(order.order_type.name)
                    
                    # Create ghost in target hex (guaranteed to be non-None by validation)
                    target_hex = order.target_hex
                    assert target_hex is not None  # Type assertion for mypy
                    ghosts.append((target_hex, player.id))
                    
                    # Log deception and ghost creation
                    log_event(game_state, f"Player {player.id} spent 3 Shih on deception")
                    log_event(game_state, f"Force {order.force.id} created ghost at {target_hex}")
                
                elif order.order_type == OrderType.ADVANCE:
                    # Deduct Shih
                    player.update_shih(-2)
                    
                    # Guaranteed to be non-None by validation
                    target_hex = order.target_hex
                    stance = order.stance
                    assert target_hex is not None  # Type assertion for mypy
                    assert stance is not None  # Type assertion for mypy
                    
                    # Log Shih expenditure
                    log_event(game_state, f"Player {player.id} spent 2 Shih on advance")
                    
                    # Check if target hex is occupied by an enemy force or ghost
                    target_occupied = False
                    occupying_force = None
                    
                    # Check for enemy forces
                    for p in game_state.players:
                        if p != player:
                            for f in p.forces:
                                if f.position == target_hex:
                                    target_occupied = True
                                    occupying_force = f
                                    break
                            if target_occupied:
                                break
                    
                    # Check for ghosts
                    if not target_occupied:
                        for ghost_pos, ghost_owner in ghosts:
                            if ghost_pos == target_hex and ghost_owner != player.id:
                                target_occupied = True
                                log_event(game_state, f"Advance into ghost at {target_hex} by enemy player {ghost_owner}")
                                break
                    
                    # Update force stance regardless of confrontation 
                    # This ensures stances come from forces themselves during confrontation resolution (GDD page 5)
                    order.force.stance = stance
                    
                    if target_occupied:
                        # Queue confrontation
                        confrontation_data = {
                            "attacking_force": order.force.id,
                            "target_hex": target_hex,
                            "occupying_force": occupying_force.id if occupying_force else None,
                            "ghost_owner": next((g[1] for g in ghosts if g[0] == target_hex), None)
                        }
                        results["confrontations"].append(confrontation_data)
                        
                        # Log confrontation
                        if occupying_force:
                            log_event(game_state, f"Confrontation initiated: {order.force.id} ({stance}) vs {occupying_force.id} at {target_hex}")
                        else:
                            log_event(game_state, f"Ghost confrontation: {order.force.id} ({stance}) vs ghost at {target_hex}")
                    else:
                        # Move to target hex if not occupied
                        old_position = order.force.position
                        order.force.position = target_hex
                        moved_forces.add(order.force.id)
                        
                        # Add order to tendency (GDD page 6-7: Strategic Tendency)
                        order.force.add_order_to_tendency(order.order_type.name)
                        
                        # Log successful movement
                        log_event(game_state, f"Force {order.force.id} moved from {old_position} to {target_hex} with {stance} stance")
                        
                        # Check if movement was into Contentious Ground for Shih bonus
                        if target_hex in game_state.map_data:
                            terrain = game_state.map_data[target_hex].terrain
                            if terrain == "Contentious":
                                log_event(game_state, f"Force {order.force.id} entered Contentious Ground at {target_hex}")
                        
        except OrderValidationError as e:
            error_msg = f"Invalid order for force {order.force.id}: {order.order_type.value} - {str(e)}"
            results["errors"].append(error_msg)
            log_event(game_state, error_msg, error_type="validation_error")
        except Exception as e:
            error_msg = f"Unexpected error processing order for force {order.force.id}: {str(e)}"
            results["errors"].append(error_msg)
            log_event(game_state, error_msg, error_type="processing_error")
    
    # Log resolution completion
    log_event(game_state, f"Order resolution completed: {len(results['confrontations'])} confrontations, {len(ghosts)} ghosts created")
    
    return results

def get_order_summary(order: Order) -> Dict[str, Any]:
    """Get a summary of an order for API responses."""
    summary = {
        "force_id": order.force.id,
        "order_type": order.order_type.value,
        "current_position": order.force.position,
        "current_stance": order.force.stance
    }
    
    if order.target_hex:
        summary["target_hex"] = order.target_hex
    
    if order.stance:
        summary["stance"] = order.stance
    
    return summary

def validate_orders_batch(orders: List[Order], game_state: GameState) -> Dict[str, List[Any]]:
    """Validate a batch of orders and return detailed error messages."""
    errors = []
    valid_orders = []
    
    # Log batch validation start
    log_event(game_state, f"Batch validation started for {len(orders)} orders")
    
    for order in orders:
        try:
            if validate_order(order, game_state):
                valid_orders.append(order)
            else:
                errors.append(f"Order validation failed for force {order.force.id}")
        except Exception as e:
            errors.append(f"Error validating order for force {order.force.id}: {str(e)}")
    
    # Log batch validation results
    log_event(game_state, f"Batch validation completed: {len(valid_orders)} valid, {len(errors)} errors")
    
    return {
        "valid_orders": [get_order_summary(order) for order in valid_orders],
        "errors": errors
    }