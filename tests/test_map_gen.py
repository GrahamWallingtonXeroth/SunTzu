"""Tests for 7x7 hex map generation."""

import pytest
from map_gen import (
    generate_map, get_hex_neighbors, hex_distance,
    is_valid_hex, a_star_path, BOARD_SIZE,
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
        assert m[(0, 0)].terrain == 'Open'
        assert m[(6, 6)].terrain == 'Open'

    def test_has_difficult_terrain(self):
        m = generate_map(seed=42)
        difficult = [h for h in m.values() if h.terrain == 'Difficult']
        assert len(difficult) >= 2  # At least some

    def test_paths_exist_to_contentious(self):
        m = generate_map(seed=42)
        contentious = [pos for pos, h in m.items() if h.terrain == 'Contentious']
        for ch in contentious:
            p1_path = a_star_path((0, 0), ch, m)
            p2_path = a_star_path((6, 6), ch, m)
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
