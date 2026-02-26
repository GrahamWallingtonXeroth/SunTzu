# The Unfought Battle v3 — Design Plan

## Problems to Solve

1. Shield-Sovereign beacon (pair always adjacent)
2. Scout role has no unique ability
3. Deterministic combat (scouting solves the game)
4. Endgame chase (no closing mechanism)
5. Shih is abundant/irrelevant
6. Feint is a no-op
7. Opening is solved (one correct deployment)
8. No way to project false information
9. Simultaneous orders = educated guessing (feedback too slow)
10. No turn pressure (patience always wins)
11. Domination victory unreachable
12. Dodge problem (can't force engagement)

## Core Design Changes

### A. Replace Fixed Roles with Concealed Power Values

Instead of 4 named roles with fixed stats, each player assigns **hidden power values** (1-5) to their 5 forces during deployment. Each value used exactly once. The Sovereign is whichever force is assigned value 1 — lose it, lose the game.

**Why this fixes problems 1, 2, 3, 7:**
- No Shield/Sovereign pair to watch for — any force could be any power
- No "Scout role" needed — power values are the only differentiation
- Combat still has hidden information even if you scout one force — you haven't narrowed the others much
- Deployment has 120 permutations (5!), not 1 dominant strategy
- Scouting reveals ONE number, not a role that tells you everything

**Power values: 1, 2, 3, 4, 5**
- Power 1 = the Sovereign. Lose it, lose the game.
- Powers 2-5 = soldiers with increasing combat strength.
- No special abilities tied to values. The game is pure information + positioning.

### B. Add Fog of War + Threat Projection

**Visibility:** You can only see enemy forces within **2 hexes** of any of your own alive forces. Beyond that, the board is dark. Enemy forces outside your vision are not shown in the state endpoint.

**Why this fixes problems 8, 9:**
- Now you CAN project false information: move forces into the fog and the enemy doesn't know where they went
- Moving out of vision and back in creates uncertainty — "is that the same force or a different one?"
- The feedback loop is richer: you see enemy movements in your vision range and must interpret them

**Threat projection:** A force you can see but haven't scouted could be power 1 or power 5. The THREAT of a force is its maximum possible power given what you know. This creates real tension.

### C. Shrinking Board (The Noose)

Every **4 turns**, the outermost ring of hexes becomes **Scorched** — impassable and deadly. Any force on a Scorched hex is eliminated. The playable board shrinks:

- Turns 1-4: full 7x7 (49 hexes)
- Turns 5-8: inner 5x5 equivalent (~37 hexes)
- Turns 9-12: inner 3x3 equivalent (~19 hexes)
- Turn 13+: just the center cluster

**Why this fixes problems 4, 10, 12:**
- The endgame chase ends because there's nowhere to run
- Patience is punished — the board is shrinking whether you're ready or not
- You can't dodge forever — eventually the noose forces contact
- Creates natural game pacing: opening (maneuver), midgame (contact), endgame (forced decisive combat)

**Implementation:** Track a `shrink_stage` on GameState. During upkeep, hexes at Manhattan distance > threshold from center become Scorched. Forces on them die. If a Sovereign dies this way, that player loses.

### D. Redesigned Orders

**Move (0 Shih):** Move to adjacent non-Scorched hex. Same as before.

**Scout (2 Shih):** Stay in place. Learn the power value of one enemy force within 2 hexes (not just adjacent). Revealed privately. **Key change:** range 2 instead of adjacent — scouting doesn't require suicidal proximity.

**Fortify (1 Shih):** Stay in place. +2 effective power this turn. Same as before.

**Ambush (2 Shih):** Stay in place. If an enemy moves to your hex or an adjacent hex THIS turn, you get +3 power in the resulting combat. The opponent doesn't know you ambushed. **Replaces Feint** — this is the offensive trap that creates real information warfare. "Did they ambush that hex? Do I walk into it?"

**Why this fixes problem 6:**
- Ambush replaces Feint and has real mechanical teeth
- Creates the bluffing/reading dynamic the game wants: "if I move there and they ambushed, I lose. If they didn't, I win."
- The opponent must consider: is that force sitting still because it's fortifying, scouting, or ambushing?

### E. Combat with Variance

Effective power = hidden value ± modifiers (fortify, ambush, terrain) + **coin flip modifier** (+1 or -1, randomly).

The random ±1 means a power-3 force beating a power-4 force happens ~sometimes. You can't guarantee outcomes even with perfect information. This creates:
- Risk assessment instead of lookup tables
- Upsets that create drama
- Incentive to stack advantages rather than rely on raw power
- Attacking a scouted force is still favorable but never certain

**Why this fixes problem 3:**
- Even perfect information doesn't solve the game
- Every combat has tension regardless of knowledge state
- The variance is small enough that stronger forces usually win but large enough that you can't ignore the risk

### F. Tighter Shih Economy

- Starting Shih: **5** (down from 8)
- Max Shih: **10** (down from 15)
- Base income: **1 per turn** (down from 2)
- Contentious bonus: **2 per hex** (up from 1)
- Scout: **3 Shih** (up from 2)
- Ambush: **2 Shih**
- Fortify: **1 Shih**
- Move: **0 Shih**

Now Contentious hexes are the primary income source. Controlling 1 hex = 3/turn (1 base + 2 bonus). Controlling 0 = 1/turn. A Scout costs 3 — that's 3 turns of base income. Resources force hard choices.

**Why this fixes problem 5:**
- Scouting is expensive — you can't scout everything
- You must choose: scout, fortify, or ambush? Can't do them all.
- Contentious control has real economic weight, not just a domination counter

### G. Domination Reworked

Control **2 of 3** Contentious hexes for **3 consecutive turns**. Not all 3 — that's impossible. Just majority control, sustained.

**Why this fixes problem 11:**
- 2 of 3 with 5 forces is achievable
- 3 turns is hard enough to be meaningful but reachable
- Creates genuine strategic tension: rush for terrain or hunt the Sovereign?

## Summary of New Model

```
Force: { id, position, power (1-5, hidden), revealed (bool), alive (bool) }
Player: { id, shih, forces, known_enemy_powers, domination_turns }

Orders: Move (0), Scout (3), Fortify (1), Ambush (2)
Visibility: 2 hex radius from own forces
Combat: attacker_power + modifiers + random(±1) vs defender_power + modifiers + random(±1)
Shrink: every 4 turns, outer ring becomes Scorched
Victory: Sovereign killed, Domination (2/3 for 3 turns), Elimination, Concession
```

## Files to Change

1. **config.json** — new values
2. **models.py** — Force.power replaces Force.role, remove ForceRole enum, add Scorched
3. **map_gen.py** — add center-distance calculation for shrinking
4. **state.py** — fog of war in player views, shrink_stage, deployment validates power 1-5
5. **orders.py** — Scout range 2, replace Feint with Ambush, new costs
6. **resolution.py** — power + modifiers + random variance, ambush bonus
7. **upkeep.py** — board shrinking, new domination rules (2/3 for 3 turns)
8. **app.py** — updated deploy, fog-filtered state
9. **tests/** — rewrite for new mechanics
