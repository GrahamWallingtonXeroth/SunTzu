"""Tests for multi-format state renderers."""

import json
import random

from benchmark.renderers import (
    RENDERERS,
    render_ascii_map,
    render_json,
    render_narrative,
    render_rules_reference,
    render_tabular,
)
from state import apply_deployment, get_player_view, initialize_game, load_config


def _make_view(seed=42):
    """Create a game view for testing."""
    game = initialize_game(seed)
    apply_deployment(game, "p1", {"p1_f1": 5, "p1_f2": 4, "p1_f3": 1, "p1_f4": 3, "p1_f5": 2})
    apply_deployment(game, "p2", {"p2_f1": 1, "p2_f2": 5, "p2_f3": 4, "p2_f4": 2, "p2_f5": 3})
    return get_player_view(game, "p1"), game


class TestRulesReference:
    def test_rules_contain_key_concepts(self):
        config = load_config()
        rules = render_rules_reference(config)
        assert "Sovereign" in rules
        assert "Move" in rules
        assert "Charge" in rules
        assert "Scout" in rules
        assert "Fortify" in rules
        assert "Ambush" in rules
        assert "supply" in rules.lower()
        assert "Contentious" in rules
        assert "noose" in rules.lower()

    def test_rules_parameterized_by_config(self):
        config = {"charge_cost": 99, "scout_accuracy": 0.5, "board_size": 7}
        rules = render_rules_reference(config)
        assert "99 Shih" in rules
        assert "50%" in rules


class TestNarrativeRenderer:
    def test_contains_turn_and_shih(self):
        view, _ = _make_view()
        config = load_config()
        text = render_narrative(view, config)
        assert f"turn {view['turn']}" in text.lower() or f"Turn {view['turn']}" in text

    def test_contains_own_forces(self):
        view, _ = _make_view()
        config = load_config()
        text = render_narrative(view, config)
        for f in view["your_forces"]:
            assert f["id"] in text

    def test_contains_own_power_values(self):
        view, _ = _make_view()
        config = load_config()
        text = render_narrative(view, config)
        for f in view["your_forces"]:
            assert str(f["power"]) in text

    def test_contains_contentious_hexes(self):
        view, _ = _make_view()
        config = load_config()
        text = render_narrative(view, config)
        assert "Contentious" in text


class TestTabularRenderer:
    def test_contains_header(self):
        view, _ = _make_view()
        config = load_config()
        text = render_tabular(view, config)
        assert "TURN" in text
        assert "Shih" in text

    def test_contains_force_table(self):
        view, _ = _make_view()
        config = load_config()
        text = render_tabular(view, config)
        assert "YOUR FORCES" in text
        for f in view["your_forces"]:
            assert f["id"] in text

    def test_contains_enemy_section(self):
        view, _ = _make_view()
        config = load_config()
        text = render_tabular(view, config)
        assert "VISIBLE ENEMIES" in text or "ENEMIES" in text


class TestAsciiMapRenderer:
    def test_contains_hex_grid(self):
        view, _ = _make_view()
        config = load_config()
        text = render_ascii_map(view, config)
        assert "q:" in text
        assert "r" in text

    def test_contains_legend(self):
        view, _ = _make_view()
        config = load_config()
        text = render_ascii_map(view, config)
        assert "Legend" in text or "legend" in text

    def test_contains_force_listing(self):
        view, _ = _make_view()
        config = load_config()
        text = render_ascii_map(view, config)
        for f in view["your_forces"]:
            assert f["id"] in text


class TestJsonRenderer:
    def test_is_valid_json(self):
        view, _ = _make_view()
        config = load_config()
        text = render_json(view, config)
        data = json.loads(text)
        assert "turn" in data
        assert "your_forces" in data

    def test_roundtrip_preserves_data(self):
        view, _ = _make_view()
        config = load_config()
        text = render_json(view, config)
        data = json.loads(text)
        assert data["turn"] == view["turn"]
        assert len(data["your_forces"]) == len(view["your_forces"])


class TestAllFormatsContainSameInfo:
    """Critical: all formats must expose the same information content."""

    def test_all_formats_contain_own_force_ids(self):
        view, _ = _make_view()
        config = load_config()
        for format_name, renderer in RENDERERS.items():
            text = renderer(view, config)
            for f in view["your_forces"]:
                assert f["id"] in text, (
                    f"Format '{format_name}' missing own force {f['id']}"
                )

    def test_all_formats_contain_turn(self):
        view, _ = _make_view()
        config = load_config()
        turn_str = str(view["turn"])
        for format_name, renderer in RENDERERS.items():
            text = renderer(view, config)
            assert turn_str in text, (
                f"Format '{format_name}' missing turn number {turn_str}"
            )


class TestHistoryRendering:
    def test_history_included_when_provided(self):
        view, _ = _make_view()
        config = load_config()
        history = [
            {"turn": 1, "type": "combat", "attacker": "p1_f1", "defender": "p2_f1",
             "attacker_power": 5, "defender_power": 2, "result": "attacker_wins"},
        ]
        text = render_narrative(view, config, history=history)
        assert "Combat" in text or "combat" in text

    def test_no_history_when_none(self):
        view, _ = _make_view()
        config = load_config()
        text = render_narrative(view, config, history=None)
        assert "RECENT EVENTS" not in text
