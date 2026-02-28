"""Tests for comprehension probe generation and validation."""

from benchmark.comprehension import (
    Probe,
    format_probes_as_prompt,
    generate_probes,
    parse_probe_responses,
    score_comprehension,
)
from state import apply_deployment, get_player_view, initialize_game, load_config


def _make_game_and_view(seed=42):
    game = initialize_game(seed)
    apply_deployment(game, "p1", {"p1_f1": 5, "p1_f2": 4, "p1_f3": 1, "p1_f4": 3, "p1_f5": 2})
    apply_deployment(game, "p2", {"p2_f1": 1, "p2_f2": 5, "p2_f3": 4, "p2_f4": 2, "p2_f5": 3})
    return game, get_player_view(game, "p1")


class TestProbeValidation:
    def test_numeric_match(self):
        p = Probe("How many?", "5", "factual", "basic")
        assert p.validate("There are 5 forces")
        assert p.validate("5")
        assert not p.validate("There are 3 forces")

    def test_yes_no_match(self):
        p_yes = Probe("Can it?", "Yes", "rule", "derived")
        assert p_yes.validate("Yes")
        assert p_yes.validate("yes, it can")
        assert p_yes.validate("True")

        p_no = Probe("Can it?", "No", "rule", "derived")
        assert p_no.validate("No")
        assert p_no.validate("no, it cannot")

    def test_exact_match(self):
        p = Probe("What terrain?", "Contentious", "terrain", "basic")
        assert p.validate("Contentious")
        assert p.validate("The terrain is Contentious")
        assert not p.validate("Open")


class TestProbeGeneration:
    def test_generates_probes(self):
        game, view = _make_game_and_view()
        config = load_config()
        probes = generate_probes(view, game, "p1", config, n_probes=5)
        assert len(probes) <= 5
        assert len(probes) > 0

    def test_covers_categories(self):
        game, view = _make_game_and_view()
        config = load_config()
        probes = generate_probes(view, game, "p1", config, n_probes=10)
        categories = {p.category for p in probes}
        assert "factual" in categories
        # At least factual probes should always be present

    def test_probes_have_correct_answers(self):
        game, view = _make_game_and_view()
        config = load_config()
        probes = generate_probes(view, game, "p1", config, n_probes=5)
        # Force count probe should have correct answer
        for p in probes:
            if "alive" in p.question.lower() and "your" in p.question.lower():
                expected = str(len(view["your_forces"]))
                assert p.expected_answer == expected
            if "shih" in p.question.lower() and "your" in p.question.lower():
                expected = str(view["your_shih"])
                assert p.expected_answer == expected


class TestScoring:
    def test_perfect_score(self):
        probes = [
            Probe("Q1?", "5", "factual", "basic"),
            Probe("Q2?", "3", "factual", "basic"),
        ]
        responses = ["5", "3"]
        assert score_comprehension(probes, responses) == 1.0

    def test_zero_score(self):
        probes = [
            Probe("Q1?", "5", "factual", "basic"),
            Probe("Q2?", "3", "factual", "basic"),
        ]
        responses = ["wrong", "bad"]
        assert score_comprehension(probes, responses) == 0.0

    def test_partial_score(self):
        probes = [
            Probe("Q1?", "5", "factual", "basic"),
            Probe("Q2?", "3", "factual", "basic"),
        ]
        responses = ["5", "wrong"]
        assert score_comprehension(probes, responses) == 0.5


class TestResponseParsing:
    def test_numbered_responses(self):
        text = "1. 5\n2. 3\n3. Contentious"
        responses = parse_probe_responses(text, 3)
        assert responses == ["5", "3", "Contentious"]

    def test_parenthetical_numbering(self):
        text = "1) Five forces\n2) 6 Shih"
        responses = parse_probe_responses(text, 2)
        assert "Five forces" in responses[0]
        assert "6 Shih" in responses[1]

    def test_pads_missing_responses(self):
        text = "1. yes"
        responses = parse_probe_responses(text, 3)
        assert len(responses) == 3
        assert responses[0] == "yes"
        assert responses[1] == ""


class TestFormatProbesAsPrompt:
    def test_formats_questions(self):
        probes = [
            Probe("How many?", "5", "factual", "basic"),
            Probe("What terrain?", "Open", "terrain", "basic"),
        ]
        prompt = format_probes_as_prompt(probes)
        assert "1." in prompt
        assert "2." in prompt
        assert "How many?" in prompt
