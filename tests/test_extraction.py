"""Tests for the extraction pipeline."""

from benchmark.extraction import (
    ExtractionResult,
    extract_beliefs_and_orders,
    normalize_beliefs,
    validate_beliefs,
    validate_orders,
)
from benchmark.providers import MockProvider
from benchmark.telemetry import BeliefState


class TestValidateBeliefs:
    def test_valid_beliefs_pass(self):
        beliefs = {
            "p2_f1": BeliefState(distribution={1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.2}),
        }
        view = {"enemy_forces": [{"id": "p2_f1"}]}
        violations = validate_beliefs(beliefs, view)
        assert violations == []

    def test_detects_sum_not_one(self):
        beliefs = {
            "p2_f1": BeliefState(distribution={1: 0.5, 2: 0.5, 3: 0.5, 4: 0.0, 5: 0.0}),
        }
        view = {"enemy_forces": [{"id": "p2_f1"}]}
        violations = validate_beliefs(beliefs, view)
        assert any("sums to" in v for v in violations)

    def test_detects_missing_belief(self):
        beliefs = {}
        view = {"enemy_forces": [{"id": "p2_f1"}]}
        violations = validate_beliefs(beliefs, view)
        assert any("Missing belief" in v for v in violations)

    def test_detects_revealed_not_one(self):
        beliefs = {
            "p2_f1": BeliefState(distribution={1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.2}),
        }
        view = {"enemy_forces": [{"id": "p2_f1", "revealed": True, "power": 3}]}
        violations = validate_beliefs(beliefs, view)
        assert any("Revealed" in v for v in violations)


class TestValidateOrders:
    def test_valid_orders_pass(self):
        orders = [
            {"force_id": "p1_f1", "order_type": "Move", "target_hex": (3, 3)},
        ]
        view = {"your_forces": [{"id": "p1_f1"}]}
        violations = validate_orders(orders, view, {})
        assert violations == []

    def test_detects_unknown_force(self):
        orders = [{"force_id": "p1_f99", "order_type": "Move"}]
        view = {"your_forces": [{"id": "p1_f1"}]}
        violations = validate_orders(orders, view, {})
        assert any("unknown force" in v for v in violations)

    def test_detects_invalid_order_type(self):
        orders = [{"force_id": "p1_f1", "order_type": "Teleport"}]
        view = {"your_forces": [{"id": "p1_f1"}]}
        violations = validate_orders(orders, view, {})
        assert any("Invalid order type" in v for v in violations)

    def test_detects_missing_order(self):
        orders = []
        view = {"your_forces": [{"id": "p1_f1"}]}
        violations = validate_orders(orders, view, {})
        assert any("No order" in v for v in violations)


class TestNormalizeBeliefs:
    def test_normalizes_to_one(self):
        beliefs = {
            "f1": BeliefState(distribution={1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 2.0}),
        }
        normalized = normalize_beliefs(beliefs)
        total = sum(normalized["f1"].distribution.values())
        assert abs(total - 1.0) < 0.001

    def test_handles_zero_total(self):
        beliefs = {
            "f1": BeliefState(distribution={1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}),
        }
        normalized = normalize_beliefs(beliefs)
        # Should fall back to uniform
        assert abs(normalized["f1"].distribution[1] - 0.2) < 0.01


class TestToolCallingExtraction:
    def test_extracts_from_tool_calls(self):
        """MockProvider returns tool call data, extraction should parse it."""
        tool_responses = [
            [
                {
                    "name": "report_beliefs",
                    "input": {
                        "beliefs": [
                            {
                                "force_id": "p2_f1",
                                "power_1_probability": 0.1,
                                "power_2_probability": 0.2,
                                "power_3_probability": 0.3,
                                "power_4_probability": 0.2,
                                "power_5_probability": 0.2,
                            }
                        ]
                    },
                    "id": "call_1",
                },
                {
                    "name": "submit_orders",
                    "input": {
                        "orders": [
                            {"force_id": "p1_f1", "order_type": "Move",
                             "target_q": 3, "target_r": 3},
                        ]
                    },
                    "id": "call_2",
                },
            ]
        ]
        provider = MockProvider(tool_responses=tool_responses)
        view = {
            "enemy_forces": [{"id": "p2_f1"}],
            "your_forces": [{"id": "p1_f1"}],
        }

        result = extract_beliefs_and_orders(
            "I think p2_f1 is probably power 3",
            view, "p1", provider, method="tool_calling",
        )

        assert result.extraction_success
        assert "p2_f1" in result.beliefs
        assert abs(result.beliefs["p2_f1"].distribution[3] - 0.3) < 0.01
        assert len(result.orders) == 1
        assert result.orders[0]["force_id"] == "p1_f1"
