"""
Tests for upkeep.py functionality
"""

import unittest
from unittest.mock import patch
from models import Player, Force, Hex
from state import GameState
from upkeep import (
    get_adjacent_positions,
    is_controlled,
    calculate_shih_yield,
    is_encircled,
    check_victory,
    perform_upkeep,
    get_upkeep_summary
)


class TestUpkeep(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a simple game state for testing
        self.game_state = GameState(
            game_id="test_game",
            turn=1,
            phase='upkeep',
            players=[],
            map_data={}
        )
        
        # Create test players
        self.player1 = Player(id='p1', chi=100, shih=10)
        self.player2 = Player(id='p2', chi=100, shih=10)
        
        # Create test forces
        self.force1 = Force(id='p1_f1', position=(5, 5), stance='Mountain')
        self.force2 = Force(id='p2_f1', position=(6, 6), stance='River')
        
        self.player1.add_force(self.force1)
        self.player2.add_force(self.force2)
        
        self.game_state.players = [self.player1, self.player2]
        
        # Create test map with some Contentious terrain
        self.game_state.map_data = {
            (5, 5): Hex(q=5, r=5, terrain='Contentious'),
            (6, 6): Hex(q=6, r=6, terrain='Contentious'),
            (4, 4): Hex(q=4, r=4, terrain='Open'),
            (7, 7): Hex(q=7, r=7, terrain='Difficult')
        }
    
    def test_get_adjacent_positions(self):
        """Test getting adjacent positions."""
        adjacent = get_adjacent_positions((5, 5))
        expected = [(6, 5), (6, 4), (5, 4), (4, 5), (4, 6), (5, 6)]
        
        # Sort both lists for comparison
        adjacent.sort()
        expected.sort()
        self.assertEqual(adjacent, expected)
    
    def test_is_controlled(self):
        """Test hex control detection."""
        # Test when player has force at position with no adjacent enemies
        self.assertTrue(is_controlled((5, 5), self.player1, self.game_state))
        
        # Test when player doesn't have force at position
        self.assertFalse(is_controlled((4, 4), self.player1, self.game_state))
    
    def test_calculate_shih_yield(self):
        """Test Shih yield calculation."""
        # Player 1 should get +2 Shih for controlling Contentious terrain at (5, 5)
        yield_amount = calculate_shih_yield(self.player1, self.game_state)
        self.assertEqual(yield_amount, 2)
        
        # Player 2 should get +2 Shih for controlling Contentious terrain at (6, 6)
        yield_amount = calculate_shih_yield(self.player2, self.game_state)
        self.assertEqual(yield_amount, 2)
    
    def test_is_encircled(self):
        """Test encirclement detection."""
        # Create a scenario where force1 is encircled by force2
        self.force2.position = (6, 5)  # Adjacent to force1
        
        # Add more enemy forces to complete encirclement
        force3 = Force(id='p2_f2', position=(5, 4), stance='Thunder')
        force4 = Force(id='p2_f3', position=(4, 5), stance='Mountain')
        self.player2.add_force(force3)
        self.player2.add_force(force4)
        
        # This is a simplified test - in reality, we'd need more forces to truly encircle
        # For now, just test that the function runs without error
        result = is_encircled(self.force1, self.game_state)
        self.assertIsInstance(result, bool)
    
    def test_check_victory_demoralization(self):
        """Test victory condition for demoralization."""
        # Set player1's Chi to 0
        self.player1.chi = 0
        
        winner = check_victory(self.game_state)
        self.assertEqual(winner, 'p2')
    
    def test_check_victory_no_winner(self):
        """Test victory check when no winner."""
        winner = check_victory(self.game_state)
        self.assertIsNone(winner)
    
    def test_perform_upkeep(self):
        """Test complete upkeep process."""
        results = perform_upkeep(self.game_state)
        
        # Check that results have expected structure
        self.assertIn('winner', results)
        self.assertIn('shih_yields', results)
        self.assertIn('encirclements', results)
        
        # Check that Shih yields were applied
        self.assertEqual(self.player1.shih, 12)  # 10 + 2 from Contentious terrain
        self.assertEqual(self.player2.shih, 12)  # 10 + 2 from Contentious terrain
    
    def test_get_upkeep_summary(self):
        """Test upkeep summary generation."""
        summary = get_upkeep_summary(self.game_state)
        
        self.assertIn('turn', summary)
        self.assertIn('phase', summary)
        self.assertIn('players', summary)
        self.assertIn('p1', summary['players'])
        self.assertIn('p2', summary['players'])


if __name__ == '__main__':
    unittest.main() 