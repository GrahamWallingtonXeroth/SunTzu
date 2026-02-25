"""
Game state management for The Unfought Battle.

The state is the source of truth, but it's not the whole truth.
Each player sees a filtered view — their own forces in full,
enemy forces as anonymous tokens. What you know depends on
what you've scouted and who you've fought.
"""

from __future__ import annotations
import uuid
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from map_gen import generate_map, BOARD_SIZE, is_valid_hex
from models import Force, Player, Hex, ForceRole, ROLE_COUNTS


@dataclass
class GameState:
    """Complete game state. The god-view that no player ever sees in full."""
    game_id: str
    turn: int = 0  # 0 = deployment phase, 1+ = gameplay
    phase: str = 'deploy'  # 'deploy', 'plan', 'resolve', 'ended'
    players: List[Player] = field(default_factory=list)
    map_data: Dict[Tuple[int, int], Hex] = field(default_factory=dict)
    log: List[Dict[str, Any]] = field(default_factory=list)
    orders_submitted: Dict[str, bool] = field(default_factory=dict)
    winner: Optional[str] = None
    victory_type: Optional[str] = None
    board_size: int = BOARD_SIZE
    # Tracks feints this turn for the reveal phase
    feints: List[Dict[str, Any]] = field(default_factory=list)

    def get_player_by_id(self, player_id: str) -> Optional[Player]:
        for player in self.players:
            if player.id == player_id:
                return player
        return None

    def get_opponent(self, player_id: str) -> Optional[Player]:
        for player in self.players:
            if player.id != player_id:
                return player
        return None

    def get_force_at_position(self, position: Tuple[int, int]) -> Optional[Force]:
        for player in self.players:
            for force in player.get_alive_forces():
                if force.position == position:
                    return force
        return None

    def get_force_owner(self, force_id: str) -> Optional[Player]:
        for player in self.players:
            for force in player.forces:
                if force.id == force_id:
                    return player
        return None

    def is_valid_position(self, position: Tuple[int, int]) -> bool:
        return is_valid_hex(position[0], position[1], self.board_size)


def load_config() -> Dict:
    """Load game configuration with defaults."""
    defaults = {
        'starting_shih': 8,
        'max_shih': 15,
        'force_count': 5,
        'board_size': 7,
    }
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            defaults.update(config)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return defaults


def initialize_game(seed: int) -> GameState:
    """
    Create a new game in the deployment phase.

    Players start at opposite corners of the 7x7 board with 5 unassigned forces.
    Roles must be assigned via the deploy endpoint before play begins.
    """
    config = load_config()
    board_size = config.get('board_size', BOARD_SIZE)
    starting_shih = config.get('starting_shih', 8)
    max_shih = config.get('max_shih', 15)
    force_count = config.get('force_count', 5)

    game_id = str(uuid.uuid4())
    map_data = generate_map(seed, board_size)

    # P1 starts at top-left corner cluster
    p1_positions = [(0, 0), (1, 0), (0, 1), (1, 1), (2, 0)][:force_count]
    # P2 starts at bottom-right corner cluster
    last = board_size - 1
    p2_positions = [
        (last, last), (last - 1, last), (last, last - 1),
        (last - 1, last - 1), (last - 2, last)
    ][:force_count]

    player1 = Player(id='p1', shih=starting_shih, max_shih=max_shih)
    for i, pos in enumerate(p1_positions, 1):
        player1.add_force(Force(id=f'p1_f{i}', position=pos))

    player2 = Player(id='p2', shih=starting_shih, max_shih=max_shih)
    for i, pos in enumerate(p2_positions, 1):
        player2.add_force(Force(id=f'p2_f{i}', position=pos))

    return GameState(
        game_id=game_id,
        turn=0,
        phase='deploy',
        players=[player1, player2],
        map_data=map_data,
        board_size=board_size,
    )


def validate_deployment(assignments: Dict[str, str]) -> Optional[str]:
    """
    Validate that a role assignment is legal.
    Must have exactly: 1 Sovereign, 2 Vanguard, 1 Scout, 1 Shield.
    Returns error message or None if valid.
    """
    role_counts: Dict[str, int] = {}
    for role_str in assignments.values():
        role_counts[role_str] = role_counts.get(role_str, 0) + 1

    for role, required in ROLE_COUNTS.items():
        actual = role_counts.get(role.value, 0)
        if actual != required:
            return f"Need exactly {required} {role.value}, got {actual}"
    return None


def apply_deployment(game_state: GameState, player_id: str, assignments: Dict[str, str]) -> Optional[str]:
    """
    Assign roles to a player's forces. Returns error message or None.
    """
    player = game_state.get_player_by_id(player_id)
    if not player:
        return f"Player {player_id} not found"
    if player.deployed:
        return f"Player {player_id} has already deployed"

    # Validate force IDs belong to this player
    for force_id in assignments:
        if not player.get_force_by_id(force_id):
            return f"Force {force_id} does not belong to {player_id}"

    # Validate all forces are assigned
    if len(assignments) != len(player.forces):
        return f"Must assign roles to all {len(player.forces)} forces"

    # Validate role composition
    error = validate_deployment(assignments)
    if error:
        return error

    # Apply roles
    for force_id, role_str in assignments.items():
        force = player.get_force_by_id(force_id)
        force.role = ForceRole(role_str)

    player.deployed = True

    game_state.log.append({
        'turn': 0,
        'phase': 'deploy',
        'event': f'Player {player_id} deployed forces',
    })

    # If both players have deployed, advance to plan phase
    if all(p.deployed for p in game_state.players):
        game_state.phase = 'plan'
        game_state.turn = 1
        game_state.log.append({
            'turn': 1,
            'phase': 'plan',
            'event': 'Both players deployed. The battle begins.',
        })

    return None


def get_player_view(game_state: GameState, player_id: str) -> Dict:
    """
    Return the game state as seen by a specific player.

    You see:
    - Your own forces with full details (role, position)
    - Enemy forces as anonymous tokens (position only)
    - Enemy roles you've discovered through scouting or combat
    - The full map

    You don't see:
    - Enemy roles you haven't discovered
    - What the enemy has scouted about you
    """
    player = game_state.get_player_by_id(player_id)
    opponent = game_state.get_opponent(player_id)

    if not player or not opponent:
        return {}

    # Your forces: full information
    own_forces = []
    for f in player.get_alive_forces():
        own_forces.append({
            'id': f.id,
            'position': {'q': f.position[0], 'r': f.position[1]},
            'role': f.role.value if f.role else None,
            'revealed': f.revealed,
            'fortified': f.fortified,
        })

    # Enemy forces: position only, plus any roles you've learned
    enemy_forces = []
    for f in opponent.get_alive_forces():
        force_data: Dict[str, Any] = {
            'id': f.id,
            'position': {'q': f.position[0], 'r': f.position[1]},
        }
        # Include role if publicly revealed (combat) or privately scouted
        if f.revealed:
            force_data['role'] = f.role.value if f.role else None
            force_data['revealed'] = True
        elif f.id in player.known_enemy_roles:
            force_data['role'] = player.known_enemy_roles[f.id]
            force_data['scouted'] = True
        enemy_forces.append(force_data)

    return {
        'game_id': game_state.game_id,
        'turn': game_state.turn,
        'phase': game_state.phase,
        'your_shih': player.shih,
        'your_forces': own_forces,
        'enemy_forces': enemy_forces,
        'enemy_shih': opponent.shih,
        'domination_turns': {
            player_id: player.domination_turns,
            opponent.id: opponent.domination_turns,
        },
        'orders_submitted': game_state.orders_submitted.copy(),
        'winner': game_state.winner,
        'victory_type': game_state.victory_type,
        'feints': game_state.feints,
        'map': [
            {'q': pos[0], 'r': pos[1], 'terrain': h.terrain}
            for pos, h in game_state.map_data.items()
        ],
    }
