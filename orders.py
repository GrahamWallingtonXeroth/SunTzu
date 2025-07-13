from enum import Enum
from typing import Optional, Tuple
from models import Force, Hex
from state import GameState

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

def validate_order(order: Order, game_state: GameState) -> bool:
    """Validate if an order is legal based on game state and GDD rules."""
    # Find the player that owns this force
    player = None
    for p in game_state.players:
        if order.force in p.forces:
            player = p
            break
    
    if not player:
        return False  # Force doesn't belong to any player
    
    if order.order_type == OrderType.ADVANCE:
        if player.shih < 2:
            return False  # Not enough Shih
        if not order.target_hex or not is_adjacent(order.force.position, order.target_hex):
            return False  # Invalid or non-adjacent target hex
        if order.stance not in ["Mountain", "River", "Thunder"]:
            return False  # Invalid stance
        if order.target_hex in game_state.map_data and game_state.map_data[order.target_hex].terrain == "Difficult" and order.stance == "Thunder":
            return False  # Thunder stance not allowed on Difficult terrain
    elif order.order_type == OrderType.MEDITATE:
        if order.target_hex or order.stance:
            return False  # Meditate takes no target or stance
    elif order.order_type == OrderType.DECEIVE:
        if player.shih < 3:
            return False  # Not enough Shih
        if not order.target_hex or not is_adjacent(order.force.position, order.target_hex):
            return False  # Invalid or non-adjacent target hex
        if order.stance:
            return False  # Deceive takes no stance
    return True

def is_adjacent(current: Tuple[int, int], target: Tuple[int, int]) -> bool:
    """Check if target hex is adjacent to current hex in axial coordinates."""
    q1, r1 = current
    q2, r2 = target
    # Hex grid adjacency: difference in q, r, and q+r must be -1, 0, or 1
    return (q2 - q1, r2 - r1, (q1 + r1) - (q2 + r2)) in [
        (1, 0, -1), (1, -1, 0), (0, -1, 1),
        (-1, 0, 1), (-1, 1, 0), (0, 1, -1)
    ]