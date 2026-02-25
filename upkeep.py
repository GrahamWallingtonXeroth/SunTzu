"""
Upkeep for The Unfought Battle.

After orders resolve, the board settles. Resources flow. The game checks
whether anyone has won — not through combat, but through position.

Victory conditions, in order of glory:
1. Sovereign Capture — you found and destroyed the enemy king. Decisive.
2. Domination — you held all Contentious ground for 2 consecutive turns.
   The enemy's position is hopeless; the battle is unfought.
3. Elimination — every enemy force is gone. Pyrrhic, but effective.
"""

import json
import os
from typing import Dict, Optional, Tuple, List, Any
from models import Player, Force, Hex, ForceRole
from state import GameState
from orders import is_adjacent


def load_upkeep_config() -> Dict:
    defaults = {
        'base_shih_income': 2,
        'contentious_shih_bonus': 1,
        'domination_turns_required': 2,
        'max_shih': 15,
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


def get_controlled_contentious(player: Player, game_state: GameState) -> List[Tuple[int, int]]:
    """
    Return the list of Contentious hexes controlled by this player.
    Control = player has an alive force on the hex.
    """
    controlled = []
    for pos, hex_data in game_state.map_data.items():
        if hex_data.terrain == 'Contentious':
            for force in player.get_alive_forces():
                if force.position == pos:
                    controlled.append(pos)
                    break
    return controlled


def check_victory(game_state: GameState, combat_sovereign_capture: Optional[Dict] = None) -> Optional[Dict[str, str]]:
    """
    Check all victory conditions. Returns {'winner': id, 'type': reason} or None.

    Checked in priority order:
    1. Sovereign Capture (from combat this turn)
    2. Elimination (all enemy forces dead)
    3. Domination (all Contentious hexes held for N consecutive turns)
    """
    # 1. Sovereign Capture — passed in from combat resolution
    if combat_sovereign_capture:
        return {
            'winner': combat_sovereign_capture['winner'],
            'type': 'sovereign_capture',
        }

    # 2. Elimination — check if either player has no alive forces
    for player in game_state.players:
        if len(player.get_alive_forces()) == 0:
            opponent = game_state.get_opponent(player.id)
            if opponent:
                return {
                    'winner': opponent.id,
                    'type': 'elimination',
                }

    # 3. Domination — check after updating domination_turns in perform_upkeep
    # (handled in perform_upkeep to properly track consecutive turns)

    return None


def perform_upkeep(game_state: GameState, combat_sovereign_capture: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Execute the upkeep phase:
    1. Check for immediate victory (Sovereign capture, elimination)
    2. Apply Shih income (base + Contentious bonus)
    3. Track domination progress
    4. Check for domination victory
    5. Clear turn state and advance
    """
    config = load_upkeep_config()
    results: Dict[str, Any] = {
        'winner': None,
        'victory_type': None,
        'shih_income': {},
        'contentious_control': {},
        'domination_progress': {},
    }

    # Step 1: Immediate victory check (Sovereign capture / elimination)
    victory = check_victory(game_state, combat_sovereign_capture)
    if victory:
        results['winner'] = victory['winner']
        results['victory_type'] = victory['type']
        game_state.winner = victory['winner']
        game_state.victory_type = victory['type']
        game_state.phase = 'ended'
        game_state.log.append({
            'turn': game_state.turn, 'phase': 'upkeep',
            'event': f"Victory: {victory['winner']} wins by {victory['type']}",
        })
        return results

    # Step 2: Shih income
    base_income = config['base_shih_income']
    contentious_bonus = config['contentious_shih_bonus']

    for player in game_state.players:
        controlled = get_controlled_contentious(player, game_state)
        income = base_income + (len(controlled) * contentious_bonus)
        old_shih = player.shih
        player.update_shih(income)
        results['shih_income'][player.id] = player.shih - old_shih
        results['contentious_control'][player.id] = [list(pos) for pos in controlled]

        game_state.log.append({
            'turn': game_state.turn, 'phase': 'upkeep',
            'event': (
                f'{player.id} earns {income} Shih '
                f'(base {base_income} + {len(controlled)} Contentious) '
                f'— now {player.shih}'
            ),
        })

    # Step 3: Domination tracking
    contentious_hexes = [
        pos for pos, h in game_state.map_data.items() if h.terrain == 'Contentious'
    ]
    domination_required = config['domination_turns_required']

    for player in game_state.players:
        controlled = get_controlled_contentious(player, game_state)
        if len(controlled) == len(contentious_hexes) and len(contentious_hexes) > 0:
            player.domination_turns += 1
        else:
            player.domination_turns = 0
        results['domination_progress'][player.id] = player.domination_turns

    # Step 4: Domination victory check
    for player in game_state.players:
        if player.domination_turns >= domination_required:
            results['winner'] = player.id
            results['victory_type'] = 'domination'
            game_state.winner = player.id
            game_state.victory_type = 'domination'
            game_state.phase = 'ended'
            game_state.log.append({
                'turn': game_state.turn, 'phase': 'upkeep',
                'event': (
                    f"Victory: {player.id} wins by domination "
                    f"(held all Contentious hexes for {domination_required} turns)"
                ),
            })
            return results

    # Step 5: Advance turn
    game_state.feints = []  # Clear feint data
    game_state.turn += 1
    game_state.phase = 'plan'
    game_state.orders_submitted = {}

    game_state.log.append({
        'turn': game_state.turn, 'phase': 'plan',
        'event': f'Turn {game_state.turn} begins.',
    })

    return results
