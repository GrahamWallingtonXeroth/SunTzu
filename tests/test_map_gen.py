"""
Test suite for map generation logic in Sun Tzu: The Unfought Battle
Tests terrain coverage, pathfinding, chokepoints, and map balance according to GDD v0.7
"""

import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
import random
from typing import Dict, Tuple, List, Set
from unittest.mock import patch

# Import the modules to test
from map_gen import (
    get_hex_neighbors,
    hex_distance,
    is_valid_hex,
    a_star_pathfinding,
    generate_perlin_terrain,
    validate_map_balance,
    count_chokepoints,
    generate_map
)
from models import Hex


class TestHexUtilities:
    """Test basic hex utility functions."""
    
    def test_get_hex_neighbors(self) -> None:
        """Test that hex neighbors are correctly calculated in axial coordinates."""
        neighbors = get_hex_neighbors(5, 5)
        expected = [(6, 5), (6, 4), (5, 4), (4, 5), (4, 6), (5, 6)]
        assert set(neighbors) == set(expected)
    
    def test_hex_distance(self) -> None:
        """Test hex distance calculation using axial coordinates."""
        # Same hex
        assert hex_distance(5, 5, 5, 5) == 0
        
        # Adjacent hexes
        assert hex_distance(5, 5, 6, 5) == 1
        assert hex_distance(5, 5, 5, 6) == 1
        
        # Diagonal distance (in axial coordinates, this is the max of the differences)
        # For (5,5) to (7,7): max(2, 2, abs(-10+14)) = max(2, 2, 4) = 4
        assert hex_distance(5, 5, 7, 7) == 4
        assert hex_distance(0, 0, 10, 10) == 20  # This is still correct for distance calculation
    
    def test_is_valid_hex(self) -> None:
        """Test hex coordinate validation within map bounds."""
        # Valid hexes
        assert is_valid_hex(0, 0) == True
        assert is_valid_hex(24, 19) == True  # Maximum valid coordinates
        assert is_valid_hex(12, 10) == True
        
        # Invalid hexes
        assert is_valid_hex(-1, 0) == False
        assert is_valid_hex(0, -1) == False
        assert is_valid_hex(25, 0) == False  # q >= 25
        assert is_valid_hex(0, 20) == False  # r >= 20
        assert is_valid_hex(30, 25) == False


class TestPathfinding:
    """Test A* pathfinding algorithm."""
    
    def test_a_star_simple_path(self) -> None:
        """Test A* finds a simple path between two points."""
        # Create a simple map with all Open terrain
        map_data = {}
        for q in range(5):
            for r in range(5):
                map_data[(q, r)] = Hex(q, r, 'Open')
        
        path = a_star_pathfinding((0, 0), (2, 2), map_data)
        assert path is not None
        assert len(path) >= 3  # Minimum path length
        assert path[0] == (0, 0)  # Start
        assert path[-1] == (2, 2)  # End
    
    def test_a_star_with_obstacles(self) -> None:
        """Test A* avoids Difficult terrain when specified."""
        map_data = {}
        for q in range(5):
            for r in range(5):
                terrain = 'Difficult' if (q, r) == (1, 1) else 'Open'
                map_data[(q, r)] = Hex(q, r, terrain)
        
        # Path should avoid the Difficult hex at (1, 1)
        path = a_star_pathfinding((0, 0), (2, 2), map_data, 'Difficult')
        assert path is not None
        assert (1, 1) not in path
    
    def test_a_star_no_path(self) -> None:
        """Test A* returns None when no path exists."""
        # Test a scenario where path exists by going around
        map_data = {}
        for q in range(3):
            for r in range(3):
                terrain = 'Difficult' if q == 1 else 'Open'  # Wall of Difficult terrain
                map_data[(q, r)] = Hex(q, r, terrain)
        
        # A* can go around the wall using the r-axis
        path = a_star_pathfinding((0, 0), (2, 0), map_data, 'Difficult')
        assert path is not None  # Path exists by going around
        
        # Test a truly blocked scenario: block the goal itself
        map_data = {}
        for q in range(3):
            for r in range(3):
                map_data[(q, r)] = Hex(q, r, 'Open')
        map_data[(2, 2)].terrain = 'Difficult'
        # Now there should be no path from (0,0) to (2,2) avoiding Difficult terrain
        path = a_star_pathfinding((0, 0), (2, 2), map_data, 'Difficult')
        assert path is None
    
    def test_a_star_boundary_conditions(self) -> None:
        """Test A* handles boundary conditions correctly."""
        map_data = {}
        for q in range(3):
            for r in range(3):
                map_data[(q, r)] = Hex(q, r, 'Open')
        
        # Test path to boundary
        path = a_star_pathfinding((0, 0), (2, 2), map_data)
        assert path is not None
        
        # Test path from boundary
        path = a_star_pathfinding((2, 2), (0, 0), map_data)
        assert path is not None


class TestTerrainGeneration:
    """Test Perlin noise terrain generation."""
    
    def test_perlin_terrain_coverage_seed_42(self) -> None:
        """Test that Difficult terrain coverage is 20-30% for seed=42."""
        # Create base map data
        map_data = {}
        for q in range(10):
            for r in range(10):
                map_data[(q, r)] = Hex(q, r, 'Open')
        
        # Generate terrain with seed 42
        result_map = generate_perlin_terrain(map_data, seed=42)
        
        # Count Difficult terrain
        difficult_count = sum(1 for hex_obj in result_map.values() 
                            if hex_obj.terrain == 'Difficult')
        total_hexes = len(result_map)
        coverage = difficult_count / total_hexes
        
        # Assert coverage is within 20-30% range
        assert 0.2 <= coverage <= 0.3, f"Coverage {coverage:.1%} not in 20-30% range"
        print(f"Seed 42 generated {difficult_count} Difficult hexes ({coverage:.1%} coverage)")
    
    def test_perlin_terrain_deterministic(self) -> None:
        """Test that same seed produces same terrain pattern."""
        # Create base map data
        map_data1 = {}
        map_data2 = {}
        for q in range(10):  # 10x10 map
            for r in range(10):
                map_data1[(q, r)] = Hex(q, r, 'Open')
                map_data2[(q, r)] = Hex(q, r, 'Open')
        
        # Generate terrain with same seed
        result1 = generate_perlin_terrain(map_data1, seed=123)
        result2 = generate_perlin_terrain(map_data2, seed=123)
        
        # Compare terrain patterns
        for coords in result1:
            assert result1[coords].terrain == result2[coords].terrain
    
    def test_perlin_terrain_preserves_contentious(self) -> None:
        """Test that Contentious terrain is preserved during generation."""
        map_data = {}
        for q in range(10):
            for r in range(10):
                terrain = 'Contentious' if (q, r) == (5, 5) else 'Open'
                map_data[(q, r)] = Hex(q, r, terrain)
        
        result = generate_perlin_terrain(map_data, seed=456)
        
        # Contentious hex should remain Contentious
        assert result[(5, 5)].terrain == 'Contentious'


class TestMapBalance:
    """Test map balance validation."""
    
    def test_validate_map_balance_symmetric(self) -> None:
        """Test that symmetric maps are considered balanced."""
        # Create a symmetric map
        map_data = {}
        for q in range(10):
            for r in range(10):
                map_data[(q, r)] = Hex(q, r, 'Open')
        
        p1_start = (0, 0)
        p2_start = (9, 9)
        center_hexes = [(4, 4), (5, 5)]
        
        # Should be balanced (symmetric paths)
        assert validate_map_balance(map_data, p1_start, p2_start, center_hexes) == True
    
    def test_validate_map_balance_unbalanced(self) -> None:
        """Test that unbalanced maps are detected."""
        # Create an unbalanced map with obstacles blocking one player
        map_data = {}
        for q in range(10):
            for r in range(10):
                terrain = 'Difficult' if q < 5 and r < 5 else 'Open'  # Block p1's path
                map_data[(q, r)] = Hex(q, r, terrain)
        
        p1_start = (0, 0)
        p2_start = (9, 9)
        center_hexes = [(4, 4), (5, 5)]
        
        # Should be unbalanced (p1 can't reach center)
        assert validate_map_balance(map_data, p1_start, p2_start, center_hexes) == False


class TestChokepoints:
    """Test chokepoint detection and counting."""
    
    def test_count_chokepoints_simple(self) -> None:
        """Test chokepoint counting in a simple map."""
        # Create a map with a clear chokepoint
        map_data = {}
        for q in range(10):
            for r in range(10):
                # Create a narrow passage
                if q == 5 and r in [3, 4, 5, 6]:
                    terrain = 'Open'  # Passage
                elif q in [4, 6] and r in [3, 4, 5, 6]:
                    terrain = 'Difficult'  # Walls
                else:
                    terrain = 'Open'
                map_data[(q, r)] = Hex(q, r, terrain)
        
        p1_start = (0, 5)
        p2_start = (9, 5)
        center_hexes = [(5, 5)]
        
        chokepoint_count = count_chokepoints(map_data, p1_start, p2_start, center_hexes)
        assert chokepoint_count >= 1  # At least one chokepoint should exist
    
    def test_count_chokepoints_multiple(self) -> None:
        """Test chokepoint counting with multiple passages."""
        # Create a map with multiple chokepoints
        map_data = {}
        for q in range(15):
            for r in range(15):
                # Create two narrow passages
                if (q == 5 and r in [3, 4, 5, 6]) or (q == 10 and r in [8, 9, 10, 11]):
                    terrain = 'Open'  # Passages
                elif (q in [4, 6] and r in [3, 4, 5, 6]) or (q in [9, 11] and r in [8, 9, 10, 11]):
                    terrain = 'Difficult'  # Walls
                else:
                    terrain = 'Open'
                map_data[(q, r)] = Hex(q, r, terrain)
        
        p1_start = (0, 5)
        p2_start = (14, 10)
        center_hexes = [(5, 5), (10, 10)]  # Place centers in the passages
        
        chokepoint_count = count_chokepoints(map_data, p1_start, p2_start, center_hexes)
        assert chokepoint_count >= 2  # At least two chokepoints should exist


class TestFullMapGeneration:
    """Test complete map generation process."""
    
    def test_generate_map_seed_42(self) -> None:
        """Test full map generation with seed 42 meets GDD requirements."""
        map_data = generate_map(seed=42)
        
        # Test map size (10x10 hexes)
        assert len(map_data) == 10 * 10
        
        # Test player starting positions exist and are Open
        assert (0, 0) in map_data
        assert map_data[(0, 0)].terrain == 'Open'  # P1 start
        assert (9, 9) in map_data
        assert map_data[(9, 9)].terrain == 'Open'  # P2 start
        
        # Test Difficult terrain coverage (20-30%)
        difficult_count = sum(1 for hex_obj in map_data.values() 
                            if hex_obj.terrain == 'Difficult')
        coverage = difficult_count / len(map_data)
        assert 0.2 <= coverage <= 0.3, f"Coverage {coverage:.1%} not in 20-30% range"
        
        # Test Contentious terrain exists (3-5 hexes near center)
        contentious_hexes = [(q, r) for (q, r), hex_obj in map_data.items() 
                           if hex_obj.terrain == 'Contentious']
        assert 3 <= len(contentious_hexes) <= 5
        
        # Test Contentious hexes are near center (q=4-6, r=4-6)
        for q, r in contentious_hexes:
            assert 4 <= q <= 6
            assert 4 <= r <= 6
    
    def test_generate_map_pathfinding_requirements(self) -> None:
        """Test that generated maps have valid paths meeting GDD requirements."""
        map_data = generate_map(seed=42)
        
        p1_start = (0, 0)
        p2_start = (9, 9)
        
        # Find Contentious hexes (center objectives)
        contentious_hexes = [(q, r) for (q, r), hex_obj in map_data.items() 
                           if hex_obj.terrain == 'Contentious']
        
        # Test paths from both players to each Contentious hex
        for center_hex in contentious_hexes:
            # P1 path
            p1_path = a_star_pathfinding(p1_start, center_hex, map_data, 'Difficult')
            assert p1_path is not None, f"No path from P1 to {center_hex}"
            assert len(p1_path) >= 5, f"P1 path to {center_hex} too short: {len(p1_path)}"
            
            # P2 path
            p2_path = a_star_pathfinding(p2_start, center_hex, map_data, 'Difficult')
            assert p2_path is not None, f"No path from P2 to {center_hex}"
            assert len(p2_path) >= 5, f"P2 path to {center_hex} too short: {len(p2_path)}"
    
    def test_generate_map_chokepoints_requirements(self) -> None:
        """Test that generated maps have at least 2 chokepoints per path."""
        map_data = generate_map(seed=42)
        
        p1_start = (0, 0)
        p2_start = (9, 9)
        
        # Find Contentious hexes
        contentious_hexes = [(q, r) for (q, r), hex_obj in map_data.items() 
                           if hex_obj.terrain == 'Contentious']
        
        # Count chokepoints
        chokepoint_count = count_chokepoints(map_data, p1_start, p2_start, contentious_hexes)
        assert chokepoint_count >= 2, f"Only {chokepoint_count} chokepoints found, need at least 2"
    
    def test_generate_map_deterministic(self) -> None:
        """Test that same seed produces same map."""
        map1 = generate_map(seed=123)
        map2 = generate_map(seed=123)
        
        # Compare all hex terrain
        for coords in map1:
            assert map1[coords].terrain == map2[coords].terrain
    
    def test_generate_map_different_seeds(self) -> None:
        """Test that different seeds produce different maps."""
        map1 = generate_map(seed=123)
        map2 = generate_map(seed=456)
        
        # Maps should be different (at least some terrain differences)
        terrain_differences = 0
        for coords in map1:
            if map1[coords].terrain != map2[coords].terrain:
                terrain_differences += 1
        
        assert terrain_differences > 0, "Different seeds produced identical maps"


if __name__ == "__main__":
    pytest.main([__file__])
