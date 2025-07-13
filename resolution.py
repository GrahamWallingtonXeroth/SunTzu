from typing import Dict, Tuple, Optional, Any
from models import Force, Hex
from state import GameState, Player
from orders import is_adjacent

class ConfrontationError(Exception):
    """Exception raised when confrontation resolution fails."""
    pass

def resolve_confrontation(attacker: Force, defender: Optional[Force], target_hex: Tuple[int, int], attacker_stance: str, game_state: GameState) -> Dict[str, Any]:
    """Resolve a confrontation between an attacking force and a defender or ghost at target_hex."""
    result = {"attacker_id": attacker.id, "target_hex": target_hex, "chi_loss": [], "retreats": []}

    # If no defender (ghost confrontation), attacker moves to target hex
    if not defender:
        attacker.position = target_hex
        attacker.stance = attacker_stance
        result["retreats"].append((attacker.id, target_hex))
        return result

    # Find players
    attacker_player = next(p for p in game_state.players if attacker in p.forces)
    defender_player = next(p for p in game_state.players if defender in p.forces)

    # Stance resolution (GDD page 5)
    beats = {
        "Mountain": "Thunder",
        "River": "Mountain",
        "Thunder": "River"
    }
    base_chi_loss = 8  # GDD page 12
    terrain_multiplier = 2 if game_state.map_data[target_hex].terrain == "Contentious" else 1

    if attacker_stance == defender.stance:
        # Stalemate: both lose 4 Chi, retreat if possible
        attacker_chi_loss = 4 * terrain_multiplier
        defender_chi_loss = 4 * terrain_multiplier
        attacker_player.chi = max(0, attacker_player.chi - attacker_chi_loss)
        defender_player.chi = max(0, defender_player.chi - defender_chi_loss)
        result["chi_loss"].append((attacker.id, attacker_chi_loss))
        result["chi_loss"].append((defender.id, defender_chi_loss))

        # Attempt retreat for both
        attacker_retreat_hex = find_retreat_hex(attacker, game_state)
        defender_retreat_hex = find_retreat_hex(defender, game_state)
        if attacker_retreat_hex:
            attacker.position = attacker_retreat_hex
            result["retreats"].append((attacker.id, attacker_retreat_hex))
        if defender_retreat_hex:
            defender.position = defender_retreat_hex
            result["retreats"].append((defender.id, defender_retreat_hex))
    elif beats[attacker_stance] == defender.stance:
        # Attacker wins
        defender_chi_loss = base_chi_loss * terrain_multiplier
        defender_player.chi = max(0, defender_player.chi - defender_chi_loss)
        result["chi_loss"].append((defender.id, defender_chi_loss))

        # Defender retreats, attacker moves
        retreat_hex = find_retreat_hex(defender, game_state)
        if retreat_hex:
            defender.position = retreat_hex
            result["retreats"].append((defender.id, retreat_hex))
        attacker.position = target_hex
        attacker.stance = attacker_stance
        result["retreats"].append((attacker.id, target_hex))
    else:
        # Defender wins
        attacker_chi_loss = base_chi_loss * terrain_multiplier
        attacker_player.chi = max(0, attacker_player.chi - attacker_chi_loss)
        result["chi_loss"].append((attacker.id, attacker_chi_loss))

        # Attacker retreats
        retreat_hex = find_retreat_hex(attacker, game_state)
        if retreat_hex:
            attacker.position = retreat_hex
            result["retreats"].append((attacker.id, retreat_hex))

    return result

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