"""Learned-oracle references: the exact cmd_oracle protocol (mean of 20
deterministic run_oracle(seed, k) reps, k=191..210) with the Baum-Welch
transition tables from learned_trans.json swapped in. Writes a NEW file
runs/ladder-v1/oracle_refs_learned.csv; never touches oracle_refs.csv.
Append+resume: rerun to continue after an interrupt.

    cd backend && uv run python analysis/learned_refs.py
"""
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import bench_config as C
from fit_oracle import load_learned_trans
from oracle_policy import run_oracle
from src.world.config import WorldConfig

OUT = Path(__file__).parent.parent / "runs" / "ladder-v1" / "oracle_refs_learned.csv"

trans = load_learned_trans(str(Path(__file__).parent.parent / "learned_trans.json"),
                           WorldConfig(sup_mask_otif=True))

done = set()
if OUT.is_file():
    done = {int(l.split(",")[0]) for l in OUT.read_text().splitlines()[1:] if l}
else:
    OUT.write_text("seed,mean,se,n,min,max\n")

for s in C.all_seeds():
    if s in done:
        continue
    xs = [run_oracle(s, k=k, trans_override=trans)
          for k in range(C.ORACLE_K_BASE, C.ORACLE_K_BASE + C.ORACLE_REPS)]
    with open(OUT, "a") as f:
        f.write(f"{s},{st.mean(xs):.1f},{st.stdev(xs)/len(xs)**0.5:.1f},"
                f"{len(xs)},{min(xs):.1f},{max(xs):.1f}\n")
    print(f"seed {s}: mean={st.mean(xs):.1f}", flush=True)
print("done")
