# Architecture Overview for Sun Tzu: The Unfought Battle API

## High-Level Structure

The project is a headless (no graphical interface) backend API built with Python and Flask. It simulates a sophisticated turn-based strategy game engine inspired by Sun Tzu's *The Art of War*, focusing on deception, terrain control, and morale management.

### Core Architecture Principles
- **Modular Design**: Separate modules for distinct game systems (orders, resolution, upkeep, map generation)
- **Stateful Game Management**: In-memory game state storage with comprehensive logging
- **Phase-Based Turn Cycle**: Structured plan → execute → upkeep phase progression
- **Comprehensive Validation**: Multi-layer validation for all game actions and state changes
- **Event-Driven Logging**: Detailed event logging for analysis and debugging

## Key Components

### 1. Game State Management (`state.py`)
- **GameState Class**: Central game state container with turn/phase tracking
- **Player & Force Models**: Resource management (Chi/Shih) and force positioning
- **Order Submission Tracking**: Per-player order submission state management
- **Map Integration**: 25x20 hex grid with axial coordinate system
- **Game Initialization**: Configurable starting conditions from `config.json`

### 2. Map Generation (`map_gen.py`)
- **Procedural Generation**: Perlin noise-based terrain generation with balance validation
- **Terrain Types**: Open (standard), Difficult (defensive), Contentious (strategic objectives)
- **Balance Algorithms**: A* pathfinding for equal access validation
- **Chokepoint Detection**: Strategic bottleneck identification for tactical gameplay
- **Regeneration Logic**: Multi-attempt generation for balanced maps

### 3. Order Processing (`orders.py`)
- **Order Validation**: Comprehensive validation including Shih costs, adjacency, terrain restrictions
- **Order Types**:
  - **Advance**: Movement with stance selection, costs 2 Shih
  - **Meditate**: Shih regeneration (+2 next turn) with order revelation
  - **Deceive**: Ghost creation, costs 3 Shih
- **Batch Processing**: Transaction-like order resolution
- **Event Logging**: Detailed action logging throughout order processing

### 4. Confrontation Resolution (`resolution.py`)
- **Stance System**: Rock-paper-scissors mechanics (Mountain > Thunder > River > Mountain)
- **Tendency Modifiers**: AI behavior prediction based on last 3 orders
  - Predictable (3 identical): -1 modifier
  - Unpredictable (3 unique): +1 modifier
  - Mixed patterns: No modifier
- **Chi Loss Calculation**: Base damage with terrain multipliers
- **Retreat Mechanics**: Automatic retreat to adjacent valid hexes

### 5. Upkeep Management (`upkeep.py`)
- **Resource Yields**: +2 Shih per controlled Contentious hex
- **Encirclement System**: Track surrounded forces, apply -20 Chi after 2 turns
- **Victory Conditions**:
  - **Demoralization**: Chi ≤ 0
  - **Domination**: Control all Contentious terrain
  - **Encirclement**: Extended surrounding penalties
- **Turn Advancement**: Phase cycling and turn increment

### 6. API Layer (`app.py`)
- **RESTful Endpoints**: CRUD operations for game management
- **Phase Validation**: Strict phase-based action restrictions
- **Error Handling**: Comprehensive error responses with detailed messages
- **CORS Support**: Cross-origin resource sharing for future frontend integration

## Data Flow Architecture

### Game Creation Flow
```
Client → POST /api/game/new → Generate Map → Initialize Players/Forces → Return Game ID
```

### Turn Cycle Flow
```
Plan Phase:
  Client → POST /api/game/{id}/action (Player 1) → Validate Orders → Store
  Client → POST /api/game/{id}/action (Player 2) → Validate Orders → Store → Execute Phase

Execute Phase:
  Client → POST /api/game/{id}/upkeep → Resolve Orders → Check Victory → Plan Phase (Next Turn)
```

### State Query Flow
```
Client → GET /api/game/{id}/state → Return Current State + Order Submission Status
Client → GET /api/game/{id}/log → Return Complete Event Log
```

## Module Dependencies

```
app.py
├── state.py
│   ├── models.py (Force, Player, Hex)
│   └── map_gen.py (Map generation)
├── orders.py
│   ├── models.py (Order types)
│   └── state.py (Validation)
├── resolution.py
│   ├── models.py (Force interactions)
│   └── state.py (State updates)
├── upkeep.py
│   ├── models.py (Resource management)
│   └── state.py (Victory conditions)
└── config.json (Game parameters)
```

## Data Models

### Core Game Entities
- **GameState**: Central state container with players, map, log, phase tracking
- **Player**: Chi (100), Shih (10, max 20), 3 Forces per player
- **Force**: Position, stance, tendency (last 3 orders), encirclement tracking
- **Hex**: Axial coordinates (q, r), terrain type

### Configuration System
```json
{
  "starting_chi": 100,
  "starting_shih": 10,
  "max_shih": 20,
  "force_count": 3,
  "base_chi_loss": 8,
  "tendency_modifier": 1
}
```

## Advanced Features

### 1. Strategic Tendency System
- **Order History Tracking**: Last 3 orders per force
- **AI Behavior Prediction**: Visible to opponents for tactical planning
- **Combat Modifiers**: Predictability affects confrontation outcomes

### 2. Comprehensive Logging System
- **Event Classification**: Order submission, validation, movement, confrontation, upkeep
- **Structured Logging**: JSON-formatted events with turn/phase context
- **Analysis Support**: Complete game replay capability

### 3. Phase-Based State Management
- **Strict Phase Transitions**: Orders only in plan, execution automatic, upkeep controlled
- **Order Submission Tracking**: Per-player submission state prevents duplicate orders
- **Phase Validation**: All endpoints validate appropriate phase for actions

### 4. Map Balance Validation
- **Path Equality**: A* pathfinding ensures equal access to objectives
- **Coverage Validation**: 20-30% Difficult terrain for strategic depth
- **Regeneration Logic**: Multiple attempts to achieve balanced layouts

## Performance Considerations

### Memory Management
- **In-Memory Storage**: Games stored in Python dictionaries for development
- **State Serialization**: JSON-compatible data structures throughout
- **Garbage Collection**: Automatic cleanup when games end

### Scalability Design
- **Stateless API**: Each request contains full context
- **Modular Architecture**: Easy horizontal scaling of individual components
- **Database Ready**: Current structure easily migrates to persistent storage

## Testing Architecture

### Test Coverage
- **Unit Tests**: Individual module functionality (`test_orders.py`, `test_resolution.py`, etc.)
- **Integration Tests**: Full API workflow testing (`test_api.py`)
- **Game Simulation**: Complete game cycle validation
- **Edge Case Handling**: Boundary condition and error state testing

### Test Structure
```
tests/
├── test_api.py (API endpoint integration tests)
├── test_orders.py (Order processing unit tests)
├── test_resolution.py (Confrontation mechanics)
├── test_upkeep.py (Turn finalization)
├── test_state.py (Game state management)
└── test_map_gen.py (Map generation validation)
```

## Deployment Architecture

### Development Setup
- **Flask Development Server**: Local testing and development
- **Virtual Environment**: Isolated dependency management
- **Hot Reload**: Automatic server restart during development

### Production Considerations
- **Google Cloud Platform**: App Engine deployment target
- **Environment Configuration**: Config-based deployment settings
- **Logging Integration**: Structured logging for production monitoring

## Future Extensions

### Planned Integrations
- **LLM Players**: AI opponents using language model decision-making
- **Godot Frontend**: Real-time visualization and player interaction
- **Database Backend**: Persistent game state storage
- **Multiplayer Support**: Session management and player authentication

### Extensibility Points
- **Plugin Architecture**: Modular order types and victory conditions
- **Custom Map Generators**: Alternative map generation algorithms
- **AI Framework**: Pluggable AI decision engines
- **Analytics System**: Game balance and player behavior analysis

This architecture ensures maintainability, testability, and scalability while providing a rich foundation for both game simulation and AI research applications.