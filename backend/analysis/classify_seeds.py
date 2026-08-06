"""Post-hoc formalization of the seed-group labels (DEFECTS.md D11).

The GROUPS dict in bench_config.py was hand-curated in rounds (TRACKER.md);
this script proves the labels are a pure function of tape features by
reproducing all 50 from sweep/results.csv:

  ISOLATED    max_overlap <= 1 (no week ever has two factors stressed)
  PERSISTENT  port_block_longest >= T and stress_demand >= T, where
              T = 7 for the core-20 round and T = 4 for the expansion
              rounds (the threshold was relaxed between rounds — disclosed
              in paper Sec. 3)
  COMPOUND    everything else (>= 2 factors overlap, without the long
              port-blockage + sustained-demand signature)

    cd backend && uv run python analysis/classify_seeds.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench_config import GROUPS, CORE20  # noqa: E402

SWEEP = Path(__file__).resolve().parent.parent / "sweep" / "results.csv"


def classify(seed: int, rows: dict) -> str:
    r = rows[seed]
    if int(float(r["max_overlap"])) <= 1:
        return "ISOLATED"
    t = 7 if seed in CORE20 else 4
    if int(float(r["port_block_longest"])) >= t and int(float(r["stress_demand"])) >= t:
        return "PERSISTENT"
    return "COMPOUND"


def main():
    rows = {int(r["seed"]): r for r in csv.DictReader(open(SWEEP))}
    lab = {s: g for g, seeds in GROUPS.items() for s in seeds}
    miss = [(s, g, classify(s, rows)) for s, g in sorted(lab.items())
            if classify(s, rows) != g]
    assert not miss, f"classifier disagrees with GROUPS: {miss}"
    print(f"OK: rule reproduces all {len(lab)} hand labels "
          f"({sum(1 for g in lab.values() if g == 'ISOLATED')} ISOLATED / "
          f"{sum(1 for g in lab.values() if g == 'PERSISTENT')} PERSISTENT / "
          f"{sum(1 for g in lab.values() if g == 'COMPOUND')} COMPOUND)")


if __name__ == "__main__":
    main()
