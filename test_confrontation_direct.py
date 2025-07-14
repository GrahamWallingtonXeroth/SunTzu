#!/usr/bin/env python3
"""
Direct confrontation test - forces start adjacent to contentious hex.
"""

import requests
import json
import time
from typing import Dict, List, Any, Optional, Tuple


class DirectConfrontationTester:
    """Direct tester for confrontation dynamics."""
    
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
    
    def submit_orders(self, player_id: str, orders: List[Dict[str, Any]]) -> bool:
        """Submit orders for a player."""
        if not self.game_id:
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
    
    def get_game_log(self) -> Optional[Dict[str, Any]]:
        """Get the current game log."""
        if not self.game_id:
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
    
    def test_direct_confrontation(self) -> bool:
        """Test confrontation by directly advancing both forces to contentious hex."""
        print("Testing direct confrontation...")
        
        if not self.create_game(seed=42):
            return False
        
        # Get initial state
        initial_state = self.get_game_state()
        if not initial_state:
            return False
        
        print("Initial map:")
        self.print_map_with_forces(initial_state)
        
        # Check current phase
        phase = initial_state.get('phase')
        print(f"Current phase: {phase}")
        
        if phase == 'plan':
            # Submit confrontation orders immediately
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
            
            print("Submitting confrontation orders:")
            print("p1_f2: Advance to (5, 5) with River stance")
            print("p2_f2: Advance to (5, 5) with Mountain stance")
            
            # Submit orders
            if not self.submit_orders('p1', p1_orders):
                return False
            
            if not self.submit_orders('p2', p2_orders):
                return False
            
            # Run upkeep to execute orders
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
            print(f"Full game log:")
            for event in log.get('log', []):
                print(f"  {event}")
            return True
        else:
            print(f"\nNo confrontation detected.")
            if log:
                print(f"Full game log:")
                for event in log.get('log', []):
                    print(f"  {event}")
            return False


def main():
    """Main function to run the direct confrontation test."""
    print("Direct Confrontation Test")
    print("=" * 40)
    
    tester = DirectConfrontationTester()
    
    if tester.test_direct_confrontation():
        print("✓ Direct confrontation working!")
    else:
        print("✗ Direct confrontation failed!")


if __name__ == "__main__":
    main() 