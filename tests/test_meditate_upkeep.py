"""
Test cases for Meditate order upkeep functionality.

Tests that Meditate orders from the previous turn are properly applied during upkeep:
- +2 Shih per Meditate order (max 20)
- Orders are cleared after application
- API responses include meditate_shih_yields
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state import GameState, initialize_game
from orders import Order, OrderType, resolve_orders
from upkeep import perform_upkeep
from models import Force, Player


class TestMeditateUpkeep(unittest.TestCase):
    """Test cases for Meditate order upkeep functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a minimal game state for testing
        self.game_state = GameState(
            game_id="test_game",
            turn=2,  # Start at turn 2 to test previous turn orders
            phase='execute',
            players=[],
            map_data={},
            log=[],
            orders_submitted={},
            last_orders={}
        )
        
        # Create test players
        self.player1 = Player(id='p1', chi=100, shih=10, max_shih=20)
        self.player2 = Player(id='p2', chi=100, shih=10, max_shih=20)
        
        # Create test forces
        self.force1 = Force(id='p1_f1', position=(0, 0), stance='Mountain', tendency=[])
        self.force2 = Force(id='p1_f2', position=(1, 0), stance='River', tendency=[])
        self.force3 = Force(id='p2_f1', position=(24, 19), stance='Thunder', tendency=[])
        
        # Add forces to players
        self.player1.add_force(self.force1)
        self.player1.add_force(self.force2)
        self.player2.add_force(self.force3)
        
        # Add players to game state
        self.game_state.players = [self.player1, self.player2]
    
    def test_meditate_orders_applied_during_upkeep(self):
        """Test that Meditate orders from previous turn are applied during upkeep."""
        # Set up last_orders with Meditate orders from previous turn
        self.game_state.last_orders = {
            'p1': [
                {'order_type': 'Meditate', 'force_id': 'p1_f1', 'shih_bonus': 2},
                {'order_type': 'Meditate', 'force_id': 'p1_f2', 'shih_bonus': 2}
            ],
            'p2': [
                {'order_type': 'Meditate', 'force_id': 'p2_f1', 'shih_bonus': 2}
            ]
        }
        
        # Record initial Shih values
        initial_p1_shih = self.player1.shih
        initial_p2_shih = self.player2.shih
        
        # Perform upkeep
        results = perform_upkeep(self.game_state)
        
        # Verify Shih was increased correctly
        self.assertEqual(self.player1.shih, initial_p1_shih + 4)  # 2 forces * 2 Shih each
        self.assertEqual(self.player2.shih, initial_p2_shih + 2)  # 1 force * 2 Shih
        
        # Verify meditate_shih_yields in results
        self.assertEqual(results['meditate_shih_yields']['p1'], 4)
        self.assertEqual(results['meditate_shih_yields']['p2'], 2)
        
        # Verify last_orders was cleared
        self.assertEqual(self.game_state.last_orders, {})
    
    def test_meditate_orders_respect_max_shih(self):
        """Test that Meditate orders respect the maximum Shih limit of 20."""
        # Set up player with high Shih
        self.player1.shih = 19  # Near max
        
        # Set up many Meditate orders (should be capped at 20)
        self.game_state.last_orders = {
            'p1': [
                {'order_type': 'Meditate', 'force_id': 'p1_f1', 'shih_bonus': 2},
                {'order_type': 'Meditate', 'force_id': 'p1_f2', 'shih_bonus': 2},
                {'order_type': 'Meditate', 'force_id': 'p1_f3', 'shih_bonus': 2}  # Extra force
            ]
        }
        
        # Perform upkeep
        results = perform_upkeep(self.game_state)
        
        # Verify Shih was capped at 20
        self.assertEqual(self.player1.shih, 20)
        
        # Verify meditate_shih_yields shows the actual amount gained
        self.assertEqual(results['meditate_shih_yields']['p1'], 1)  # Only gained 1 to reach max
    
    def test_no_meditate_orders_no_shih_gain(self):
        """Test that no Shih is gained when there are no Meditate orders."""
        # Set up last_orders with no Meditate orders
        self.game_state.last_orders = {
            'p1': [
                {'order_type': 'Advance', 'force_id': 'p1_f1', 'target_hex': (1, 1)}
            ]
        }
        
        # Record initial Shih values
        initial_p1_shih = self.player1.shih
        
        # Perform upkeep
        results = perform_upkeep(self.game_state)
        
        # Verify Shih was not changed
        self.assertEqual(self.player1.shih, initial_p1_shih)
        
        # Verify no meditate_shih_yields
        self.assertEqual(results['meditate_shih_yields'], {})
    
    def test_mixed_orders_only_meditate_applied(self):
        """Test that only Meditate orders are applied during upkeep."""
        # Set up mixed orders
        self.game_state.last_orders = {
            'p1': [
                {'order_type': 'Meditate', 'force_id': 'p1_f1', 'shih_bonus': 2},
                {'order_type': 'Advance', 'force_id': 'p1_f2', 'target_hex': (2, 0)},
                {'order_type': 'Deceive', 'force_id': 'p1_f3', 'target_hex': (0, 1)}
            ]
        }
        
        # Record initial Shih values
        initial_p1_shih = self.player1.shih
        
        # Perform upkeep
        results = perform_upkeep(self.game_state)
        
        # Verify only Meditate order was applied
        self.assertEqual(self.player1.shih, initial_p1_shih + 2)  # Only 1 Meditate order
        self.assertEqual(results['meditate_shih_yields']['p1'], 2)
    
    def test_resolve_orders_stores_meditate_for_upkeep(self):
        """Test that resolve_orders stores Meditate orders in last_orders."""
        # Create Meditate orders
        meditate_order1 = Order(OrderType.MEDITATE, self.force1)
        meditate_order2 = Order(OrderType.MEDITATE, self.force2)
        
        # Resolve orders
        results = resolve_orders([meditate_order1, meditate_order2], self.game_state)
        
        # Verify orders were stored in last_orders
        self.assertIn('p1', self.game_state.last_orders)
        self.assertEqual(len(self.game_state.last_orders['p1']), 2)
        
        # Verify order structure
        for order in self.game_state.last_orders['p1']:
            self.assertEqual(order['order_type'], 'Meditate')
            self.assertIn('force_id', order)
            self.assertEqual(order['shih_bonus'], 2)
        
        # Verify no immediate Shih gain (should wait for upkeep)
        self.assertEqual(self.player1.shih, 10)  # Initial value
    
    def test_api_response_includes_meditate_yields(self):
        """Test that API response includes meditate_shih_yields."""
        # Set up Meditate orders
        self.game_state.last_orders = {
            'p1': [
                {'order_type': 'Meditate', 'force_id': 'p1_f1', 'shih_bonus': 2}
            ]
        }
        
        # Perform upkeep
        results = perform_upkeep(self.game_state)
        
        # Verify meditate_shih_yields is in results
        self.assertIn('meditate_shih_yields', results)
        self.assertEqual(results['meditate_shih_yields']['p1'], 2)


if __name__ == '__main__':
    unittest.main() 