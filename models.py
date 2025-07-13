# Models for game elements based on GDD v0.7

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict


@dataclass
class Hex:
    """Represents a map hex with axial coordinates and terrain type."""
    q: int  # Axial coordinate q
    r: int  # Axial coordinate r
    terrain: str  # Terrain type: 'Open', 'Difficult', or 'Contentious'


@dataclass
class Force:
    """
    Represents a player's force with position, stance, and order history.
    Based on GDD: Forces have positions, stances (Mountain/River/Thunder),
    and maintain tendency (last 3 orders) for AI behavior prediction.
    """
    id: str  # Force identifier (e.g., 'f1', 'f2', 'f3')
    position: Tuple[int, int]  # Position as (q, r) axial coordinates
    stance: str = 'Mountain'  # Current stance: 'Mountain', 'River', 'Thunder'
    tendency: List[str] = field(default_factory=list)  # Last 3 orders for AI prediction
    encircled_turns: int = 0  # Number of turns this force has been encircled

    def add_order_to_tendency(self, order: str) -> None:
        """Add an order to the tendency list, maintaining only last 3."""
        self.tendency.append(order)
        if len(self.tendency) > 3:
            self.tendency.pop(0)  # Remove oldest order

@dataclass
class Player:
    """
    Represents a player with resources and forces.
    Based on GDD: Players have Chi (morale, starts 100) and Shih (momentum, 
    starts 10, max 20) as primary resources. Each player starts with 3 forces.
    """
    id: str  # Player identifier ('p1' or 'p2')
    chi: int = 100  # Chi resource (morale, starts at 100)
    shih: int = 10  # Shih resource (momentum, starts at 10, max 20)
    max_shih: int = 20  # Maximum Shih value
    forces: List[Force] = field(default_factory=list)  # List of player's forces

    def add_force(self, force: Force) -> None:
        """Add a force to this player's forces."""
        self.forces.append(force)

    def get_force_by_id(self, force_id: str) -> Optional[Force]:
        """Get a force by its ID."""
        for force in self.forces:
            if force.id == force_id:
                return force
        return None

    def update_shih(self, amount: int, max_shih: Optional[int] = None) -> None:
        """Update Shih resource, ensuring it stays within 0-max_shih range."""
        if max_shih is None:
            max_shih = self.max_shih
        self.shih = max(0, min(max_shih, self.shih + amount))

    def update_chi(self, amount: int) -> None:
        """Update Chi resource, ensuring it doesn't go below 0."""
        self.chi = max(0, self.chi + amount)



