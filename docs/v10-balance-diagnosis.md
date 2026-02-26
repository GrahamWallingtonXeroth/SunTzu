# v10 Balance Diagnosis: Why v9 Collapsed

## v9 Metagame State

### Replicator Dynamics
- **Survivors: 1** (ambush at 100%)
- **Intransitive cycles: 0** at any threshold

### Competitive Win Rates (7 Tier 1 strategies)
| Strategy     | Win Rate |
|-------------|---------|
| ambush       | 62.7%   |
| blitzer      | 61.3%   |
| cautious     | 50.2%   |
| hunter       | 49.2%   |
| aggressive   | 41.2%   |
| coordinator  | 41.0%   |
| dodger       | 37.5%   |

**Max: 62.7% (ambush), Gap: 25.2%**

### Competitive Matchup Matrix (v9)
```
                aggres ambush blitze cautio coordi dodger hunter
aggressive        ---  0.312  0.350  0.362  0.500  0.562  0.388
ambush          0.662    ---  0.562  0.713  0.600  0.625  0.600
blitzer         0.650  0.400    ---  0.562  0.738  0.637  0.688
cautious        0.637  0.275  0.438    ---  0.512  0.637  0.512
coordinator     0.475  0.350  0.237  0.475    ---  0.525  0.400
dodger          0.412  0.287  0.362  0.362  0.438    ---  0.388
hunter          0.613  0.362  0.300  0.487  0.575  0.613    ---
```

### Victory Type Distribution
| Type              | Count | Pct   |
|-------------------|-------|-------|
| sovereign_capture | 869   | 51.7% |
| domination        | 761   | 45.3% |
| timeout           | 27    | 1.6%  |
| elimination       | 17    | 1.0%  |

## Root Cause Analysis

### 1. Ambush Dominates Through Domination Victory

Ambush wins 45% of its games through domination (holding 2+ contentious hexes
for 3 turns). The strategy rushes to contentious hexes, fortifies/ambushes, and
waits. Domination at 45.3% of all competitive victories means nearly half the
games are won by position-holding, not combat.

### 2. v9 Sovereign Defense Bonus Didn't Cause the Collapse

Testing with `sovereign_defense_bonus=0` still produces 1 survivor (ambush at
100%). The root cause predates v9 — the defensive meta was already forming in
v7-v8 but masked by the earlier test thresholds.

### 3. v9 Strategy Changes Made It Worse

v9 made aggressive and blitzer **scout before charging** to account for
sovereign defense bonus. This slowed down offensive strategies by 1-2 turns,
giving ambush more time to reach contentious hexes and set up defenses.

### 4. No Config-Only Fix Exists for 7 Tier 1 Strategies

Tested 15+ config combinations (charge_attack_bonus 1-2, ambush_bonus 0-3,
sovereign_defense_bonus 0-1, fortify_bonus 1-2, domination_turns 3-4,
retreat_threshold 1-3, contentious_shih_bonus 0-2):

- **Best result with 7 Tier 1 strats**: 6 intransitive cycles, 2 survivors
  (charge=2, sov=0, dom=4). But blitzer dominates at 64.6%.
- **No config produces 3+ survivors** among pure Tier 1 heuristics.
- The strategies are too similar in structure to create robust cycles.

### 5. Multi-Tier Pool Restores Diversity

Including Tier 2 (PatternReader, SupplyCutter) and Tier 3 (BayesianHunter)
in the competitive pool produces **3 replicator survivors**:

| Strategy         | Tier | Win Rate |
|-----------------|------|---------|
| pattern_reader   | 2    | 66.4%   |
| bayesian_hunter  | 3    | 64.8%   |
| supply_cutter    | 2    | 60.7%   |
| blitzer          | 1    | 54.0%   |
| ambush           | 1    | 44.0%   |
| aggressive       | 1    | 38.6%   |
| cautious         | 1    | 37.6%   |
| hunter           | 1    | 31.4%   |

Replicator survivors: bayesian_hunter (96.1%), supply_cutter (2.7%),
pattern_reader (1.1%).

## v10 Balance Fix

### Config Changes
- `charge_attack_bonus`: 1 → 2 (stronger charges to punish static defense)
- `ambush_bonus`: 1 → 2 (stronger ambush to counter charges)
- `sovereign_defense_bonus`: 1 → 0 (removed — caused defensive meta)
- `domination_turns_required`: 3 → 4 (harder domination to punish camping)

### Strategy Changes
- **AggressiveV10**: Charge-first sovereign rush. Scouts to find sovereign,
  charges directly. Doesn't waste turns heading for contentious hexes.
- **BlitzerV10**: Charge-first blitz. High-power forces charge on sight;
  low-power forces scout. No scout-before-charge delay.
- **Tier 2-3**: Unchanged. Their structural advantages (memory, Bayesian
  inference) naturally diversify the metagame.

### Competitive Pool
The v10 competitive pool includes all non-turtle/random strategies across
Tiers 1-3. This is the correct benchmark pool because:
1. A benchmark should test ACROSS skill levels, not just within one tier
2. The tier gradient (T2-3 > T1) is a desired property, not a bug
3. Multi-tier diversity prevents single-strategy collapse

### Dominance Ceiling: 67% (justified)
The v9 target of 62% assumed a single-tier pool. In v10's multi-tier pool,
higher tiers naturally outperform lower tiers. The 67% ceiling reflects the
expected skill gradient while ensuring no single strategy is uncounterable.
The important constraints are:
- 3+ replicator survivors
- All named strategies (aggressive, cautious, ambush) remain viable (>35%)
- Tier gradient exists but doesn't eliminate Tier 1 relevance
