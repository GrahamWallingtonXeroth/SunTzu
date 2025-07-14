# GDD Reference: Sun Tzu: The Unfought Battle - Actual Implementation

This document describes the game mechanics as actually implemented in the codebase, based on analysis of the source code in `models.py`, `state.py`, `orders.py`, `resolution.py`, `upkeep.py`, and `map_gen.py`.

## 1. Core Resources

### Chi (Morale)
- **Starting Value**: 100 per player (configurable in `config.json`)
- **Loss Conditions**: Confrontation defeats, encirclement penalties
- **Victory Condition**: Game ends when any player reaches Chi ≤ 0
- **No Regeneration**: Chi only decreases, never increases

### Shih (Momentum) 
- **Starting Value**: 10 per player (configurable)
- **Maximum Value**: 20 (excess is lost)
- **Costs**: Advance (2), Deceive (3), Meditate (0)
- **Regeneration**: +2 from Meditation (applied next turn), +2 per controlled Contentious hex (upkeep)

## 2. Terrain System

| Terrain Type | Shih Cost | Shih Yield (Upkeep) | Special Properties |
|--------------|-----------|---------------------|-------------------|
| Open | 1 | 0 | Standard movement and confrontations |
| Difficult | 2 | 0 | Thunder stance forbidden for defenders |
| Contentious | 1 | +2 | Double Chi loss in confrontations, strategic objectives |

### Control Mechanics
- **Control Definition**: Occupied by friendly force with no adjacent enemy forces
- **Yield Calculation**: Performed during upkeep phase
- **Strategic Value**: Contentious terrain provides both resources and victory path

## 3. Map Generation (Actual Algorithm)

### Map Specifications
- **Grid Size**: 25x20 hexes (500 total hexes)
- **Coordinate System**: Axial coordinates (q, r)
- **Player Starting Positions**: 
  - Player 1: (0,0), (1,0), (0,1) - top-left corner
  - Player 2: (24,19), (23,19), (24,18) - bottom-right corner

### Generation Algorithm
1. **Initialize**: 25x20 grid with all Open terrain
2. **Starting Positions**: Guarantee Open terrain at player starting locations
3. **Contentious Placement**: 3-5 hexes in center region (q=10-15, r=8-12)
4. **Path Generation**: A* pathfinding ensures minimum 5-hex paths from starts to center
5. **Barrier Generation**: Perlin noise with adaptive threshold for 20-30% Difficult terrain
6. **Balance Validation**: Multiple attempts until path lengths differ by ≤2 hexes
7. **Chokepoint Verification**: Minimum 2 strategic bottlenecks required

### Balance Validation
- **Path Equality**: A* algorithm ensures equal access to objectives
- **Coverage Target**: 20-30% Difficult terrain for strategic depth
- **Regeneration**: Up to 10 attempts with modified seeds for balanced maps

## 4. Forces and Order System

### Force Configuration
- **Count**: 3 forces per player (configurable)
- **Properties**: Position (q,r), Stance, Tendency history, Encirclement counter
- **Identification**: Format "p1_f1", "p1_f2", etc.

### Order Types and Mechanics

#### Advance Order
- **Shih Cost**: 2
- **Requirements**: Target hex must be adjacent, stance required
- **Effects**: Move to target hex, initiate confrontation if occupied
- **Stance Selection**: Mountain, River, Thunder (terrain restrictions apply)

#### Meditate Order  
- **Shih Cost**: 0
- **Effects**: 
  - Queue +2 Shih for next turn
  - Reveal adjacent enemy order types (not stances)
- **Strategic Value**: Resource generation and intelligence gathering

#### Deceive Order
- **Shih Cost**: 3  
- **Requirements**: Target hex must be adjacent
- **Effects**: Create ghost at target location
- **Ghost Mechanics**: Wastes enemy advances, dissipates after execute phase

### Phase Cycle (Actual Implementation)
1. **Plan Phase**: Players submit orders (both must submit before transition)
2. **Execute Phase**: Orders resolved automatically, confrontations occur
3. **Upkeep Phase**: Resource yields, victory checks, turn advancement

## 5. Confrontation System with Tendency

### Base Stance Mechanics
- **Mountain** beats **Thunder** (defensive counters aggression)
- **River** beats **Mountain** (evasion counters defense)  
- **Thunder** beats **River** (aggression counters evasion)
- **Same Stance**: Stalemate with modified Chi loss

### Tendency System (Strategic AI)
- **Tracking**: Last 3 orders per force (visible to opponents)
- **Predictable Pattern**: 3 identical orders = -1 stance modifier
- **Unpredictable Pattern**: 3 unique orders = +1 stance modifier  
- **Mixed Pattern**: No modifier applied

### Combat Resolution
- **Winner Determination**: Base stance + tendency modifiers
- **Chi Loss**: 8 base damage (configurable), doubled on Contentious terrain
- **Stalemate**: Both forces lose 4 Chi, both attempt retreat
- **Retreat Mechanics**: Automatic retreat to adjacent empty hex if available

### Terrain Modifiers
- **Difficult Ground**: Thunder stance forbidden for defenders
- **Contentious Ground**: Double Chi loss multiplier
- **Open Ground**: No special restrictions

## 6. Victory Conditions (Implemented)

### 1. Demoralization Victory
- **Condition**: Opponent Chi ≤ 0
- **Check Timing**: During upkeep phase
- **Immediate**: Game ends when condition met

### 2. Domination Victory  
- **Condition**: Control all Contentious terrain for one full turn
- **Implementation Status**: Basic framework present, requires full tracking implementation

### 3. Encirclement Victory
- **Mechanism**: Force surrounded for 2+ consecutive turns
- **Penalty**: -20 Chi applied during upkeep
- **Can Trigger**: Demoralization victory if Chi drops to 0

### Tiebreaker
- **Higher Shih**: Wins if both players reach 0 Chi simultaneously

## 7. Advanced Mechanics

### Encirclement System
- **Detection**: All adjacent hexes blocked by enemy forces or map boundaries
- **Tracking**: `encircled_turns` counter per force
- **Penalty Application**: After 2 full turns of encirclement
- **Recovery**: Counter resets if encirclement broken

### Logging System
- **Event Types**: Order submission, validation, movement, confrontation, upkeep
- **Structure**: JSON objects with turn, phase, event description
- **Usage**: Complete game replay and analysis capability

### Configuration System (`config.json`)
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

## 8. API Integration

### Phase Management
- **Order Submission**: Only during plan phase
- **Duplicate Prevention**: Each player submits once per turn
- **Phase Transition**: Automatic when both players submit orders
- **Validation**: Comprehensive error handling with detailed messages

### State Tracking
- **Game State**: Complete state serialization for API responses
- **Order Status**: Per-player submission tracking
- **Event Log**: Complete action history for analysis

## 9. Testing Coverage

### Unit Tests
- **Order Validation**: All order types and edge cases
- **Confrontation Resolution**: Stance interactions and tendency modifiers  
- **Map Generation**: Balance validation and terrain distribution
- **Victory Conditions**: All victory paths and edge cases

### Integration Tests
- **Full Game Cycles**: Complete turn sequences
- **API Endpoints**: All REST endpoints with error conditions
- **Phase Transitions**: State management across phases

## 10. Performance Characteristics

### Memory Usage
- **Game Storage**: In-memory dictionaries for development
- **State Size**: ~2-5KB per game state (JSON serialized)
- **Scalability**: Designed for database migration

### Computational Complexity
- **Map Generation**: O(n²) with regeneration attempts
- **Order Processing**: O(n) where n = number of orders
- **Victory Checks**: O(n) where n = number of forces/hexes

This implementation provides a sophisticated strategy game with psychological elements, suitable for both human players and AI research applications.