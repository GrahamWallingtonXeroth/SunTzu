"""
Data model for The Unfought Battle v9.

No more fixed roles. Each player assigns hidden power values (1-5) to their
5 forces during deployment. Each value is used exactly once. Power 1 is the
Sovereign — lose it, lose the game. Powers 2-5 are soldiers with increasing
combat strength. The game is pure information + positioning.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Set


# The 5 power values each player must assign, one per force
POWER_VALUES = {1, 2, 3, 4, 5}

# Power 1 is always the Sovereign
SOVEREIGN_POWER = 1


@dataclass
class Hex:
    """A map hex with axial coordinates and terrain type."""
    q: int
    r: int
    terrain: str  # 'Open', 'Difficult', 'Contentious', or 'Scorched'


@dataclass
class Force:
    """
    A player's force on the board.

    The power value is hidden from the opponent until revealed through combat
    or scouting. Every force looks identical to the enemy — a blank token
    on a hex. The entire game turns on what you know and what you don't.
    """
    id: str
    position: Tuple[int, int]
    power: Optional[int] = None       # 1-5, assigned during deployment
    revealed: bool = False             # True once power is public knowledge
    alive: bool = True
    fortified: bool = False            # True for this turn only if Fortify order given
    ambushing: bool = False            # True for this turn only if Ambush order given
    charging: bool = False             # True for this turn only if Charge order given

    @property
    def is_sovereign(self) -> bool:
        return self.power == SOVEREIGN_POWER


@dataclass
class Player:
    """
    A player with resources, forces, and private intelligence.

    known_enemy_powers tracks what this player has learned about enemy forces
    through scouting (private) and combat (public). The opponent doesn't
    know what you've scouted.
    """
    id: str
    shih: int = 4
    max_shih: int = 8
    forces: List[Force] = field(default_factory=list)
    deployed: bool = False
    known_enemy_powers: Dict[str, int] = field(default_factory=dict)
    domination_turns: int = 0  # Consecutive turns controlling 2+ Contentious hexes

    def add_force(self, force: Force) -> None:
        self.forces.append(force)

    def get_force_by_id(self, force_id: str) -> Optional[Force]:
        for force in self.forces:
            if force.id == force_id:
                return force
        return None

    def get_alive_forces(self) -> List[Force]:
        return [f for f in self.forces if f.alive]

    def update_shih(self, amount: int) -> None:
        self.shih = max(0, min(self.max_shih, self.shih + amount))
