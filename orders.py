"""
Order processing for The Unfought Battle v8.

Five orders. Movement is free. Special orders require supply lines.

Move    — 0 Shih. Go to an adjacent non-Scorched hex. Always available.
Charge  — 2 Shih. Move up to 2 hexes. +1 attack if entering combat. Requires supply.
Scout   — 2 Shih. Stay put. Learn one enemy's power within 2 hexes. Requires supply.
Fortify — 2 Shih. Stay put. +2 combat power this turn. Requires supply.
Ambush  — 3 Shih. Stay put. +1 power when defending. Hidden. Requires supply.

Supply: A force has supply if it can chain back to the Sovereign through
friendly forces, where each link is within supply_range hexes and the total
chain depth does not exceed max_supply_hops. Forces without supply can only Move.

v8: Anti-Goodhart measurement overhaul. No game rule changes.

v7 changes:
- Supply chain hops limited by max_supply_hops (default 2) — supply no longer infinite.
- Scout/charge costs raised to 2 Shih.
"""

import json
import os
from enum import Enum
from typing import Optional, Tuple, List, Dict, Any
from models import Force
from state import GameState
from map_gen import hex_distance, get_hex_neighbors


class OrderType(Enum):
    MOVE = "Move"
    SCOUT = "Scout"
    FORTIFY = "Fortify"
    AMBUSH = "Ambush"
    CHARGE = "Charge"


def _load_order_config() -> Dict:
    """Load order-related config."""
    defaults = {
        'scout_cost': 1,
        'fortify_cost': 1,
        'ambush_cost': 2,
        'charge_cost': 1,
        'supply_range': 3,
        'max_supply_hops': 0,  # 0 = unlimited chain, >0 = max chain links
    }
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            for k in defaults:
                if k in config:
                    defaults[k] = config[k]
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return defaults


def _build_order_costs() -> Dict['OrderType', int]:
    """Build ORDER_COSTS from config."""
    cfg = _load_order_config()
    return {
        OrderType.MOVE: 0,
        OrderType.SCOUT: cfg['scout_cost'],
        OrderType.FORTIFY: cfg['fortify_cost'],
        OrderType.AMBUSH: cfg['ambush_cost'],
        OrderType.CHARGE: cfg['charge_cost'],
    }


ORDER_COSTS = _build_order_costs()


class Order:
    def __init__(self, order_type: OrderType, force: Force,
                 target_hex: Optional[Tuple[int, int]] = None,
                 scout_target_id: Optional[str] = None):
        self.order_type = order_type
        self.force = force
        self.target_hex = target_hex          # For Move and Charge
        self.scout_target_id = scout_target_id  # For Scout: which enemy force to reveal


class OrderValidationError(Exception):
    pass


def is_adjacent(current: Tuple[int, int], target: Tuple[int, int]) -> bool:
    """Check if target hex is adjacent to current hex in axial coordinates."""
    q1, r1 = current
    q2, r2 = target
    diffs = (q2 - q1, r2 - r1, (q1 + r1) - (q2 + r2))
    return diffs in [
        (1, 0, -1), (1, -1, 0), (0, -1, 1),
        (-1, 0, 1), (-1, 1, 0), (0, 1, -1),
    ]


def within_range(pos1: Tuple[int, int], pos2: Tuple[int, int], max_range: int) -> bool:
    """Check if two positions are within a given range."""
    return hex_distance(pos1[0], pos1[1], pos2[0], pos2[1]) <= max_range


def has_supply(force: Force, player_forces: List[Force], supply_range: int = 3,
               max_hops: int = 0) -> bool:
    """
    Check if a force has supply.

    A force has supply if:
    1. It IS the Sovereign, or
    2. It can be reached via a chain of friendly alive forces back to the Sovereign,
       where each link in the chain is within supply_range hexes.

    max_hops: maximum chain links allowed (0 = unlimited). When set to 1,
    a force must be directly within supply_range of the Sovereign — no relay.
    When set to 2, one intermediate relay is allowed, etc.

    Uses BFS from the Sovereign outward.
    """
    if force.power == 1:  # Is the Sovereign
        return True

    alive_forces = [f for f in player_forces if f.alive]

    # Find the Sovereign
    sovereign = None
    for f in alive_forces:
        if f.power == 1:
            sovereign = f
            break

    if sovereign is None:
        return False  # Sovereign dead = no supply for anyone

    # BFS: start from Sovereign, spread supply through chain
    supplied = {sovereign.id: 0}  # id -> hop count
    queue = [(sovereign, 0)]

    while queue:
        current, hops = queue.pop(0)
        for f in alive_forces:
            if f.id not in supplied:
                dist = hex_distance(
                    current.position[0], current.position[1],
                    f.position[0], f.position[1]
                )
                if dist <= supply_range:
                    new_hops = hops + 1
                    # If max_hops is set, don't chain beyond that depth
                    if max_hops > 0 and new_hops > max_hops:
                        continue
                    supplied[f.id] = new_hops
                    queue.append((f, new_hops))

    return force.id in supplied


def validate_order(order: Order, game_state: GameState, player_id: str) -> None:
    """Validate an order. Raises OrderValidationError if invalid."""
    player = game_state.get_player_by_id(player_id)
    if not player:
        raise OrderValidationError(f"Player {player_id} not found")

    force = order.force
    if not force.alive:
        raise OrderValidationError(f"Force {force.id} is dead")
    if force not in player.forces:
        raise OrderValidationError(f"Force {force.id} doesn't belong to {player_id}")

    cost = ORDER_COSTS[order.order_type]
    if player.shih < cost:
        raise OrderValidationError(
            f"Insufficient Shih: have {player.shih}, need {cost} for {order.order_type.value}"
        )

    # Supply check: special orders require supply line to Sovereign
    if order.order_type in (OrderType.SCOUT, OrderType.FORTIFY, OrderType.AMBUSH, OrderType.CHARGE):
        cfg = _load_order_config()
        supply_range = cfg['supply_range']
        max_hops = cfg['max_supply_hops']
        if not has_supply(force, player.forces, supply_range, max_hops=max_hops):
            raise OrderValidationError(
                f"Force {force.id} has no supply line to Sovereign — can only Move"
            )

    if order.order_type == OrderType.MOVE:
        if not order.target_hex:
            raise OrderValidationError("Move requires a target hex")
        if not game_state.is_valid_position(order.target_hex):
            raise OrderValidationError(f"Target {order.target_hex} is off the board or Scorched")
        if not is_adjacent(force.position, order.target_hex):
            raise OrderValidationError(f"Target {order.target_hex} is not adjacent to {force.position}")

    elif order.order_type == OrderType.CHARGE:
        if not order.target_hex:
            raise OrderValidationError("Charge requires a target hex")
        if not game_state.is_valid_position(order.target_hex):
            raise OrderValidationError(f"Target {order.target_hex} is off the board or Scorched")
        dist = hex_distance(force.position[0], force.position[1],
                           order.target_hex[0], order.target_hex[1])
        if dist < 1 or dist > 2:
            raise OrderValidationError(f"Charge target must be 1-2 hexes away, got {dist}")
        if dist == 2:
            # Verify there's a walkable intermediate hex (shared neighbor)
            intermediates = set(get_hex_neighbors(force.position[0], force.position[1]))
            target_neighbors = set(get_hex_neighbors(order.target_hex[0], order.target_hex[1]))
            shared = intermediates & target_neighbors
            valid_path = any(
                game_state.is_valid_position(h) for h in shared
            )
            if not valid_path:
                raise OrderValidationError("No valid path for 2-hex charge")

    elif order.order_type == OrderType.SCOUT:
        if not order.scout_target_id:
            raise OrderValidationError("Scout requires a scout_target_id")
        # The target must be an enemy force within scout range (2 hexes)
        opponent = game_state.get_opponent(player_id)
        if not opponent:
            raise OrderValidationError("No opponent found")
        target_force = opponent.get_force_by_id(order.scout_target_id)
        if not target_force:
            raise OrderValidationError(f"Enemy force {order.scout_target_id} not found")
        if not target_force.alive:
            raise OrderValidationError(f"Enemy force {order.scout_target_id} is dead")
        if not within_range(force.position, target_force.position, 2):
            raise OrderValidationError(
                f"Enemy force {order.scout_target_id} at {target_force.position} "
                f"is not within scout range (2) of {force.position}"
            )

    elif order.order_type == OrderType.FORTIFY:
        pass  # No additional validation needed

    elif order.order_type == OrderType.AMBUSH:
        pass  # No additional validation needed — just stay put and wait


def resolve_orders(
    p1_orders: List[Order],
    p2_orders: List[Order],
    game_state: GameState,
) -> Dict[str, Any]:
    """
    Resolve both players' orders simultaneously.

    Resolution order:
    1. Deduct Shih costs for all orders
    2. Apply Fortify markers
    3. Apply Ambush markers
    4. Process Moves and Charges simultaneously — detect collisions
    5. Resolve combats at contested hexes (ambush/charge bonuses apply)
    6. Apply Scout revelations
    7. Clear Fortify/Ambush/Charging markers at end of next resolution

    Returns a results dict with combats, scout results, and errors.
    """
    results: Dict[str, Any] = {
        'combats': [],
        'scouts': [],
        'movements': [],
        'errors': [],
        'sovereign_captured': None,
    }

    all_orders = [(o, 'p1') for o in p1_orders] + [(o, 'p2') for o in p2_orders]

    # Reset fortified/ambushing/charging status from last turn
    for player in game_state.players:
        for force in player.get_alive_forces():
            force.fortified = False
            force.ambushing = False
            force.charging = False

    # Phase 1: Deduct Shih and validate
    valid_orders: List[tuple] = []
    for order, pid in all_orders:
        try:
            validate_order(order, game_state, pid)
            player = game_state.get_player_by_id(pid)
            cost = ORDER_COSTS[order.order_type]
            player.update_shih(-cost)
            valid_orders.append((order, pid))
        except OrderValidationError as e:
            results['errors'].append({'player': pid, 'force': order.force.id, 'error': str(e)})

    # Track executed order counts (after validation and shih deduction)
    order_counts: Dict[str, int] = {}
    for order, pid in valid_orders:
        key = order.order_type.value.lower()
        order_counts[key] = order_counts.get(key, 0) + 1
    results['order_counts'] = order_counts

    # Phase 2: Apply Fortify
    for order, pid in valid_orders:
        if order.order_type == OrderType.FORTIFY:
            order.force.fortified = True
            game_state.log.append({
                'turn': game_state.turn, 'phase': 'resolve',
                'event': f'{order.force.id} fortifies at {order.force.position}',
            })

    # Phase 3: Apply Ambush
    for order, pid in valid_orders:
        if order.order_type == OrderType.AMBUSH:
            order.force.ambushing = True
            game_state.log.append({
                'turn': game_state.turn, 'phase': 'resolve',
                'event': f'{order.force.id} sets ambush at {order.force.position} (hidden)',
            })

    # Phase 4: Process Moves and Charges
    # Both are treated as movement orders with a target hex
    move_orders = [(o, pid) for o, pid in valid_orders
                   if o.order_type in (OrderType.MOVE, OrderType.CHARGE)]
    move_targets: Dict[Tuple[int, int], List[tuple]] = {}
    for order, pid in move_orders:
        target = order.target_hex
        if target not in move_targets:
            move_targets[target] = []
        move_targets[target].append((order, pid))

    # Also check for forces already occupying target hexes
    combats: List[Dict[str, Any]] = []
    moved_force_ids: set = set()

    for target, movers in move_targets.items():
        # Check if multiple forces from different players are moving to the same hex
        mover_players = set(pid for _, pid in movers)

        if len(mover_players) > 1:
            # Head-on collision: forces from both players moving to same hex
            p1_mover = next((o, pid) for o, pid in movers if pid == 'p1')
            p2_mover = next((o, pid) for o, pid in movers if pid == 'p2')
            combats.append({
                'attacker': p1_mover[0].force,
                'attacker_player': 'p1',
                'defender': p2_mover[0].force,
                'defender_player': 'p2',
                'hex': target,
                'type': 'collision',
                'attacker_charging': p1_mover[0].order_type == OrderType.CHARGE,
                'defender_charging': p2_mover[0].order_type == OrderType.CHARGE,
            })
            moved_force_ids.add(p1_mover[0].force.id)
            moved_force_ids.add(p2_mover[0].force.id)
        else:
            # All movers are from same player. Check if enemy occupies target.
            for order, pid in movers:
                occupant = game_state.get_force_at_position(target)
                if occupant and occupant.id not in moved_force_ids:
                    occ_owner = game_state.get_force_owner(occupant.id)
                    if occ_owner and occ_owner.id != pid:
                        # Moving into enemy-occupied hex
                        combats.append({
                            'attacker': order.force,
                            'attacker_player': pid,
                            'defender': occupant,
                            'defender_player': occ_owner.id,
                            'hex': target,
                            'type': 'assault',
                            'attacker_charging': order.order_type == OrderType.CHARGE,
                        })
                        moved_force_ids.add(order.force.id)
                    else:
                        # Moving into friendly-occupied hex — invalid, skip
                        results['errors'].append({
                            'player': pid,
                            'force': order.force.id,
                            'error': f'Cannot move to {target}: occupied by friendly force',
                        })
                else:
                    # Empty hex — move succeeds
                    old_pos = order.force.position
                    order.force.position = target
                    moved_force_ids.add(order.force.id)
                    results['movements'].append({
                        'force_id': order.force.id,
                        'from': old_pos,
                        'to': target,
                    })
                    game_state.log.append({
                        'turn': game_state.turn, 'phase': 'resolve',
                        'event': f'{order.force.id} moves from {old_pos} to {target}',
                    })

    # Phase 5: Resolve Combats
    from resolution import resolve_combat
    for combat in combats:
        # Set charging flags before combat resolution
        if combat.get('attacker_charging'):
            combat['attacker'].charging = True
        if combat.get('defender_charging'):
            combat['defender'].charging = True

        combat_result = resolve_combat(
            combat['attacker'], combat['attacker_player'],
            combat['defender'], combat['defender_player'],
            combat['hex'], game_state,
        )
        results['combats'].append(combat_result)
        if combat_result.get('sovereign_captured'):
            results['sovereign_captured'] = combat_result['sovereign_captured']

    # Phase 6: Apply Scouts
    for order, pid in valid_orders:
        if order.order_type == OrderType.SCOUT:
            player = game_state.get_player_by_id(pid)
            opponent = game_state.get_opponent(pid)
            if player and opponent:
                target_force = opponent.get_force_by_id(order.scout_target_id)
                if target_force and target_force.alive and within_range(order.force.position, target_force.position, 2):
                    # Reveal to this player only (not public)
                    power_val = target_force.power if target_force.power is not None else 0
                    player.known_enemy_powers[target_force.id] = power_val
                    results['scouts'].append({
                        'scouting_force': order.force.id,
                        'scouted_force': target_force.id,
                        'revealed_power': power_val,
                        'player': pid,
                    })
                    game_state.log.append({
                        'turn': game_state.turn, 'phase': 'resolve',
                        'event': f'{order.force.id} scouted {target_force.id}: power {power_val} (private to {pid})',
                    })

    return results
