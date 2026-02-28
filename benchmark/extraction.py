"""
Extraction pipeline: free-text reasoning → structured AgentReport.

Decouples reasoning quality from format compliance. The LLM reasons freely
in natural language; this module converts that reasoning into structured
beliefs and orders via a separate extraction step.

Two extraction methods:
- tool_calling: Use tool/function calling for structured output (default)
- secondary_llm: Separate LLM call to parse reasoning text
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from benchmark.providers import LLMProvider
from benchmark.telemetry import BeliefState

EXTRACTION_TOOLS = [
    {
        "name": "report_beliefs",
        "description": (
            "Report your beliefs about each visible enemy force's hidden power level. "
            "For each force, provide the probability (0.0 to 1.0) that it has each power "
            "level (1 through 5). Probabilities for each force should sum to 1.0."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "beliefs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "force_id": {"type": "string", "description": "Enemy force ID (e.g. p2_f1)"},
                            "power_1_probability": {"type": "number", "description": "Probability of power 1"},
                            "power_2_probability": {"type": "number", "description": "Probability of power 2"},
                            "power_3_probability": {"type": "number", "description": "Probability of power 3"},
                            "power_4_probability": {"type": "number", "description": "Probability of power 4"},
                            "power_5_probability": {"type": "number", "description": "Probability of power 5"},
                        },
                        "required": [
                            "force_id",
                            "power_1_probability",
                            "power_2_probability",
                            "power_3_probability",
                            "power_4_probability",
                            "power_5_probability",
                        ],
                    },
                },
            },
            "required": ["beliefs"],
        },
    },
    {
        "name": "submit_orders",
        "description": (
            "Submit your orders for each of your alive forces this turn. Each force must receive exactly one order."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "orders": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "force_id": {"type": "string", "description": "Your force ID (e.g. p1_f1)"},
                            "order_type": {
                                "type": "string",
                                "enum": ["Move", "Charge", "Scout", "Fortify", "Ambush"],
                                "description": "The order type",
                            },
                            "target_q": {"type": "integer", "description": "Target hex q coordinate (for Move/Charge)"},
                            "target_r": {"type": "integer", "description": "Target hex r coordinate (for Move/Charge)"},
                            "scout_target_id": {"type": "string", "description": "Enemy force ID to scout (for Scout)"},
                        },
                        "required": ["force_id", "order_type"],
                    },
                },
            },
            "required": ["orders"],
        },
    },
]

DEPLOYMENT_TOOL = {
    "name": "deploy_forces",
    "description": (
        "Assign power values 1-5 to your forces. Each value must be used exactly once. "
        "Power 1 is your Sovereign — if it is captured or eliminated, you lose."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "force_id": {"type": "string"},
                        "power": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    "required": ["force_id", "power"],
                },
            },
        },
        "required": ["assignments"],
    },
}


@dataclass
class ExtractionResult:
    """Result of extracting structured data from LLM reasoning."""

    beliefs: dict[str, BeliefState] = field(default_factory=dict)
    orders: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5
    raw_reasoning: str = ""
    extraction_method: str = "tool_calling"
    extraction_success: bool = True
    extraction_errors: list[str] = field(default_factory=list)


def extract_beliefs_and_orders(
    reasoning_text: str,
    view: dict,
    player_id: str,
    provider: LLMProvider,
    method: str = "tool_calling",
) -> ExtractionResult:
    """Extract structured data from free-text reasoning.

    Args:
        reasoning_text: The LLM's free-form reasoning output
        view: The player's game view (from get_player_view)
        player_id: This agent's player ID
        provider: LLM provider for extraction calls
        method: "tool_calling" or "secondary_llm"
    """
    if method == "tool_calling":
        return _extract_via_tools(reasoning_text, view, player_id, provider)
    else:
        return _extract_via_secondary(reasoning_text, view, player_id, provider)


def _extract_via_tools(
    reasoning_text: str,
    view: dict,
    player_id: str,
    provider: LLMProvider,
) -> ExtractionResult:
    """Use tool calling to extract structured beliefs and orders."""
    result = ExtractionResult(
        raw_reasoning=reasoning_text,
        extraction_method="tool_calling",
    )

    # Build extraction prompt
    enemy_ids = [f["id"] for f in view.get("enemy_forces", [])]
    own_ids = [f["id"] for f in view.get("your_forces", [])]

    system = (
        "You are extracting structured data from game reasoning. "
        "Use the provided tools to report the agent's beliefs about enemy forces "
        "and the orders chosen for each force."
    )

    user_msg = (
        f"Based on this reasoning about a strategy game, extract the beliefs and orders.\n\n"
        f"REASONING:\n{reasoning_text}\n\n"
        f"Visible enemy forces: {enemy_ids}\n"
        f"Your alive forces: {own_ids}\n\n"
        f"Call report_beliefs for each visible enemy force, then submit_orders for each "
        f"of your alive forces. Each power value (1-5) is used exactly once across "
        f"the enemy's forces, so probabilities should reflect this constraint."
    )

    try:
        response = provider.complete_with_tools(
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            tools=EXTRACTION_TOOLS,
            temperature=0.0,
        )

        for tool_call in response.tool_calls:
            if tool_call["name"] == "report_beliefs":
                _parse_belief_tool_call(tool_call["input"], result)
            elif tool_call["name"] == "submit_orders":
                _parse_order_tool_call(tool_call["input"], result)

    except Exception as e:
        result.extraction_success = False
        result.extraction_errors.append(f"Tool calling failed: {e}")

    return result


def _extract_via_secondary(
    reasoning_text: str,
    view: dict,
    player_id: str,
    provider: LLMProvider,
) -> ExtractionResult:
    """Use a separate LLM call to parse reasoning into structured data."""
    result = ExtractionResult(
        raw_reasoning=reasoning_text,
        extraction_method="secondary_llm",
    )

    enemy_ids = [f["id"] for f in view.get("enemy_forces", [])]
    own_ids = [f["id"] for f in view.get("your_forces", [])]

    system = "You extract structured data from game reasoning. Respond with valid JSON only."

    user_msg = (
        f"Extract beliefs and orders from this strategy game reasoning.\n\n"
        f"REASONING:\n{reasoning_text}\n\n"
        f"Visible enemy forces: {enemy_ids}\n"
        f"Your alive forces: {own_ids}\n\n"
        f"Respond with JSON in this exact format:\n"
        f'{{"beliefs": [{{"force_id": "...", "power_1_probability": 0.2, '
        f'"power_2_probability": 0.2, "power_3_probability": 0.2, '
        f'"power_4_probability": 0.2, "power_5_probability": 0.2}}], '
        f'"orders": [{{"force_id": "...", "order_type": "Move", '
        f'"target_q": 3, "target_r": 3}}]}}'
    )

    try:
        response = provider.complete(
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            temperature=0.0,
        )

        import json

        # Try to parse JSON from response
        content = response.content.strip()
        # Handle markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        data = json.loads(content)

        if "beliefs" in data:
            _parse_belief_tool_call(data, result)
        if "orders" in data:
            _parse_order_tool_call(data, result)

    except Exception as e:
        result.extraction_success = False
        result.extraction_errors.append(f"Secondary LLM extraction failed: {e}")

    return result


def _parse_belief_tool_call(data: dict, result: ExtractionResult) -> None:
    """Parse belief data from tool call input into ExtractionResult."""
    for belief_data in data.get("beliefs", []):
        force_id = belief_data.get("force_id", "")
        dist = {}
        for power in range(1, 6):
            key = f"power_{power}_probability"
            prob = belief_data.get(key, 0.2)
            dist[power] = max(0.0, min(1.0, float(prob)))

        # Normalize to sum to 1.0
        total = sum(dist.values())
        if total > 0:
            dist = {k: v / total for k, v in dist.items()}
        else:
            dist = {i: 0.2 for i in range(1, 6)}

        result.beliefs[force_id] = BeliefState(distribution=dist)


def _parse_order_tool_call(data: dict, result: ExtractionResult) -> None:
    """Parse order data from tool call input into ExtractionResult."""
    for order_data in data.get("orders", []):
        order: dict[str, Any] = {
            "force_id": order_data.get("force_id", ""),
            "order_type": order_data.get("order_type", "Move"),
        }
        if "target_q" in order_data and "target_r" in order_data:
            order["target_hex"] = (order_data["target_q"], order_data["target_r"])
        if "scout_target_id" in order_data:
            order["scout_target_id"] = order_data["scout_target_id"]
        result.orders.append(order)


def extract_deployment(
    reasoning_text: str,
    player_id: str,
    force_ids: list[str],
    provider: LLMProvider,
) -> dict[str, int]:
    """Extract deployment assignments from LLM reasoning.

    Returns dict mapping force_id -> power (1-5).
    Falls back to sequential assignment on failure.
    """
    system = "You are extracting deployment decisions. Use the deploy_forces tool."
    user_msg = (
        f"Based on this reasoning about force deployment, extract the assignments.\n\n"
        f"REASONING:\n{reasoning_text}\n\n"
        f"Forces to assign: {force_ids}\n"
        f"Assign each power value 1-5 exactly once."
    )

    try:
        response = provider.complete_with_tools(
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            tools=[DEPLOYMENT_TOOL],
            temperature=0.0,
        )

        for tool_call in response.tool_calls:
            if tool_call["name"] == "deploy_forces":
                assignments = {}
                for item in tool_call["input"].get("assignments", []):
                    assignments[item["force_id"]] = item["power"]
                if set(assignments.values()) == {1, 2, 3, 4, 5}:
                    return assignments
    except Exception:
        pass

    # Fallback: sequential assignment
    return dict(zip(force_ids, [1, 2, 3, 4, 5], strict=False))


def validate_beliefs(beliefs: dict[str, BeliefState], view: dict) -> list[str]:
    """Validate extracted beliefs for correctness.

    Returns list of violations (empty = valid).
    """
    violations = []

    for force_id, belief in beliefs.items():
        # Check distribution sums to ~1.0
        total = sum(belief.distribution.values())
        if abs(total - 1.0) > 0.05:
            violations.append(f"Belief for {force_id} sums to {total:.3f}, expected ~1.0")

        # Check all probabilities in [0, 1]
        for power, prob in belief.distribution.items():
            if prob < -0.01 or prob > 1.01:
                violations.append(f"Belief for {force_id} power {power} = {prob:.3f}, out of [0,1]")

    # Check beliefs exist for visible enemy forces
    enemy_ids = {f["id"] for f in view.get("enemy_forces", [])}
    for eid in enemy_ids:
        if eid not in beliefs:
            violations.append(f"Missing belief for visible enemy {eid}")

    # Check revealed powers have probability 1.0
    for ef in view.get("enemy_forces", []):
        if ef.get("revealed") and ef["id"] in beliefs:
            actual_power = ef.get("power")
            if actual_power is not None:
                prob = beliefs[ef["id"]].distribution.get(actual_power, 0.0)
                if prob < 0.9:
                    violations.append(
                        f"Revealed force {ef['id']} has power {actual_power} but belief probability is only {prob:.3f}"
                    )

    return violations


def validate_orders(orders: list[dict], view: dict, config: dict) -> list[str]:
    """Validate extracted orders for correctness.

    Returns list of violations (empty = valid).
    """
    violations = []
    valid_types = {"Move", "Charge", "Scout", "Fortify", "Ambush"}
    own_ids = {f["id"] for f in view.get("your_forces", [])}

    for order in orders:
        force_id = order.get("force_id", "")
        order_type = order.get("order_type", "")

        if force_id not in own_ids:
            violations.append(f"Order for unknown force {force_id}")

        if order_type not in valid_types:
            violations.append(f"Invalid order type '{order_type}' for {force_id}")

    # Check all forces have orders
    ordered_ids = {o.get("force_id") for o in orders}
    for fid in own_ids:
        if fid not in ordered_ids:
            violations.append(f"No order for force {fid}")

    return violations


def normalize_beliefs(beliefs: dict[str, BeliefState]) -> dict[str, BeliefState]:
    """Force distributions to sum to 1.0 via normalization."""
    normalized = {}
    for force_id, belief in beliefs.items():
        total = sum(belief.distribution.values())
        if total > 0:
            dist = {k: v / total for k, v in belief.distribution.items()}
        else:
            dist = {i: 0.2 for i in range(1, 6)}
        normalized[force_id] = BeliefState(distribution=dist)
    return normalized
