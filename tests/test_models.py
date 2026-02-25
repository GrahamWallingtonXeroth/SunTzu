"""Tests for the data model layer."""

import pytest
from models import Force, Player, ForceRole, ROLE_POWER, ROLE_COUNTS, Hex


class TestForceRole:
    def test_role_values(self):
        assert ForceRole.SOVEREIGN.value == "Sovereign"
        assert ForceRole.VANGUARD.value == "Vanguard"
        assert ForceRole.SCOUT.value == "Scout"
        assert ForceRole.SHIELD.value == "Shield"

    def test_role_power(self):
        assert ROLE_POWER[ForceRole.SOVEREIGN] == 1
        assert ROLE_POWER[ForceRole.VANGUARD] == 4
        assert ROLE_POWER[ForceRole.SCOUT] == 2
        assert ROLE_POWER[ForceRole.SHIELD] == 3

    def test_role_counts(self):
        assert ROLE_COUNTS[ForceRole.SOVEREIGN] == 1
        assert ROLE_COUNTS[ForceRole.VANGUARD] == 2
        assert ROLE_COUNTS[ForceRole.SCOUT] == 1
        assert ROLE_COUNTS[ForceRole.SHIELD] == 1
        assert sum(ROLE_COUNTS.values()) == 5


class TestForce:
    def test_create_force(self):
        f = Force(id='p1_f1', position=(0, 0))
        assert f.id == 'p1_f1'
        assert f.position == (0, 0)
        assert f.role is None
        assert f.revealed is False
        assert f.alive is True
        assert f.fortified is False

    def test_base_power_no_role(self):
        f = Force(id='p1_f1', position=(0, 0))
        assert f.base_power == 0

    def test_base_power_with_role(self):
        f = Force(id='p1_f1', position=(0, 0), role=ForceRole.VANGUARD)
        assert f.base_power == 4

    def test_base_power_sovereign(self):
        f = Force(id='p1_f1', position=(0, 0), role=ForceRole.SOVEREIGN)
        assert f.base_power == 1


class TestPlayer:
    def test_create_player(self):
        p = Player(id='p1')
        assert p.shih == 8
        assert p.max_shih == 15
        assert p.deployed is False
        assert p.domination_turns == 0
        assert len(p.forces) == 0
        assert len(p.known_enemy_roles) == 0

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
        f1 = Force(id='p1_f1', position=(0, 0), role=ForceRole.VANGUARD)
        f2 = Force(id='p1_f2', position=(1, 0), role=ForceRole.SOVEREIGN)
        f2.alive = False
        p.add_force(f1)
        p.add_force(f2)
        alive = p.get_alive_forces()
        assert len(alive) == 1
        assert alive[0].id == 'p1_f1'

    def test_update_shih_caps(self):
        p = Player(id='p1', shih=8, max_shih=15)
        p.update_shih(100)
        assert p.shih == 15
        p.update_shih(-100)
        assert p.shih == 0

    def test_known_enemy_roles(self):
        p = Player(id='p1')
        p.known_enemy_roles['p2_f1'] = 'Vanguard'
        assert p.known_enemy_roles['p2_f1'] == 'Vanguard'
