"""
Map generation module for "Sun Tzu: The Unfought Battle"
Implements procedural hex map generation with axial coordinates.
"""

import random
import numpy as np
from typing import Dict, Tuple, List, Set, Optional
from dataclasses import asdict
from noise import pnoise2
from models import Hex


def get_hex_neighbors(q: int, r: int) -> List[Tuple[int, int]]:
    """
    Get the 6 neighboring hex coordinates in axial system.
    
    Args:
        q: Axial coordinate q
        r: Axial coordinate r
        
    Returns:
        List of (q, r) coordinates for neighboring hexes
    """
    # 6 directions: (1,0), (1,-1), (0,-1), (-1,0), (-1,1), (0,1)
    directions = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
    return [(q + dq, r + dr) for dq, dr in directions]


def hex_distance(q1: int, r1: int, q2: int, r2: int) -> int:
    """
    Calculate distance between two hexes using axial coordinates.
    
    Args:
        q1, r1: Coordinates of first hex
        q2, r2: Coordinates of second hex
        
    Returns:
        Distance between hexes
    """
    return max(abs(q1 - q2), abs(r1 - r2), abs(-(q1 + r1) + (q2 + r2)))


def is_valid_hex(q: int, r: int, max_q: int = 25, max_r: int = 20) -> bool:
    """
    Check if hex coordinates are within valid bounds.
    
    Args:
        q, r: Hex coordinates
        max_q: Maximum q coordinate (exclusive)
        max_r: Maximum r coordinate (exclusive)
        
    Returns:
        True if coordinates are valid
    """
    return 0 <= q < max_q and 0 <= r < max_r


def a_star_pathfinding(
    start: Tuple[int, int], 
    goal: Tuple[int, int], 
    map_data: Dict[Tuple[int, int], Hex],
    avoid_terrain: Optional[str] = None
) -> Optional[List[Tuple[int, int]]]:
    """
    A* pathfinding algorithm for hex grid.
    
    Args:
        start: Starting hex coordinates (q, r)
        goal: Goal hex coordinates (q, r)
        map_data: Current map data
        avoid_terrain: Terrain type to avoid (e.g., 'Difficult')
        
    Returns:
        List of hex coordinates forming path, or None if no path found
    """
    open_set = {start}
    came_from = {}
    g_score = {start: 0}
    f_score = {start: hex_distance(start[0], start[1], goal[0], goal[1])}
    
    while open_set:
        current = min(open_set, key=lambda x: f_score.get(x, float('inf')))
        
        if current == goal:
            # Reconstruct path
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            path.reverse()
            return path
        
        open_set.remove(current)
        
        for neighbor in get_hex_neighbors(current[0], current[1]):
            if not is_valid_hex(neighbor[0], neighbor[1]):
                continue
                
            # Skip if neighbor has terrain to avoid
            if (avoid_terrain and neighbor in map_data and 
                map_data[neighbor].terrain == avoid_terrain):
                continue
                
            tentative_g_score = g_score[current] + 1
            
            if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g_score
                f_score[neighbor] = tentative_g_score + hex_distance(
                    neighbor[0], neighbor[1], goal[0], goal[1]
                )
                open_set.add(neighbor)
    
    return None


def generate_perlin_terrain(
    map_data: Dict[Tuple[int, int], Hex], 
    seed: int,
    target_coverage: float = 0.25,
    frequency: float = 8.0,
    max_attempts: int = 10
) -> Dict[Tuple[int, int], Hex]:
    """
    Apply Perlin noise to generate Difficult Ground terrain with target coverage.
    
    Uses adaptive threshold adjustment to achieve 20-30% Difficult terrain coverage,
    creating ridges and chokepoints for strategic gameplay.
    
    Args:
        map_data: Current map data
        seed: Random seed for noise generation
        target_coverage: Target percentage of Difficult terrain (0.2-0.3)
        frequency: Frequency of Perlin noise (lower = more clustered)
        max_attempts: Maximum attempts to adjust threshold
        
    Returns:
        Updated map data with Difficult Ground terrain
    """
    # Set random seed for noise
    random.seed(seed)
    
    # Calculate target number of Difficult hexes
    total_hexes = len(map_data)
    target_difficult = int(total_hexes * target_coverage)
    
    # Try different thresholds to achieve target coverage
    for attempt in range(max_attempts):
        # Start with threshold that creates ridges (using abs() for clustering)
        # Use more conservative threshold range for better control
        threshold = 0.45 - (attempt * 0.03)  # Decrease threshold each attempt
        
        # Reset all hexes to Open (except Contentious)
        for hex_obj in map_data.values():
            if hex_obj.terrain != 'Contentious':
                hex_obj.terrain = 'Open'
        
        # Apply Perlin noise with current threshold
        for q in range(25):
            for r in range(20):
                if (q, r) not in map_data:
                    continue
                    
                # Skip if already Contentious Ground
                if map_data[(q, r)].terrain == 'Contentious':
                    continue
                
                # Generate Perlin noise value (range: [-1, 1])
                noise_val = pnoise2(q / frequency, r / frequency, octaves=2, 
                                  persistence=0.6, lacunarity=2.5, 
                                  repeatx=25, repeaty=20, base=seed)
                
                # Use abs() to create ridges and clusters
                # Place Difficult Ground where noise magnitude exceeds threshold
                if abs(noise_val) > threshold:
                    map_data[(q, r)].terrain = 'Difficult'
        
        # Check if we achieved target coverage
        difficult_count = sum(1 for hex_obj in map_data.values() 
                            if hex_obj.terrain == 'Difficult')
        current_coverage = difficult_count / total_hexes
        
        # Accept if within 20-30% range
        if 0.2 <= current_coverage <= 0.3:
            print(f"Perlin terrain generated: {difficult_count} Difficult hexes "
                  f"({current_coverage:.1%} coverage) with threshold {threshold:.2f}")
            return map_data
    
    # If we couldn't achieve target coverage, return with current result
    difficult_count = sum(1 for hex_obj in map_data.values() 
                         if hex_obj.terrain == 'Difficult')
    current_coverage = difficult_count / total_hexes
    print(f"Warning: Could not achieve target coverage. "
          f"Generated {difficult_count} Difficult hexes ({current_coverage:.1%} coverage)")
    
    return map_data


def validate_map_balance(
    map_data: Dict[Tuple[int, int], Hex],
    p1_start: Tuple[int, int],
    p2_start: Tuple[int, int],
    center_hexes: List[Tuple[int, int]]
) -> bool:
    """
    Validate that the map is balanced for both players.
    
    Args:
        map_data: Current map data
        p1_start: Player 1 starting position
        p2_start: Player 2 starting position
        center_hexes: List of center hexes to check access to
        
    Returns:
        True if map is balanced, False otherwise
    """
    # Check path lengths to center for both players
    p1_paths = []
    p2_paths = []
    
    for center_hex in center_hexes:
        p1_path = a_star_pathfinding(p1_start, center_hex, map_data, 'Difficult')
        p2_path = a_star_pathfinding(p2_start, center_hex, map_data, 'Difficult')
        
        if p1_path:
            p1_paths.append(len(p1_path))
        if p2_path:
            p2_paths.append(len(p2_path))
    
    if not p1_paths or not p2_paths:
        return False
    
    # Check if path lengths are within ±2 hexes
    avg_p1_length = sum(p1_paths) / len(p1_paths)
    avg_p2_length = sum(p2_paths) / len(p2_paths)
    
    return abs(avg_p1_length - avg_p2_length) <= 2


def count_chokepoints(
    map_data: Dict[Tuple[int, int], Hex],
    p1_start: Tuple[int, int],
    p2_start: Tuple[int, int],
    center_hexes: List[Tuple[int, int]]
) -> int:
    """
    Count the number of chokepoints (narrow passages) in the map.
    
    Args:
        map_data: Current map data
        p1_start: Player 1 starting position
        p2_start: Player 2 starting position
        center_hexes: List of center hexes
        
    Returns:
        Number of chokepoints found
    """
    chokepoints = set()
    
    # Check paths from both players to center
    for center_hex in center_hexes:
        for start_pos in [p1_start, p2_start]:
            path = a_star_pathfinding(start_pos, center_hex, map_data, 'Difficult')
            if path:
                # Look for narrow passages (hexes with limited adjacent open terrain)
                for q, r in path:
                    open_neighbors = 0
                    for nq, nr in get_hex_neighbors(q, r):
                        if (is_valid_hex(nq, nr) and 
                            (nq, nr) in map_data and 
                            map_data[(nq, nr)].terrain == 'Open'):
                            open_neighbors += 1
                    
                    # Consider it a chokepoint if it has 2 or fewer open neighbors
                    if open_neighbors <= 2:
                        chokepoints.add((q, r))
    
    return len(chokepoints)


def generate_map(seed: int) -> Dict[Tuple[int, int], Hex]:
    """
    Generate a procedural hex map for "Sun Tzu: The Unfought Battle".
    
    Args:
        seed: Random seed for reproducible generation
        
    Returns:
        Dictionary mapping (q, r) coordinates to Hex objects
    """
    random.seed(seed)
    
    # Initialize map with all Open Ground
    map_data = {}
    for q in range(25):
        for r in range(20):
            map_data[(q, r)] = Hex(q=q, r=r, terrain='Open')
    
    # Step 1: Place starting positions
    p1_start = (0, 0)
    p2_start = (24, 19)
    
    map_data[p1_start].terrain = 'Open'  # Player 1 starting position
    map_data[p2_start].terrain = 'Open'  # Player 2 starting position
    
    # Step 2: Generate Contentious Ground in center cluster
    center_q_range = range(10, 16)  # q=10-15
    center_r_range = range(8, 13)   # r=8-12
    
    center_hexes = []
    num_contentious = random.randint(3, 5)
    
    for _ in range(num_contentious):
        attempts = 0
        while attempts < 50:
            q = random.choice(center_q_range)
            r = random.choice(center_r_range)
            
            if (q, r) in map_data and map_data[(q, r)].terrain == 'Open':
                map_data[(q, r)].terrain = 'Contentious'
                center_hexes.append((q, r))
                break
            attempts += 1
    
    # Step 3: Create paths using A* pathfinding
    for center_hex in center_hexes:
        # Path from Player 1 to center
        p1_path = a_star_pathfinding(p1_start, center_hex, map_data)
        if p1_path and len(p1_path) >= 5:
            for q, r in p1_path:
                if map_data[(q, r)].terrain == 'Open':
                    map_data[(q, r)].terrain = 'Open'  # Ensure path is Open
        
        # Path from Player 2 to center
        p2_path = a_star_pathfinding(p2_start, center_hex, map_data)
        if p2_path and len(p2_path) >= 5:
            for q, r in p2_path:
                if map_data[(q, r)].terrain == 'Open':
                    map_data[(q, r)].terrain = 'Open'  # Ensure path is Open
    
    # Step 4: Add barriers using Perlin noise
    map_data = generate_perlin_terrain(map_data, seed, target_coverage=0.25, frequency=8.0)
    
    # Step 5: Validate balance and regenerate if necessary
    max_attempts = 10
    for attempt in range(max_attempts):
        # Check if map is balanced
        if validate_map_balance(map_data, p1_start, p2_start, center_hexes):
            # Check for minimum chokepoints
            chokepoints = count_chokepoints(map_data, p1_start, p2_start, center_hexes)
            if chokepoints >= 2:
                # Check Difficult Ground coverage (20-30%)
                difficult_count = sum(1 for hex_obj in map_data.values() 
                                    if hex_obj.terrain == 'Difficult')
                coverage = difficult_count / len(map_data)
                
                if 0.2 <= coverage <= 0.3:
                    return map_data
        
        # If not balanced, regenerate with new seed
        if attempt < max_attempts - 1:
            new_seed = seed + attempt + 1
            random.seed(new_seed)
            
            # Reset map and try again
            map_data = {}
            for q in range(25):
                for r in range(20):
                    map_data[(q, r)] = Hex(q=q, r=r, terrain='Open')
            
            # Reapply all steps with new seed
            map_data[p1_start].terrain = 'Open'
            map_data[p2_start].terrain = 'Open'
            
            # Regenerate center hexes
            center_hexes = []
            for _ in range(num_contentious):
                attempts = 0
                while attempts < 50:
                    q = random.choice(center_q_range)
                    r = random.choice(center_r_range)
                    
                    if (q, r) in map_data and map_data[(q, r)].terrain == 'Open':
                        map_data[(q, r)].terrain = 'Contentious'
                        center_hexes.append((q, r))
                        break
                    attempts += 1
            
            # Regenerate paths
            for center_hex in center_hexes:
                p1_path = a_star_pathfinding(p1_start, center_hex, map_data)
                if p1_path and len(p1_path) >= 5:
                    for q, r in p1_path:
                        if map_data[(q, r)].terrain == 'Open':
                            map_data[(q, r)].terrain = 'Open'
                
                p2_path = a_star_pathfinding(p2_start, center_hex, map_data)
                if p2_path and len(p2_path) >= 5:
                    for q, r in p2_path:
                        if map_data[(q, r)].terrain == 'Open':
                            map_data[(q, r)].terrain = 'Open'
            
            # Regenerate Perlin terrain
            map_data = generate_perlin_terrain(map_data, new_seed, target_coverage=0.25, frequency=8.0)
    
    # If we couldn't generate a balanced map, return the last attempt
    return map_data


def print_map_stats(map_data: Dict[Tuple[int, int], Hex]) -> None:
    """
    Print detailed statistics about the generated map.
    
    Args:
        map_data: Generated map data
    """
    terrain_counts = {}
    for hex_obj in map_data.values():
        terrain_counts[hex_obj.terrain] = terrain_counts.get(hex_obj.terrain, 0) + 1
    
    print("\n" + "="*50)
    print("MAP STATISTICS")
    print("="*50)
    print(f"Total hexes: {len(map_data)}")
    print(f"Map size: 25x20 hexes")
    print("-"*30)
    
    for terrain, count in terrain_counts.items():
        percentage = (count / len(map_data)) * 100
        print(f"{terrain:12}: {count:3d} hexes ({percentage:5.1f}%)")
    
    # Check coverage requirements
    difficult_count = terrain_counts.get('Difficult', 0)
    difficult_coverage = difficult_count / len(map_data)
    
    print("-"*30)
    if 0.2 <= difficult_coverage <= 0.3:
        print(f"✓ Difficult terrain coverage: {difficult_coverage:.1%} (within 20-30% target)")
    else:
        print(f"✗ Difficult terrain coverage: {difficult_coverage:.1%} (outside 20-30% target)")
    
    print("="*50)


def test_perlin_terrain_generation() -> None:
    """
    Test function for Perlin terrain generation with different seeds.
    """
    print("Testing Perlin terrain generation...")
    print("="*50)
    
    # Test with different seeds
    test_seeds = [42, 123, 456, 789, 999]
    
    for seed in test_seeds:
        print(f"\nTesting seed: {seed}")
        print("-"*30)
        
        # Create a simple test map
        test_map = {}
        for q in range(25):
            for r in range(20):
                test_map[(q, r)] = Hex(q=q, r=r, terrain='Open')
        
        # Add some Contentious Ground in center
        center_hexes = [(12, 10), (13, 10), (12, 11)]
        for q, r in center_hexes:
            test_map[(q, r)].terrain = 'Contentious'
        
        # Generate Perlin terrain
        result_map = generate_perlin_terrain(test_map, seed, target_coverage=0.25)
        
        # Print statistics
        print_map_stats(result_map)


if __name__ == "__main__":
    # Test Perlin terrain generation
    test_perlin_terrain_generation()
    
    print("\n" + "="*50)
    print("FULL MAP GENERATION TEST")
    print("="*50)
    
    # Example usage of full map generation
    seed = 42
    map_data = generate_map(seed)
    print_map_stats(map_data)
