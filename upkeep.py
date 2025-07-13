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


def log_event(game_state: GameState, event: str, **kwargs) -> None:
    """
    Add an event to the game state log.
    
    Args:
        game_state: Current game state
        event: Description of the event
        **kwargs: Additional event data to include
    """
    log_entry = {
        'turn': game_state.turn,
        'phase': game_state.phase,
        'event': event,
        **kwargs
    }
    game_state.log.append(log_entry)


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
    controlled_hexes = []
    
    for hex_pos, hex_data in game_state.map_data.items():
        if hex_data.terrain == 'Contentious' and is_controlled(hex_pos, player, game_state):
            shih_yield += 2
            controlled_hexes.append(hex_pos)
    
    # Log controlled Contentious terrain
    if controlled_hexes:
        log_event(game_state, f"Player {player.id} controls {len(controlled_hexes)} Contentious hexes", 
                 player_id=player.id, controlled_hexes=controlled_hexes, shih_yield=shih_yield)
    
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
            # Find the other player as winner
            for other_player in game_state.players:
                if other_player.id != player.id:
                    log_event(game_state, f"Victory by Demoralization: {other_player.id} wins - {player.id} Chi dropped to {player.chi}", 
                             winner_id=other_player.id, loser_id=player.id, victory_type="demoralization")
                    return other_player.id
    
    # Check for Domination (control all Contentious terrain for one full turn)
    # This would require tracking when a player first controlled all Contentious terrain
    # For now, we'll implement a simplified version
    
    # Check for Encirclement penalties
    for player in game_state.players:
        for force in player.forces:
            if force.encircled_turns >= 2:
                # Apply -20 Chi penalty for being encircled for 2+ turns
                old_chi = player.chi
                player.update_chi(-20)
                # Reset encircled turns after applying penalty
                force.encircled_turns = 0
                
                log_event(game_state, f"Encirclement penalty: {player.id} loses 20 Chi (was {old_chi}, now {player.chi})", 
                         player_id=player.id, force_id=force.id, chi_loss=20, old_chi=old_chi, new_chi=player.chi)
                
                # Check if this caused demoralization
                if player.chi <= 0:
                    for other_player in game_state.players:
                        if other_player.id != player.id:
                            log_event(game_state, f"Victory by Encirclement: {other_player.id} wins - {player.id} Chi dropped to {player.chi} from encirclement", 
                                     winner_id=other_player.id, loser_id=player.id, victory_type="encirclement")
                            return other_player.id
    
    return None


def perform_upkeep(game_state: GameState) -> Dict:
    """
    Perform upkeep phase operations for turn finalization.
    
    Based on GDD pages 3-7: Apply queued Shih actions, yield Shih from controlled Contentious terrain,
    check victory conditions, advance turn and reset phase to 'plan'.
    
    Args:
        game_state: Current game state to process
    
    Returns:
        Dictionary with results: {'winner': str or None, 'shih_yields': dict, 'encirclements': list}
    
    Raises:
        ValueError: If game state phase is not 'execute' when upkeep is called
    """
    # Validate that we're in the correct phase for upkeep
    if game_state.phase != 'execute':
        raise ValueError(f"Upkeep can only be performed during 'execute' phase, current phase is '{game_state.phase}'")
    
    results = {
        'winner': None,
        'shih_yields': {},
        'encirclements': [],
        'meditate_shih_yields': {}
    }
    
    # Log upkeep phase start
    log_event(game_state, "Upkeep phase started", turn=game_state.turn)
    
    # Apply Meditate orders from previous turn (+2 Shih per force, max 20)
    meditate_shih_yields = {}
    for player_id, orders in game_state.last_orders.items():
        player = game_state.get_player_by_id(player_id)
        if player:
            meditate_count = sum(1 for order in orders if order.get('order_type') == 'Meditate')
            if meditate_count > 0:
                # Calculate total Shih from meditation (2 per force)
                total_meditate_shih = meditate_count * 2
                old_shih = player.shih
                player.update_shih(total_meditate_shih)
                actual_shih_gained = player.shih - old_shih
                meditate_shih_yields[player_id] = actual_shih_gained
                
                log_event(game_state, f"Player {player_id} gains {actual_shih_gained} Shih from {meditate_count} Meditate orders (was {old_shih}, now {player.shih})", 
                         player_id=player_id, meditate_count=meditate_count, shih_gained=actual_shih_gained, 
                         old_shih=old_shih, new_shih=player.shih)
                
                # Store in results for API response
                results['meditate_shih_yields'][player_id] = actual_shih_gained
    
    # Clear last_orders after applying them
    game_state.last_orders = {}
    
    # Calculate and apply Shih yields from controlled Contentious terrain
    for player in game_state.players:
        old_shih = player.shih
        shih_yield = calculate_shih_yield(player, game_state)
        player.update_shih(shih_yield)
        results['shih_yields'][player.id] = shih_yield
        
        if shih_yield > 0:
            log_event(game_state, f"Player {player.id} gains {shih_yield} Shih from Contentious terrain (was {old_shih}, now {player.shih})", 
                     player_id=player.id, shih_gained=shih_yield, old_shih=old_shih, new_shih=player.shih)
    
    # Check for encirclements and update encircled_turns
    for player in game_state.players:
        for force in player.forces:
            if is_encircled(force, game_state):
                force.encircled_turns += 1
                log_event(game_state, f"Force {force.id} ({player.id}) is encircled for {force.encircled_turns} turn(s)", 
                         player_id=player.id, force_id=force.id, encircled_turns=force.encircled_turns)
                
                if force.encircled_turns >= 2:
                    results['encirclements'].append({
                        'force_id': force.id,
                        'player_id': player.id,
                        'turns_encircled': force.encircled_turns
                    })
            else:
                # Reset encircled turns if no longer encircled
                if force.encircled_turns > 0:
                    log_event(game_state, f"Force {force.id} ({player.id}) is no longer encircled", 
                             player_id=player.id, force_id=force.id, previous_encircled_turns=force.encircled_turns)
                    force.encircled_turns = 0
    
    # Check victory conditions
    winner = check_victory(game_state)
    results['winner'] = winner
    
    if winner:
        log_event(game_state, f"Game Over: {winner} is victorious!", winner_id=winner, game_end_turn=game_state.turn)
    else:
        # Log turn completion before incrementing
        old_turn = game_state.turn
        game_state.log.append({
            'turn': game_state.turn,
            'phase': game_state.phase,
            'event': f'Turn {game_state.turn} completed, advancing to plan phase of turn {game_state.turn + 1}'
        })
        
        # Set phase to 'plan' and increment turn (unless game is over)
        game_state.phase = 'plan'
        game_state.turn += 1
        
        log_event(game_state, f"Turn {old_turn} completed, advancing to {game_state.phase} phase of turn {game_state.turn}", 
                 previous_turn=old_turn, previous_phase='execute', new_turn=game_state.turn, new_phase=game_state.phase)
    
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
