# API Endpoints for Sun Tzu: The Unfought Battle

This document details the headless API endpoints for game simulation. All endpoints use JSON for requests/responses.

**Base URL:** `/api` (e.g., `http://localhost:5000/api/game/new`)

**Error Format:** HTTP 4xx/5xx responses return JSON with `{"error": "message"}`

---

## 1. Create New Game

**Method:** `POST`  
**Path:** `/game/new`  
**Description:** Creates a new game instance with a procedural map and initial state.

### Request Body (JSON)

```json
{
  "seed": 42
}
```

**Parameters:**
- `seed` (integer, optional): RNG seed for map reproducibility (default: 42)

### Response (200 OK)

```json
{
  "game_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Notes:** Returns a UUID4 game identifier for accessing the game.

---

## 2. Get Game State

**Method:** `GET`  
**Path:** `/game/<game_id>/state` (e.g., `/game/550e8400-e29b-41d4-a716-446655440000/state`)  
**Description:** Retrieves the current game state, including map, players, forces, and order submission status.

### Query Parameters
None

### Response (200 OK)

```json
{
  "game_id": "550e8400-e29b-41d4-a716-446655440000",
  "turn": 1,
  "phase": "plan",
  "orders_submitted": {
    "p1": false,
    "p2": false
  },
  "players": [
    {
      "id": "p1",
      "chi": 100,
      "shih": 10,
      "forces": [
        {
          "id": "p1_f1",
          "position": {"q": 0, "r": 0},
          "stance": "Mountain"
        },
        {
          "id": "p1_f2", 
          "position": {"q": 1, "r": 0},
          "stance": "Mountain"
        },
        {
          "id": "p1_f3",
          "position": {"q": 0, "r": 1}, 
          "stance": "Mountain"
        }
      ]
    },
    {
      "id": "p2",
      "chi": 100,
      "shih": 10,
      "forces": [
        {
          "id": "p2_f1",
          "position": {"q": 24, "r": 19},
          "stance": "Mountain"
        },
        {
          "id": "p2_f2",
          "position": {"q": 23, "r": 19},
          "stance": "Mountain"
        },
        {
          "id": "p2_f3",
          "position": {"q": 24, "r": 18},
          "stance": "Mountain"
        }
      ]
    }
  ],
  "map": [
    {"q": 0, "r": 0, "terrain": "Open"},
    {"q": 1, "r": 0, "terrain": "Open"},
    {"q": 12, "r": 10, "terrain": "Contentious"},
    {"q": 5, "r": 8, "terrain": "Difficult"},
    ...
  ]
}
```

**Phase Values:** "plan", "execute", "upkeep", "ended"  
**Terrain Types:** "Open", "Difficult", "Contentious"  
**Stance Types:** "Mountain", "River", "Thunder"

---

## 3. Submit Player Orders

**Method:** `POST`  
**Path:** `/game/<game_id>/action`  
**Description:** Submits orders for a player's forces in the plan phase. Phase transitions to 'execute' only when both players have submitted orders.

### Request Body (JSON)

```json
{
  "player_id": "p1",
  "orders": [
    {
      "force_id": "p1_f1",
      "order": "Advance",
      "target_hex": {"q": 1, "r": 0},
      "stance": "Mountain"
    },
    {
      "force_id": "p1_f2",
      "order": "Meditate"
    },
    {
      "force_id": "p1_f3",
      "order": "Deceive",
      "target_hex": {"q": 1, "r": 1}
    }
  ]
}
```

**Required Fields:**
- `player_id`: "p1" or "p2"
- `orders`: Array of order objects

**Order Types:**
- `"Advance"`: Requires `target_hex` and `stance`, costs 2 Shih
- `"Meditate"`: No additional fields, gains +2 Shih next turn, reveals adjacent enemy orders
- `"Deceive"`: Requires `target_hex`, costs 3 Shih, creates ghost

**Stance Types:** "Mountain", "River", "Thunder" (for Advance orders only)

### Response (200 OK)

```json
{
  "game_id": "550e8400-e29b-41d4-a716-446655440000",
  "turn": 1,
  "phase": "plan",
  "orders_processed": 3,
  "revealed_orders": [
    ["p2_f1", "Advance"]
  ],
  "confrontations": [
    {
      "attacking_force": "p1_f1",
      "target_hex": [1, 0],
      "occupying_force": "p2_f2",
      "ghost_owner": null
    }
  ],
  "errors": [],
  "orders_submitted": {
    "p1": true,
    "p2": false
  },
  "state": {
    // ... full game state as in GET /state
  }
}
```

**Notes:** 
- Validates Shih costs and terrain restrictions
- Each player can only submit orders once per turn
- Phase transitions to 'execute' when both players submit
- Returns updated game state and order processing results
- Logs all actions for analysis

### Error Responses

**400 Bad Request:**
- Invalid JSON data
- Missing required fields
- Wrong phase (not 'plan')
- Player already submitted orders
- Insufficient Shih
- Invalid order parameters

---

## 4. Perform Upkeep

**Method:** `POST`  
**Path:** `/game/<game_id>/upkeep`  
**Description:** Performs upkeep phase operations including Shih yields, encirclement checks, and victory conditions. Advances to next turn.

### Request Body
Empty

### Response (200 OK)

```json
{
  "game_id": "550e8400-e29b-41d4-a716-446655440000",
  "turn": 2,
  "phase": "plan",
  "winner": null,
  "shih_yields": {
    "p1": 4,
    "p2": 0
  },
  "encirclements": [
    {
      "force_id": "p2_f1",
      "player_id": "p2", 
      "turns_encircled": 2
    }
  ],
  "state": {
    // ... full game state
  }
}
```

**Operations Performed:**
- Calculate Shih yields from controlled Contentious terrain (+2 per hex)
- Check for encirclements and apply penalties (-20 Chi after 2 turns)
- Check victory conditions (Demoralization, Domination, Encirclement)
- Advance turn and reset phase to 'plan' (unless game ended)

### Error Responses

**400 Bad Request:** Not in 'execute' phase  
**404 Not Found:** Game not found

---

## 5. Get Game Log

**Method:** `GET`  
**Path:** `/game/<game_id>/log`  
**Description:** Returns a complete event log for analysis and debugging.

### Response (200 OK)

```json
{
  "game_id": "550e8400-e29b-41d4-a716-446655440000",
  "turn": 2,
  "phase": "plan",
  "log": [
    {
      "turn": 1,
      "phase": "plan",
      "event": "Player p1 submitted Advance for force p1_f1 to (1,0) with Mountain stance"
    },
    {
      "turn": 1,
      "phase": "plan", 
      "event": "Order validated successfully for force p1_f1"
    },
    {
      "turn": 1,
      "phase": "execute",
      "event": "Confrontation initiated: p1_f1 (Mountain) vs p2_f2 at (1,0)"
    },
    {
      "turn": 1,
      "phase": "upkeep",
      "event": "Player p1 gains 4 Shih from Contentious terrain"
    }
  ]
}
```

**Log Event Types:**
- Order submission and validation
- Force movements and confrontations
- Shih gains/losses and Chi penalties
- Phase transitions and turn advancement
- Victory conditions and game end

---

## Implementation Notes

### Phase Cycle
1. **Plan Phase**: Players submit orders (both must submit before advancing)
2. **Execute Phase**: Orders resolved, confrontations occur, automatic phase transition
3. **Upkeep Phase**: Resource yields, victory checks, turn advancement

### Order Validation
- Shih requirements: Advance (2), Deceive (3), Meditate (0)
- Terrain restrictions: Thunder stance forbidden on Difficult terrain
- Adjacency: Target hexes must be adjacent to force position
- Map bounds: All positions validated against 25x20 hex grid

### Confrontation System
- Stance effectiveness: Mountain > Thunder > River > Mountain
- Tendency modifiers: Predictable (-1), Unpredictable (+1), Mixed (0)
- Chi loss: Base 8, doubled on Contentious terrain
- Retreat mechanics with position validation

### Victory Conditions
- **Demoralization**: Opponent Chi ≤ 0
- **Domination**: Control all Contentious terrain for one full turn
- **Encirclement**: Force surrounded for 2+ turns (-20 Chi penalty)

### Error Handling
- Comprehensive validation with detailed error messages
- Graceful handling of invalid game states
- Transaction-like order processing (all or none)

### Testing
- Full test coverage in `tests/test_api.py`
- Use pytest: `pytest tests/test_api.py`
- Mock game states for isolated testing