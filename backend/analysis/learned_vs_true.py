"""Learned-oracle vs true-oracle references, paired over all benchmark seeds.

Primary (decided before looking): mean per-seed cost difference
(learned - true), paired bootstrap CI + Wilcoxon vs 0. Secondary
(descriptive): per-group differences, relative size vs headroom, and the
skill-scale shift per model if scores were recomputed against the learned
reference. Stratified: seeds whose tapes contain quality / disruption
stress weeks (where the badly-fit deep-age arcs should matter if anywhere).

    cd backend && uv run --with numpy,scipy python analysis/learned_vs_true.py
"""
import csv
import sys
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

sys.path.insert(0, str(Path(__file__).parent.parent))
import bench_config as C

RUNS = Path(__file__).parent.parent / "runs" / "ladder-v1"
N_BOOT, BOOT_SEED = 10_000, 20260728

true_ref = {int(r["seed"]): r for r in csv.DictReader(open(RUNS / "oracle_refs.csv"))}
learn_ref = {int(r["seed"]): r for r in csv.DictReader(open(RUNS / "oracle_refs_learned.csv"))}
skills = list(csv.DictReader(open(RUNS / "skill_scores.csv")))

seeds = sorted(true_ref)
assert sorted(learn_ref) == seeds and len(seeds) == 50

# which seeds contain quality / disruption stress weeks (from beliefs.csv truth)
stress_of = {}
for r in csv.DictReader(open(RUNS / "beliefs.csv")):
    stress_of.setdefault(int(r["seed"]), set()).update(
        f for f in r["factors_stressed_true"].split(";") if f)

d = np.array([float(learn_ref[s]["mean"]) - float(true_ref[s]["mean"]) for s in seeds])
tm = np.array([float(true_ref[s]["mean"]) for s in seeds])
groups = [C.group_of(s) if hasattr(C, "group_of") else None for s in seeds]
if groups[0] is None:
    gmap = {s: g for g, ss in C.GROUPS.items() for s in ss}
    groups = [gmap[s] for s in seeds]

rng = np.random.default_rng(BOOT_SEED)
idx = rng.integers(0, len(seeds), (N_BOOT, len(seeds)))

def ci(v, ix=None):
    ix = idx if ix is None else ix
    m = v[ix].mean(axis=1)
    return v.mean(), *np.percentile(m, [2.5, 97.5])

m, lo, hi = ci(d)
w = wilcoxon(d)
print(f"ALL 50 seeds: learned - true cost  mean {m:+.1f} [{lo:+.1f}, {hi:+.1f}]  "
      f"wilcoxon p={w.pvalue:.3g}")
print(f"  relative to true ref cost: {m / tm.mean():+.2%} of mean reference cost")

for g in ("ISOLATED", "PERSISTENT", "COMPOUND"):
    sel = np.array([i for i, gg in enumerate(groups) if gg == g])
    ixg = rng.integers(0, len(sel), (N_BOOT, len(sel)))
    mg, log, hig = ci(d[sel], ixg)
    print(f"  {g:>10} (n={len(sel)}): {mg:+.1f} [{log:+.1f}, {hig:+.1f}]")

for name, fac in (("quality-stressed", "quality"), ("disruption-stressed", "disruption")):
    sel = np.array([i for i, s in enumerate(seeds) if fac in stress_of.get(s, set())])
    ixg = rng.integers(0, len(sel), (N_BOOT, len(sel)))
    mg, log, hig = ci(d[sel], ixg)
    print(f"  {name:>19} (n={len(sel)}): {mg:+.1f} [{log:+.1f}, {hig:+.1f}]")

# skill-scale shift: recompute each model's mean skill with the learned
# reference, applying the metric's own exclusion rule (positive headroom) to
# BOTH scales so no blown-up ratio contaminates the mean.
bad = {s for s in seeds
       for r in skills
       if int(r["seed"]) == s and r["skill"] != ""
       and float(r["basestock"]) - float(learn_ref[s]["mean"]) <= 0}
print(f"\nseeds excluded under learned ref (negative headroom): {sorted(bad)}")
print("mean skill, true ref -> learned ref (jointly scoreable seeds):")
for mdl in C.MODELS if hasattr(C, "MODELS") else sorted({r["model"] for r in skills}):
    rows = [r for r in skills if r["model"] == mdl and r["skill"] != ""
            and int(r["seed"]) not in bad]
    if len(rows) < 40:  # skip the single-seed gemini smoke row
        continue
    st_, sl = [], []
    for r in rows:
        s = int(r["seed"])
        bs, llm = float(r["basestock"]), float(r["llm_cost"])
        st_.append((bs - llm) / (bs - float(true_ref[s]["mean"])))
        sl.append((bs - llm) / (bs - float(learn_ref[s]["mean"])))
    st_, sl = np.array(st_), np.array(sl)
    ixm = rng.integers(0, len(rows), (N_BOOT, len(rows)))
    dm, dlo, dhi = ci(sl - st_, ixm)
    print(f"  {mdl:>28}: {st_.mean():+.3f} -> {sl.mean():+.3f}  "
          f"shift {dm:+.3f} [{dlo:+.3f}, {dhi:+.3f}]")

# negative-headroom sanity: does seed 11 stay unscoreable under the learned ref?
for s in seeds:
    bs_rows = [r for r in skills if int(r["seed"]) == s]
    if bs_rows:
        bs = float(bs_rows[0]["basestock"])
        if bs - float(learn_ref[s]["mean"]) <= 0:
            print(f"\nnegative headroom under learned ref: seed {s}")
