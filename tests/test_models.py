"""Tests for the v3 data model layer — power values instead of roles."""

import pytest
from models import Force, Player, Hex, POWER_VALUES, SOVEREIGN_POWER


class TestPowerValues:
    def test_power_values_are_1_through_5(self):
        assert POWER_VALUES == {1, 2, 3, 4, 5}

    def test_sovereign_is_power_1(self):
        assert SOVEREIGN_POWER == 1


class TestForce:
    def test_create_force(self):
        f = Force(id='p1_f1', position=(0, 0))
        assert f.id == 'p1_f1'
        assert f.position == (0, 0)
        assert f.power is None
        assert f.revealed is False
        assert f.alive is True
        assert f.fortified is False
        assert f.ambushing is False
        assert f.charging is False

    def test_is_sovereign_when_power_1(self):
        f = Force(id='p1_f1', position=(0, 0), power=1)
        assert f.is_sovereign is True

    def test_is_not_sovereign_when_other_power(self):
        f = Force(id='p1_f1', position=(0, 0), power=5)
        assert f.is_sovereign is False

    def test_is_not_sovereign_when_no_power(self):
        f = Force(id='p1_f1', position=(0, 0))
        assert f.is_sovereign is False

    def test_power_values_assigned(self):
        f = Force(id='p1_f1', position=(0, 0), power=4)
        assert f.power == 4


class TestPlayer:
    def test_create_player(self):
        p = Player(id='p1')
        assert p.shih == 4
        assert p.max_shih == 8
        assert p.deployed is False
        assert p.domination_turns == 0
        assert len(p.forces) == 0
        assert len(p.known_enemy_powers) == 0

    def test_add_force(self):
        p = Player(id='p1')
        f = Force(id='p1_f1', position=(0, 0))
        p.add_force(f)
        assert len(p.forces) == 1

    def test_get_force_by_id(self):
        p = Player(id='p1')
        f = Force(id='p1_f1', position=(0, 0))
        p.add_force(f)
        assert p.get_force_by_id('p1_f1') is f
        assert p.get_force_by_id('p1_f99') is None

    def test_get_alive_forces(self):
        p = Player(id='p1')
        f1 = Force(id='p1_f1', position=(0, 0), power=4)
        f2 = Force(id='p1_f2', position=(1, 0), power=1)
        f2.alive = False
        p.add_force(f1)
        p.add_force(f2)
        alive = p.get_alive_forces()
        assert len(alive) == 1
        assert alive[0].id == 'p1_f1'

    def test_update_shih_caps(self):
        p = Player(id='p1', shih=4, max_shih=8)
        p.update_shih(100)
        assert p.shih == 8
        p.update_shih(-100)
        assert p.shih == 0

    def test_known_enemy_powers(self):
        p = Player(id='p1')
        p.known_enemy_powers['p2_f1'] = 4
        assert p.known_enemy_powers['p2_f1'] == 4


class TestHex:
    def test_create_hex(self):
        h = Hex(q=3, r=3, terrain='Open')
        assert h.q == 3
        assert h.r == 3
        assert h.terrain == 'Open'

    def test_scorched_terrain(self):
        h = Hex(q=0, r=0, terrain='Scorched')
        assert h.terrain == 'Scorched'
