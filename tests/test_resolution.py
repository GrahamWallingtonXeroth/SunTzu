import pytest
from resolution import resolve_confrontation, find_retreat_hex
from state import GameState, Player
from models import Force, Hex
from typing import Dict, Tuple, List

class TestConfrontationResolution:
    """Test suite for confrontation resolution mechanics."""
    
    @pytest.fixture
    def basic_game_state(self):
        """Create a basic game state for testing confrontations."""
        game_state = GameState(
            game_id="test_game_123",
            turn=1,
            phase="plan",
            players=[
                Player(id="p1", chi=100, shih=10, forces=[
                    Force(id="p1_f1", position=(0, 0), stance="Mountain"),
                    Force(id="p1_f2", position=(1, 0), stance="Mountain")
                ]),
                Player(id="p2", chi=100, shih=10, forces=[
                    Force(id="p2_f1", position=(1, 1), stance="Thunder"),
                    Force(id="p2_f2", position=(2, 1), stance="River")
                ])
            ],
            map_data={
                (0, 0): Hex(q=0, r=0, terrain="Open"),
                (1, 0): Hex(q=1, r=0, terrain="Open"),
                (1, 1): Hex(q=1, r=1, terrain="Contentious"),
                (2, 1): Hex(q=2, r=1, terrain="Open"),
                (0, 1): Hex(q=0, r=1, terrain="Open"),
                (2, 0): Hex(q=2, r=0, terrain="Open"),
                (-1, 0): Hex(q=-1, r=0, terrain="Open"),
                (0, -1): Hex(q=0, r=-1, terrain="Open"),
                (1, -1): Hex(q=1, r=-1, terrain="Open")
            }
        )
        return game_state

    @pytest.fixture
    def corner_game_state(self):
        """Create a game state with forces at map corners for boundary testing."""
        game_state = GameState(
            game_id="test_corner_game",
            turn=1,
            phase="plan",
            players=[
                Player(id="p1", chi=100, shih=10, forces=[
                    Force(id="p1_f1", position=(0, 0), stance="Mountain"),  # Corner
                    Force(id="p1_f2", position=(24, 0), stance="River"),    # Top-right corner
                ]),
                Player(id="p2", chi=100, shih=10, forces=[
                    Force(id="p2_f1", position=(0, 19), stance="Thunder"),  # Bottom-left corner
                    Force(id="p2_f2", position=(24, 19), stance="Mountain"), # Bottom-right corner
                ])
            ],
            map_data={
                (0, 0): Hex(q=0, r=0, terrain="Open"),
                (1, 0): Hex(q=1, r=0, terrain="Open"),
                (0, 1): Hex(q=0, r=1, terrain="Open"),
                (24, 0): Hex(q=24, r=0, terrain="Open"),
                (23, 0): Hex(q=23, r=0, terrain="Open"),
                (24, 1): Hex(q=24, r=1, terrain="Open"),
                (0, 19): Hex(q=0, r=19, terrain="Open"),
                (1, 19): Hex(q=1, r=19, terrain="Open"),
                (0, 18): Hex(q=0, r=18, terrain="Open"),
                (24, 19): Hex(q=24, r=19, terrain="Open"),
                (23, 19): Hex(q=23, r=19, terrain="Open"),
                (24, 18): Hex(q=24, r=18, terrain="Open"),
            }
        )
        return game_state

    @pytest.fixture
    def surrounded_game_state(self):
        """Create a game state where a force is completely surrounded."""
        game_state = GameState(
            game_id="test_surrounded_game",
            turn=1,
            phase="plan",
            players=[
                Player(id="p1", chi=100, shih=10, forces=[
                    Force(id="p1_f1", position=(5, 5), stance="Mountain"),  # Surrounded force
                ]),
                Player(id="p2", chi=100, shih=10, forces=[
                    Force(id="p2_f1", position=(6, 5), stance="Thunder"),
                    Force(id="p2_f2", position=(4, 5), stance="River"),
                    Force(id="p2_f3", position=(5, 6), stance="Mountain"),
                    Force(id="p2_f4", position=(5, 4), stance="Thunder"),
                    Force(id="p2_f5", position=(6, 4), stance="River"),
                    Force(id="p2_f6", position=(4, 6), stance="Mountain"),
                ])
            ],
            map_data={
                (5, 5): Hex(q=5, r=5, terrain="Open"),
                (6, 5): Hex(q=6, r=5, terrain="Open"),
                (4, 5): Hex(q=4, r=5, terrain="Open"),
                (5, 6): Hex(q=5, r=6, terrain="Open"),
                (5, 4): Hex(q=5, r=4, terrain="Open"),
                (6, 4): Hex(q=6, r=4, terrain="Open"),
                (4, 6): Hex(q=4, r=6, terrain="Open"),
            }
        )
        return game_state

    def test_attacker_wins_mountain_vs_thunder(self, basic_game_state):
        """Test attacker wins: Mountain beats Thunder."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[0].forces[1].position = (1, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        basic_game_state.players[1].forces[1].position = (2, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[0]  # p2_f1 at (1, 1)
        initial_attacker_chi = basic_game_state.players[0].chi
        initial_defender_chi = basic_game_state.players[1].chi
        
        attacker.stance = "Mountain"
        result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Verify Chi changes
        assert basic_game_state.players[0].chi == initial_attacker_chi  # Attacker no Chi loss
        assert basic_game_state.players[1].chi == initial_defender_chi - 16  # Defender loses 16 (8 * 2 for Contentious)
        
        # Verify position changes
        assert attacker.position == (1, 1)  # Attacker moves to target
        assert attacker.stance == "Mountain"
        assert defender.position in [(0, 1), (2, 0)]  # Defender retreats to available hex
        
        # Verify result structure
        assert result["attacker_id"] == attacker.id
        assert result["target_hex"] == (1, 1)
        assert result["chi_loss"] == [(defender.id, 16)]
        assert len(result["retreats"]) == 2
        assert (defender.id, defender.position) in result["retreats"]
        assert (attacker.id, (1, 1)) in result["retreats"]

    def test_defender_wins_thunder_vs_river(self, basic_game_state):
        """Test defender wins: Thunder beats River."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[0].forces[1].position = (1, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        basic_game_state.players[1].forces[1].position = (2, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[1]  # p2_f2 at (2, 1) - has River stance
        initial_attacker_chi = basic_game_state.players[0].chi
        initial_defender_chi = basic_game_state.players[1].chi
        
        attacker.stance = "Thunder"
        result = resolve_confrontation(attacker, defender, (2, 1), basic_game_state)
        
        # Verify Chi changes
        assert basic_game_state.players[0].chi == initial_attacker_chi  # Attacker no Chi loss
        assert basic_game_state.players[1].chi == initial_defender_chi - 8  # Defender loses 8
        
        # Verify position changes
        assert attacker.position == (2, 1)  # Attacker moves to target
        assert attacker.stance == "Thunder"
        assert defender.position in [(1, 1), (3, 1), (2, 0), (2, 2)]  # Defender retreats
        
        # Verify result structure
        assert result["chi_loss"] == [(defender.id, 8)]
        assert len(result["retreats"]) == 2
        assert (defender.id, defender.position) in result["retreats"]
        assert (attacker.id, (2, 1)) in result["retreats"]

    def test_stalemate_same_stance(self, basic_game_state):
        """Test stalemate: both forces have same stance."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[0].forces[1].position = (1, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        basic_game_state.players[1].forces[1].position = (2, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[0]  # p2_f1 at (1, 1)
        initial_attacker_chi = basic_game_state.players[0].chi
        initial_defender_chi = basic_game_state.players[1].chi
        
        attacker.stance = "Thunder"
        result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Verify Chi changes (both lose 8 due to Contentious terrain)
        assert basic_game_state.players[0].chi == initial_attacker_chi - 8
        assert basic_game_state.players[1].chi == initial_defender_chi - 8
        
        # Verify both retreat
        assert attacker.position in [(0, 1), (1, 0)]
        assert defender.position in [(0, 1), (2, 0)]
        
        # Verify result structure
        assert len(result["chi_loss"]) == 2
        assert any(chi_loss[0] == attacker.id and chi_loss[1] == 8 for chi_loss in result["chi_loss"])
        assert any(chi_loss[0] == defender.id and chi_loss[1] == 8 for chi_loss in result["chi_loss"])
        assert len(result["retreats"]) >= 1

    def test_ghost_confrontation(self, basic_game_state):
        """Test confrontation with no defender (ghost)."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[0].forces[1].position = (1, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        basic_game_state.players[1].forces[1].position = (2, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        initial_attacker_chi = basic_game_state.players[0].chi
        
        attacker.stance = "Mountain"
        result = resolve_confrontation(attacker, None, (1, 0), basic_game_state)
        
        # Verify no Chi loss
        assert basic_game_state.players[0].chi == initial_attacker_chi
        
        # Verify attacker moves to target
        assert attacker.position == (1, 0)
        assert attacker.stance == "Mountain"
        
        # Verify result structure
        assert result["chi_loss"] == []
        assert result["retreats"] == [(attacker.id, (1, 0))]

    def test_retreat_from_corner(self, corner_game_state):
        """Test retreat from map corner positions."""
        # Test each corner
        corners = [(0, 0), (24, 0), (0, 19), (24, 19)]
        expected_retreats = {
            (0, 0): [(1, 0), (0, 1)],
            (24, 0): [(23, 0), (24, 1)],
            (0, 19): [(1, 19), (0, 18)],
            (24, 19): [(23, 19), (24, 18)]
        }
        
        for corner in corners:
            force = Force(id=f"test_force_{corner}", position=corner, stance="Mountain")
            retreat_hex = find_retreat_hex(force, corner_game_state)
            
            assert retreat_hex is not None
            assert retreat_hex in expected_retreats[corner]

    def test_no_retreat_available_surrounded(self, surrounded_game_state):
        """Test retreat when force is completely surrounded."""
        surrounded_force = surrounded_game_state.players[0].forces[0]  # p1_f1 at (5, 5)
        
        retreat_hex = find_retreat_hex(surrounded_force, surrounded_game_state)
        
        assert retreat_hex is None

    def test_retreat_hex_validation(self, basic_game_state):
        """Test that retreat hexes are valid and unoccupied."""
        force = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        
        retreat_hex = find_retreat_hex(force, basic_game_state)
        
        if retreat_hex is not None:
            # Verify hex is within bounds
            assert 0 <= retreat_hex[0] < 25
            assert 0 <= retreat_hex[1] < 20
            
            # Verify hex exists in map data
            assert retreat_hex in basic_game_state.map_data
            
            # Verify hex is unoccupied
            for player in basic_game_state.players:
                for other_force in player.forces:
                    assert other_force.position != retreat_hex

    def test_chi_never_goes_below_zero(self, basic_game_state):
        """Test that Chi never goes below zero."""
        attacker = basic_game_state.players[0].forces[0]
        defender = basic_game_state.players[1].forces[0]
        
        # Set both players to very low Chi
        basic_game_state.players[0].chi = 2
        basic_game_state.players[1].chi = 1
        
        attacker.stance = "Thunder"
        result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Chi should not go below 0
        assert basic_game_state.players[0].chi >= 0
        assert basic_game_state.players[1].chi >= 0

    def test_invalid_stance_handling(self, basic_game_state):
        """Test handling of invalid stance combinations."""
        attacker = basic_game_state.players[0].forces[0]
        defender = basic_game_state.players[1].forces[0]
        
        # Test with invalid stance
        attacker.stance = "InvalidStance"
        with pytest.raises(KeyError):
            resolve_confrontation(attacker, defender, (1, 1), basic_game_state)

    def test_all_stance_combinations(self, basic_game_state):
        """Test all valid stance combinations."""
        stances = ["Mountain", "River", "Thunder"]
        beats = {
            "Mountain": "Thunder",
            "River": "Mountain", 
            "Thunder": "River"
        }
        
        for attacker_stance in stances:
            for defender_stance in stances:
                attacker = basic_game_state.players[0].forces[0]
                defender = basic_game_state.players[1].forces[0]
                defender.stance = defender_stance
                
                # Reset Chi for each test
                basic_game_state.players[0].chi = 100
                basic_game_state.players[1].chi = 100
                
                attacker.stance = attacker_stance
                result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
                
                # Verify result structure is valid
                assert "attacker_id" in result
                assert "target_hex" in result
                assert "chi_loss" in result
                assert "retreats" in result
                assert result["attacker_id"] == attacker.id
                assert result["target_hex"] == (1, 1)

    def test_terrain_multiplier_effects(self, basic_game_state):
        """Test that Contentious terrain doubles Chi loss."""
        attacker = basic_game_state.players[0].forces[0]
        defender = basic_game_state.players[1].forces[0]
        
        # Test on Contentious terrain (should double Chi loss)
        attacker.stance = "Mountain"
        result_contentious = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Reset and test on Open terrain
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        attacker.position = (0, 0)
        defender.position = (1, 1)
        
        # Add Open terrain hex
        basic_game_state.map_data[(1, 1)] = Hex(q=1, r=1, terrain="Open")
        
        attacker.stance = "Mountain"
        result_open = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Contentious terrain should cause double Chi loss
        contentious_loss = next(loss[1] for loss in result_contentious["chi_loss"] if loss[0] == defender.id)
        open_loss = next(loss[1] for loss in result_open["chi_loss"] if loss[0] == defender.id)
        
        assert contentious_loss == open_loss * 2

    def test_retreat_hex_adjacency(self, basic_game_state):
        """Test that retreat hexes are adjacent to the original position."""
        force = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        original_pos = force.position
        
        retreat_hex = find_retreat_hex(force, basic_game_state)
        
        if retreat_hex is not None:
            # Calculate distance (should be 1 for adjacent hexes)
            q_diff = abs(retreat_hex[0] - original_pos[0])
            r_diff = abs(retreat_hex[1] - original_pos[1])
            s_diff = abs(-retreat_hex[0] - retreat_hex[1] - (-original_pos[0] - original_pos[1]))
            
            # In axial coordinates, adjacent hexes have distance 1
            distance = max(q_diff, r_diff, s_diff)
            assert distance == 1

    def test_multiple_forces_same_player(self, basic_game_state):
        """Test confrontation with multiple forces from same player."""
        # Add another force to player 1
        new_force = Force(id="p1_f3", position=(0, 1), stance="River")
        basic_game_state.players[0].forces.append(new_force)
        basic_game_state.map_data[(0, 1)] = Hex(q=0, r=1, terrain="Open")
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[0]  # p2_f1 at (1, 1)
        
        attacker.stance = "Mountain"
        result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Verify the confrontation still works correctly
        assert result["attacker_id"] == attacker.id

    def test_empty_map_data_handling(self, basic_game_state):
        """Test handling when map data is missing for some positions."""
        # Remove some map data
        del basic_game_state.map_data[(1, 0)]
        
        force = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        retreat_hex = find_retreat_hex(force, basic_game_state)
        
        # Should still find valid retreat hexes that exist in map_data
        if retreat_hex is not None:
            assert retreat_hex in basic_game_state.map_data

    def test_performance_large_game_state(self):
        """Test performance with larger game state."""
        # Create a larger game state
        players = []
        map_data = {}
        
        # Add more players and forces
        for i in range(4):  # 4 players
            forces = []
            for j in range(3):  # 3 forces per player
                pos = (i * 5, j * 5)
                forces.append(Force(id=f"p{i+1}_f{j+1}", position=pos, stance="Mountain"))
                map_data[pos] = Hex(q=pos[0], r=pos[1], terrain="Open")
            
            players.append(Player(id=f"p{i+1}", chi=100, shih=10, forces=forces))
        
        game_state = GameState(
            game_id="performance_test",
            turn=1,
            phase="plan",
            players=players,
            map_data=map_data
        )
        
        # Test confrontation resolution performance
        attacker = players[0].forces[0]
        defender = players[1].forces[0]
        
        import time
        start_time = time.time()
        attacker.stance = "Mountain"
        result = resolve_confrontation(attacker, defender, (5, 5), game_state)
        end_time = time.time()
        
        # Should complete quickly (less than 100ms)
        assert end_time - start_time < 0.1
        assert result is not None

    # Tendency Modifier Tests (GDD pages 6-7)
    
    def test_attacker_plus_one_mod_wins_stalemate(self, basic_game_state):
        """Test attacker with +1 modifier wins stalemate vs defender with 0 modifier."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[0]  # p2_f1 at (1, 1)
        initial_attacker_chi = basic_game_state.players[0].chi
        initial_defender_chi = basic_game_state.players[1].chi
        
        # Set same stance for stalemate condition
        attacker.stance = "Mountain"
        defender.stance = "Mountain"
        
        # Set tendency: attacker gets +1 (3 unique orders), defender gets 0 (mixed)
        attacker.tendency = ["Advance", "Retreat", "Hold"]  # 3 unique = +1 modifier
        defender.tendency = ["Advance", "Advance", "Retreat"]  # Mixed = 0 modifier
        
        result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Attacker should win due to +1 modifier breaking stalemate
        assert basic_game_state.players[0].chi == initial_attacker_chi  # Attacker no Chi loss
        assert basic_game_state.players[1].chi == initial_defender_chi - 16  # Defender loses 16 (8 * 2 for Contentious)
        
        # Verify attacker moves to target, defender retreats
        assert attacker.position == (1, 1)  # Attacker moves to target
        assert defender.position in [(0, 1), (2, 0)]  # Defender retreats
        
        # Verify result structure
        assert result["chi_loss"] == [(defender.id, 16)]
        assert len(result["retreats"]) == 2
        assert (defender.id, defender.position) in result["retreats"]
        assert (attacker.id, (1, 1)) in result["retreats"]

    def test_defender_minus_one_mod_loses_normal_win(self, basic_game_state):
        """Test defender with -1 modifier loses normal win vs attacker with 0 modifier."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[0]  # p2_f1 at (1, 1)
        initial_attacker_chi = basic_game_state.players[0].chi
        initial_defender_chi = basic_game_state.players[1].chi
        
        # Set River vs Mountain: River normally beats Mountain
        attacker.stance = "River"
        defender.stance = "Mountain"
        
        # Set tendency: attacker gets 0 (mixed), defender gets -1 (3 identical)
        attacker.tendency = ["Advance", "Advance", "Retreat"]  # Mixed = 0 modifier
        defender.tendency = ["Hold", "Hold", "Hold"]  # 3 identical = -1 modifier
        
        result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Attacker should win due to defender's -1 modifier
        assert basic_game_state.players[0].chi == initial_attacker_chi  # Attacker no Chi loss
        assert basic_game_state.players[1].chi == initial_defender_chi - 16  # Defender loses 16 (8 * 2 for Contentious)
        
        # Verify attacker moves to target, defender retreats
        assert attacker.position == (1, 1)  # Attacker moves to target
        assert defender.position in [(0, 1), (2, 0)]  # Defender retreats
        
        # Verify result structure
        assert result["chi_loss"] == [(defender.id, 16)]
        assert len(result["retreats"]) == 2
        assert (defender.id, defender.position) in result["retreats"]
        assert (attacker.id, (1, 1)) in result["retreats"]

    def test_attacker_three_identical_orders_penalty(self, basic_game_state):
        """Test attacker with 3 identical orders gets -1 penalty."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[0]  # p2_f1 at (1, 1)
        initial_attacker_chi = basic_game_state.players[0].chi
        initial_defender_chi = basic_game_state.players[1].chi
        
        # Set Mountain vs Thunder: Mountain normally beats Thunder
        attacker.stance = "Mountain"
        defender.stance = "Thunder"
        
        # Set tendency: attacker gets -1 (3 identical), defender gets 0 (mixed)
        attacker.tendency = ["Advance", "Advance", "Advance"]  # 3 identical = -1 modifier
        defender.tendency = ["Advance", "Retreat", "Advance"]  # Mixed = 0 modifier
        
        result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Defender should win due to attacker's -1 modifier
        assert basic_game_state.players[0].chi == initial_attacker_chi - 16  # Attacker loses 16 (8 * 2 for Contentious)
        assert basic_game_state.players[1].chi == initial_defender_chi  # Defender no Chi loss
        
        # Verify attacker retreats, defender stays
        assert attacker.position in [(0, 1), (1, 0)]  # Attacker retreats
        assert defender.position == (1, 1)  # Defender stays in place
        
        # Verify result structure
        assert result["chi_loss"] == [(attacker.id, 16)]
        assert len(result["retreats"]) == 1
        assert (attacker.id, attacker.position) in result["retreats"]

    def test_attacker_three_unique_orders_bonus(self, basic_game_state):
        """Test attacker with 3 unique orders gets +1 bonus."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[0]  # p2_f1 at (1, 1)
        initial_attacker_chi = basic_game_state.players[0].chi
        initial_defender_chi = basic_game_state.players[1].chi
        
        # Set Thunder vs River: Thunder normally loses to River
        attacker.stance = "Thunder"
        defender.stance = "River"
        
        # Set tendency: attacker gets +1 (3 unique), defender gets 0 (mixed)
        attacker.tendency = ["Advance", "Retreat", "Hold"]  # 3 unique = +1 modifier
        defender.tendency = ["Advance", "Advance", "Retreat"]  # Mixed = 0 modifier
        
        result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Attacker should win due to +1 modifier overcoming normal loss
        assert basic_game_state.players[0].chi == initial_attacker_chi  # Attacker no Chi loss
        assert basic_game_state.players[1].chi == initial_defender_chi - 16  # Defender loses 16 (8 * 2 for Contentious)
        
        # Verify attacker moves to target, defender retreats
        assert attacker.position == (1, 1)  # Attacker moves to target
        assert defender.position in [(0, 1), (2, 0)]  # Defender retreats
        
        # Verify result structure
        assert result["chi_loss"] == [(defender.id, 16)]
        assert len(result["retreats"]) == 2
        assert (defender.id, defender.position) in result["retreats"]
        assert (attacker.id, (1, 1)) in result["retreats"]

    def test_mixed_tendency_gives_zero_modifier(self, basic_game_state):
        """Test mixed tendency gives 0 modifier."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[0]  # p2_f1 at (1, 1)
        initial_attacker_chi = basic_game_state.players[0].chi
        initial_defender_chi = basic_game_state.players[1].chi
        
        # Set same stance for stalemate condition
        attacker.stance = "Mountain"
        defender.stance = "Mountain"
        
        # Set tendency: both get 0 (mixed patterns)
        attacker.tendency = ["Advance", "Advance", "Retreat"]  # Mixed = 0 modifier
        defender.tendency = ["Hold", "Retreat", "Hold"]  # Mixed = 0 modifier
        
        result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Should be stalemate since both have 0 modifiers
        assert basic_game_state.players[0].chi == initial_attacker_chi - 8  # Attacker loses 8 (4 * 2 for Contentious)
        assert basic_game_state.players[1].chi == initial_defender_chi - 8  # Defender loses 8 (4 * 2 for Contentious)
        
        # Verify both retreat
        assert attacker.position in [(0, 1), (1, 0)]  # Attacker retreats
        assert defender.position in [(0, 1), (2, 0)]  # Defender retreats
        
        # Verify result structure
        assert len(result["chi_loss"]) == 2
        assert any(chi_loss[0] == attacker.id and chi_loss[1] == 8 for chi_loss in result["chi_loss"])
        assert any(chi_loss[0] == defender.id and chi_loss[1] == 8 for chi_loss in result["chi_loss"])
        assert len(result["retreats"]) >= 1

    def test_tendency_ignored_if_length_less_than_three(self, basic_game_state):
        """Test tendency ignored if length < 3."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[0]  # p2_f1 at (1, 1)
        initial_attacker_chi = basic_game_state.players[0].chi
        initial_defender_chi = basic_game_state.players[1].chi
        
        # Set same stance for stalemate condition
        attacker.stance = "Mountain"
        defender.stance = "Mountain"
        
        # Set tendency: attacker has < 3 orders, defender has 3 identical
        attacker.tendency = ["Advance", "Retreat"]  # Only 2 orders = 0 modifier
        defender.tendency = ["Hold", "Hold", "Hold"]  # 3 identical = -1 modifier
        
        result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Attacker should win due to 0 modifier vs defender's -1
        assert basic_game_state.players[0].chi == initial_attacker_chi  # Attacker no Chi loss
        assert basic_game_state.players[1].chi == initial_defender_chi - 16  # Defender loses 16 (8 * 2 for Contentious)
        
        # Verify attacker moves to target, defender retreats
        assert attacker.position == (1, 1)  # Attacker moves to target
        assert defender.position in [(0, 1), (2, 0)]  # Defender retreats
        
        # Verify result structure
        assert result["chi_loss"] == [(defender.id, 16)]
        assert len(result["retreats"]) == 2
        assert (defender.id, defender.position) in result["retreats"]
        assert (attacker.id, (1, 1)) in result["retreats"]

    def test_tendency_with_more_than_three_orders(self, basic_game_state):
        """Test tendency with more than 3 orders (should only consider last 3)."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[0]  # p2_f1 at (1, 1)
        initial_attacker_chi = basic_game_state.players[0].chi
        initial_defender_chi = basic_game_state.players[1].chi
        
        # Set same stance for stalemate condition
        attacker.stance = "Mountain"
        defender.stance = "Mountain"
        
        # Test tendency with more than 3 orders (should only consider last 3)
        attacker.tendency = ["Advance", "Retreat", "Hold", "Advance", "Retreat"]  # Last 3: "Hold", "Advance", "Retreat" = 3 unique = +1
        defender.tendency = ["Advance", "Advance", "Advance"]  # 3 identical = -1 modifier
        
        result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Attacker should win due to +1 modifier vs defender's -1
        assert basic_game_state.players[0].chi == initial_attacker_chi  # Attacker no Chi loss
        assert basic_game_state.players[1].chi == initial_defender_chi - 16  # Defender loses 16 (8 * 2 for Contentious)
        
        # Verify attacker moves to target, defender retreats
        assert attacker.position == (1, 1)  # Attacker moves to target
        assert defender.position in [(0, 1), (2, 0)]  # Defender retreats
        
        # Verify result structure
        assert result["chi_loss"] == [(defender.id, 16)]
        assert len(result["retreats"]) == 2
        assert (defender.id, defender.position) in result["retreats"]
        assert (attacker.id, (1, 1)) in result["retreats"]

    def test_ghost_confrontation_ignores_tendency(self, basic_game_state):
        """Test ghost confrontation ignores tendency."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[0].forces[1].position = (1, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        basic_game_state.players[1].forces[1].position = (2, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        initial_attacker_chi = basic_game_state.players[0].chi
        
        attacker.stance = "Mountain"
        # Set tendency that would normally give penalty
        attacker.tendency = ["Advance", "Advance", "Advance"]  # 3 identical = -1 modifier
        
        result = resolve_confrontation(attacker, None, (1, 0), basic_game_state)
        
        # Verify no Chi loss (ghost confrontation)
        assert basic_game_state.players[0].chi == initial_attacker_chi
        
        # Verify attacker moves to target
        assert attacker.position == (1, 0)
        assert attacker.stance == "Mountain"
        
        # Verify result structure
        assert result["chi_loss"] == []
        assert result["retreats"] == [(attacker.id, (1, 0))]

    def test_tendency_modifier_with_different_config_values(self, basic_game_state):
        """Test tendency modifier with different config values."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[0]  # p2_f1 at (1, 1)
        initial_attacker_chi = basic_game_state.players[0].chi
        initial_defender_chi = basic_game_state.players[1].chi
        
        # Set same stance for stalemate condition
        attacker.stance = "Mountain"
        defender.stance = "Mountain"
        
        # Set tendency: attacker gets +1 (3 unique), defender gets 0 (mixed)
        attacker.tendency = ["Advance", "Retreat", "Hold"]  # 3 unique = +1 modifier
        defender.tendency = ["Advance", "Advance", "Retreat"]  # Mixed = 0 modifier
        
        # Temporarily modify config to test different modifier values
        import json
        import os
        
        # Backup original config
        with open('config.json', 'r') as f:
            original_config = json.load(f)
        
        try:
            # Test with tendency_modifier = 2
            test_config = original_config.copy()
            test_config['tendency_modifier'] = 2
            
            with open('config.json', 'w') as f:
                json.dump(test_config, f)
            
            result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
            
            # Attacker should win due to +2 modifier breaking stalemate
            assert basic_game_state.players[0].chi == initial_attacker_chi  # Attacker no Chi loss
            assert basic_game_state.players[1].chi == initial_defender_chi - 16  # Defender loses 16 (8 * 2 for Contentious)
            
            # Reset Chi for next test
            basic_game_state.players[0].chi = 100
            basic_game_state.players[1].chi = 100
            attacker.position = (0, 0)
            defender.position = (1, 1)
            
            # Test with tendency_modifier = 0 (no effect)
            test_config['tendency_modifier'] = 0
            
            with open('config.json', 'w') as f:
                json.dump(test_config, f)
            
            result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
            
            # Should be stalemate since modifier is 0
            assert basic_game_state.players[0].chi == initial_attacker_chi - 8  # Attacker loses 8 (4 * 2 for Contentious)
            assert basic_game_state.players[1].chi == initial_defender_chi - 8  # Defender loses 8 (4 * 2 for Contentious)
            
        finally:
            # Restore original config
            with open('config.json', 'w') as f:
                json.dump(original_config, f)

    def test_empty_tendency_list(self, basic_game_state):
        """Test empty tendency list (should be ignored)."""
        # Reset Chi to ensure clean state
        basic_game_state.players[0].chi = 100
        basic_game_state.players[1].chi = 100
        
        # Reset force positions
        basic_game_state.players[0].forces[0].position = (0, 0)
        basic_game_state.players[1].forces[0].position = (1, 1)
        
        attacker = basic_game_state.players[0].forces[0]  # p1_f1 at (0, 0)
        defender = basic_game_state.players[1].forces[0]  # p2_f1 at (1, 1)
        initial_attacker_chi = basic_game_state.players[0].chi
        initial_defender_chi = basic_game_state.players[1].chi
        
        # Set same stance for stalemate condition
        attacker.stance = "Mountain"
        defender.stance = "Mountain"
        
        # Test empty tendency list
        attacker.tendency = []
        defender.tendency = ["Advance", "Advance", "Advance"]  # 3 identical = -1 modifier
        
        result = resolve_confrontation(attacker, defender, (1, 1), basic_game_state)
        
        # Attacker should win due to 0 modifier vs defender's -1 (empty list = 0)
        assert basic_game_state.players[0].chi == initial_attacker_chi  # Attacker no Chi loss
        assert basic_game_state.players[1].chi == initial_defender_chi - 16  # Defender loses 16 (8 * 2 for Contentious)
        
        # Verify attacker moves to target, defender retreats
        assert attacker.position == (1, 1)  # Attacker moves to target
        assert defender.position in [(0, 1), (2, 0)]  # Defender retreats
        
        # Verify result structure
        assert result["chi_loss"] == [(defender.id, 16)]
        assert len(result["retreats"]) == 2
        assert (defender.id, defender.position) in result["retreats"]
        assert (attacker.id, (1, 1)) in result["retreats"]