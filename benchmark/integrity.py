"""
Information integrity verification for the LLM reasoning benchmark.

Ensures prompts contain exactly the information the player should have:
no fog-of-war leaks, no hidden power values, no invisible enemy positions,
and no omissions of the player's own information.

Zero violations across all games is a prerequisite for publication.
"""

from __future__ import annotations

import re

from map_gen import hex_distance
from state import GameState


def verify_fog_of_war(view: dict, full_state: GameState, player_id: str,
                      visibility_range: int = 2) -> list[str]:
    """Verify the view dict is correctly fog-of-war filtered.

    Run on get_player_view() output before rendering.
    Returns list of violations (empty = clean).
    """
    violations = []
    player = full_state.get_player_by_id(player_id)
    opponent = full_state.get_opponent(player_id)

    if not player or not opponent:
        return violations

    # Check: no invisible enemy forces are included
    visible_enemy_ids = {f["id"] for f in view.get("enemy_forces", [])}

    for enemy_force in opponent.get_alive_forces():
        is_visible = any(
            hex_distance(
                own.position[0], own.position[1],
                enemy_force.position[0], enemy_force.position[1]
            ) <= visibility_range
            for own in player.get_alive_forces()
        )

        if enemy_force.id in visible_enemy_ids and not is_visible:
            violations.append(
                f"LEAK: Enemy force {enemy_force.id} at {enemy_force.position} included "
                f"in view but is outside visibility range {visibility_range}"
            )

        if is_visible and enemy_force.id not in visible_enemy_ids:
            violations.append(
                f"OMISSION: Enemy force {enemy_force.id} at {enemy_force.position} is "
                f"within visibility range but not included in view"
            )

    # Check: no hidden power values leaked for enemy forces
    for ef in view.get("enemy_forces", []):
        force_id = ef["id"]
        if "power" in ef and ef["power"] is not None:
            actual_force = opponent.get_force_by_id(force_id)
            if actual_force and not actual_force.revealed and force_id not in player.known_enemy_powers:
                violations.append(
                    f"LEAK: Enemy force {force_id} has power {ef['power']} in view "
                    f"but is neither revealed nor scouted"
                )

    # Check: own forces are complete
    own_ids_in_view = {f["id"] for f in view.get("your_forces", [])}
    for own_force in player.get_alive_forces():
        if own_force.id not in own_ids_in_view:
            violations.append(
                f"OMISSION: Own force {own_force.id} is alive but not in view"
            )

    # Check: own force powers are present
    for f in view.get("your_forces", []):
        if f.get("power") is None:
            violations.append(
                f"OMISSION: Own force {f['id']} has no power value in view"
            )

    return violations


def verify_prompt_integrity(
    prompt: str,
    player_view: dict,
    full_state: GameState,
    player_id: str,
) -> list[str]:
    """Verify prompt contains exactly the information the player should have.

    Returns list of violations (empty = clean).
    """
    violations = []
    opponent = full_state.get_opponent(player_id)
    player = full_state.get_player_by_id(player_id)

    if not player or not opponent:
        return violations

    # 1. Check no invisible enemy force IDs appear in prompt
    visible_enemy_ids = {f["id"] for f in player_view.get("enemy_forces", [])}
    for enemy_force in opponent.get_alive_forces():
        if enemy_force.id not in visible_enemy_ids:
            # This force should NOT appear in the prompt at all
            if enemy_force.id in prompt:
                violations.append(
                    f"LEAK: Invisible enemy force ID '{enemy_force.id}' found in prompt"
                )

    # 2. Check no hidden power values appear for unrevealed enemy forces
    for enemy_force in opponent.get_alive_forces():
        if not enemy_force.revealed and enemy_force.id not in player.known_enemy_powers:
            # Search for patterns like "power 4" or "pow=4" near the force ID
            if enemy_force.id in prompt and enemy_force.power is not None:
                # Look for the power value near the force ID
                id_positions = [m.start() for m in re.finditer(re.escape(enemy_force.id), prompt)]
                for pos in id_positions:
                    context = prompt[max(0, pos - 30):pos + len(enemy_force.id) + 50]
                    power_str = str(enemy_force.power)
                    # Check for power value patterns near the ID
                    power_patterns = [
                        f"power {power_str}",
                        f"power={power_str}",
                        f"pow={power_str}",
                        f"pow {power_str}",
                        f'"power": {power_str}',
                    ]
                    for pattern in power_patterns:
                        if pattern in context:
                            violations.append(
                                f"LEAK: Hidden power value {enemy_force.power} for "
                                f"unrevealed enemy {enemy_force.id} found in prompt"
                            )
                            break

    # 3. Check own forces are present
    for own_force in player.get_alive_forces():
        if own_force.id not in prompt:
            violations.append(
                f"OMISSION: Own force {own_force.id} not found in prompt"
            )

    # 4. Check turn number is correct
    turn = full_state.turn
    turn_str = str(turn)
    if f"turn {turn_str}" not in prompt.lower() and f"turn {turn_str}" not in prompt:
        # Also check for "Turn N" format
        found = False
        for pattern in [f"turn {turn_str}", f"Turn {turn_str}", f"TURN {turn_str}",
                        f'"turn": {turn_str}', f'"turn":{turn_str}']:
            if pattern in prompt:
                found = True
                break
        if not found:
            violations.append(
                f"OMISSION: Turn number {turn} not found in prompt"
            )

    return violations
