"""Tests for 7x7 hex map generation — v4 with shrinking board support."""

import pytest
from map_gen import (
    generate_map, get_hex_neighbors, hex_distance,
    is_valid_hex, a_star_path, distance_from_center,
    max_distance_for_shrink_stage, is_scorched,
    BOARD_SIZE, CENTER_Q, CENTER_R,
)
from models import Hex


class TestHexUtilities:
    def test_neighbors_count(self):
        neighbors = get_hex_neighbors(3, 3)
        assert len(neighbors) == 6

    def test_distance_same_hex(self):
        assert hex_distance(3, 3, 3, 3) == 0

    def test_distance_adjacent(self):
        assert hex_distance(0, 0, 1, 0) == 1
        assert hex_distance(0, 0, 0, 1) == 1

    def test_distance_across_board(self):
        assert hex_distance(0, 0, 6, 6) == 12

    def test_valid_hex_corners(self):
        assert is_valid_hex(0, 0) is True
        assert is_valid_hex(6, 6) is True

    def test_invalid_hex_out_of_bounds(self):
        assert is_valid_hex(7, 0) is False
        assert is_valid_hex(-1, 0) is False
        assert is_valid_hex(0, 7) is False


class TestCenterDistance:
    def test_center_is_distance_0(self):
        assert distance_from_center(CENTER_Q, CENTER_R) == 0

    def test_corner_distance(self):
        d = distance_from_center(0, 0)
        assert d > 0

    def test_adjacent_to_center(self):
        assert distance_from_center(4, 3) == 1
        assert distance_from_center(3, 4) == 1


class TestShrinkStages:
    def test_stage_0_no_limit(self):
        assert max_distance_for_shrink_stage(0) == BOARD_SIZE

    def test_stage_1_limits(self):
        assert max_distance_for_shrink_stage(1) == 5

    def test_stage_2_limits(self):
        assert max_distance_for_shrink_stage(2) == 4

    def test_stage_3_limits(self):
        assert max_distance_for_shrink_stage(3) == 3

    def test_stage_4_limits(self):
        assert max_distance_for_shrink_stage(4) == 2

    def test_stage_5_plus(self):
        assert max_distance_for_shrink_stage(5) == 1
        assert max_distance_for_shrink_stage(6) == 1

    def test_is_scorched_stage_0(self):
        assert is_scorched(0, 0, 0) is False
        assert is_scorched(6, 6, 0) is False

    def test_is_scorched_stage_1(self):
        # (0,0) is distance 6 from center (3,3), stage 1 allows max 4
        assert is_scorched(0, 0, 1) is True
        # (3,3) is center, never scorched
        assert is_scorched(3, 3, 1) is False

    def test_is_scorched_stage_2(self):
        # Center adjacent should be fine
        assert is_scorched(3, 4, 2) is False
        # Far corners should be scorched
        assert is_scorched(0, 0, 2) is True


class TestMapGeneration:
    def test_map_size(self):
        m = generate_map(seed=42)
        assert len(m) == 49  # 7x7

    def test_has_3_contentious(self):
        m = generate_map(seed=42)
        contentious = [h for h in m.values() if h.terrain == 'Contentious']
        assert len(contentious) == 3

    def test_contentious_near_center(self):
        m = generate_map(seed=42)
        for pos, h in m.items():
            if h.terrain == 'Contentious':
                q, r = pos
                assert 2 <= q <= 4
                assert 2 <= r <= 4

    def test_starting_positions_are_open(self):
        m = generate_map(seed=42)
        # v4: starting cluster centers at (1,2) and (5,4)
        p1_positions = [(0, 2), (1, 1), (0, 3), (1, 2), (1, 3)]
        p2_positions = [(6, 4), (5, 5), (6, 3), (5, 4), (5, 3)]
        for pos in p1_positions + p2_positions:
            assert m[pos].terrain == 'Open', f"Starting position {pos} should be Open"

    def test_has_difficult_terrain(self):
        m = generate_map(seed=42)
        difficult = [h for h in m.values() if h.terrain == 'Difficult']
        assert len(difficult) >= 2

    def test_paths_exist_to_contentious(self):
        m = generate_map(seed=42)
        contentious = [pos for pos, h in m.items() if h.terrain == 'Contentious']
        for ch in contentious:
            p1_path = a_star_path((1, 2), ch, m)
            p2_path = a_star_path((5, 4), ch, m)
            assert p1_path is not None
            assert p2_path is not None

    def test_deterministic(self):
        m1 = generate_map(seed=123)
        m2 = generate_map(seed=123)
        for pos in m1:
            assert m1[pos].terrain == m2[pos].terrain

    def test_different_seeds_different_maps(self):
        m1 = generate_map(seed=1)
        m2 = generate_map(seed=999)
        diffs = sum(1 for pos in m1 if m1[pos].terrain != m2[pos].terrain)
        assert diffs > 0

    def test_a_star_avoids_scorched(self):
        m = generate_map(seed=42)
        # Scorch a hex and verify A* avoids it
        m[(3, 3)].terrain = 'Scorched'
        path = a_star_path((2, 3), (4, 3), m)
        if path:
            assert (3, 3) not in path
