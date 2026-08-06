"""Oracle per-week cost decomposition under the exact oracle_refs protocol
(20 deterministic reps, k=191..210, per seed). Collects the engine's own
cost_breakdown each week via run_oracle(week_rows=...). Writes
runs/ladder-v1/oracle_cost_weeks.csv (seed,k,week,components,total).
Append+resume: rerun to continue after an interrupt. Gates per rep:
sum of weekly totals must equal run_oracle's returned total (<= $0.05).

    cd backend && uv run python analysis/oracle_cost_weeks.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import bench_config as C
from oracle_policy import run_oracle

COST_KEYS = ["shipping", "surcharge", "holding", "in_transit", "stockout",
             "couple", "demurrage", "rework", "briefing", "audit", "air",
             "inspect", "dual_source"]

OUT = Path(__file__).parent.parent / "runs" / "ladder-v1" / "oracle_cost_weeks.csv"

done = set()  # (seed, k) pairs already on disk with all 26 weeks
if OUT.is_file():
    counts = {}
    for r in csv.DictReader(open(OUT)):
        counts[(int(r["seed"]), int(r["k"]))] = counts.get((int(r["seed"]), int(r["k"])), 0) + 1
    done = {sk for sk, n in counts.items() if n == 26}
    partial = {sk for sk, n in counts.items() if n != 26}
    if partial:
        sys.exit(f"partial reps on disk (delete their rows first): {sorted(partial)}")
else:
    with open(OUT, "w", newline="") as f:
        csv.writer(f).writerow(["seed", "k", "week"] + COST_KEYS + ["total"])

for seed in C.all_seeds():
    for k in range(C.ORACLE_K_BASE, C.ORACLE_K_BASE + C.ORACLE_REPS):
        if (seed, k) in done:
            continue
        rows = []
        total = run_oracle(seed, k=k, week_rows=rows)
        assert len(rows) == 26, f"seed {seed} k {k}: {len(rows)} weeks"
        wk_totals = [sum(float(cb.get(c, 0.0)) for c in COST_KEYS) for _, cb in rows]
        assert abs(sum(wk_totals) - total) <= 0.05, (
            f"seed {seed} k {k}: weekly components sum {sum(wk_totals):.2f} "
            f"!= episode total {total:.2f}")
        with open(OUT, "a", newline="") as f:
            w = csv.writer(f)
            for (wk, cb), wt in zip(rows, wk_totals):
                w.writerow([seed, k, wk]
                           + [round(float(cb.get(c, 0.0)), 2) for c in COST_KEYS]
                           + [round(wt, 2)])
    print(f"seed {seed} done", flush=True)
print("all done")
