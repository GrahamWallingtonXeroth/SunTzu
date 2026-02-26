"""
Map generation for The Unfought Battle v10.
7x7 hex grid with axial coordinates. Tight enough that every hex matters.

v10: Strategic reasoning benchmark. Metagame rebalanced with multi-tier pool.
v9: Wider starting separation.
"""

import random
from typing import Dict, Tuple, List, Optional
from models import Hex


BOARD_SIZE = 7
CENTER_Q = BOARD_SIZE // 2  # 3
CENTER_R = BOARD_SIZE // 2  # 3


def get_hex_neighbors(q: int, r: int) -> List[Tuple[int, int]]:
    """Get the 6 neighboring hex coordinates in axial system."""
    directions = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
    return [(q + dq, r + dr) for dq, dr in directions]


def hex_distance(q1: int, r1: int, q2: int, r2: int) -> int:
    """Distance between two hexes in axial coordinates."""
    return max(abs(q1 - q2), abs(r1 - r2), abs(-(q1 + r1) + (q2 + r2)))


def distance_from_center(q: int, r: int) -> int:
    """Distance from the board center (3,3). Used for shrinking board."""
    return hex_distance(q, r, CENTER_Q, CENTER_R)


def max_distance_for_shrink_stage(stage: int) -> int:
    """
    Return the maximum allowed distance from center for a given shrink stage.
    Stage 0: full board (max distance 6 — all hexes reachable)
    Stage 1: distance <= 5 (only far corners scorched)
    Stage 2: distance <= 4
    Stage 3: distance <= 3
    Stage 4: distance <= 2
    Stage 5+: distance <= 1
    """
    if stage <= 0:
        return BOARD_SIZE  # No shrinking
    limits = {1: 5, 2: 4, 3: 3, 4: 2}
    return limits.get(stage, 1)


def is_valid_hex(q: int, r: int, size: int = BOARD_SIZE) -> bool:
    """Check if hex coordinates are within the board."""
    return 0 <= q < size and 0 <= r < size


def is_scorched(q: int, r: int, shrink_stage: int) -> bool:
    """Check if a hex has been Scorched by the shrinking board."""
    if shrink_stage <= 0:
        return False
    return distance_from_center(q, r) > max_distance_for_shrink_stage(shrink_stage)


def a_star_path(
    start: Tuple[int, int],
    goal: Tuple[int, int],
    map_data: Dict[Tuple[int, int], Hex],
    avoid_terrain: Optional[str] = None,
    size: int = BOARD_SIZE,
) -> Optional[List[Tuple[int, int]]]:
    """A* pathfinding on the hex grid."""
    open_set = {start}
    came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
    g_score = {start: 0}
    f_score = {start: hex_distance(start[0], start[1], goal[0], goal[1])}

    while open_set:
        current = min(open_set, key=lambda x: f_score.get(x, float('inf')))
        if current == goal:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            path.reverse()
            return path

        open_set.remove(current)
        for nq, nr in get_hex_neighbors(current[0], current[1]):
            if not is_valid_hex(nq, nr, size):
                continue
            if (nq, nr) in map_data and map_data[(nq, nr)].terrain == 'Scorched':
                continue
            if avoid_terrain and (nq, nr) in map_data and map_data[(nq, nr)].terrain == avoid_terrain:
                continue
            tentative = g_score[current] + 1
            if (nq, nr) not in g_score or tentative < g_score[(nq, nr)]:
                came_from[(nq, nr)] = current
                g_score[(nq, nr)] = tentative
                f_score[(nq, nr)] = tentative + hex_distance(nq, nr, goal[0], goal[1])
                open_set.add((nq, nr))

    return None


def generate_map(seed: int, size: int = BOARD_SIZE) -> Dict[Tuple[int, int], Hex]:
    """
    Generate a 7x7 hex map.

    Layout:
    - P1 starts left cluster (distance 2-4 from center), P2 right cluster (symmetric)
    - 3 Contentious hexes clustered in the center — the objectives
    - Difficult terrain scattered to create chokepoints and cover
    - Both players have equal path lengths to the center
    """
    random.seed(seed)

    # Initialize all hexes as Open
    map_data: Dict[Tuple[int, int], Hex] = {}
    for q in range(size):
        for r in range(size):
            map_data[(q, r)] = Hex(q=q, r=r, terrain='Open')

    # Starting positions: cluster centers for path balance
    p1_start = (0, 2)
    p2_start = (6, 4)

    # All starting positions (for protected zone calculation)
    p1_positions = [(0, 1), (0, 2), (0, 3), (1, 1), (1, 2)]
    p2_positions = [(6, 5), (6, 4), (6, 3), (5, 5), (5, 4)]

    # Place 3 Contentious hexes in the center zone (q=2-4, r=2-4)
    center_min = size // 2 - 1  # 2
    center_max = size // 2 + 1  # 4
    center_candidates = [
        (q, r)
        for q in range(center_min, center_max + 1)
        for r in range(center_min, center_max + 1)
        if (q, r) in map_data
    ]
    random.shuffle(center_candidates)
    contentious_hexes = center_candidates[:3]
    for pos in contentious_hexes:
        map_data[pos].terrain = 'Contentious'

    # Protect starting positions from becoming Difficult
    protected: set = set()
    for start in p1_positions + p2_positions:
        protected.add(start)
    # Contentious hexes are never Difficult
    for pos in contentious_hexes:
        protected.add(pos)

    # Scatter Difficult terrain: ~20-25% of non-protected hexes
    open_hexes = [
        pos for pos in map_data
        if pos not in protected and map_data[pos].terrain == 'Open'
    ]
    random.shuffle(open_hexes)
    num_difficult = max(4, min(10, len(open_hexes) // 4))
    difficult_placed = 0

    for pos in open_hexes:
        if difficult_placed >= num_difficult:
            break
        # Don't block ALL paths — ensure A* still works after placement
        map_data[pos].terrain = 'Difficult'
        # Verify both players can still reach all contentious hexes
        blocked = False
        for ch in contentious_hexes:
            p1_path = a_star_path(p1_start, ch, map_data, 'Difficult', size)
            p2_path = a_star_path(p2_start, ch, map_data, 'Difficult', size)
            if p1_path is None or p2_path is None:
                blocked = True
                break
        if blocked:
            map_data[pos].terrain = 'Open'  # Revert
        else:
            difficult_placed += 1

    # Validate balance: path lengths within +/-1 for fairness
    for _ in range(5):
        balanced = True
        for ch in contentious_hexes:
            p1_path = a_star_path(p1_start, ch, map_data, 'Difficult', size)
            p2_path = a_star_path(p2_start, ch, map_data, 'Difficult', size)
            if p1_path and p2_path:
                if abs(len(p1_path) - len(p2_path)) > 1:
                    balanced = False
                    break
        if balanced:
            break
        # If unbalanced, remove a random Difficult hex and try again
        diff_hexes = [pos for pos in map_data if map_data[pos].terrain == 'Difficult']
        if diff_hexes:
            remove = random.choice(diff_hexes)
            map_data[remove].terrain = 'Open'

    return map_data
