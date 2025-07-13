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
    """Represents a player's force with position, owner, stance, and orders."""
    id: str  # Force identifier (e.g., 'f1')
    position: Tuple[int, int]  # Position as (q, r) coordinates
    owner: str  # Player owner ('p1' or 'p2')
    stance: Optional[str] = None  # Current stance: 'Mountain', 'River', 'Thunder', or None
    order: Optional[str] = None  # Current order: 'Advance', 'Meditate', 'Deceive', or None
    target_hex: Optional[Tuple[int, int]] = None  # Target hex coordinates (q, r) or None
    tendency: List[str] = field(default_factory=list)  # Last 3 orders (initially empty list)


@dataclass
class Player:
    """Represents a player with resources and forces."""
    id: str  # Player identifier ('p1' or 'p2')
    chi: int  # Chi resource (starts at 100)
    shih: int  # Shih resource (starts at 10)
    forces: List[Force]  # List of player's forces


@dataclass
class GameState:
    """High-level game state containing turn, phase, players, map, and ghosts."""
    turn: int  # Current turn number
    phase: str  # Current phase: 'plan', 'execute', or 'upkeep'
    players: List[Player]  # List of players in the game
    map: Dict[Tuple[int, int], Hex]  # Map of hex coordinates to Hex objects
    ghosts: List[Tuple[Tuple[int, int], str]]  # List of (hex_coords, owner) for ghost forces
