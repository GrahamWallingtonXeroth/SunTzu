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
  "seed": 42,
  "player1_type": "human",
  "player2_type": "ai"
}
```

**Parameters:**
- `seed` (integer, optional): RNG seed for map reproducibility (default: random)
- `player1_type` (string): "human", "ai", or "llm" (future)
- `player2_type` (string): Same as above

### Response (201 Created)

```json
{
  "game_id": "abc123"
}
```

**Example:** Use Postman or curl to test later.

---

## 2. Get Game State

**Method:** `GET`  
**Path:** `/game/<game_id>/state` (e.g., `/game/abc123/state`)  
**Description:** Retrieves the current game state, including map, players, forces, etc.

### Query Parameters
None

### Response (200 OK)

Follows the JSON schema from GDD section 11:

```json
{
  "game_id": "abc123",
  "turn": 1,
  "phase": "plan",
  "players": [
    {
      "id": "p1",
      "chi": 100,
      "shih": 10,
      "forces": [
        {
          "id": "f1",
          "position": {"q": 0, "r": 0},
          "tendency": ["advance", "meditate"],
          "stance": null
        }
      ]
    }
  ],
  "map": [
    {"q": 0, "r": 0, "terrain": "open", "controlled_by": null}
  ],
  "ghosts": []
}
```

**Phase Values:** "plan", "execute", "upkeep"  
**Example:** Returns full state for clients to render or LLMs to analyze.

---

## 3. Submit Player Actions/Orders

**Method:** `POST`  
**Path:** `/action/<player_id>` (e.g., `/action/p1`)  
**Description:** Submits orders for a player's forces in the plan phase.

### Request Body (JSON)

```json
{
  "game_id": "abc123",
  "orders": [
    {
      "force_id": "f1",
      "order": "advance",
      "target_hex": {"q": 1, "r": 0},
      "stance": "mountain"
    }
  ]
}
```

**Order Types:** "advance", "meditate", "deceive"  
**Stance Types:** "mountain", "river", "thunder" (for advance orders)

### Response (200 OK)

```json
{
  "status": "orders_submitted"
}
```

**Notes:** 
- Validates Shih costs and terrains
- Both players must submit before resolution
- Requires game_id in query or header (TBD; for now, assume per game context)

---

## 4. Get Game Log

**Method:** `GET`  
**Path:** `/game/<game_id>/log`  
**Description:** Returns a full event log for analysis (e.g., turns, resolutions).

### Response (200 OK)

```json
{
  "log": [
    "Turn 1: Player1 advanced to (1,0)",
    "Turn 1: Player2 meditated at (2,1)"
  ]
}
```

---

## 5. Generate Report (LLM Analysis)

**Method:** `POST`  
**Path:** `/report/<game_id>`  
**Description:** Triggers an LLM-generated narrative report (future; for now, placeholder).

### Request Body

Empty or:

```json
{
  "prompt": "Analyze as Sun Tzu"
}
```

### Response (200 OK)

```json
{
  "report": "Key deceptions: Player1 used ghosts effectively..."
}
```

---

## Implementation Notes

- Use Flask routes in `app.py`
- Secure with keys if multiplayer
- Test with pytest and Postman