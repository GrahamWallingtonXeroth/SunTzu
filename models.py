from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional, Dict, Set


class ForceRole(Enum):
    """Secret role assigned to each force during deployment."""
    SOVEREIGN = "Sovereign"   # Power 1. Lose it, lose the game.
    VANGUARD = "Vanguard"     # Power 4. Your killers.
    SCOUT = "Scout"           # Power 2. Reveals enemy roles via Scout order.
    SHIELD = "Shield"         # Power 3. Adjacent friendly forces get +2 power.


# Base combat power for each role
ROLE_POWER = {
    ForceRole.SOVEREIGN: 1,
    ForceRole.VANGUARD: 4,
    ForceRole.SCOUT: 2,
    ForceRole.SHIELD: 3,
}

# How many of each role a player must deploy
ROLE_COUNTS = {
    ForceRole.SOVEREIGN: 1,
    ForceRole.VANGUARD: 2,
    ForceRole.SCOUT: 1,
    ForceRole.SHIELD: 1,
}


@dataclass
class Hex:
    """A map hex with axial coordinates and terrain type."""
    q: int
    r: int
    terrain: str  # 'Open', 'Difficult', or 'Contentious'


@dataclass
class Force:
    """
    A player's force on the board.

    The role is hidden from the opponent until revealed through combat
    or scouting. Every force looks identical to the enemy — a blank token
    on a hex. The entire game turns on what you know and what you don't.
    """
    id: str
    position: Tuple[int, int]
    role: Optional[ForceRole] = None   # Assigned during deployment
    revealed: bool = False             # True once role is public knowledge
    alive: bool = True
    fortified: bool = False            # True for this turn only if Fortify order given

    @property
    def base_power(self) -> int:
        if self.role is None:
            return 0
        return ROLE_POWER[self.role]


@dataclass
class Player:
    """
    A player with resources, forces, and private intelligence.

    known_enemy_roles tracks what this player has learned about enemy forces
    through scouting (private) and combat (public). The opponent doesn't
    know what you've scouted.
    """
    id: str
    shih: int = 8
    max_shih: int = 15
    forces: List[Force] = field(default_factory=list)
    deployed: bool = False
    known_enemy_roles: Dict[str, str] = field(default_factory=dict)
    domination_turns: int = 0  # Consecutive turns controlling all Contentious hexes

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
