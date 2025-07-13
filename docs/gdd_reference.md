# GDD Reference Excerpts for Sun Tzu: The Unfought Battle

This file extracts key sections from the Game Design Document (GDD) PDF for quick code reference. Full GDD in docs/TheUnfoughtBattle.pdf (attach if needed).

## 1. Core Resources
- Chi (Morale): Starts at 100, drops to 0 = defeat. Lost in confrontations; no regain.
- Shih (Momentum): Starts at 10, max 20 (excess lost). Spent on orders, regained via positioning/meditation.

## 2. Terrains
| Terrain | Shih Cost to Enter | Shih Yield per Turn (if Controlled) | Special Properties |
|---------|--------------------|-------------------------------------|---------------------|
| Open Ground | 1 | 0 | Neutral: Standard movement/confrontations. |
| Difficult Ground | 2 | 0 | Barrier: No Thunder Stance; ideal for defense. |
| Contentious Ground | 1 | +2 | Objective: Double Chi loss on loss; control grants Shih. |

Control: Occupied by friendly force with no adjacent enemies.

## 3. Map Generation
- Grid: 25x20 hexes, axial coords (q, r).
- Algorithm:
  1. Seed RNG.
  2. Player starts: P1 at (0,0), P2 at (24,19) on Open.
  3. 3-5 Contentious hexes near center (q=10-15, r=8-12).
  4. Paths: A* connect starts to center with Open (min 5 hexes/path).
  5. Barriers: Perlin noise (threshold 0.6) for Difficult (20-30% coverage, 2+ chokepoints/path).
  6. Balance: Symmetric access (±2 hexes); regenerate if not.

Use NumPy for coords/noise.

## 4. Forces and Orders
- 3 Forces per player (abstract armies).
- Phases: Plan (secret orders), Execute (simultaneous resolve), Upkeep (resources/victory).
- Orders:
  | Order | Shih Cost | Effect |
  |-------|-----------|--------|
  | Advance | 2 | Move to adjacent hex; confront if enemy. Choose stance. |
  | Meditate | 0 | Stay; +2 Shih next turn; reveal adjacent enemy orders (not stances). |
  | Deceive | 3 | Stay; create ghost in adjacent (looks like force; wastes enemy move if advanced into). |

Ghosts: Dissipate after Execute; intangible.

## 5. Confrontations and Stances
- Trigger: Advance into enemy hex.
- Stances (rock-paper-scissors):
  - Mountain (defensive): Beats Thunder.
  - River (evasive): Beats Mountain.
  - Thunder (aggressive): Beats River.
- Resolution:
  - Winner: Loser loses base Chi (8), doubled on Contentious; loser retreats (or extra Chi loss if can't).
  - Stalemate (same stance): Both lose 4 Chi; both retreat.
- Terrain mod: Difficult blocks Thunder for defender.

## 6. Victory Conditions
1. Demoralization: Opponent Chi <= 0.
2. Domination: Control all Contentious for one full turn.
3. Deception Mastery: Encircle enemy force (all adjacent hexes blocked by enemies/ghosts) for 2 turns (-20 Chi instant).

Tie: Higher Shih wins.

## 7. Advanced Systems
- Tendency: Last 3 orders per force (visible to opponent).
  - All same: -1 stance mod (predictable).
  - All unique: +1 stance mod (unpredictable).

## 8. API/JSON Schema
See api_endpoints.md for details. State JSON example in GDD section 11.

Tunables: config.json with defaults like starting_chi=100, base_chi_loss=8.