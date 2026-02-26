"""Tests for v7 order processing: Move, Scout, Fortify, Ambush, Charge + supply lines + chain hops."""

import pytest
from state import initialize_game, apply_deployment, GameState
from orders import (
    Order, OrderType, OrderValidationError, is_adjacent, within_range,
    validate_order, resolve_orders, ORDER_COSTS,
)
from models import Force, Player, Hex
from map_gen import get_hex_neighbors


def make_deployed_game(seed=42):
    """Helper to create a fully deployed game with power values."""
    game = initialize_game(seed)
    p1_assign = {'p1_f1': 1, 'p1_f2': 5, 'p1_f3': 4, 'p1_f4': 2, 'p1_f5': 3}
    p2_assign = {'p2_f1': 1, 'p2_f2': 5, 'p2_f3': 4, 'p2_f4': 2, 'p2_f5': 3}
    apply_deployment(game, 'p1', p1_assign)
    apply_deployment(game, 'p2', p2_assign)
    return game


@pytest.fixture
def game():
    return make_deployed_game()


class TestAdjacency:
    def test_adjacent_hexes(self):
        assert is_adjacent((0, 0), (1, 0)) is True
        assert is_adjacent((0, 0), (0, 1)) is True
        assert is_adjacent((0, 0), (1, -1)) is True

    def test_non_adjacent(self):
        assert is_adjacent((0, 0), (2, 0)) is False
        assert is_adjacent((0, 0), (0, 0)) is False
        assert is_adjacent((0, 0), (3, 3)) is False


class TestWithinRange:
    def test_within_range_1(self):
        assert within_range((0, 0), (1, 0), 1) is True
        assert within_range((0, 0), (2, 0), 1) is False

    def test_within_range_2(self):
        assert within_range((0, 0), (2, 0), 2) is True
        assert within_range((0, 0), (3, 0), 2) is False

    def test_same_hex_is_range_0(self):
        assert within_range((3, 3), (3, 3), 0) is True


class TestOrderCosts:
    def test_move_is_free(self):
        assert ORDER_COSTS[OrderType.MOVE] == 0

    def test_scout_costs_2(self):
        assert ORDER_COSTS[OrderType.SCOUT] == 2

    def test_fortify_costs_2(self):
        assert ORDER_COSTS[OrderType.FORTIFY] == 2

    def test_ambush_costs_3(self):
        assert ORDER_COSTS[OrderType.AMBUSH] == 3

    def test_charge_costs_2(self):
        assert ORDER_COSTS[OrderType.CHARGE] == 2


class TestMoveValidation:
    def test_valid_move(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        neighbors = [(force.position[0] + dq, force.position[1] + dr)
                     for dq, dr in [(1, 0), (0, 1), (1, -1), (-1, 0), (-1, 1), (0, -1)]]
        target = None
        for n in neighbors:
            if game.is_valid_position(n) and game.get_force_at_position(n) is None:
                target = n
                break
        if target:
            order = Order(OrderType.MOVE, force, target_hex=target)
            validate_order(order, game, 'p1')  # Should not raise

    def test_move_off_board(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        order = Order(OrderType.MOVE, force, target_hex=(-1, -1))
        with pytest.raises(OrderValidationError, match="off the board"):
            validate_order(order, game, 'p1')

    def test_move_non_adjacent(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        order = Order(OrderType.MOVE, force, target_hex=(5, 5))
        with pytest.raises(OrderValidationError, match="not adjacent"):
            validate_order(order, game, 'p1')

    def test_move_no_target(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        order = Order(OrderType.MOVE, force)
        with pytest.raises(OrderValidationError, match="target hex"):
            validate_order(order, game, 'p1')

    def test_move_to_scorched_hex(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]  # at (0, 2)
        target = (0, 1)  # adjacent to (0, 2)
        game.map_data[target].terrain = 'Scorched'
        order = Order(OrderType.MOVE, force, target_hex=target)
        with pytest.raises(OrderValidationError, match="Scorched"):
            validate_order(order, game, 'p1')


class TestScoutValidation:
    def test_scout_requires_target_id(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        order = Order(OrderType.SCOUT, force)
        with pytest.raises(OrderValidationError, match="scout_target_id"):
            validate_order(order, game, 'p1')

    def test_scout_insufficient_shih(self, game):
        p1 = game.get_player_by_id('p1')
        p1.shih = 0  # Need 1 for scout
        p2 = game.get_player_by_id('p2')
        p2.forces[0].position = (1, 0)
        force = p1.forces[0]
        order = Order(OrderType.SCOUT, force, scout_target_id=p2.forces[0].id)
        with pytest.raises(OrderValidationError, match="Insufficient Shih"):
            validate_order(order, game, 'p1')

    def test_scout_within_range_2(self, game):
        """Scout can target enemies within 2 hexes, not just adjacent."""
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        p1.forces[0].position = (3, 3)
        p2.forces[0].position = (5, 3)  # Distance 2
        order = Order(OrderType.SCOUT, p1.forces[0], scout_target_id=p2.forces[0].id)
        validate_order(order, game, 'p1')  # Should not raise

    def test_scout_out_of_range(self, game):
        """Scout cannot target enemies beyond 2 hexes."""
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        p1.forces[0].position = (0, 0)
        p2.forces[0].position = (6, 6)  # Way too far
        order = Order(OrderType.SCOUT, p1.forces[0], scout_target_id=p2.forces[0].id)
        with pytest.raises(OrderValidationError, match="not within scout range"):
            validate_order(order, game, 'p1')


class TestFortifyValidation:
    def test_fortify_valid(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        order = Order(OrderType.FORTIFY, force)
        validate_order(order, game, 'p1')  # Should not raise

    def test_fortify_insufficient_shih(self, game):
        p1 = game.get_player_by_id('p1')
        p1.shih = 0
        force = p1.forces[0]
        order = Order(OrderType.FORTIFY, force)
        with pytest.raises(OrderValidationError, match="Insufficient Shih"):
            validate_order(order, game, 'p1')


class TestAmbushValidation:
    def test_ambush_valid(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        order = Order(OrderType.AMBUSH, force)
        validate_order(order, game, 'p1')  # Should not raise

    def test_ambush_insufficient_shih(self, game):
        p1 = game.get_player_by_id('p1')
        p1.shih = 1  # Need 2 for ambush
        force = p1.forces[0]
        order = Order(OrderType.AMBUSH, force)
        with pytest.raises(OrderValidationError, match="Insufficient Shih"):
            validate_order(order, game, 'p1')


class TestOrderResolution:
    def test_move_to_empty_hex(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        old_pos = force.position
        target = None
        for dq, dr in [(1, 0), (0, 1), (1, -1), (-1, 0), (-1, 1), (0, -1)]:
            candidate = (old_pos[0] + dq, old_pos[1] + dr)
            if game.is_valid_position(candidate) and game.get_force_at_position(candidate) is None:
                target = candidate
                break
        if target:
            p1_orders = [Order(OrderType.MOVE, force, target_hex=target)]
            results = resolve_orders(p1_orders, [], game)
            assert force.position == target
            assert len(results['movements']) == 1

    def test_fortify_sets_flag(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        assert force.fortified is False
        p1_orders = [Order(OrderType.FORTIFY, force)]
        resolve_orders(p1_orders, [], game)
        assert force.fortified is True

    def test_fortify_deducts_shih(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        old_shih = p1.shih
        p1_orders = [Order(OrderType.FORTIFY, force)]
        resolve_orders(p1_orders, [], game)
        assert p1.shih == old_shih - 2

    def test_ambush_sets_flag(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        assert force.ambushing is False
        p1_orders = [Order(OrderType.AMBUSH, force)]
        resolve_orders(p1_orders, [], game)
        assert force.ambushing is True

    def test_ambush_deducts_shih(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        old_shih = p1.shih
        p1_orders = [Order(OrderType.AMBUSH, force)]
        resolve_orders(p1_orders, [], game)
        assert p1.shih == old_shih - 3

    def test_move_into_enemy_triggers_combat(self, game):
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        attacker = p1.forces[0]
        defender = p2.forces[0]
        attacker.position = (3, 3)
        defender.position = (4, 3)
        game.map_data[(3, 3)] = Hex(q=3, r=3, terrain='Open')
        game.map_data[(4, 3)] = Hex(q=4, r=3, terrain='Open')

        p1_orders = [Order(OrderType.MOVE, attacker, target_hex=(4, 3))]
        results = resolve_orders(p1_orders, [], game)
        assert len(results['combats']) == 1

    def test_scout_reveals_power_privately(self, game):
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        scout_force = p1.forces[3]  # power 2
        target_force = p2.forces[0]  # power 1 (Sovereign)
        scout_force.position = (3, 3)
        target_force.position = (4, 3)
        game.map_data[(3, 3)] = Hex(q=3, r=3, terrain='Open')
        game.map_data[(4, 3)] = Hex(q=4, r=3, terrain='Open')

        p1_orders = [Order(OrderType.SCOUT, scout_force, scout_target_id=target_force.id)]
        results = resolve_orders(p1_orders, [], game)
        assert len(results['scouts']) == 1
        assert results['scouts'][0]['revealed_power'] == 1
        assert target_force.id in p1.known_enemy_powers
        assert target_force.revealed is False  # Not publicly revealed

    def test_simultaneous_collision(self, game):
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        f1 = p1.forces[1]  # power 5
        f2 = p2.forces[1]  # power 5
        f1.position = (2, 3)
        f2.position = (4, 3)
        target = (3, 3)
        game.map_data[(2, 3)] = Hex(q=2, r=3, terrain='Open')
        game.map_data[(4, 3)] = Hex(q=4, r=3, terrain='Open')
        game.map_data[(3, 3)] = Hex(q=3, r=3, terrain='Open')

        p1_orders = [Order(OrderType.MOVE, f1, target_hex=target)]
        p2_orders = [Order(OrderType.MOVE, f2, target_hex=target)]
        results = resolve_orders(p1_orders, p2_orders, game)
        assert len(results['combats']) == 1

    def test_dead_force_cant_order(self, game):
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        force.alive = False
        order = Order(OrderType.FORTIFY, force)
        with pytest.raises(OrderValidationError, match="dead"):
            validate_order(order, game, 'p1')

    def test_charge_to_empty_hex(self, game):
        """Charge moves the force up to 2 hexes to an empty target."""
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        force = p1.forces[0]
        force.position = (2, 3)
        target = (4, 3)  # 2 hexes away, should be empty
        # Ensure no force occupies the target
        for f in p1.forces[1:] + p2.forces:
            if f.position == target:
                f.position = (0, 0)
        p1_orders = [Order(OrderType.CHARGE, force, target_hex=target)]
        results = resolve_orders(p1_orders, [], game)
        assert force.position == target
        assert len(results['movements']) == 1

    def test_charge_deducts_shih(self, game):
        p1 = game.get_player_by_id('p1')
        p2 = game.get_player_by_id('p2')
        force = p1.forces[0]
        force.position = (2, 3)
        target = (3, 3)  # 1 hex away
        # Ensure target is empty
        for f in p1.forces[1:] + p2.forces:
            if f.position == target:
                f.position = (0, 0)
        old_shih = p1.shih
        p1_orders = [Order(OrderType.CHARGE, force, target_hex=target)]
        resolve_orders(p1_orders, [], game)
        assert p1.shih == old_shih - 2


class TestChargeValidation:
    def test_charge_1_hex_valid(self, game):
        """Charge to an adjacent hex (distance 1) is valid."""
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        force.position = (3, 3)
        order = Order(OrderType.CHARGE, force, target_hex=(4, 3))
        validate_order(order, game, 'p1')  # Should not raise

    def test_charge_2_hex_valid(self, game):
        """Charge to a hex 2 away with a valid intermediate path is valid."""
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        force.position = (3, 3)
        order = Order(OrderType.CHARGE, force, target_hex=(5, 3))
        validate_order(order, game, 'p1')  # Should not raise

    def test_charge_3_hex_invalid(self, game):
        """Charge target more than 2 hexes away is rejected."""
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        force.position = (0, 0)
        order = Order(OrderType.CHARGE, force, target_hex=(3, 0))
        with pytest.raises(OrderValidationError, match="1-2 hexes"):
            validate_order(order, game, 'p1')

    def test_charge_no_target(self, game):
        """Charge requires a target hex."""
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        order = Order(OrderType.CHARGE, force)
        with pytest.raises(OrderValidationError, match="target hex"):
            validate_order(order, game, 'p1')

    def test_charge_to_scorched_hex(self, game):
        """Charge cannot target a Scorched hex."""
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        force.position = (3, 3)
        game.map_data[(4, 3)].terrain = 'Scorched'
        order = Order(OrderType.CHARGE, force, target_hex=(4, 3))
        with pytest.raises(OrderValidationError, match="Scorched"):
            validate_order(order, game, 'p1')

    def test_charge_insufficient_shih(self, game):
        """Charge costs 1 Shih; player with 0 cannot charge."""
        p1 = game.get_player_by_id('p1')
        p1.shih = 0
        force = p1.forces[0]
        force.position = (3, 3)
        order = Order(OrderType.CHARGE, force, target_hex=(4, 3))
        with pytest.raises(OrderValidationError, match="Insufficient Shih"):
            validate_order(order, game, 'p1')

    def test_charge_2_hex_no_valid_path(self, game):
        """2-hex charge with all intermediate hexes Scorched is rejected."""
        p1 = game.get_player_by_id('p1')
        force = p1.forces[0]
        force.position = (3, 3)
        target = (5, 3)
        # Scorch all shared neighbors between (3,3) and (5,3) to block the path
        src_neighbors = set(get_hex_neighbors(3, 3))
        tgt_neighbors = set(get_hex_neighbors(5, 3))
        shared = src_neighbors & tgt_neighbors
        for h in shared:
            if h in game.map_data:
                game.map_data[h].terrain = 'Scorched'
        order = Order(OrderType.CHARGE, force, target_hex=target)
        with pytest.raises(OrderValidationError, match="No valid path"):
            validate_order(order, game, 'p1')
