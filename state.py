"""
Game state management for The Unfought Battle v10.

The state is the source of truth, but it's not the whole truth.
Each player sees a filtered view — their own forces in full,
enemy forces only within visibility range. What you know depends on
what you've scouted and who you've fought.

v10: Strategic reasoning benchmark. Metagame rebalanced with multi-tier pool.
v9: Sovereign defense bonus. Wider starting separation.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from map_gen import BOARD_SIZE, generate_map, hex_distance, is_valid_hex
from models import POWER_VALUES, Force, Hex, Player


@dataclass
class GameState:
    """Complete game state. The god-view that no player ever sees in full."""

    game_id: str
    turn: int = 0  # 0 = deployment phase, 1+ = gameplay
    phase: str = "deploy"  # 'deploy', 'plan', 'resolve', 'ended'
    players: list[Player] = field(default_factory=list)
    map_data: dict[tuple[int, int], Hex] = field(default_factory=dict)
    log: list[dict[str, Any]] = field(default_factory=list)
    orders_submitted: dict[str, bool] = field(default_factory=dict)
    winner: str | None = None
    victory_type: str | None = None
    board_size: int = BOARD_SIZE
    shrink_stage: int = 0  # Increments every shrink_interval turns

    def get_player_by_id(self, player_id: str) -> Player | None:
        for player in self.players:
            if player.id == player_id:
                return player
        return None

    def get_opponent(self, player_id: str) -> Player | None:
        for player in self.players:
            if player.id != player_id:
                return player
        return None

    def get_force_at_position(self, position: tuple[int, int]) -> Force | None:
        for player in self.players:
            for force in player.get_alive_forces():
                if force.position == position:
                    return force
        return None

    def get_force_owner(self, force_id: str) -> Player | None:
        for player in self.players:
            for force in player.forces:
                if force.id == force_id:
                    return player
        return None

    def is_valid_position(self, position: tuple[int, int]) -> bool:
        if not is_valid_hex(position[0], position[1], self.board_size):
            return False
        hex_data = self.map_data.get(position)
        return not (hex_data and hex_data.terrain == "Scorched")


def load_config() -> dict:
    """Load game configuration with defaults."""
    defaults = {
        "starting_shih": 6,
        "max_shih": 10,
        "force_count": 5,
        "board_size": 7,
        "visibility_range": 2,
        "shrink_interval": 6,
        "scout_range": 2,
        "supply_range": 3,
    }
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
            defaults.update(config)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return defaults


def initialize_game(seed: int) -> GameState:
    """
    Create a new game in the deployment phase.

    Players start at opposite corners of the 7x7 board with 5 unassigned forces.
    Power values must be assigned via the deploy endpoint before play begins.
    """
    config = load_config()
    board_size = config.get("board_size", BOARD_SIZE)
    starting_shih = config.get("starting_shih", 5)
    max_shih = config.get("max_shih", 8)
    force_count = config.get("force_count", 5)

    game_id = str(uuid.uuid4())
    map_data = generate_map(seed, board_size)

    # P1: left cluster, pushed back for wider separation (min 6 hexes to P2)
    p1_positions = [(0, 1), (0, 2), (0, 3), (1, 1), (1, 2)][:force_count]
    # P2: right cluster, symmetric to P1, pushed back
    p2_positions = [(6, 5), (6, 4), (6, 3), (5, 5), (5, 4)][:force_count]

    player1 = Player(id="p1", shih=starting_shih, max_shih=max_shih)
    for i, pos in enumerate(p1_positions, 1):
        player1.add_force(Force(id=f"p1_f{i}", position=pos))

    player2 = Player(id="p2", shih=starting_shih, max_shih=max_shih)
    for i, pos in enumerate(p2_positions, 1):
        player2.add_force(Force(id=f"p2_f{i}", position=pos))

    return GameState(
        game_id=game_id,
        turn=0,
        phase="deploy",
        players=[player1, player2],
        map_data=map_data,
        board_size=board_size,
    )


def validate_deployment(assignments: dict[str, int]) -> str | None:
    """
    Validate that a power assignment is legal.
    Must assign each of values 1-5 exactly once across the 5 forces.
    Returns error message or None if valid.
    """
    values = list(assignments.values())
    if len(values) != len(POWER_VALUES):
        return f"Must assign exactly {len(POWER_VALUES)} power values, got {len(values)}"
    if set(values) != POWER_VALUES:
        return f"Must use each power value (1-5) exactly once, got {sorted(values)}"
    return None


def apply_deployment(game_state: GameState, player_id: str, assignments: dict[str, int]) -> str | None:
    """
    Assign power values to a player's forces. Returns error message or None.
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
        return f"Must assign power to all {len(player.forces)} forces"

    # Validate power composition (each of 1-5 exactly once)
    error = validate_deployment(assignments)
    if error:
        return error

    # Apply power values
    for force_id, power_val in assignments.items():
        force = player.get_force_by_id(force_id)
        force.power = power_val

    player.deployed = True

    game_state.log.append(
        {
            "turn": 0,
            "phase": "deploy",
            "event": f"Player {player_id} deployed forces",
        }
    )

    # If both players have deployed, advance to plan phase
    if all(p.deployed for p in game_state.players):
        game_state.phase = "plan"
        game_state.turn = 1
        game_state.log.append(
            {
                "turn": 1,
                "phase": "plan",
                "event": "Both players deployed. The battle begins.",
            }
        )

    return None


def is_visible_to_player(position: tuple[int, int], player: Player, visibility_range: int = 2) -> bool:
    """Check if a position is within visibility range of any of the player's alive forces."""
    for force in player.get_alive_forces():
        if hex_distance(force.position[0], force.position[1], position[0], position[1]) <= visibility_range:
            return True
    return False


def get_player_view(game_state: GameState, player_id: str) -> dict:
    """
    Return the game state as seen by a specific player.

    v3 fog of war:
    - You can only see enemy forces within visibility range (2 hexes) of your alive forces
    - Enemy forces outside visibility are not shown at all
    - Power values you've discovered through scouting or combat are shown
    """
    config = load_config()
    visibility_range = config.get("visibility_range", 2)

    player = game_state.get_player_by_id(player_id)
    opponent = game_state.get_opponent(player_id)

    if not player or not opponent:
        return {}

    # Your forces: full information
    from orders import has_supply

    supply_range = config.get("supply_range", 3)
    own_forces = []
    for f in player.get_alive_forces():
        own_forces.append(
            {
                "id": f.id,
                "position": {"q": f.position[0], "r": f.position[1]},
                "power": f.power,
                "revealed": f.revealed,
                "fortified": f.fortified,
                "has_supply": has_supply(f, player.forces, supply_range),
            }
        )

    # Enemy forces: only those within visibility range
    enemy_forces = []
    for f in opponent.get_alive_forces():
        if not is_visible_to_player(f.position, player, visibility_range):
            continue  # Not visible — fog of war
        force_data: dict[str, Any] = {
            "id": f.id,
            "position": {"q": f.position[0], "r": f.position[1]},
        }
        # Include power if publicly revealed (combat) or privately scouted
        if f.revealed:
            force_data["power"] = f.power
            force_data["revealed"] = True
        elif f.id in player.known_enemy_powers:
            force_data["power"] = player.known_enemy_powers[f.id]
            force_data["scouted"] = True
        enemy_forces.append(force_data)

    # Map: show terrain, mark Scorched hexes
    map_view = []
    for pos, h in game_state.map_data.items():
        map_view.append(
            {
                "q": pos[0],
                "r": pos[1],
                "terrain": h.terrain,
            }
        )

    return {
        "game_id": game_state.game_id,
        "turn": game_state.turn,
        "phase": game_state.phase,
        "your_shih": player.shih,
        "your_forces": own_forces,
        "enemy_forces": enemy_forces,
        "enemy_shih": opponent.shih,
        "domination_turns": {
            player_id: player.domination_turns,
            opponent.id: opponent.domination_turns,
        },
        "orders_submitted": game_state.orders_submitted.copy(),
        "winner": game_state.winner,
        "victory_type": game_state.victory_type,
        "shrink_stage": game_state.shrink_stage,
        "map": map_view,
    }
