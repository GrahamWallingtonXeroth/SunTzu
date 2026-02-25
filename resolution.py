"""
Combat resolution for The Unfought Battle v3.

Combat is decisive. Both power values are revealed permanently — even winning
costs you the secrecy that was protecting you.

v3 changes:
- Power values (1-5) replace role-based power
- No more Shield adjacency bonus
- Ambush bonus: +3 if the ambushing force is defending against a moving enemy
- Combat variance: random +/-1 to each side (coin flip)
- A revealed power-5 can be avoided. A revealed power-1 (Sovereign) can be hunted.
"""

import json
import os
import random
from typing import Dict, Any, Optional, Tuple
from models import Force, SOVEREIGN_POWER
from state import GameState
from orders import is_adjacent


def load_combat_config() -> Dict:
    """Load combat-related configuration."""
    defaults = {
        'fortify_bonus': 2,
        'difficult_defense_bonus': 1,
        'ambush_bonus': 3,
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
    apply_variance: bool = True,
    rng: Optional[random.Random] = None,
) -> int:
    """
    Calculate a force's effective combat power.

    Base power (assigned value 1-5)
    + 2 if fortified this turn
    + 3 if ambushing and defending
    + 1 if defending on Difficult terrain
    + random(-1, +1) combat variance (coin flip)
    """
    config = load_combat_config()
    power = force.power if force.power is not None else 0

    # Fortify bonus
    if force.fortified:
        power += config['fortify_bonus']

    # Ambush bonus: only if this force is ambushing AND is the defender
    if force.ambushing and is_defender:
        power += config['ambush_bonus']

    # Difficult terrain defense bonus
    if is_defender and hex_pos:
        hex_data = game_state.map_data.get(hex_pos)
        if hex_data and hex_data.terrain == 'Difficult':
            power += config['difficult_defense_bonus']

    # Combat variance: +1 or -1 randomly
    if apply_variance:
        r = rng if rng else random
        power += r.choice([-1, 1])

    return power


def resolve_combat(
    attacker: Force,
    attacker_player_id: str,
    defender: Force,
    defender_player_id: str,
    combat_hex: Tuple[int, int],
    game_state: GameState,
    rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    """
    Resolve combat between two forces.

    1. Both power values are revealed permanently (the information cost of fighting).
    2. Calculate effective power for each (with variance).
    3. Higher power wins. Equal power = both retreat.
    4. Loser is eliminated. Winner occupies the hex.
    5. If a Sovereign (power 1) is eliminated, that player loses.
    """
    result: Dict[str, Any] = {
        'attacker_id': attacker.id,
        'defender_id': defender.id,
        'hex': combat_hex,
        'attacker_base_power': attacker.power,
        'defender_base_power': defender.power,
        'outcome': None,
        'sovereign_captured': None,
    }

    # Step 1: Reveal both power values permanently
    attacker.revealed = True
    defender.revealed = True

    # Also add to both players' knowledge
    att_player = game_state.get_player_by_id(attacker_player_id)
    def_player = game_state.get_player_by_id(defender_player_id)
    if att_player and defender.power is not None:
        att_player.known_enemy_powers[defender.id] = defender.power
    if def_player and attacker.power is not None:
        def_player.known_enemy_powers[attacker.id] = attacker.power

    # Step 2: Calculate effective power (with variance)
    att_power = calculate_effective_power(
        attacker, game_state, is_defender=False, hex_pos=combat_hex, rng=rng
    )
    def_power = calculate_effective_power(
        defender, game_state, is_defender=True, hex_pos=combat_hex, rng=rng
    )

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
                f'Combat at {combat_hex}: {attacker.id} (power {att_power}) '
                f'defeats {defender.id} (power {def_power})'
            ),
        })

        # Check Sovereign capture
        if defender.is_sovereign:
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
                f'Combat at {combat_hex}: {defender.id} (power {def_power}) '
                f'defeats {attacker.id} (power {att_power})'
            ),
        })

        if attacker.is_sovereign:
            result['sovereign_captured'] = {
                'loser': attacker_player_id,
                'winner': defender_player_id,
                'capturing_force': defender.id,
            }

    else:
        # Tie: both retreat, nobody eliminated
        result['outcome'] = 'stalemate'
        game_state.log.append({
            'turn': game_state.turn, 'phase': 'resolve',
            'event': (
                f'Combat stalemate at {combat_hex}: {attacker.id} (power {att_power}) '
                f'vs {defender.id} (power {def_power}) — both retreat'
            ),
        })

    return result
