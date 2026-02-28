"""
Multi-format state renderers for the LLM reasoning benchmark.

Four deterministic functions transform get_player_view() output into different
string representations. Format invariance across these is a validity check:
if reasoning metrics shift dramatically between formats, prompt format is a
confound, not reasoning.

All renderers receive the SAME view dict from get_player_view(), guaranteeing
identical information content across formats.
"""

from __future__ import annotations

import json
from typing import Any

from map_gen import BOARD_SIZE

TERRAIN_CHAR = {
    "Open": ".",
    "Difficult": "#",
    "Contentious": "*",
    "Scorched": "X",
}

RENDERERS: dict[str, Any] = {}  # populated at module bottom


def render_rules_reference(config: dict) -> str:
    """Concise rules summary parameterized by config. ~400 tokens."""
    return (
        f"RULES:\n"
        f"- 7x7 hex grid. Two players, 5 forces each.\n"
        f"- Each player assigns hidden power values 1-5 to forces (each used once).\n"
        f"- Power 1 = Sovereign. Lose your Sovereign, lose the game.\n"
        f"- Victory: capture enemy Sovereign, OR control {config.get('domination_hexes_required', 2)}+ "
        f"Contentious hexes for {config.get('domination_turns_required', 4)} consecutive turns "
        f"(domination), OR eliminate all enemy forces.\n"
        f"\n"
        f"ORDERS (one per force per turn):\n"
        f"- Move (free): move to adjacent hex.\n"
        f"- Charge ({config.get('charge_cost', 2)} Shih): move 1-2 hexes, "
        f"+{config.get('charge_attack_bonus', 2)} attack if entering combat. Requires supply.\n"
        f"- Scout ({config.get('scout_cost', 2)} Shih): stay put, reveal one enemy within "
        f"{config.get('scout_range', 2)} hexes ({int(config.get('scout_accuracy', 0.7) * 100)}% "
        f"exact, otherwise power band). Requires supply.\n"
        f"- Fortify ({config.get('fortify_cost', 2)} Shih): stay put, "
        f"+{config.get('fortify_bonus', 2)} defense this turn. Requires supply.\n"
        f"- Ambush ({config.get('ambush_cost', 3)} Shih): stay put, "
        f"+{config.get('ambush_bonus', 2)} defense when defending, hidden from enemy. Requires supply.\n"
        f"\n"
        f"SUPPLY: A force has supply if it can chain back to your Sovereign through "
        f"friendly forces within {config.get('supply_range', 2)} hexes per link "
        f"(max {config.get('max_supply_hops', 2)} hops). Forces without supply can only Move.\n"
        f"\n"
        f"COMBAT: When forces collide, effective_power = base_power + bonuses + support "
        f"(up to +{config.get('max_support_bonus', 2)} from adjacent friendlies) + random(-2 to +2). "
        f"Higher wins. Difference <= {config.get('retreat_threshold', 2)}: loser retreats. "
        f"Difference > {config.get('retreat_threshold', 2)}: loser eliminated. "
        f"Tie: both retreat. Both powers revealed permanently after combat.\n"
        f"\n"
        f"TERRAIN: Open (no effect), Difficult (+{config.get('difficult_defense_bonus', 1)} "
        f"defense), Contentious (strategic objective, +{config.get('contentious_shih_bonus', 2)} "
        f"Shih income), Scorched (impassable, forces die).\n"
        f"\n"
        f"VISIBILITY: You see enemies within {config.get('visibility_range', 2)} hexes of "
        f"your forces. Beyond that is fog of war.\n"
        f"\n"
        f"THE NOOSE: Every {config.get('shrink_interval', 5)} turns, the outermost ring "
        f"becomes Scorched. Forces on scorched hexes die.\n"
        f"\n"
        f"RESOURCES: Base income {config.get('base_shih_income', 1)} Shih/turn + "
        f"{config.get('contentious_shih_bonus', 2)} per Contentious hex held. "
        f"Max {config.get('max_shih', 8)} Shih."
    )


def render_history(events: list[dict], player_id: str, max_turns: int | None = None) -> str:
    """Render recent game history (combat results, scout reveals, movements).

    Used by all format renderers when history is provided.
    """
    if not events:
        return ""

    if max_turns is not None:
        events = events[-max_turns:]

    lines = ["RECENT EVENTS:"]
    for event in events:
        turn = event.get("turn", "?")
        etype = event.get("type", "")

        if etype == "combat":
            att = event.get("attacker", "?")
            dfn = event.get("defender", "?")
            att_p = event.get("attacker_power", "?")
            def_p = event.get("defender_power", "?")
            result = event.get("result", "?")
            lines.append(
                f"  Turn {turn}: Combat - {att} (power {att_p}) vs {dfn} (power {def_p}), "
                f"result: {result}"
            )
        elif etype == "scout_reveal":
            scout = event.get("scout", "?")
            target = event.get("target", "?")
            revealed = event.get("revealed", "?")
            lines.append(f"  Turn {turn}: Scout - {scout} revealed {target} as {revealed}")
        elif etype == "movement":
            force = event.get("force", "?")
            from_pos = event.get("from", "?")
            to_pos = event.get("to", "?")
            lines.append(f"  Turn {turn}: {force} moved {from_pos} -> {to_pos}")
        elif etype == "noose_kill":
            force = event.get("force", "?")
            sov = " (SOVEREIGN)" if event.get("was_sovereign") else ""
            lines.append(f"  Turn {turn}: {force} killed by the Noose{sov}")
        else:
            lines.append(f"  Turn {turn}: {event}")

    return "\n".join(lines)


def _format_own_forces(forces: list[dict]) -> list[dict]:
    """Standardize own force data for rendering."""
    result = []
    for f in forces:
        pos = f.get("position", {})
        result.append({
            "id": f["id"],
            "q": pos.get("q", 0),
            "r": pos.get("r", 0),
            "power": f.get("power"),
            "is_sovereign": f.get("power") == 1,
            "has_supply": f.get("has_supply", False),
            "revealed": f.get("revealed", False),
            "fortified": f.get("fortified", False),
        })
    return result


def _format_enemy_forces(forces: list[dict]) -> list[dict]:
    """Standardize enemy force data for rendering."""
    result = []
    for f in forces:
        pos = f.get("position", {})
        entry: dict[str, Any] = {
            "id": f["id"],
            "q": pos.get("q", 0),
            "r": pos.get("r", 0),
        }
        if f.get("revealed"):
            entry["power"] = f["power"]
            entry["source"] = "combat"
        elif f.get("scouted"):
            entry["power"] = f["power"]
            entry["source"] = "scouted"
        else:
            entry["power"] = None
            entry["source"] = None
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Format A: Natural language narrative
# ---------------------------------------------------------------------------


def render_narrative(view: dict, config: dict, history: list[dict] | None = None) -> str:
    """Natural language narrative representation of the game state."""
    parts = []

    if history:
        parts.append(render_history(history, view.get("your_forces", [{}])[0].get("id", "p1")[:2]))
        parts.append("")

    turn = view.get("turn", 0)
    your_shih = view.get("your_shih", 0)
    enemy_shih = view.get("enemy_shih", "?")
    shrink = view.get("shrink_stage", 0)
    dom = view.get("domination_turns", {})

    parts.append(f"It is turn {turn}. You have {your_shih} Shih. The enemy has {enemy_shih} Shih.")

    # Domination
    dom_keys = list(dom.keys())
    if len(dom_keys) >= 2:
        parts.append(
            f"Domination progress: you have {dom[dom_keys[0]]}, enemy has {dom[dom_keys[1]]} "
            f"consecutive turns."
        )

    if shrink > 0:
        parts.append(f"The Noose has shrunk {shrink} time(s).")

    # Own forces
    own = _format_own_forces(view.get("your_forces", []))
    parts.append(f"\nYou have {len(own)} force(s) alive:")
    for f in own:
        sov = " (your Sovereign)" if f["is_sovereign"] else ""
        supply = "has supply" if f["has_supply"] else "NO SUPPLY"
        rev = ", revealed to enemy" if f["revealed"] else ""
        parts.append(
            f"  {f['id']} at position ({f['q']},{f['r']}), power {f['power']}{sov}, {supply}{rev}."
        )

    # Enemy forces
    enemies = _format_enemy_forces(view.get("enemy_forces", []))
    if enemies:
        parts.append(f"\nYou can see {len(enemies)} enemy force(s):")
        for e in enemies:
            if e["power"] is not None:
                src = f" ({e['source']})" if e["source"] else ""
                parts.append(f"  {e['id']} at ({e['q']},{e['r']}), power {e['power']}{src}.")
            else:
                parts.append(f"  {e['id']} at ({e['q']},{e['r']}), power unknown.")
    else:
        parts.append("\nNo enemy forces are currently visible.")

    # Map terrain summary
    contentious = [(h["q"], h["r"]) for h in view.get("map", []) if h["terrain"] == "Contentious"]
    difficult = [(h["q"], h["r"]) for h in view.get("map", []) if h["terrain"] == "Difficult"]
    scorched = [(h["q"], h["r"]) for h in view.get("map", []) if h["terrain"] == "Scorched"]

    parts.append(f"\nContentious hexes (objectives): {contentious}")
    if difficult:
        parts.append(f"Difficult terrain: {difficult}")
    if scorched:
        parts.append(f"Scorched hexes (impassable): {scorched}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Format B: Structured tables
# ---------------------------------------------------------------------------


def render_tabular(view: dict, config: dict, history: list[dict] | None = None) -> str:
    """Structured tabular representation of the game state."""
    parts = []

    if history:
        parts.append(render_history(history, view.get("your_forces", [{}])[0].get("id", "p1")[:2]))
        parts.append("")

    turn = view.get("turn", 0)
    your_shih = view.get("your_shih", 0)
    enemy_shih = view.get("enemy_shih", "?")
    shrink = view.get("shrink_stage", 0)
    dom = view.get("domination_turns", {})

    dom_keys = list(dom.keys())
    your_dom = dom[dom_keys[0]] if dom_keys else 0
    enemy_dom = dom[dom_keys[1]] if len(dom_keys) >= 2 else 0
    dom_req = config.get("domination_turns_required", 4)

    parts.append(
        f"TURN {turn} | Your Shih: {your_shih} | Enemy Shih: {enemy_shih} | "
        f"Domination: You {your_dom}/{dom_req}, Enemy {enemy_dom}/{dom_req} | "
        f"Shrink stage: {shrink}"
    )

    # Own forces table
    own = _format_own_forces(view.get("your_forces", []))
    parts.append("\nYOUR FORCES:")
    parts.append(f"{'ID':<10} {'Pos':<8} {'Power':<7} {'Supply':<8} {'Status'}")
    parts.append("-" * 50)
    for f in own:
        status_parts = []
        if f["is_sovereign"]:
            status_parts.append("Sovereign")
        if f["revealed"]:
            status_parts.append("Revealed")
        if f["fortified"]:
            status_parts.append("Fortified")
        status = ", ".join(status_parts) if status_parts else "-"
        supply = "Yes" if f["has_supply"] else "NO"
        parts.append(f"{f['id']:<10} ({f['q']},{f['r']})  {f['power']:<7} {supply:<8} {status}")

    # Enemy forces table
    enemies = _format_enemy_forces(view.get("enemy_forces", []))
    parts.append("\nVISIBLE ENEMIES:")
    if enemies:
        parts.append(f"{'ID':<10} {'Pos':<8} {'Power':<9} {'Source'}")
        parts.append("-" * 40)
        for e in enemies:
            power_str = str(e["power"]) if e["power"] is not None else "Unknown"
            source_str = e["source"] if e["source"] else "-"
            parts.append(f"{e['id']:<10} ({e['q']},{e['r']})  {power_str:<9} {source_str}")
    else:
        parts.append("  (none visible)")

    # Terrain summary
    contentious = [(h["q"], h["r"]) for h in view.get("map", []) if h["terrain"] == "Contentious"]
    parts.append(f"\nCONTENTIOUS HEXES: {contentious}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Format C: ASCII hex map
# ---------------------------------------------------------------------------


def render_ascii_map(view: dict, config: dict, history: list[dict] | None = None) -> str:
    """ASCII hex map with status, adapted from play_cli.py."""
    parts = []

    if history:
        pid_guess = view.get("your_forces", [{}])[0].get("id", "p1")[:2] if view.get("your_forces") else "p1"
        parts.append(render_history(history, pid_guess))
        parts.append("")

    turn = view.get("turn", 0)
    your_shih = view.get("your_shih", 0)
    enemy_shih = view.get("enemy_shih", "?")
    shrink = view.get("shrink_stage", 0)
    dom = view.get("domination_turns", {})
    dom_keys = list(dom.keys())
    dom_req = config.get("domination_turns_required", 4)

    parts.append(f"Turn {turn} | Shih: {your_shih} (enemy: {enemy_shih}) | Shrink: {shrink}")
    if len(dom_keys) >= 2:
        parts.append(f"Domination: You {dom[dom_keys[0]]}/{dom_req}, Enemy {dom[dom_keys[1]]}/{dom_req}")

    board_size = config.get("board_size", BOARD_SIZE)

    # Build display grid
    display: dict[tuple[int, int], str] = {}
    for h in view.get("map", []):
        pos = (h["q"], h["r"])
        display[pos] = TERRAIN_CHAR.get(h["terrain"], ".")

    # Own forces: show power number
    own_positions: dict[tuple[int, int], dict] = {}
    for f in view.get("your_forces", []):
        pos = (f["position"]["q"], f["position"]["r"])
        power = f.get("power")
        display[pos] = str(power) if power else "?"
        own_positions[pos] = f

    # Enemy forces: show 'e' for unknown, power digit if known
    enemy_positions: dict[tuple[int, int], dict] = {}
    for f in view.get("enemy_forces", []):
        pos = (f["position"]["q"], f["position"]["r"])
        if f.get("revealed") or f.get("scouted"):
            display[pos] = str(f.get("power", "?"))
        else:
            display[pos] = "e"
        enemy_positions[pos] = f

    # Render hex grid
    parts.append("")
    parts.append("    q: " + "  ".join(str(q) for q in range(board_size)))
    parts.append("  r  " + "-" * (board_size * 3))
    for r in range(board_size):
        offset = "  " if r % 2 == 0 else " "
        row_chars = []
        for q in range(board_size):
            row_chars.append(display.get((q, r), " "))
        parts.append(f"  {r} {offset}" + "  ".join(row_chars))
    parts.append("")
    parts.append("Legend: . Open  # Difficult  * Contentious  X Scorched")
    parts.append("        1-5 = your force power  e = enemy (unknown power)")

    # Force listing
    own = _format_own_forces(view.get("your_forces", []))
    parts.append("\nYour forces:")
    for f in own:
        sov = " [SOVEREIGN]" if f["is_sovereign"] else ""
        supply = "[supplied]" if f["has_supply"] else "[NO SUPPLY]"
        parts.append(f"  {f['id']} pow={f['power']} pos=({f['q']},{f['r']}) {supply}{sov}")

    enemies = _format_enemy_forces(view.get("enemy_forces", []))
    if enemies:
        parts.append("Visible enemies:")
        for e in enemies:
            power_str = f"pow={e['power']}" if e["power"] is not None else "pow=?"
            src = f" ({e['source']})" if e["source"] else ""
            parts.append(f"  {e['id']} {power_str} pos=({e['q']},{e['r']}){src}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Format D: Raw JSON
# ---------------------------------------------------------------------------


def render_json(view: dict, config: dict, history: list[dict] | None = None) -> str:
    """Raw JSON representation of the player view."""
    output = dict(view)
    if history:
        output["recent_history"] = history
    return json.dumps(output, indent=2, default=str)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

RENDERERS = {
    "narrative": render_narrative,
    "tabular": render_tabular,
    "ascii": render_ascii_map,
    "json": render_json,
}
