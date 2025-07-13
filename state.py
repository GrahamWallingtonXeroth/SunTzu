"""
Game state management for "Sun Tzu: The Unfought Battle"
Implements game state, player management, and force tracking based on GDD v0.7.

Resources: Chi (morale, starts 100), Shih (momentum, starts 10, max 20)
Forces: 3 per player with positions, stances, and order tendencies
Map: 25x20 hexes with axial coordinate system
"""

from __future__ import annotations
import uuid
import json
import os
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


def create_player(player_id: str, starting_positions: List[Tuple[int, int]], 
                 starting_chi: int = 100, starting_shih: int = 10, 
                 force_count: int = 3, max_shih: int = 20) -> Player:
    """
    Create a new player with forces at the specified starting positions.
    
    Args:
        player_id: Player identifier ('p1' or 'p2')
        starting_positions: List of starting positions for forces
        starting_chi: Starting Chi value (default: 100)
        starting_shih: Starting Shih value (default: 10)
        force_count: Number of forces to create (default: 3)
        max_shih: Maximum Shih value (default: 20)
    
    Returns:
        New Player instance with forces
    """
    player = Player(id=player_id, chi=starting_chi, shih=starting_shih, max_shih=max_shih)
    
    # Create forces for the player
    for i, position in enumerate(starting_positions[:force_count], 1):
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
    # Load config values with defaults
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    starting_chi = 100
    starting_shih = 10
    max_shih = 20
    force_count = 3
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            starting_chi = config.get('starting_chi', starting_chi)
            starting_shih = config.get('starting_shih', starting_shih)
            max_shih = config.get('max_shih', max_shih)
            force_count = config.get('force_count', force_count)
    except (FileNotFoundError, json.JSONDecodeError):
        # Use defaults if config file is missing or invalid
        pass
    
    # Generate unique game ID
    game_id = str(uuid.uuid4())
    
    # Generate map data
    map_data = generate_map(seed)
    
    # Create players with starting positions
    # P1 starts at (0,0) - top-left corner
    p1_positions = [(0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2)]  # Support up to 6 forces
    player1 = create_player('p1', p1_positions, starting_chi, starting_shih, force_count, max_shih)
    
    # P2 starts at (24,19) - bottom-right corner  
    p2_positions = [(24, 19), (23, 19), (24, 18), (23, 18), (22, 19), (24, 17)]  # Support up to 6 forces
    player2 = create_player('p2', p2_positions, starting_chi, starting_shih, force_count, max_shih)
    
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
