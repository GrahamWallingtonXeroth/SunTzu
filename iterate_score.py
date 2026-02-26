"""Quick iteration script: change config, measure scores, report."""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def run_with_config(overrides, label):
    """Apply config overrides, compute scores, restore."""
    with open('config.json', 'r') as f:
        original = json.load(f)
    cfg = dict(original)
    cfg.update(overrides)
    with open('config.json', 'w') as f:
        json.dump(cfg, f, indent=2)

    # Must reimport everything with new config
    import importlib
    for mod_name in list(sys.modules.keys()):
        if mod_name in ('orders', 'upkeep', 'resolution', 'state', 'map_gen', 'models'):
            importlib.reload(sys.modules[mod_name])
    if 'tests.simulate' in sys.modules:
        importlib.reload(sys.modules['tests.simulate'])
    if 'tests.test_fun_score' in sys.modules:
        importlib.reload(sys.modules['tests.test_fun_score'])

    from tests.test_fun_score import compute_fun_scores
    scores, overall = compute_fun_scores(verbose=False)

    # Restore
    with open('config.json', 'w') as f:
        json.dump(original, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"  Config: {overrides}")
    print(f"{'=' * 60}")
    for name, val in sorted(scores.items()):
        flag = " <<<" if val < 5.0 else ""
        print(f"  {name}: {val:.1f}{flag}")
    print(f"  OVERALL: {overall:.1f}")
    return scores, overall


if __name__ == "__main__":
    experiments = [
        ({}, "BASELINE (no changes)"),
        ({"supply_range": 2}, "Supply range 3 -> 2"),
        ({"supply_range": 1}, "Supply range 3 -> 1"),
        ({"supply_range": 2, "board_size": 9}, "Supply 2 + Board 9x9"),
        ({"board_size": 9}, "Board 7x7 -> 9x9"),
        ({"board_size": 9, "force_count": 7}, "Board 9x9 + 7 forces"),
        ({"visibility_range": 3}, "Visibility 2 -> 3"),
        ({"visibility_range": 1}, "Visibility 2 -> 1"),
    ]

    results = []
    for overrides, label in experiments:
        scores, overall = run_with_config(overrides, label)
        results.append((label, overall, scores))

    print(f"\n\n{'=' * 60}")
    print("SUMMARY TABLE")
    print(f"{'=' * 60}")
    print(f"{'Experiment':<35} {'Overall':>7} {'Supply':>7} {'Roles':>7} {'Space':>7}")
    for label, overall, scores in results:
        print(f"{label:<35} {overall:>7.1f} {scores.get('9. Supply Relevance', 0):>7.1f} "
              f"{scores.get('8. Role Emergence', 0):>7.1f} {scores.get('7. Spatial Freedom', 0):>7.1f}")
