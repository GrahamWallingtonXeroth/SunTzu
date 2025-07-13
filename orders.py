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
        
    except OrderValidationError:
        return False

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
    
    # Track queued Shih for next turn
    queued_shih: Dict[str, int] = {player.id: 0 for player in game_state.players}
    
    # Track forces that have already moved to prevent conflicts
    moved_forces: set = set()
    
    # Validate all orders first
    valid_orders = []
    for order in orders:
        if validate_order(order, game_state):
            valid_orders.append(order)
        else:
            results["errors"].append(f"Invalid order for force {order.force.id}: {order.order_type.value}")

    # Process orders by type to handle conflicts properly
    # Process MEDITATE first (no movement, just information gathering)
    for order in valid_orders:
        if order.order_type == OrderType.MEDITATE:
            player = next(p for p in game_state.players if order.force in p.forces)
            
            # Queue +2 Shih for next turn
            queued_shih[player.id] += 2
            
            # Reveal adjacent enemy orders
            for p in game_state.players:
                if p != player:
                    for f in p.forces:
                        if is_adjacent(order.force.position, f.position):
                            # Find the order for this force, if any
                            for o in valid_orders:
                                if o.force == f:
                                    results["revealed_orders"].append((f.id, o.order_type.value))
                                    break
    
    # Process DECEIVE orders (create ghosts)
    for order in valid_orders:
        if order.order_type == OrderType.DECEIVE:
            player = next(p for p in game_state.players if order.force in p.forces)
            
            # Deduct Shih
            player.update_shih(-3)
            
            # Create ghost in target hex (guaranteed to be non-None by validation)
            target_hex = order.target_hex  # type: ignore
            ghosts.append((target_hex, player.id))
    
    # Process ADVANCE orders (movement and confrontations)
    for order in valid_orders:
        if order.order_type == OrderType.ADVANCE:
            player = next(p for p in game_state.players if order.force in p.forces)
            
            # Deduct Shih
            player.update_shih(-2)
            
            # Guaranteed to be non-None by validation
            target_hex = order.target_hex  # type: ignore
            stance = order.stance  # type: ignore
            
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
                        break
            
            if target_occupied:
                # Queue confrontation
                results["confrontations"].append({
                    "attacking_force": order.force.id,
                    "target_hex": target_hex,
                    "attacking_stance": stance,
                    "occupying_force": occupying_force.id if occupying_force else None,
                    "ghost_owner": next((g[1] for g in ghosts if g[0] == target_hex), None)
                })
            else:
                # Move to target hex if not occupied
                order.force.position = target_hex
                order.force.stance = stance
                moved_forces.add(order.force.id)
                
                # Add order to tendency
                order.force.add_order_to_tendency(order.order_type.value)
    
    # Apply queued Shih for next turn
    for player_id, shih_amount in queued_shih.items():
        if shih_amount > 0:
            player = game_state.get_player_by_id(player_id)
            if player:
                player.update_shih(shih_amount)
    
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
    
    for order in orders:
        try:
            if validate_order(order, game_state):
                valid_orders.append(order)
            else:
                errors.append(f"Order validation failed for force {order.force.id}")
        except Exception as e:
            errors.append(f"Error validating order for force {order.force.id}: {str(e)}")
    
    return {
        "valid_orders": [get_order_summary(order) for order in valid_orders],
        "errors": errors
    }