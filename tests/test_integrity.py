"""Tests for information integrity verification."""

import random

from benchmark.integrity import verify_fog_of_war, verify_prompt_integrity
from benchmark.renderers import render_narrative
from state import apply_deployment, get_player_view, initialize_game, load_config


def _make_game(seed=42):
    game = initialize_game(seed)
    apply_deployment(game, "p1", {"p1_f1": 5, "p1_f2": 4, "p1_f3": 1, "p1_f4": 3, "p1_f5": 2})
    apply_deployment(game, "p2", {"p2_f1": 1, "p2_f2": 5, "p2_f3": 4, "p2_f4": 2, "p2_f5": 3})
    return game


class TestFogOfWarVerification:
    def test_clean_view_has_no_violations(self):
        game = _make_game()
        view = get_player_view(game, "p1")
        violations = verify_fog_of_war(view, game, "p1")
        assert violations == [], f"Unexpected violations: {violations}"

    def test_detects_omitted_own_force(self):
        game = _make_game()
        view = get_player_view(game, "p1")
        # Remove an own force from view
        view["your_forces"] = view["your_forces"][1:]
        violations = verify_fog_of_war(view, game, "p1")
        assert any("OMISSION" in v for v in violations)


class TestPromptIntegrity:
    def test_clean_prompt_has_no_violations(self):
        game = _make_game()
        view = get_player_view(game, "p1")
        config = load_config()
        prompt = render_narrative(view, config)
        violations = verify_prompt_integrity(prompt, view, game, "p1")
        assert violations == [], f"Unexpected violations: {violations}"

    def test_detects_invisible_enemy_in_prompt(self):
        game = _make_game()
        view = get_player_view(game, "p1")
        # At turn 1, p2 forces should be outside visibility
        # Create a prompt that mentions an invisible enemy
        prompt = f"Turn {game.turn}. p1_f1 is at (0,1). Enemy p2_f1 is nearby."
        violations = verify_prompt_integrity(prompt, view, game, "p1")
        # p2_f1 should not be visible at start
        if "p2_f1" not in {f["id"] for f in view.get("enemy_forces", [])}:
            assert any("LEAK" in v and "p2_f1" in v for v in violations)

    def test_detects_missing_own_force(self):
        game = _make_game()
        view = get_player_view(game, "p1")
        # Prompt that doesn't mention p1_f1
        prompt = f"Turn {game.turn}. p1_f2 at (0,2). p1_f3 at (0,3). p1_f4 at (1,1). p1_f5 at (1,2)."
        violations = verify_prompt_integrity(prompt, view, game, "p1")
        assert any("OMISSION" in v and "p1_f1" in v for v in violations)
