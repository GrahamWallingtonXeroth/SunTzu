# Sun Tzu: The Unfought Battle - Core Game Engine API

## Overview
This repository contains the fully implemented backend API for "Sun Tzu: The Unfought Battle," a sophisticated turn-based strategy simulation inspired by Sun Tzu's *The Art of War*. It's a headless (no UI) Python/Flask API for simulating strategic games, focusing on deception, terrain control, and psychological warfare. Serves dual purposes: engaging strategic gameplay and AI research platform.

## Key Features Implemented

### Core Game Systems
- **Procedural Map Generation**: 25x20 hex grid with balanced terrain placement using Perlin noise
- **Three Terrain Types**: Open (standard), Difficult (defensive advantage), Contentious (strategic objectives)
- **Resource Management**: Chi (morale, 100 starting) and Shih (momentum, 10 starting, max 20)
- **Strategic Orders**: Advance (movement + confrontation), Meditate (resource + intelligence), Deceive (ghost creation)

### Advanced Mechanics  
- **Rock-Paper-Scissors Combat**: Mountain > Thunder > River > Mountain with terrain modifiers
- **Tendency System**: AI behavior tracking (last 3 orders) affecting confrontation outcomes
- **Encirclement Penalties**: Forces surrounded for 2+ turns lose 20 Chi
- **Phase-Based Turns**: Plan → Execute → Upkeep cycle with strict validation

### Victory Conditions
- **Demoralization**: Opponent Chi ≤ 0
- **Domination**: Control all Contentious terrain
- **Encirclement**: Extended surrounding causes Chi penalties leading to demoralization

### API Features
- **RESTful Endpoints**: Complete game lifecycle management
- **Real-time State**: JSON-based game state with order submission tracking  
- **Comprehensive Logging**: Detailed event logs for game analysis and replay
- **Error Handling**: Robust validation with detailed error messages

## Setup and Installation

### Prerequisites
- Python 3.12+ (tested on 3.12)
- pip package manager

### Installation Steps
1. **Clone the repository**:
   ```bash
   git clone https://github.com/GrahamWallingtonXeroth/SunTzu.git
   cd SunTzu
   ```

2. **Create and activate virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the API server**:
   ```bash
   python app.py
   ```

   The API will be available at `http://localhost:5000`

### Dependencies
- **Flask**: Web framework for API endpoints
- **Flask-CORS**: Cross-origin resource sharing support
- **NumPy**: Numerical computing for coordinates and calculations
- **noise**: Perlin noise generation for map terrain
- **pytest**: Testing framework (development)

## API Usage

### Quick Start Example
```bash
# Create a new game
curl -X POST http://localhost:5000/api/game/new \
  -H "Content-Type: application/json" \
  -d '{"seed": 42}'

# Get game state (replace {game_id} with returned ID)
curl http://localhost:5000/api/game/{game_id}/state

# Submit orders for player 1
curl -X POST http://localhost:5000/api/game/{game_id}/action \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "p1",
    "orders": [
      {
        "force_id": "p1_f1",
        "order": "Advance", 
        "target_hex": {"q": 1, "r": 0},
        "stance": "Mountain"
      }
    ]
  }'
```

### Available Endpoints
- `POST /api/game/new` - Create new game
- `GET /api/game/{id}/state` - Get current game state
- `POST /api/game/{id}/action` - Submit player orders
- `POST /api/game/{id}/upkeep` - Perform upkeep phase
- `GET /api/game/{id}/log` - Get complete game log

See `docs/api_endpoints.md` for complete API documentation.

## Project Structure

```
SunTzu/
├── app.py                 # Main Flask application and API endpoints
├── models.py              # Game entity data classes (Player, Force, Hex)
├── state.py              # Game state management and initialization
├── orders.py             # Order processing and validation
├── resolution.py         # Confrontation mechanics and combat resolution
├── upkeep.py             # Turn finalization and victory conditions
├── map_gen.py            # Procedural map generation with balance validation
├── config.json           # Game parameter configuration
├── requirements.txt      # Python dependencies
├── docs/
│   ├── api_endpoints.md  # Complete API documentation
│   ├── architecture.md   # System architecture overview
│   └── gdd_reference.md  # Game mechanics reference
├── tests/                # Comprehensive test suite
│   ├── test_api.py       # API integration tests  
│   ├── test_orders.py    # Order processing unit tests
│   ├── test_resolution.py # Combat mechanics tests
│   ├── test_upkeep.py    # Turn finalization tests
│   ├── test_state.py     # Game state management tests
│   └── test_map_gen.py   # Map generation tests
└── venv/                 # Virtual environment (created during setup)
```

## Development

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_api.py

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=. --cov-report=html
```

### Game Configuration
Edit `config.json` to modify game parameters:
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

### Code Style
- Follow PEP 8 Python style guidelines
- Use type hints for function parameters and returns
- Include docstrings for all public functions and classes
- Maintain comprehensive test coverage

## Game Mechanics Summary

### Turn Structure
1. **Plan Phase**: Both players submit orders simultaneously
2. **Execute Phase**: Orders resolved, confrontations occur automatically  
3. **Upkeep Phase**: Resources updated, victory conditions checked, next turn begins

### Order Types
- **Advance** (2 Shih): Move to adjacent hex, choose combat stance, confrontation if occupied
- **Meditate** (0 Shih): Stay in place, gain +2 Shih next turn, reveal adjacent enemy orders
- **Deceive** (3 Shih): Create ghost in adjacent hex to waste enemy moves

### Strategic Elements
- **Terrain Control**: Contentious hexes provide +2 Shih per turn when controlled
- **Tendency Tracking**: Predictable patterns (3 same orders) weaken combat effectiveness
- **Encirclement**: Surrounding enemy forces for 2+ turns inflicts major Chi penalties
- **Information Warfare**: Meditation reveals enemy intentions for tactical advantage

## Deployment

### Development Server
The Flask development server is suitable for testing and development:
```bash
python app.py  # Runs on http://localhost:5000
```

### Production Deployment
Designed for Google Cloud Platform App Engine:
- Stateless API design for horizontal scaling
- JSON-based state management
- Comprehensive logging for monitoring
- Database-ready architecture for persistent storage

## Research Applications

This implementation serves as a platform for AI research in:
- **Strategic Planning**: Multi-turn decision making under uncertainty
- **Deception Analysis**: Information asymmetry and misdirection tactics  
- **Resource Management**: Balancing immediate and long-term resource allocation
- **Psychological Modeling**: Tendency tracking and behavioral prediction

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make changes with appropriate tests
4. Ensure all tests pass (`pytest`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

MIT License - see LICENSE file for details. Open-source development philosophy aligned with game design principles.

## Acknowledgments

- Built with guidance from various AI assistants
- Inspired by Sun Tzu's *The Art of War* strategic principles
- Game design focused on psychological depth and strategic complexity
- Testing methodology ensures robust, reliable gameplay mechanics

---

**Status**: Fully implemented and tested. Ready for gameplay, AI research, and frontend integration.