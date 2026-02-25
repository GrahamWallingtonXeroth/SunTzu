"""
Upkeep for The Unfought Battle v3.

After orders resolve, the board settles. Resources flow. The game checks
whether anyone has won — not through combat, but through position.

v3 changes:
- Shrinking board: every shrink_interval turns, outer ring becomes Scorched
- Domination: control 2 of 3 Contentious hexes for 3 consecutive turns
- Tighter economy: base income 1, contentious bonus 2

Victory conditions, in order of glory:
1. Sovereign Capture — you found and destroyed the power-1 force. Decisive.
2. Domination — you held 2+ Contentious hexes for 3 consecutive turns.
3. Elimination — every enemy force is gone. Pyrrhic, but effective.
"""

import json
import os
from typing import Dict, Optional, Tuple, List, Any
from models import Player, Force, Hex, SOVEREIGN_POWER
from state import GameState
from map_gen import is_scorched, distance_from_center, max_distance_for_shrink_stage


def load_upkeep_config() -> Dict:
    defaults = {
        'base_shih_income': 1,
        'contentious_shih_bonus': 2,
        'domination_turns_required': 3,
        'domination_hexes_required': 2,
        'max_shih': 8,
        'shrink_interval': 3,
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


def apply_board_shrink(game_state: GameState) -> List[Dict[str, Any]]:
    """
    Apply the board shrink (The Noose). Hexes beyond the allowed distance
    from center become Scorched. Any force on a Scorched hex is killed.

    Returns a list of events (forces killed, hexes scorched).
    """
    events = []
    max_dist = max_distance_for_shrink_stage(game_state.shrink_stage)

    # Scorch hexes
    for pos, hex_data in game_state.map_data.items():
        if hex_data.terrain != 'Scorched' and distance_from_center(pos[0], pos[1]) > max_dist:
            hex_data.terrain = 'Scorched'
            events.append({
                'type': 'scorched',
                'hex': pos,
            })

    # Kill forces on Scorched hexes
    for player in game_state.players:
        for force in player.get_alive_forces():
            hex_data = game_state.map_data.get(force.position)
            if hex_data and hex_data.terrain == 'Scorched':
                force.alive = False
                events.append({
                    'type': 'force_scorched',
                    'force_id': force.id,
                    'player': player.id,
                    'position': force.position,
                    'was_sovereign': force.is_sovereign,
                })
                game_state.log.append({
                    'turn': game_state.turn, 'phase': 'upkeep',
                    'event': f'{force.id} consumed by the Noose at {force.position}',
                })

    return events


def check_victory(game_state: GameState, combat_sovereign_capture: Optional[Dict] = None) -> Optional[Dict[str, str]]:
    """
    Check all victory conditions. Returns {'winner': id, 'type': reason} or None.

    Checked in priority order:
    1. Sovereign Capture (from combat this turn)
    2. Sovereign killed by Noose (board shrink)
    3. Elimination (all enemy forces dead)
    4. Domination (2+ Contentious hexes held for N consecutive turns)
    """
    # 1. Sovereign Capture — passed in from combat resolution
    if combat_sovereign_capture:
        return {
            'winner': combat_sovereign_capture['winner'],
            'type': 'sovereign_capture',
        }

    # 2 & 3. Check if either player has lost their Sovereign or all forces
    # Collect ALL losers before deciding — handles simultaneous death fairly
    losers = []
    for player in game_state.players:
        alive_forces = player.get_alive_forces()
        # All forces dead = elimination
        if len(alive_forces) == 0:
            losers.append(('elimination', player))
            continue
        # Sovereign dead specifically (could be from Noose)
        sovereign_alive = any(f.is_sovereign for f in alive_forces)
        if not sovereign_alive and player.deployed:
            had_sovereign = any(f.power == SOVEREIGN_POWER for f in player.forces)
            if had_sovereign:
                losers.append(('sovereign_capture', player))

    # Both players lost simultaneously — draw
    if len(losers) >= 2:
        return {
            'winner': 'draw',
            'type': 'mutual_destruction',
        }

    # One player lost
    if len(losers) == 1:
        reason, loser = losers[0]
        opponent = game_state.get_opponent(loser.id)
        if opponent:
            return {
                'winner': opponent.id,
                'type': reason,
            }

    return None


def perform_upkeep(game_state: GameState, combat_sovereign_capture: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Execute the upkeep phase:
    1. Check for immediate victory (Sovereign capture, elimination)
    2. Apply board shrink (The Noose) if interval reached
    3. Re-check victory (Noose may have killed Sovereign)
    4. Apply Shih income (base + Contentious bonus)
    5. Track domination progress (2 of 3 Contentious for 3 turns)
    6. Check for domination victory
    7. Clear turn state and advance
    """
    config = load_upkeep_config()
    results: Dict[str, Any] = {
        'winner': None,
        'victory_type': None,
        'shih_income': {},
        'contentious_control': {},
        'domination_progress': {},
        'noose_events': [],
    }

    # Step 1: Immediate victory check (Sovereign capture / elimination from combat)
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

    # Step 2: Board shrink (The Noose)
    shrink_interval = config['shrink_interval']
    if game_state.turn > 0 and game_state.turn % shrink_interval == 0:
        game_state.shrink_stage += 1
        game_state.log.append({
            'turn': game_state.turn, 'phase': 'upkeep',
            'event': f'The Noose tightens. Shrink stage {game_state.shrink_stage}.',
        })
        noose_events = apply_board_shrink(game_state)
        results['noose_events'] = noose_events

        # Step 3: Re-check victory after Noose
        victory = check_victory(game_state)
        if victory:
            results['winner'] = victory['winner']
            results['victory_type'] = victory['type']
            game_state.winner = victory['winner']
            game_state.victory_type = victory['type']
            game_state.phase = 'ended'
            game_state.log.append({
                'turn': game_state.turn, 'phase': 'upkeep',
                'event': f"Victory: {victory['winner']} wins by {victory['type']} (after Noose)",
            })
            return results

    # Step 4: Shih income
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

    # Step 5: Domination tracking (2 of 3 Contentious hexes)
    contentious_hexes = [
        pos for pos, h in game_state.map_data.items() if h.terrain == 'Contentious'
    ]
    domination_required_turns = config['domination_turns_required']
    domination_required_hexes = config['domination_hexes_required']

    for player in game_state.players:
        controlled = get_controlled_contentious(player, game_state)
        if len(controlled) >= domination_required_hexes and len(contentious_hexes) > 0:
            player.domination_turns += 1
        else:
            player.domination_turns = 0
        results['domination_progress'][player.id] = player.domination_turns

    # Step 6: Domination victory check
    for player in game_state.players:
        if player.domination_turns >= domination_required_turns:
            results['winner'] = player.id
            results['victory_type'] = 'domination'
            game_state.winner = player.id
            game_state.victory_type = 'domination'
            game_state.phase = 'ended'
            game_state.log.append({
                'turn': game_state.turn, 'phase': 'upkeep',
                'event': (
                    f"Victory: {player.id} wins by domination "
                    f"(held {domination_required_hexes}+ Contentious hexes "
                    f"for {domination_required_turns} turns)"
                ),
            })
            return results

    # Step 7: Advance turn
    game_state.turn += 1
    game_state.phase = 'plan'
    game_state.orders_submitted = {}

    game_state.log.append({
        'turn': game_state.turn, 'phase': 'plan',
        'event': f'Turn {game_state.turn} begins.',
    })

    return results
