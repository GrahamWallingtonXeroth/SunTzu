"""
Game state management for "Sun Tzu: The Unfought Battle"
Implements game state, player management, and force tracking based on GDD v0.7.

Resources: Chi (morale, starts 100), Shih (momentum, starts 10, max 20)
Forces: 3 per player with positions, stances, and order tendencies
Map: 25x20 hexes with axial coordinate system
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from map_gen import generate_map
from models import Force, Player, Hex

@dataclass
class GameState:
    """
    Complete game state containing all game information.
    
    Based on GDD: Game progresses through turns and phases (plan/execute/upkeep),
    with players managing forces on a 25x20 hex map.
    """
    game_id: str  # Unique game identifier
    turn: int = 1  # Current turn number (starts at 1)
    phase: str = 'plan'  # Current phase: 'plan', 'execute', 'upkeep'
    players: List[Player] = field(default_factory=list)  # List of players
    map_data: Dict[Tuple[int, int], Hex] = field(default_factory=dict)  # Map data
    
    def get_player_by_id(self, player_id: str) -> Optional[Player]:
        """Get a player by their ID."""
        for player in self.players:
            if player.id == player_id:
                return player
        return None
    
    def get_force_at_position(self, position: Tuple[int, int]) -> Optional[Force]:
        """Get the force at a specific position, if any."""
        for player in self.players:
            for force in player.forces:
                if force.position == position:
                    return force
        return None
    
    def advance_phase(self) -> None:
        """Advance to the next phase in the game cycle."""
        phase_cycle = ['plan', 'execute', 'upkeep']
        current_index = phase_cycle.index(self.phase)
        next_index = (current_index + 1) % len(phase_cycle)
        self.phase = phase_cycle[next_index]
        
        # If we've completed a full cycle, advance the turn
        if self.phase == 'plan':
            self.turn += 1
    
    def is_valid_position(self, position: Tuple[int, int]) -> bool:
        """Check if a position is within the valid map bounds (25x20)."""
        q, r = position
        return 0 <= q < 25 and 0 <= r < 20


def create_force(force_id: str, position: Tuple[int, int], stance: str = 'Mountain') -> Force:
    """
    Create a new force with the specified parameters.
    
    Args:
        force_id: Unique identifier for the force
        position: Starting position as (q, r) coordinates
        stance: Initial stance (default: 'Mountain')
    
    Returns:
        New Force instance
    """
    return Force(
        id=force_id,
        position=position,
        stance=stance,
        tendency=[]
    )


def create_player(player_id: str, starting_positions: List[Tuple[int, int]]) -> Player:
    """
    Create a new player with forces at the specified starting positions.
    
    Args:
        player_id: Player identifier ('p1' or 'p2')
        starting_positions: List of 3 starting positions for forces
    
    Returns:
        New Player instance with 3 forces
    """
    player = Player(id=player_id)
    
    # Create 3 forces for the player
    for i, position in enumerate(starting_positions, 1):
        force_id = f"{player_id}_f{i}"
        force = create_force(force_id, position)
        player.add_force(force)
    
    return player


def initialize_game(seed: int) -> GameState:
    """
    Initialize a new game state with two players and generated map.
    
    Based on GDD: Players start at opposite corners with 3 forces each.
    P1 starts at (0,0), P2 starts at (24,19) - opposite corners of 25x20 map.
    
    Args:
        seed: Random seed for map generation (required)
    
    Returns:
        New GameState instance ready for gameplay
    """
    # Generate unique game ID
    game_id = str(uuid.uuid4())
    
    # Generate map data
    map_data = generate_map(seed)
    
    # Create players with starting positions
    # P1 starts at (0,0) - top-left corner
    p1_positions = [(0, 0), (1, 0), (0, 1)]
    player1 = create_player('p1', p1_positions)
    
    # P2 starts at (24,19) - bottom-right corner  
    p2_positions = [(24, 19), (23, 19), (24, 18)]
    player2 = create_player('p2', p2_positions)
    
    # Create game state
    game_state = GameState(
        game_id=game_id,
        turn=1,
        phase='plan',
        players=[player1, player2],
        map_data=map_data
    )
    
    return game_state


def get_game_summary(game_state: GameState) -> Dict:
    """
    Get a summary of the current game state for API responses.
    
    Args:
        game_state: Current game state
    
    Returns:
        Dictionary with game summary information
    """
    return {
        'game_id': game_state.game_id,
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
                        'position': force.position,
                        'stance': force.stance,
                        'tendency': force.tendency
                    }
                    for force in player.forces
                ]
            }
            for player in game_state.players
        ],
        'map_size': (25, 20)
    }
