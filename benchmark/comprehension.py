"""
Comprehension probe generator for the LLM reasoning benchmark.

Generates verifiable questions from game state to gate reasoning measurement.
If an LLM can't answer basic factual questions about the game state, its
reasoning metrics are uninterpretable — it's reasoning from a misunderstood state.

Probes are injected at configurable frequency and scored separately from
reasoning metrics. Games with comprehension below threshold are flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from orders import _load_order_config, has_supply
from state import GameState

COMPREHENSION_THRESHOLD = 0.8  # Below this, reasoning metrics are uninterpretable


@dataclass
class Probe:
    """A verifiable comprehension question with known answer."""

    question: str
    expected_answer: str
    category: str  # "factual", "visibility", "rule", "terrain", "knowledge"
    difficulty: str  # "basic", "derived"

    def validate(self, response: str) -> bool:
        """Check if response matches expected answer (flexible matching)."""
        response_lower = response.lower().strip()
        expected_lower = self.expected_answer.lower().strip()

        # Exact match
        if expected_lower in response_lower:
            return True

        # Numeric match: extract numbers from both
        response_nums = set(re.findall(r"\d+", response_lower))
        expected_nums = set(re.findall(r"\d+", expected_lower))
        if expected_nums and expected_nums.issubset(response_nums):
            return True

        # Yes/No matching
        if expected_lower in ("yes", "no"):
            # Accept affirmative/negative variations
            yes_words = {"yes", "true", "correct", "it can", "has supply", "can use"}
            no_words = {"no", "false", "incorrect", "cannot", "can't", "it cannot", "does not have supply", "no supply"}
            if expected_lower == "yes":
                return any(w in response_lower for w in yes_words)
            else:
                return any(w in response_lower for w in no_words)

        # List matching: check all expected items are present
        if "," in expected_lower:
            items = [item.strip() for item in expected_lower.split(",")]
            return all(item in response_lower for item in items)

        return False


def _generate_factual_probes(view: dict) -> list[Probe]:
    """Generate basic factual probes about the game state."""
    probes = []

    # Force count
    alive_count = len(view.get("your_forces", []))
    probes.append(
        Probe(
            question="How many of your forces are currently alive?",
            expected_answer=str(alive_count),
            category="factual",
            difficulty="basic",
        )
    )

    # Shih
    shih = view.get("your_shih", 0)
    probes.append(
        Probe(
            question="How much Shih do you currently have?",
            expected_answer=str(shih),
            category="factual",
            difficulty="basic",
        )
    )

    # Turn number
    turn = view.get("turn", 0)
    probes.append(
        Probe(
            question="What is the current turn number?",
            expected_answer=str(turn),
            category="factual",
            difficulty="basic",
        )
    )

    return probes


def _generate_visibility_probes(view: dict) -> list[Probe]:
    """Generate probes about what the player can see."""
    probes = []

    enemy_forces = view.get("enemy_forces", [])
    probes.append(
        Probe(
            question="How many enemy forces can you currently see?",
            expected_answer=str(len(enemy_forces)),
            category="visibility",
            difficulty="basic",
        )
    )

    if enemy_forces:
        ids = ", ".join(f["id"] for f in enemy_forces)
        probes.append(
            Probe(
                question="List the IDs of all visible enemy forces.",
                expected_answer=ids,
                category="visibility",
                difficulty="basic",
            )
        )

    return probes


def _generate_terrain_probes(view: dict) -> list[Probe]:
    """Generate probes about map terrain."""
    probes = []

    map_data = view.get("map", [])
    contentious = [h for h in map_data if h["terrain"] == "Contentious"]

    if contentious:
        target = contentious[0]
        probes.append(
            Probe(
                question=f"What type of terrain is at position ({target['q']},{target['r']})?",
                expected_answer="Contentious",
                category="terrain",
                difficulty="basic",
            )
        )

    # Find a non-contentious hex
    for h in map_data:
        if h["terrain"] == "Difficult":
            probes.append(
                Probe(
                    question=f"What type of terrain is at position ({h['q']},{h['r']})?",
                    expected_answer="Difficult",
                    category="terrain",
                    difficulty="basic",
                )
            )
            break

    return probes


def _generate_knowledge_probes(view: dict) -> list[Probe]:
    """Generate probes about known enemy information."""
    probes = []

    enemy_forces = view.get("enemy_forces", [])
    for ef in enemy_forces:
        if ef.get("revealed"):
            probes.append(
                Probe(
                    question=f"What do you know about {ef['id']}'s power level?",
                    expected_answer=f"{ef['power']}",
                    category="knowledge",
                    difficulty="basic",
                )
            )
            break

    unknown = [ef for ef in enemy_forces if not ef.get("revealed") and not ef.get("scouted")]
    if unknown:
        ids = ", ".join(ef["id"] for ef in unknown)
        probes.append(
            Probe(
                question="Which visible enemy forces have completely unknown power?",
                expected_answer=ids,
                category="knowledge",
                difficulty="derived",
            )
        )

    return probes


def _generate_rule_probes(view: dict, game_state: GameState, player_id: str, config: dict) -> list[Probe]:
    """Generate probes that test rule understanding (supply chain, etc.)."""
    probes = []
    player = game_state.get_player_by_id(player_id)
    if not player:
        return probes

    order_cfg = _load_order_config()
    supply_range = order_cfg["supply_range"]
    max_hops = order_cfg["max_supply_hops"]

    for force in player.get_alive_forces():
        supplied = has_supply(force, player.forces, supply_range, max_hops=max_hops)
        probes.append(
            Probe(
                question=f"Can your force {force.id} use Scout this turn?",
                expected_answer="Yes" if (supplied and player.shih >= order_cfg["scout_cost"]) else "No",
                category="rule",
                difficulty="derived",
            )
        )
        break  # One rule probe is enough

    return probes


def generate_probes(
    view: dict,
    game_state: GameState,
    player_id: str,
    config: dict,
    n_probes: int = 5,
) -> list[Probe]:
    """Generate n_probes questions with known answers from the current state.

    Deterministically selects probes to cover categories.
    """
    all_probes: list[Probe] = []
    all_probes.extend(_generate_factual_probes(view))
    all_probes.extend(_generate_visibility_probes(view))
    all_probes.extend(_generate_terrain_probes(view))
    all_probes.extend(_generate_knowledge_probes(view))
    all_probes.extend(_generate_rule_probes(view, game_state, player_id, config))

    # Select up to n_probes, prioritizing category diversity
    selected: list[Probe] = []
    seen_categories: set[str] = set()

    # First pass: one from each category
    for probe in all_probes:
        if probe.category not in seen_categories and len(selected) < n_probes:
            selected.append(probe)
            seen_categories.add(probe.category)

    # Second pass: fill remaining
    for probe in all_probes:
        if probe not in selected and len(selected) < n_probes:
            selected.append(probe)

    return selected[:n_probes]


def score_comprehension(probes: list[Probe], responses: list[str]) -> float:
    """Score comprehension: fraction of probes answered correctly."""
    if not probes or not responses:
        return 0.0
    correct = sum(1 for probe, response in zip(probes, responses, strict=False) if probe.validate(response))
    return correct / len(probes)


def format_probes_as_prompt(probes: list[Probe]) -> str:
    """Format probes as questions for inclusion in an LLM prompt."""
    lines = ["Answer each question briefly and precisely:"]
    for i, probe in enumerate(probes, 1):
        lines.append(f"  {i}. {probe.question}")
    return "\n".join(lines)


def parse_probe_responses(text: str, n_probes: int) -> list[str]:
    """Parse numbered responses from LLM output.

    Expects format like:
    1. 4
    2. 6
    3. p2_f1, p2_f3
    """
    responses = []
    lines = text.strip().split("\n")

    for line in lines:
        line = line.strip()
        # Match numbered responses: "1. answer" or "1) answer"
        match = re.match(r"^\d+[.)]\s*(.*)", line)
        if match:
            responses.append(match.group(1).strip())

    # Pad with empty strings if we didn't get enough
    while len(responses) < n_probes:
        responses.append("")

    return responses[:n_probes]
