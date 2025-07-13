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

    def update_shih(self, amount: int) -> None:
        """Update Shih resource, ensuring it stays within 0-20 range."""
        self.shih = max(0, min(20, self.shih + amount))

    def update_chi(self, amount: int) -> None:
        """Update Chi resource, ensuring it doesn't go below 0."""
        self.chi = max(0, self.chi + amount)


@dataclass
class GameState:
    """High-level game state containing turn, phase, players, map, and ghosts."""
    turn: int  # Current turn number
    phase: str  # Current phase: 'plan', 'execute', or 'upkeep'
    players: List[Player]  # List of players in the game
    map: Dict[Tuple[int, int], Hex]  # Map of hex coordinates to Hex objects
    ghosts: List[Tuple[Tuple[int, int], str]]  # List of (hex_coords, owner) for ghost forces
