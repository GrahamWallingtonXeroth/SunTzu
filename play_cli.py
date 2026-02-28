"""
CLI play mode for The Unfought Battle.

Human vs AI on a 7x7 hex grid. ASCII renderer, deploy phase,
order entry, resolution display, full game loop.

Usage: python play_cli.py
"""

import random

from map_gen import BOARD_SIZE, hex_distance
from orders import ORDER_COSTS, Order, OrderType, _load_order_config, has_supply, resolve_orders
from state import GameState, apply_deployment, initialize_game, is_visible_to_player, load_config
from tests.simulate import (
    AggressiveStrategy,
    BlitzerStrategy,
    CautiousStrategy,
    CoordinatorStrategy,
    SovereignHunterStrategy,
    Strategy,
)
from tests.strategies_advanced import (
    BayesianHunterStrategy,
    LookaheadStrategy,
    PatternReaderStrategy,
    SupplyCutterStrategy,
)
from upkeep import perform_upkeep

MAX_TURNS = 30

AVAILABLE_STRATEGIES = [
    AggressiveStrategy(),
    CautiousStrategy(),
    BlitzerStrategy(),
    SovereignHunterStrategy(),
    CoordinatorStrategy(),
    PatternReaderStrategy(),
    SupplyCutterStrategy(),
    BayesianHunterStrategy(),
    LookaheadStrategy(),
]

TERRAIN_CHAR = {
    "Open": ".",
    "Difficult": "#",
    "Contentious": "*",
    "Scorched": "X",
}


# ---------------------------------------------------------------------------
# ASCII Hex Renderer
# ---------------------------------------------------------------------------


def render_board(game: GameState, player_id: str):
    """Render the board from a player's perspective with fog of war."""
    config = load_config()
    vis_range = config.get("visibility_range", 2)
    player = game.get_player_by_id(player_id)
    opponent = game.get_opponent(player_id)

    # Build lookup: position -> display character
    display = {}
    for pos, h in game.map_data.items():
        display[pos] = TERRAIN_CHAR.get(h.terrain, ".")

    # Own forces: show power number
    for f in player.get_alive_forces():
        display[f.position] = str(f.power) if f.power else "?"

    # Enemy forces: show '?' or scouted power if visible
    if opponent:
        for f in opponent.get_alive_forces():
            if is_visible_to_player(f.position, player, vis_range):
                if f.revealed:
                    display[f.position] = str(f.power)
                elif f.id in player.known_enemy_powers:
                    display[f.position] = str(player.known_enemy_powers[f.id])
                else:
                    display[f.position] = "?"

    # Print the grid row by row with offset for hex effect
    print()
    # Header
    print("    q: " + "  ".join(str(q) for q in range(BOARD_SIZE)))
    print("  r  " + "-" * (BOARD_SIZE * 3))
    for r in range(BOARD_SIZE):
        offset = "  " if r % 2 == 0 else " "
        row_chars = []
        for q in range(BOARD_SIZE):
            row_chars.append(display.get((q, r), " "))
        print(f"  {r} {offset}" + "  ".join(row_chars))
    print()


# ---------------------------------------------------------------------------
# Deploy Phase
# ---------------------------------------------------------------------------


def deploy_human(game: GameState, player_id: str):
    """Interactive deployment: assign powers 1-5 to forces."""
    player = game.get_player_by_id(player_id)
    print("\n=== DEPLOYMENT PHASE ===")
    print("Assign power values 1-5 to your forces (each used exactly once).")
    print("Power 1 = Sovereign (lose it, lose the game).")
    print()
    print("Your forces and starting positions:")
    for f in player.forces:
        print(f"  {f.id}  at ({f.position[0]},{f.position[1]})")

    render_board(game, player_id)

    while True:
        print("Format: assign f1=5 f2=4 f3=1 f4=3 f5=2")
        print("  (use force numbers 1-5, e.g. f1 for p1_f1)")
        raw = input("> ").strip()
        if not raw.startswith("assign"):
            print("Command must start with 'assign'.")
            continue
        parts = raw.split()[1:]
        assignments = {}
        ok = True
        for part in parts:
            if "=" not in part:
                print(f"  Bad token: {part}  (expected fN=P)")
                ok = False
                break
            key, val = part.split("=", 1)
            force_id = f"{player_id}_{key}"
            try:
                power = int(val)
            except ValueError:
                print(f"  Bad power value: {val}")
                ok = False
                break
            if not player.get_force_by_id(force_id):
                print(f"  Unknown force: {force_id}")
                ok = False
                break
            assignments[force_id] = power
        if not ok:
            continue
        err = apply_deployment(game, player_id, assignments)
        if err:
            print(f"  Error: {err}")
        else:
            print("Deployed successfully.")
            break


def deploy_ai(game: GameState, ai_player_id: str, strategy: Strategy, rng: random.Random):
    """AI deploys using its strategy."""
    player = game.get_player_by_id(ai_player_id)
    assignments = strategy.deploy(player, rng)
    err = apply_deployment(game, ai_player_id, assignments)
    if err:
        print(f"AI deploy error: {err}")
    else:
        print(f"AI ({strategy.name}) deployed.")


# ---------------------------------------------------------------------------
# Order Phase
# ---------------------------------------------------------------------------


def show_status(game: GameState, player_id: str):
    """Show turn info, Shih, domination, known enemy powers, and force details."""
    player = game.get_player_by_id(player_id)
    opponent = game.get_opponent(player_id)
    config = load_config()
    vis_range = config.get("visibility_range", 2)
    order_cfg = _load_order_config()
    supply_range = order_cfg["supply_range"]
    max_hops = order_cfg["max_supply_hops"]

    print(f"\n=== TURN {game.turn} ===")
    print(f"  Your Shih: {player.shih}    Enemy Shih: {opponent.shih if opponent else '?'}")
    print(f"  Domination: You={player.domination_turns}/3  Enemy={opponent.domination_turns}/3" if opponent else "")
    print(f"  Shrink stage: {game.shrink_stage}")

    # Known enemy powers
    if player.known_enemy_powers:
        known = ", ".join(f"{fid}=pow{p}" for fid, p in player.known_enemy_powers.items())
        print(f"  Known enemy powers: {known}")

    # Order costs reminder
    print(
        f"  Costs: Scout={ORDER_COSTS[OrderType.SCOUT]}, Fortify={ORDER_COSTS[OrderType.FORTIFY]}, "
        f"Ambush={ORDER_COSTS[OrderType.AMBUSH]}, Charge={ORDER_COSTS[OrderType.CHARGE]}, Move=free"
    )

    render_board(game, player_id)

    print("Your forces:")
    for f in player.get_alive_forces():
        supplied = has_supply(f, player.forces, supply_range, max_hops=max_hops)
        sov_tag = " [SOVEREIGN]" if f.is_sovereign else ""
        supply_tag = " [supplied]" if supplied else " [NO SUPPLY]"

        # Adjacent enemies
        adj_enemies = []
        if opponent:
            for ef in opponent.get_alive_forces():
                d = hex_distance(f.position[0], f.position[1], ef.position[0], ef.position[1])
                if d <= vis_range:
                    pwr = "?"
                    if ef.revealed:
                        pwr = str(ef.power)
                    elif ef.id in player.known_enemy_powers:
                        pwr = str(player.known_enemy_powers[ef.id])
                    dist_tag = "adj" if d == 1 else f"d={d}"
                    adj_enemies.append(f"{ef.id}(pow={pwr},{dist_tag})")

        enemy_str = f"  nearby: {', '.join(adj_enemies)}" if adj_enemies else ""
        print(f"  {f.id}  pow={f.power}  pos=({f.position[0]},{f.position[1]}){sov_tag}{supply_tag}{enemy_str}")


def get_human_orders(game: GameState, player_id: str) -> list:
    """Collect orders from human player. Returns list of Order objects."""
    player = game.get_player_by_id(player_id)
    opponent = game.get_opponent(player_id)
    orders = []
    ordered_forces = set()

    print("\nEnter orders (one per line). Commands:")
    print("  move <force> <q> <r>     - move to adjacent hex")
    print("  charge <force> <q> <r>   - charge up to 2 hexes")
    print("  scout <force> <enemy_id> - reveal enemy power")
    print("  fortify <force>          - fortify in place")
    print("  ambush <force>           - ambush in place")
    print("  auto                     - AI orders for remaining forces")
    print("  done                     - finish (unordered forces hold)")
    print("  (force = f1..f5, e.g. 'move f2 3 4')")

    while True:
        raw = input("order> ").strip().lower()
        if not raw:
            continue

        if raw == "done":
            break

        if raw == "auto":
            # Use AggressiveStrategy as the auto-pilot for remaining forces
            auto_strat = AggressiveStrategy()
            auto_rng = random.Random()
            all_auto = auto_strat.plan(player_id, game, auto_rng)
            for o in all_auto:
                if o.force.id not in ordered_forces:
                    orders.append(o)
                    ordered_forces.add(o.force.id)
                    print(
                        f"  auto: {o.force.id} -> {o.order_type.value}"
                        f"{' to ' + str(o.target_hex) if o.target_hex else ''}"
                        f"{' on ' + str(o.scout_target_id) if o.scout_target_id else ''}"
                    )
            break

        tokens = raw.split()
        cmd = tokens[0]

        if cmd in ("move", "charge"):
            if len(tokens) < 4:
                print("  Usage: move <force> <q> <r>")
                continue
            force_key = f"{player_id}_{tokens[1]}"
            try:
                tq, tr = int(tokens[2]), int(tokens[3])
            except ValueError:
                print("  q and r must be integers.")
                continue
            force = player.get_force_by_id(force_key)
            if not force or not force.alive:
                print(f"  Force {force_key} not found or dead.")
                continue
            if force.id in ordered_forces:
                print(f"  {force.id} already has an order this turn.")
                continue
            otype = OrderType.MOVE if cmd == "move" else OrderType.CHARGE
            orders.append(Order(otype, force, target_hex=(tq, tr)))
            ordered_forces.add(force.id)
            print(f"  -> {force.id} {cmd} to ({tq},{tr})")

        elif cmd == "scout":
            if len(tokens) < 3:
                print("  Usage: scout <force> <enemy_id>")
                continue
            force_key = f"{player_id}_{tokens[1]}"
            # Allow both "p2_f3" and "f3" (auto-prefix enemy)
            enemy_id = tokens[2]
            if not enemy_id.startswith("p"):
                enemy_pid = opponent.id if opponent else "p2"
                enemy_id = f"{enemy_pid}_{enemy_id}"
            force = player.get_force_by_id(force_key)
            if not force or not force.alive:
                print(f"  Force {force_key} not found or dead.")
                continue
            if force.id in ordered_forces:
                print(f"  {force.id} already has an order this turn.")
                continue
            orders.append(Order(OrderType.SCOUT, force, scout_target_id=enemy_id))
            ordered_forces.add(force.id)
            print(f"  -> {force.id} scouts {enemy_id}")

        elif cmd in ("fortify", "ambush"):
            if len(tokens) < 2:
                print(f"  Usage: {cmd} <force>")
                continue
            force_key = f"{player_id}_{tokens[1]}"
            force = player.get_force_by_id(force_key)
            if not force or not force.alive:
                print(f"  Force {force_key} not found or dead.")
                continue
            if force.id in ordered_forces:
                print(f"  {force.id} already has an order this turn.")
                continue
            otype = OrderType.FORTIFY if cmd == "fortify" else OrderType.AMBUSH
            orders.append(Order(otype, force))
            ordered_forces.add(force.id)
            print(f"  -> {force.id} {cmd}")

        else:
            print(f"  Unknown command: {cmd}")

    return orders


# ---------------------------------------------------------------------------
# Resolution Display
# ---------------------------------------------------------------------------


def show_resolution(result: dict, game: GameState, player_id: str):
    """Display what happened during resolution."""
    print("\n--- Resolution ---")

    # Movements
    for mv in result.get("movements", []):
        print(f"  {mv['force_id']} moved {mv['from']} -> {mv['to']}")

    # Combats
    for cb in result.get("combats", []):
        att = cb.get("attacker_id", "?")
        dfn = cb.get("defender_id", "?")
        att_p = cb.get("attacker_power", "?")
        def_p = cb.get("defender_power", "?")
        outcome = cb.get("outcome", "?")
        print(f"  COMBAT at {cb.get('hex', '?')}: {att}(eff={att_p}) vs {dfn}(eff={def_p})")
        print(f"    base powers: {cb.get('attacker_base_power', '?')} vs {cb.get('defender_base_power', '?')}")
        if "eliminated" in cb:
            print(f"    ELIMINATED: {cb['eliminated']}")
        if "retreated" in cb:
            print(f"    retreated: {cb['retreated']} -> {cb.get('retreat_to', '?')}")
        if outcome == "stalemate":
            print("    STALEMATE - both retreat")
        if cb.get("sovereign_captured"):
            cap = cb["sovereign_captured"]
            print(f"    *** SOVEREIGN CAPTURED! Winner: {cap['winner']} ***")

    # Scouts (only show player's own scouts)
    for sc in result.get("scouts", []):
        if sc.get("player") == player_id:
            print(f"  SCOUT: {sc['scouting_force']} reveals {sc['scouted_force']} = power {sc['revealed_power']}")

    # Errors
    for err in result.get("errors", []):
        if err.get("player") == player_id:
            print(f"  ERROR: {err['force']}: {err['error']}")

    if not any([result.get("movements"), result.get("combats"), result.get("scouts"), result.get("errors")]):
        print("  (nothing happened)")


def show_upkeep(upkeep: dict, game: GameState, player_id: str):
    """Display upkeep results."""
    # Noose events
    for evt in upkeep.get("noose_events", []):
        if evt.get("type") == "scorched":
            print(f"  The Noose scorches hex {evt['hex']}")
        elif evt.get("type") == "force_scorched":
            sov = " (SOVEREIGN!)" if evt.get("was_sovereign") else ""
            print(f"  {evt['force_id']} consumed by the Noose at {evt['position']}{sov}")

    # Shih income
    for pid, income in upkeep.get("shih_income", {}).items():
        tag = "You" if pid == player_id else "Enemy"
        print(f"  {tag} earns {income} Shih")

    # Domination
    for pid, turns in upkeep.get("domination_progress", {}).items():
        if turns > 0:
            tag = "You" if pid == player_id else "Enemy"
            print(f"  {tag} domination progress: {turns}/3")


# ---------------------------------------------------------------------------
# Main Game Loop
# ---------------------------------------------------------------------------


def choose_strategy() -> Strategy:
    """Let the player pick an AI opponent."""
    print("\nChoose AI opponent:")
    for i, s in enumerate(AVAILABLE_STRATEGIES, 1):
        print(f"  {i}. {s.name}")
    while True:
        raw = input("Pick (number): ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(AVAILABLE_STRATEGIES):
                return AVAILABLE_STRATEGIES[idx]
        except ValueError:
            pass
        print(f"  Enter 1-{len(AVAILABLE_STRATEGIES)}")


def choose_side() -> str:
    """Let the player choose p1 or p2."""
    print("\nPlay as Player 1 (left) or Player 2 (right)?")
    print("  1. Player 1 (start left)")
    print("  2. Player 2 (start right)")
    while True:
        raw = input("Pick (1 or 2): ").strip()
        if raw == "1":
            return "p1"
        if raw == "2":
            return "p2"
        print("  Enter 1 or 2")


def main():
    print("=" * 50)
    print("  THE UNFOUGHT BATTLE  -  CLI Play Mode")
    print("=" * 50)

    ai_strategy = choose_strategy()
    human_side = choose_side()
    ai_side = "p2" if human_side == "p1" else "p1"

    seed = random.randint(0, 99999)
    rng = random.Random(seed)
    print(f"\nMap seed: {seed}")

    game = initialize_game(seed)

    # --- Deploy Phase ---
    if human_side == "p1":
        deploy_human(game, human_side)
        deploy_ai(game, ai_side, ai_strategy, rng)
    else:
        deploy_ai(game, ai_side, ai_strategy, rng)
        deploy_human(game, human_side)

    # --- Game Loop ---
    while game.phase != "ended" and game.turn <= MAX_TURNS:
        if game.phase != "plan":
            break

        # Show status and board
        show_status(game, human_side)

        # Collect orders
        human_orders = get_human_orders(game, human_side)
        ai_orders = ai_strategy.plan(ai_side, game, rng)

        # Resolve
        game.phase = "resolve"
        if human_side == "p1":
            result = resolve_orders(human_orders, ai_orders, game)
        else:
            result = resolve_orders(ai_orders, human_orders, game)

        show_resolution(result, game, human_side)

        # Upkeep
        sovereign_capture = result.get("sovereign_captured")
        upkeep = perform_upkeep(game, sovereign_capture)
        show_upkeep(upkeep, game, human_side)

        if upkeep.get("winner"):
            break

    # --- End ---
    print("\n" + "=" * 50)
    if game.winner == "draw":
        print("  RESULT: DRAW (mutual destruction)")
    elif game.winner == human_side:
        print(f"  VICTORY! You win by {game.victory_type}!")
    elif game.winner:
        print(f"  DEFEAT. {ai_strategy.name} wins by {game.victory_type}.")
    else:
        print("  Game ended (turn limit reached). No winner.")
    print(f"  Final turn: {game.turn}")
    print("=" * 50)


if __name__ == "__main__":
    main()
