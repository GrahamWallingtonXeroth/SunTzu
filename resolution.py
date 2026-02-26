"""
Combat resolution for The Unfought Battle v10.

Combat is decisive but not always lethal. Both power values are revealed
permanently — even winning costs you the secrecy that was protecting you.

v10: Strategic reasoning benchmark. Charge bonus +2, ambush bonus +2,
     sovereign defense removed. Metagame rebalanced with multi-tier pool.
v9: Sovereign defense bonus. Wider starting separation.
v8: Anti-Goodhart measurement overhaul.
v7: Charge +1, support, retreat threshold 2, combat variance ±2.
"""

import json
import os
import random
from typing import Dict, Any, Optional, Tuple, List
from models import Force, SOVEREIGN_POWER
from state import GameState
from orders import is_adjacent
from map_gen import get_hex_neighbors, hex_distance


def load_combat_config() -> Dict:
    """Load combat-related configuration."""
    defaults = {
        'fortify_bonus': 2,
        'difficult_defense_bonus': 1,
        'ambush_bonus': 2,
        'charge_attack_bonus': 2,
        'support_bonus': 1,
        'max_support_bonus': 2,
        'retreat_threshold': 2,
        'sovereign_defense_bonus': 1,
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
    friendly_forces: Optional[List[Force]] = None,
) -> int:
    """
    Calculate a force's effective combat power.

    Base power (assigned value 1-5)
    + 2 if fortified this turn
    + 2 if ambushing and defending
    + 2 if charging and attacking
    + 1 if defending on Difficult terrain
    + 1 per adjacent friendly force (max +2) — support bonus
    + 1 if sovereign (power 1) and defending — sovereign defense bonus
    + random(-2, -1, 0, +1, +2) combat variance
    """
    config = load_combat_config()
    power = force.power if force.power is not None else 0

    # Fortify bonus
    if force.fortified:
        power += config['fortify_bonus']

    # Ambush bonus: only if this force is ambushing AND is the defender
    if force.ambushing and is_defender:
        power += config['ambush_bonus']

    # Charge attack bonus: only if this force is charging AND is the attacker
    if force.charging and not is_defender:
        power += config['charge_attack_bonus']

    # Difficult terrain defense bonus
    if is_defender and hex_pos:
        hex_data = game_state.map_data.get(hex_pos)
        if hex_data and hex_data.terrain == 'Difficult':
            power += config['difficult_defense_bonus']

    # Support bonus: +1 per adjacent friendly force, capped
    if friendly_forces is not None:
        combat_pos = hex_pos if hex_pos else force.position
        adjacent_friendlies = sum(
            1 for ally in friendly_forces
            if ally.id != force.id and ally.alive
            and is_adjacent(ally.position, combat_pos)
        )
        power += min(
            adjacent_friendlies * config['support_bonus'],
            config['max_support_bonus']
        )

    # Sovereign defense bonus: sovereign is harder to capture
    if is_defender and force.power == SOVEREIGN_POWER:
        power += config.get('sovereign_defense_bonus', 2)

    # Combat variance: -2 to +2
    if apply_variance:
        r = rng if rng else random
        power += r.choice([-2, -1, 0, 1, 2])

    return power


def _find_retreat_hex(
    force: Force,
    combat_hex: Tuple[int, int],
    game_state: GameState,
) -> Optional[Tuple[int, int]]:
    """
    Find a valid retreat hex for a force pushed out of combat.
    Prefers hexes closest to the force's pre-combat position.
    """
    candidates = []
    for nq, nr in get_hex_neighbors(combat_hex[0], combat_hex[1]):
        pos = (nq, nr)
        if not game_state.is_valid_position(pos):
            continue
        occupant = game_state.get_force_at_position(pos)
        if occupant is not None:
            continue
        candidates.append(pos)
    if not candidates:
        return None
    # Pick the hex closest to the force's current position (retreat toward origin)
    return min(candidates, key=lambda p: hex_distance(
        p[0], p[1], force.position[0], force.position[1]))


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
    2. Calculate effective power for each (with variance and support).
    3. Higher power wins. Equal power = both retreat.
    4. If power difference > retreat_threshold: loser is eliminated.
       If power difference <= retreat_threshold: loser retreats alive.
    5. If a Sovereign (power 1) is eliminated, that player loses.
    """
    config = load_combat_config()

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

    # Step 2: Calculate effective power (with variance and support)
    att_forces = att_player.get_alive_forces() if att_player else []
    def_forces = def_player.get_alive_forces() if def_player else []

    att_power = calculate_effective_power(
        attacker, game_state, is_defender=False, hex_pos=combat_hex, rng=rng,
        friendly_forces=att_forces,
    )
    def_power = calculate_effective_power(
        defender, game_state, is_defender=True, hex_pos=combat_hex, rng=rng,
        friendly_forces=def_forces,
    )

    result['attacker_power'] = att_power
    result['defender_power'] = def_power

    # Step 3: Determine outcome with retreat mechanic
    power_diff = abs(att_power - def_power)
    retreat_threshold = config['retreat_threshold']

    if att_power > def_power:
        # Attacker wins — takes the hex
        if power_diff <= retreat_threshold:
            # Close combat: defender retreats alive
            retreat_hex = _find_retreat_hex(defender, combat_hex, game_state)
            if retreat_hex:
                defender.position = retreat_hex
                result['outcome'] = 'attacker_wins_retreat'
                result['retreated'] = defender.id
                result['retreat_to'] = retreat_hex
            else:
                # No retreat available — defender is eliminated
                defender.alive = False
                result['outcome'] = 'attacker_wins'
                result['eliminated'] = defender.id
        else:
            # Decisive: defender is eliminated
            defender.alive = False
            result['outcome'] = 'attacker_wins'
            result['eliminated'] = defender.id

        attacker.position = combat_hex

        game_state.log.append({
            'turn': game_state.turn, 'phase': 'resolve',
            'event': (
                f'Combat at {combat_hex}: {attacker.id} (power {att_power}) '
                f'{"pushes back" if "retreat" in result["outcome"] else "defeats"} '
                f'{defender.id} (power {def_power})'
            ),
        })

        # Check Sovereign capture (only if eliminated, not retreated)
        if not defender.alive and defender.is_sovereign:
            result['sovereign_captured'] = {
                'loser': defender_player_id,
                'winner': attacker_player_id,
                'capturing_force': attacker.id,
            }

    elif def_power > att_power:
        # Defender wins
        if power_diff <= retreat_threshold:
            # Close combat: attacker retreats alive (stays at original position)
            result['outcome'] = 'defender_wins_retreat'
            result['retreated'] = attacker.id
        else:
            # Decisive: attacker eliminated
            attacker.alive = False
            result['outcome'] = 'defender_wins'
            result['eliminated'] = attacker.id

        game_state.log.append({
            'turn': game_state.turn, 'phase': 'resolve',
            'event': (
                f'Combat at {combat_hex}: {defender.id} (power {def_power}) '
                f'{"pushes back" if "retreat" in result["outcome"] else "defeats"} '
                f'{attacker.id} (power {att_power})'
            ),
        })

        if not attacker.alive and attacker.is_sovereign:
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
