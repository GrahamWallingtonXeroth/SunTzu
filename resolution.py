from typing import Dict, Tuple, Optional, Any
import json
from models import Force, Hex
from state import GameState, Player
from orders import is_adjacent

class ConfrontationError(Exception):
    """Exception raised when confrontation resolution fails."""
    pass

def resolve_confrontation(attacker: Force, defender: Optional[Force], target_hex: Tuple[int, int], game_state: GameState) -> Dict[str, Any]:
    """Resolve a confrontation between an attacking force and a defender or ghost at target_hex.
    
    Stances are taken from the forces themselves after orders are resolved (GDD page 5).
    Tendency modifiers are applied based on last 3 orders (GDD page 6-7).
    """
    result = {"attacker_id": attacker.id, "target_hex": target_hex, "chi_loss": [], "retreats": []}

    # If no defender (ghost confrontation), attacker moves to target hex
    if not defender:
        attacker.position = target_hex
        result["retreats"].append((attacker.id, target_hex))
        
        # Log ghost confrontation
        game_state.log.append({
            'turn': game_state.turn,
            'phase': game_state.phase,
            'event': f'Ghost confrontation: {attacker.id} moves to {target_hex}'
        })
        
        return result

    # Load configuration from config.json
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        tendency_modifier = config.get('tendency_modifier', 1)
        base_chi_loss = config.get('base_chi_loss', 8)  # GDD page 12: Confrontation impact
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        tendency_modifier = 1  # Default fallback
        base_chi_loss = 8  # Default fallback

    # Find players
    attacker_player = next(p for p in game_state.players if attacker in p.forces)
    defender_player = next(p for p in game_state.players if defender in p.forces)

    # Calculate stance modifiers based on tendency (GDD page 6-7)
    attacker_stance_mod = calculate_stance_modifier(attacker.tendency, tendency_modifier)
    defender_stance_mod = calculate_stance_modifier(defender.tendency, tendency_modifier)

    # Stance resolution with tendency modifiers
    beats = {
        "Mountain": "Thunder",
        "River": "Mountain", 
        "Thunder": "River"
    }
    terrain_multiplier = 2 if game_state.map_data[target_hex].terrain == "Contentious" else 1

    # Determine winner considering stance modifiers
    winner = determine_winner_with_modifiers(attacker.stance, defender.stance, attacker_stance_mod, defender_stance_mod, beats)

    if winner == "stalemate":
        # Stalemate: both lose 4 Chi, retreat if possible
        attacker_chi_loss = 4 * terrain_multiplier
        defender_chi_loss = 4 * terrain_multiplier
        attacker_player.chi = max(0, attacker_player.chi - attacker_chi_loss)
        defender_player.chi = max(0, defender_player.chi - defender_chi_loss)
        result["chi_loss"].append((attacker.id, attacker_chi_loss))
        result["chi_loss"].append((defender.id, defender_chi_loss))

        # Log stalemate
        game_state.log.append({
            'turn': game_state.turn,
            'phase': game_state.phase,
            'event': f'Confrontation between {attacker.id} ({attacker.stance}) and {defender.id} ({defender.stance}): Stalemate, both lose {attacker_chi_loss} Chi'
        })

        # Attempt retreat for both
        attacker_retreat_hex = find_retreat_hex(attacker, game_state)
        defender_retreat_hex = find_retreat_hex(defender, game_state)
        if attacker_retreat_hex:
            attacker.position = attacker_retreat_hex
            result["retreats"].append((attacker.id, attacker_retreat_hex))
            game_state.log.append({
                'turn': game_state.turn,
                'phase': game_state.phase,
                'event': f'{attacker.id} retreats to {attacker_retreat_hex}'
            })
        if defender_retreat_hex:
            defender.position = defender_retreat_hex
            result["retreats"].append((defender.id, defender_retreat_hex))
            game_state.log.append({
                'turn': game_state.turn,
                'phase': game_state.phase,
                'event': f'{defender.id} retreats to {defender_retreat_hex}'
            })
    elif winner == "attacker":
        # Attacker wins
        defender_chi_loss = base_chi_loss * terrain_multiplier
        defender_player.chi = max(0, defender_player.chi - defender_chi_loss)
        result["chi_loss"].append((defender.id, defender_chi_loss))

        # Log attacker victory
        game_state.log.append({
            'turn': game_state.turn,
            'phase': game_state.phase,
            'event': f'Confrontation between {attacker.id} ({attacker.stance}) and {defender.id} ({defender.stance}): {attacker.id} wins, {defender.id} loses {defender_chi_loss} Chi'
        })

        # Defender retreats, attacker moves
        retreat_hex = find_retreat_hex(defender, game_state)
        if retreat_hex:
            defender.position = retreat_hex
            result["retreats"].append((defender.id, retreat_hex))
            game_state.log.append({
                'turn': game_state.turn,
                'phase': game_state.phase,
                'event': f'{defender.id} retreats to {retreat_hex}'
            })
        attacker.position = target_hex
        result["retreats"].append((attacker.id, target_hex))
        game_state.log.append({
            'turn': game_state.turn,
            'phase': game_state.phase,
            'event': f'{attacker.id} advances to {target_hex}'
        })
    else:  # winner == "defender"
        # Defender wins
        attacker_chi_loss = base_chi_loss * terrain_multiplier
        attacker_player.chi = max(0, attacker_player.chi - attacker_chi_loss)
        result["chi_loss"].append((attacker.id, attacker_chi_loss))

        # Log defender victory
        game_state.log.append({
            'turn': game_state.turn,
            'phase': game_state.phase,
            'event': f'Confrontation between {attacker.id} ({attacker.stance}) and {defender.id} ({defender.stance}): {defender.id} wins, {attacker.id} loses {attacker_chi_loss} Chi'
        })

        # Attacker retreats
        retreat_hex = find_retreat_hex(attacker, game_state)
        if retreat_hex:
            attacker.position = retreat_hex
            result["retreats"].append((attacker.id, retreat_hex))
            game_state.log.append({
                'turn': game_state.turn,
                'phase': game_state.phase,
                'event': f'{attacker.id} retreats to {retreat_hex}'
            })

    return result

def calculate_stance_modifier(tendency: list, tendency_modifier: int) -> int:
    """Calculate stance modifier based on tendency (last 3 orders).
    
    Args:
        tendency: List of last 3 orders
        tendency_modifier: Base modifier value from config
        
    Returns:
        Stance modifier: negative for predictable (3 identical), 
                        positive for unpredictable (3 unique), 
                        0 for mixed patterns
    """
    if len(tendency) != 3:
        return 0  # Not enough orders for tendency analysis
    
    unique_orders = set(tendency)
    
    if len(unique_orders) == 1:
        # 3 identical orders: predictable = vulnerable (penalty)
        return -tendency_modifier
    elif len(unique_orders) == 3:
        # 3 unique orders: unpredictable = strong (bonus)
        return tendency_modifier
    else:
        # Mixed pattern: no modifier
        return 0

def determine_winner_with_modifiers(attacker_stance: str, defender_stance: str, 
                                  attacker_mod: int, defender_mod: int, 
                                  beats: Dict[str, str]) -> str:
    """Determine confrontation winner considering stance modifiers.
    
    Args:
        attacker_stance: Attacker's stance
        defender_stance: Defender's stance  
        attacker_mod: Attacker's stance modifier
        defender_mod: Defender's stance modifier
        beats: Dictionary mapping stances to what they beat
        
    Returns:
        "attacker", "defender", or "stalemate"
    """
    # Base rock-paper-scissors logic
    if attacker_stance == defender_stance:
        # Same stance: modifiers break the tie
        if attacker_mod > defender_mod:
            return "attacker"
        elif defender_mod > attacker_mod:
            return "defender"
        else:
            return "stalemate"
    elif beats[attacker_stance] == defender_stance:
        # Attacker normally wins, but defender modifier might overcome
        if defender_mod > attacker_mod:
            return "defender"
        else:
            return "attacker"
    else:
        # Defender normally wins, but attacker modifier might overcome
        if attacker_mod > defender_mod:
            return "attacker"
        else:
            return "defender"

def find_retreat_hex(force: Force, game_state: GameState) -> Optional[Tuple[int, int]]:
    """Find an adjacent, empty, valid hex for retreat."""
    current_pos = force.position
    # Possible adjacent hexes
    neighbors = [
        (current_pos[0] + dq, current_pos[1] + dr)
        for dq, dr in [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
    ]
    
    for hex_pos in neighbors:
        if (game_state.is_valid_position(hex_pos) and
            hex_pos in game_state.map_data and
            not any(f.position == hex_pos for p in game_state.players for f in p.forces)):
            return hex_pos
    return None