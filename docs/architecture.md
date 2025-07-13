# Architecture Overview for Sun Tzu: The Unfought Battle API

## High-Level Structure
The project is a headless (no graphical interface) backend API built with Python and Flask. It simulates the game engine for turn-based strategy games. Key components:
- **Map Generation**: Procedural creation of a hexagonal grid battlefield using NumPy for coordinates and noise libraries if needed (e.g., Perlin for terrain placement).
- **Game State Management**: Tracks players, resources (Chi and Shih), forces, orders, and the map. Stored in memory (dicts/objects) per game ID.
- **Order Processing**: Handles player-submitted orders (Advance, Meditate, Deceive), resolves confrontations (stances: rock-paper-scissors), and applies effects like ghosts or retreats.
- **API Layer**: Flask endpoints for creating games, submitting actions, getting state, and logs. JSON for all data exchange.
- **Advanced Features**: Tendency tracking for forces, victory checks, tunable parameters via config.json.
- **Testing**: Unit/integration tests with pytest.
- **Deployment**: Runs as a Flask app, deployable to Google Cloud Platform App Engine.

Future: Integration with LLMs for AI players (e.g., via prompts for order decisions) and a separate Godot frontend for UI.

## Data Flow Diagram
(Simple text-based diagram; in code, this could be visualized better with tools like Mermaid if needed.)

User/Client --> POST /api/game/new --> Create Game (seed) --> Generate Map & Initial State

User/Client --> POST /api/action/player_id --> Submit Orders (JSON) --> Validate & Store Orders

Internal --> Resolve Phase: Process Orders --> Resolve Confrontations --> Upkeep (update resources, check victory)

User/Client --> GET /api/game/game_id/state --> Return Current State JSON

## Key Modules (Planned Files)
- `app.py`: Main Flask app and endpoints.
- `map_gen.py`: Map generation logic.
- `models.py`: Data classes for Hex, Force, Player, etc.
- `state.py`: Game state management.
- `orders.py`: Order validation and effects.
- `resolution.py`: Confrontation and phase resolution.
- `config.json`: Tunable parameters.
- `tests/`: Folder for pytest files.

This architecture ensures modularity: Easy to test/simulate games without a UI, and scalable for research (e.g., running many headless simulations).