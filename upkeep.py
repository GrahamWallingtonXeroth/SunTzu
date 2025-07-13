"""
Upkeep phase management for "Sun Tzu: The Unfought Battle"
Handles turn finalization, resource updates, and victory condition checking.

Based on GDD v0.7 pages 3-7:
- Apply queued Shih actions
- Yield Shih from controlled Contentious terrain (+2 per hex)
- Check victory conditions (Demoralization, Domination, Encirclement)
- Advance turn and reset phase to 'plan'
"""

from typing import Dict, List, Optional, Tuple, Set
from models import Player, Force, Hex
from state import GameState


def get_adjacent_positions(position: Tuple[int, int]) -> List[Tuple[int, int]]:
    """
    Get all adjacent hex positions using axial coordinate system.
    
    Args:
        position: Current position as (q, r) coordinates
    
    Returns:
        List of adjacent positions
    """
    q, r = position
    # Axial coordinate system: 6 directions
    directions = [
        (1, 0), (1, -1), (0, -1),  # Right, Right-Up, Up
        (-1, 0), (-1, 1), (0, 1)   # Left, Left-Down, Down
    ]
    
    adjacent = []
    for dq, dr in directions:
        new_pos = (q + dq, r + dr)
        # Check if position is within map bounds (25x20)
        if 0 <= new_pos[0] < 25 and 0 <= new_pos[1] < 20:
            adjacent.append(new_pos)
    
    return adjacent


def is_controlled(hex_pos: Tuple[int, int], player: Player, game_state: GameState) -> bool:
    """
    Check if a hex is controlled by the specified player.
    
    Control means: occupied by friendly force with no adjacent enemy forces.
    
    Args:
        hex_pos: Hex position to check
        player: Player to check control for
        game_state: Current game state
    
    Returns:
        True if the hex is controlled by the player
    """
    # Check if player has a force at this position
    player_force_here = False
    for force in player.forces:
        if force.position == hex_pos:
            player_force_here = True
            break
    
    if not player_force_here:
        return False
    
    # Check if any enemy forces are adjacent
    adjacent_positions = get_adjacent_positions(hex_pos)
    for adj_pos in adjacent_positions:
        force_at_adj = game_state.get_force_at_position(adj_pos)
        if force_at_adj:
            # Check if this force belongs to an enemy player
            for other_player in game_state.players:
                if other_player.id != player.id:
                    for enemy_force in other_player.forces:
                        if enemy_force.id == force_at_adj.id:
                            return False  # Enemy force adjacent, not controlled
    
    return True


def calculate_shih_yield(player: Player, game_state: GameState) -> int:
    """
    Calculate Shih yield from controlled Contentious terrain.
    
    Args:
        player: Player to calculate yield for
        game_state: Current game state
    
    Returns:
        Amount of Shih to yield (+2 per controlled Contentious hex)
    """
    shih_yield = 0
    
    for hex_pos, hex_data in game_state.map_data.items():
        if hex_data.terrain == 'Contentious' and is_controlled(hex_pos, player, game_state):
            shih_yield += 2
    
    return shih_yield


def is_encircled(force: Force, game_state: GameState) -> bool:
    """
    Check if a force is encircled by enemy forces or ghosts.
    
    Encirclement: all adjacent hexes blocked by enemies/ghosts.
    
    Args:
        force: Force to check for encirclement
        game_state: Current game state
    
    Returns:
        True if the force is encircled
    """
    adjacent_positions = get_adjacent_positions(force.position)
    
    for adj_pos in adjacent_positions:
        # Check if position is accessible (not blocked by enemy or ghost)
        force_at_pos = game_state.get_force_at_position(adj_pos)
        
        if force_at_pos:
            # Check if this is an enemy force
            for player in game_state.players:
                for player_force in player.forces:
                    if player_force.id == force_at_pos.id:
                        # If it's not the same player as our force, it's an enemy
                        if player_force.id != force.id:
                            # Check if it belongs to a different player
                            force_player = None
                            for p in game_state.players:
                                for f in p.forces:
                                    if f.id == force.id:
                                        force_player = p
                                        break
                                if force_player:
                                    break
                            
                            if force_player and player.id != force_player.id:
                                continue  # This adjacent hex is blocked by enemy
                            else:
                                return False  # Adjacent hex is accessible
                        else:
                            return False  # Adjacent hex is accessible (same force)
        else:
            # No force at this position, so it's accessible
            return False
    
    # All adjacent positions are blocked
    return True


def check_victory(game_state: GameState) -> Optional[str]:
    """
    Check for victory conditions and return winner ID if any.
    
    Victory conditions:
    - Demoralization: Chi <= 0
    - Domination: Control all Contentious terrain for one full turn
    - Encirclement: Enemy force surrounded for 2 turns causing -20 Chi
    
    Args:
        game_state: Current game state
    
    Returns:
        Winner player ID if victory achieved, None otherwise
    """
    # Check for Demoralization (Chi <= 0)
    for player in game_state.players:
        if player.chi <= 0:
            # Return the other player as winner
            for other_player in game_state.players:
                if other_player.id != player.id:
                    return other_player.id
    
    # Check for Domination (control all Contentious terrain for one full turn)
    # This would require tracking when a player first controlled all Contentious terrain
    # For now, we'll implement a simplified version
    
    # Check for Encirclement penalties
    for player in game_state.players:
        for force in player.forces:
            if force.encircled_turns >= 2:
                # Apply -20 Chi penalty for being encircled for 2+ turns
                player.update_chi(-20)
                # Reset encircled turns after applying penalty
                force.encircled_turns = 0
                
                # Check if this caused demoralization
                if player.chi <= 0:
                    for other_player in game_state.players:
                        if other_player.id != player.id:
                            return other_player.id
    
    return None


def perform_upkeep(game_state: GameState) -> Dict:
    """
    Perform upkeep phase operations for turn finalization.
    
    Based on GDD: Apply queued Shih, yield Shih from controlled Contentious terrain,
    check victory conditions, advance turn and reset phase to 'plan'.
    
    Args:
        game_state: Current game state to process
    
    Returns:
        Dictionary with results: {'winner': str or None, 'shih_yields': dict, 'encirclements': list}
    """
    results = {
        'winner': None,
        'shih_yields': {},
        'encirclements': []
    }
    
    # Apply queued Shih actions (this would be implemented based on queued actions)
    # For now, we'll assume no queued actions to apply
    
    # Calculate and apply Shih yields from controlled Contentious terrain
    for player in game_state.players:
        shih_yield = calculate_shih_yield(player, game_state)
        player.update_shih(shih_yield)
        results['shih_yields'][player.id] = shih_yield
    
    # Check for encirclements and update encircled_turns
    for player in game_state.players:
        for force in player.forces:
            if is_encircled(force, game_state):
                force.encircled_turns += 1
                if force.encircled_turns >= 2:
                    results['encirclements'].append({
                        'force_id': force.id,
                        'player_id': player.id,
                        'turns_encircled': force.encircled_turns
                    })
            else:
                # Reset encircled turns if no longer encircled
                force.encircled_turns = 0
    
    # Check victory conditions
    winner = check_victory(game_state)
    results['winner'] = winner
    
    # Advance turn and reset phase to 'plan' (unless game is over)
    if not winner:
        game_state.advance_phase()
    
    return results


def get_upkeep_summary(game_state: GameState) -> Dict:
    """
    Get a summary of the current state for upkeep calculations.
    
    Args:
        game_state: Current game state
    
    Returns:
        Dictionary with upkeep-relevant information
    """
    summary = {
        'turn': game_state.turn,
        'phase': game_state.phase,
        'players': {}
    }
    
    for player in game_state.players:
        controlled_contentious = 0
        encircled_forces = []
        
        # Count controlled Contentious terrain
        for hex_pos, hex_data in game_state.map_data.items():
            if hex_data.terrain == 'Contentious' and is_controlled(hex_pos, player, game_state):
                controlled_contentious += 1
        
        # Check for encircled forces
        for force in player.forces:
            if is_encircled(force, game_state):
                encircled_forces.append({
                    'force_id': force.id,
                    'turns_encircled': force.encircled_turns
                })
        
        summary['players'][player.id] = {
            'chi': player.chi,
            'shih': player.shih,
            'controlled_contentious': controlled_contentious,
            'encircled_forces': encircled_forces
        }
    
    return summary
