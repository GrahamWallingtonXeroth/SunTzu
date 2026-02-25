"""
Combat resolution for The Unfought Battle.

Combat is decisive. Both roles are revealed permanently — even winning
costs you the secrecy that was protecting you. The calculation is simple:
higher effective power wins. But the consequences ripple.

A revealed Vanguard can be avoided. A revealed Sovereign can be hunted.
The information cost of fighting often outweighs the tactical gain.
That's the unfought battle: the fight you win by never having it.
"""

import json
import os
from typing import Dict, Any, Optional, Tuple
from models import Force, ForceRole, ROLE_POWER
from state import GameState
from orders import is_adjacent


def load_combat_config() -> Dict:
    """Load combat-related configuration."""
    defaults = {
        'fortify_bonus': 2,
        'shield_bonus': 2,
        'difficult_defense_bonus': 1,
    }
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            for k in defaults:
                if k in config:
                    defaults[k] = config[k]
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return defaults


def calculate_effective_power(
    force: Force,
    game_state: GameState,
    is_defender: bool = False,
    hex_pos: Optional[Tuple[int, int]] = None,
) -> int:
    """
    Calculate a force's effective combat power.

    Base power (from role)
    + 2 if fortified this turn
    + 2 if adjacent to a friendly Shield
    + 1 if defending on Difficult terrain
    """
    config = load_combat_config()
    power = force.base_power

    # Fortify bonus
    if force.fortified:
        power += config['fortify_bonus']

    # Shield adjacency bonus
    owner = game_state.get_force_owner(force.id)
    if owner:
        for ally in owner.get_alive_forces():
            if ally.id != force.id and ally.role == ForceRole.SHIELD:
                if is_adjacent(force.position, ally.position):
                    power += config['shield_bonus']
                    break  # Only one Shield bonus

    # Difficult terrain defense bonus
    if is_defender and hex_pos:
        hex_data = game_state.map_data.get(hex_pos)
        if hex_data and hex_data.terrain == 'Difficult':
            power += config['difficult_defense_bonus']

    return power


def resolve_combat(
    attacker: Force,
    attacker_player_id: str,
    defender: Force,
    defender_player_id: str,
    combat_hex: Tuple[int, int],
    game_state: GameState,
) -> Dict[str, Any]:
    """
    Resolve combat between two forces.

    1. Both roles are revealed permanently (the information cost of fighting).
    2. Calculate effective power for each.
    3. Higher power wins. Equal power = both retreat.
    4. Loser is eliminated. Winner occupies the hex.
    5. If a Sovereign is eliminated, that player loses.
    """
    result: Dict[str, Any] = {
        'attacker_id': attacker.id,
        'defender_id': defender.id,
        'hex': combat_hex,
        'attacker_role': attacker.role.value if attacker.role else None,
        'defender_role': defender.role.value if defender.role else None,
        'outcome': None,
        'sovereign_captured': None,
    }

    # Step 1: Reveal both roles permanently
    attacker.revealed = True
    defender.revealed = True

    # Also add to both players' knowledge
    att_player = game_state.get_player_by_id(attacker_player_id)
    def_player = game_state.get_player_by_id(defender_player_id)
    if att_player and defender.role:
        att_player.known_enemy_roles[defender.id] = defender.role.value
    if def_player and attacker.role:
        def_player.known_enemy_roles[attacker.id] = attacker.role.value

    # Step 2: Calculate effective power
    att_power = calculate_effective_power(attacker, game_state, is_defender=False, hex_pos=combat_hex)
    def_power = calculate_effective_power(defender, game_state, is_defender=True, hex_pos=combat_hex)

    result['attacker_power'] = att_power
    result['defender_power'] = def_power

    # Step 3: Determine outcome
    if att_power > def_power:
        # Attacker wins
        defender.alive = False
        attacker.position = combat_hex
        result['outcome'] = 'attacker_wins'
        result['eliminated'] = defender.id

        game_state.log.append({
            'turn': game_state.turn, 'phase': 'resolve',
            'event': (
                f'Combat at {combat_hex}: {attacker.id} ({attacker.role.value}, power {att_power}) '
                f'defeats {defender.id} ({defender.role.value}, power {def_power})'
            ),
        })

        # Check Sovereign capture
        if defender.role == ForceRole.SOVEREIGN:
            result['sovereign_captured'] = {
                'loser': defender_player_id,
                'winner': attacker_player_id,
                'capturing_force': attacker.id,
            }

    elif def_power > att_power:
        # Defender wins
        attacker.alive = False
        result['outcome'] = 'defender_wins'
        result['eliminated'] = attacker.id

        game_state.log.append({
            'turn': game_state.turn, 'phase': 'resolve',
            'event': (
                f'Combat at {combat_hex}: {defender.id} ({defender.role.value}, power {def_power}) '
                f'defeats {attacker.id} ({attacker.role.value}, power {att_power})'
            ),
        })

        if attacker.role == ForceRole.SOVEREIGN:
            result['sovereign_captured'] = {
                'loser': attacker_player_id,
                'winner': defender_player_id,
                'capturing_force': defender.id,
            }

    else:
        # Tie: both retreat, nobody eliminated
        result['outcome'] = 'stalemate'
        # Attacker stays at original position (didn't move yet in collision case)
        # For assault case, attacker also stays at origin
        game_state.log.append({
            'turn': game_state.turn, 'phase': 'resolve',
            'event': (
                f'Combat stalemate at {combat_hex}: {attacker.id} ({attacker.role.value}, power {att_power}) '
                f'vs {defender.id} ({defender.role.value}, power {def_power}) — both retreat'
            ),
        })

    return result
