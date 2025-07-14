#!/usr/bin/env python3
"""
Simple test script to verify confrontation dynamics work.
"""

import requests
import json
import time
import pytest
from typing import Dict, List, Any, Optional, Tuple


class ConfrontationTester:
    """Simple tester for confrontation dynamics."""
    
    def __init__(self, base_url: str = 'https://halogen-valve-465821-v7.uc.r.appspot.com/api'):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.game_id: Optional[str] = None
    
    def create_game(self, seed: int = 42) -> bool:
        """Create a new game."""
        try:
            url = f"{self.base_url}/game/new"
            data = {"seed": seed}
            
            print(f"Creating new game with seed {seed}...")
            response = self.session.post(url, json=data)
            
            if response.status_code == 200:
                result = response.json()
                self.game_id = result.get('game_id')
                print(f"Game created successfully with ID: {self.game_id}")
                return True
            else:
                print(f"Failed to create game: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error creating game: {e}")
            return False
    
    def get_game_state(self) -> Optional[Dict[str, Any]]:
        """Get the current game state."""
        if not self.game_id:
            print("No game ID available")
            return None
            
        try:
            url = f"{self.base_url}/game/{self.game_id}/state"
            response = self.session.get(url)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Failed to get game state: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Error getting game state: {e}")
            return None
    
    def get_game_log(self) -> Optional[Dict[str, Any]]:
        """Get the current game log."""
        if not self.game_id:
            print("No game ID available")
            return None
            
        try:
            url = f"{self.base_url}/game/{self.game_id}/log"
            response = self.session.get(url)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Failed to get game log: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Error getting game log: {e}")
            return None
    
    def submit_orders(self, player_id: str, orders: List[Dict[str, Any]]) -> bool:
        """Submit orders for a player."""
        if not self.game_id:
            print("No game ID available")
            return False
            
        try:
            url = f"{self.base_url}/game/{self.game_id}/action"
            data = {
                "player_id": player_id,
                "orders": orders
            }
            
            response = self.session.post(url, json=data)
            
            if response.status_code == 200:
                print(f"Orders submitted successfully for {player_id}")
                return True
            else:
                print(f"Failed to submit orders for {player_id}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error submitting orders for {player_id}: {e}")
            return False
    
    def run_upkeep(self) -> bool:
        """Run the upkeep phase."""
        if not self.game_id:
            print("No game ID available")
            return False
            
        try:
            url = f"{self.base_url}/game/{self.game_id}/upkeep"
            response = self.session.post(url)
            
            if response.status_code == 200:
                print("Upkeep completed successfully")
                return True
            else:
                print(f"Failed to run upkeep: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error running upkeep: {e}")
            return False
    
    def hex_distance(self, a: Tuple[int, int], b: Tuple[int, int]) -> int:
        """Calculate hex distance between two positions."""
        dq = abs(a[0] - b[0])
        dr = abs(a[1] - b[1])
        ds = abs(a[0] + a[1] - b[0] - b[1])
        return (dq + dr + ds) // 2
    
    def get_adjacent_hexes(self, position: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Get valid adjacent hexes for a given position."""
        q, r = position
        adjacent = [
            (q + 1, r), (q - 1, r),  # East/West
            (q, r + 1), (q, r - 1),  # Northeast/Southwest
            (q + 1, r - 1), (q - 1, r + 1)  # Southeast/Northwest
        ]
        
        # Filter to valid map bounds (10x10)
        valid = [(q, r) for q, r in adjacent if 0 <= q < 10 and 0 <= r < 10]
        return valid
    
    def check_for_confrontation(self, log: Dict[str, Any]) -> bool:
        """Check if a confrontation occurred in the given log."""
        if not log or 'log' not in log:
            return False
        
        events = log.get('log', [])
        
        # Look for confrontation-related events
        for event in events:
            event_text = str(event).lower()
            if 'confrontation' in event_text or 'battle' in event_text or 'combat' in event_text:
                return True
        
        return False
    
    def print_map_with_forces(self, state: Dict[str, Any]):
        """Print a simple map showing forces and the contentious hex."""
        print("\nMap (10x10):")
        print("  " + "".join([f"{i:2}" for i in range(10)]))
        for r in range(10):
            row = f"{r:2}"
            for q in range(10):
                # Check if this is the contentious hex (center)
                if (q, r) == (5, 5):
                    row += "XX"
                else:
                    force_here = None
                    for player in state.get('players', []):
                        for force in player['forces']:
                            pos = force['position']
                            if (pos['q'], pos['r']) == (q, r):
                                force_here = force['id']
                                break
                        if force_here:
                            break
                    if force_here:
                        if force_here == 'p1_f2':
                            row += "P1"
                        elif force_here == 'p2_f2':
                            row += "P2"
                        else:
                            row += "FF"
                    else:
                        row += " ."
            print(row)
        print("Legend: XX = Contentious hex, P1 = p1_f2, P2 = p2_f2, FF = other forces, . = empty")

    def test_confrontation(self) -> bool:
        """Test confrontation dynamics."""
        print("Testing confrontation dynamics...")
        if not self.create_game(seed=42):
            return False
        initial_state = self.get_game_state()
        if not initial_state:
            return False
        print("Initial map:")
        self.print_map_with_forces(initial_state)
        print("Step 1: Moving forces toward contentious hex (5, 5)...")
        contentious_hex = (5, 5)
        for turn in range(1, 40):
            print(f"\nTurn {turn}: Moving forces closer to contentious hex...")
            current_state = self.get_game_state()
            if not current_state:
                return False
            phase = current_state.get('phase')
            orders_submitted = current_state.get('orders_submitted', {})
            # Only submit orders in 'plan' phase and if not already submitted
            if phase == 'plan':
                # Find current positions
                p1_f2_pos = None
                p2_f2_pos = None
                for player in current_state.get('players', []):
                    for force in player['forces']:
                        if force['id'] == 'p1_f2':
                            p1_f2_pos = (force['position']['q'], force['position']['r'])
                        elif force['id'] == 'p2_f2':
                            p2_f2_pos = (force['position']['q'], force['position']['r'])
                
                print(f"Current positions: p1_f2 at {p1_f2_pos}, p2_f2 at {p2_f2_pos}")
                
                # Check Shih levels
                p1_shih = None
                p2_shih = None
                for player in current_state.get('players', []):
                    if player['id'] == 'p1':
                        p1_shih = player['shih']
                    elif player['id'] == 'p2':
                        p2_shih = player['shih']
                
                print(f"Shih levels: p1={p1_shih}, p2={p2_shih}")
                
                # Print current map
                self.print_map_with_forces(current_state)
                
                # Check if we're close enough to test confrontation
                if p1_f2_pos is None or p2_f2_pos is None:
                    print("Could not find force positions")
                    return False
                
                p1_distance = self.hex_distance(p1_f2_pos, contentious_hex)
                p2_distance = self.hex_distance(p2_f2_pos, contentious_hex)
                
                if p1_distance <= 1 and p2_distance <= 1:
                    print(f"Forces are close enough! p1_f2 distance: {p1_distance}, p2_f2 distance: {p2_distance}")
                    break
                
                # Generate orders to move toward contentious hex
                p1_orders = []
                p2_orders = []
                
                # Move p1_f2 toward contentious hex
                if p1_distance > 1:
                    if p1_shih is not None and p1_shih >= 2:  # Only advance if we have enough Shih
                        adjacent = self.get_adjacent_hexes(p1_f2_pos)
                        if adjacent:
                            # Find the best adjacent hex that moves toward contentious hex
                            best_adjacent = None
                            best_distance = float('inf')
                            
                            for adj in adjacent:
                                distance = self.hex_distance(adj, contentious_hex)
                                if distance < best_distance:
                                    best_distance = distance
                                    best_adjacent = adj
                            
                            if best_adjacent:
                                p1_orders.append({
                                    'force_id': 'p1_f2',
                                    'order': 'Advance',
                                    'target_hex': {'q': best_adjacent[0], 'r': best_adjacent[1]},
                                    'stance': 'River'
                                })
                    else:
                        # Meditate to build Shih if we don't have enough
                        p1_orders.append({
                            'force_id': 'p1_f2',
                            'order': 'Meditate'
                        })
                else:
                    # Meditate to build Shih - be more aggressive about this
                    p1_orders.append({
                        'force_id': 'p1_f2',
                        'order': 'Meditate'
                    })
                
                # Move p2_f2 toward contentious hex
                if p2_distance > 1:
                    if p2_shih is not None and p2_shih >= 2:  # Only advance if we have enough Shih
                        adjacent = self.get_adjacent_hexes(p2_f2_pos)
                        if adjacent:
                            # Find the best adjacent hex that moves toward contentious hex
                            best_adjacent = None
                            best_distance = float('inf')
                            
                            for adj in adjacent:
                                distance = self.hex_distance(adj, contentious_hex)
                                if distance < best_distance:
                                    best_distance = distance
                                    best_adjacent = adj
                            
                            if best_adjacent:
                                p2_orders.append({
                                    'force_id': 'p2_f2',
                                    'order': 'Advance',
                                    'target_hex': {'q': best_adjacent[0], 'r': best_adjacent[1]},
                                    'stance': 'Mountain'
                                })
                    else:
                        # Meditate to build Shih if we don't have enough
                        p2_orders.append({
                            'force_id': 'p2_f2',
                            'order': 'Meditate'
                        })
                else:
                    # Meditate to build Shih - be more aggressive about this
                    p2_orders.append({
                        'force_id': 'p2_f2',
                        'order': 'Meditate'
                    })
                
                # If we're very close (distance 2 or less), be more aggressive about moving
                if p1_distance <= 2 and p1_shih is not None and p1_shih >= 2:
                    # Force movement toward the target even if it's not the optimal path
                    if not p1_orders:  # Only if we haven't already generated an order
                        adjacent = self.get_adjacent_hexes(p1_f2_pos)
                        if adjacent:
                            # Just pick any adjacent hex that gets us closer
                            for adj in adjacent:
                                if self.hex_distance(adj, contentious_hex) < p1_distance:
                                    p1_orders.append({
                                        'force_id': 'p1_f2',
                                        'order': 'Advance',
                                        'target_hex': {'q': adj[0], 'r': adj[1]},
                                        'stance': 'River'
                                    })
                                    break
                
                if p2_distance <= 2 and p2_shih is not None and p2_shih >= 2:
                    # Force movement toward the target even if it's not the optimal path
                    if not p2_orders:  # Only if we haven't already generated an order
                        adjacent = self.get_adjacent_hexes(p2_f2_pos)
                        if adjacent:
                            # Just pick any adjacent hex that gets us closer
                            for adj in adjacent:
                                if self.hex_distance(adj, contentious_hex) < p2_distance:
                                    p2_orders.append({
                                        'force_id': 'p2_f2',
                                        'order': 'Advance',
                                        'target_hex': {'q': adj[0], 'r': adj[1]},
                                        'stance': 'Mountain'
                                    })
                                    break
                
                # Submit orders if we have any
                if p1_orders and not orders_submitted.get('p1', False):
                    if not self.submit_orders('p1', p1_orders):
                        return False
                
                if p2_orders and not orders_submitted.get('p2', False):
                    if not self.submit_orders('p2', p2_orders):
                        return False
            # Only run upkeep in 'execute' phase
            elif phase == 'execute':
                if not self.run_upkeep():
                    return False
            else:
                print(f"Unexpected phase: {phase}")
                return False
        
        # Get state after movement
        state_after_movement = self.get_game_state()
        if not state_after_movement:
            return False
        
        print(f"\nAfter movement:")
        for player in state_after_movement.get('players', []):
            for force in player['forces']:
                if force['id'] in ['p1_f2', 'p2_f2']:
                    pos = force['position']
                    print(f"  {force['id']}: position=({pos['q']}, {pos['r']}), stance={force['stance']}")
        
        # Check if we're close enough to test confrontation
        p1_f2_pos = None
        p2_f2_pos = None
        for player in state_after_movement.get('players', []):
            for force in player['forces']:
                if force['id'] == 'p1_f2':
                    p1_f2_pos = (force['position']['q'], force['position']['r'])
                elif force['id'] == 'p2_f2':
                    p2_f2_pos = (force['position']['q'], force['position']['r'])
        
        if p1_f2_pos is None or p2_f2_pos is None:
            print("Could not find force positions")
            return False
        
        p1_distance = self.hex_distance(p1_f2_pos, contentious_hex)
        p2_distance = self.hex_distance(p2_f2_pos, contentious_hex)
        
        if p1_distance > 1 or p2_distance > 1:
            print(f"Forces are not close enough to test confrontation. p1_f2 distance: {p1_distance}, p2_f2 distance: {p2_distance}")
            return False
        
        print(f"\nStep 2: Testing confrontation by both advancing to contentious hex (5, 5)...")
        
        # Now both forces are adjacent to contentious hex, test confrontation
        p1_orders = [
            {
                'force_id': 'p1_f2',
                'order': 'Advance',
                'target_hex': {'q': 5, 'r': 5},
                'stance': 'River'
            }
        ]
        
        p2_orders = [
            {
                'force_id': 'p2_f2',
                'order': 'Advance',
                'target_hex': {'q': 5, 'r': 5},
                'stance': 'Mountain'
            }
        ]
        
        print(f"Submitting confrontation orders:")
        print(f"p1_f2: Advance to (5, 5) with River stance")
        print(f"p2_f2: Advance to (5, 5) with Mountain stance")
        
        # Submit orders
        if not self.submit_orders('p1', p1_orders):
            return False
        
        if not self.submit_orders('p2', p2_orders):
            return False
        
        # Run upkeep
        if not self.run_upkeep():
            return False
        
        # Get final state and log
        final_state = self.get_game_state()
        log = self.get_game_log()
        
        print(f"\nFinal state:")
        if final_state:
            for player in final_state.get('players', []):
                print(f"{player['id']}: Chi={player['chi']}, Shih={player['shih']}")
                for force in player['forces']:
                    if force['id'] in ['p1_f2', 'p2_f2']:
                        pos = force['position']
                        print(f"  {force['id']}: position=({pos['q']}, {pos['r']}), stance={force['stance']}")
        
        # Check for confrontation
        if log and self.check_for_confrontation(log):
            print(f"\n*** CONFRONTATION DETECTED! ***")
            return True
        else:
            print(f"\nNo confrontation detected.")
            if log:
                print(f"Log events: {log}")
            return False


def test_confrontation_dynamics():
    """Test that confrontation dynamics work correctly."""
    print("Confrontation Dynamics Test")
    print("=" * 40)
    
    tester = ConfrontationTester()
    
    # Run the confrontation test
    result = tester.test_confrontation()
    
    # Assert that the test passed
    assert result, "Confrontation dynamics test failed!"


def main():
    """Main function to run the confrontation test."""
    print("Confrontation Dynamics Test")
    print("=" * 40)
    
    tester = ConfrontationTester()
    
    if tester.test_confrontation():
        print("✓ Confrontation dynamics working!")
    else:
        print("✗ Confrontation dynamics failed!")


if __name__ == "__main__":
    main() 