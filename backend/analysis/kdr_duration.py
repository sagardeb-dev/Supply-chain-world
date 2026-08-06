"""KDR duration-confound test (DEFECTS.md D12; pre-registered F6/F7 in
research/STATS-GUIDELINES.md 2026-07-31 BEFORE any number below existed).

Per-seed KDR (share of diagnosed stressed weeks, week<26, that stocked
out — engine-truth stockout column of beliefs.csv) vs port_block_longest
(sweep/results.csv). F6: Spearman KDR~duration per model. F7: partial
association of PERSISTENT membership after rank-residualizing on
duration. Seed-cluster bootstrap.

    cd backend && uv run --with numpy python analysis/kdr_duration.py
"""
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench_config import GROUPS  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
RUNS = BASE / "runs" / "ladder-v1"
MODELS = ["openai-gpt-5.4", "anthropic-claude-sonnet-5",
          "x-ai-grok-4.5", "deepseek-deepseek-v4-pro"]
SHORT = {"openai-gpt-5.4": "gpt-5.4", "anthropic-claude-sonnet-5": "claude-sonnet-5",
         "x-ai-grok-4.5": "grok-4.5", "deepseek-deepseek-v4-pro": "deepseek-v4-pro"}
N_BOOT = 10_000
BOOT_SEED = 20260728


def holm(pvals):
    pvals = np.array(pvals, float)
    order = np.argsort(pvals)
    adj = np.empty_like(pvals)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, pvals[i] * (len(pvals) - rank))
        adj[i] = min(1.0, running)
    return adj


def boot_p(dist):
    return min(1.0, 2 * min((dist <= 0).mean(), (dist >= 0).mean()))


def rank(v):
    # average ranks, ties handled; NaNs propagate
    out = np.full(v.shape, np.nan)
    m = ~np.isnan(v)
    x = v[m]
    order = np.argsort(x, kind="stable")
    r = np.empty(len(x))
    r[order] = np.arange(len(x), dtype=float)
    # average tied ranks
    for val in np.unique(x):
        t = x == val
        r[t] = r[t].mean()
    out[m] = r
    return out


def spearman(a, b):
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 3:
        return np.nan
    ra, rb = rank(a[m]), rank(b[m])
    ra, rb = ra - ra.mean(), rb - rb.mean()
    d = np.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / d) if d > 0 else np.nan


def partial_assoc(kdr, dur, pers):
    """Correlation of PERSISTENT indicator with KDR after removing the
    rank-linear effect of duration from both."""
    m = ~np.isnan(kdr)
    if m.sum() < 3:
        return np.nan
    rk, rd, p = rank(kdr[m]), rank(dur[m]), pers[m].astype(float)
    rd = rd - rd.mean()
    denom = (rd**2).sum()
    if denom == 0:
        return np.nan
    res_k = (rk - rk.mean()) - ((rk - rk.mean()) * rd).sum() / denom * rd
    res_p = (p - p.mean()) - ((p - p.mean()) * rd).sum() / denom * rd
    d = np.sqrt((res_k**2).sum() * (res_p**2).sum())
    return float((res_k * res_p).sum() / d) if d > 0 else np.nan


def main():
    sweep = {int(r["seed"]): r for r in csv.DictReader(open(BASE / "sweep" / "results.csv"))}
    grp = {s: g for g, seeds in GROUPS.items() for s in seeds}

    # per (model, seed): diagnosed stressed weeks (week<26) and their stockouts
    diag = {}
    for r in csv.DictReader(open(RUNS / "beliefs.csv")):
        if r["model"] not in MODELS:
            continue
        true = set(r["factors_stressed_true"].split(";")) - {""}
        named = set(r["factors_named"].split(";")) - {""}
        if not true or int(r["week"]) >= 26 or not (true & named):
            continue
        n, k = diag.get((r["model"], int(r["seed"])), (0, 0))
        diag[(r["model"], int(r["seed"]))] = (n + 1, k + int(r["stockout"]))

    seeds = sorted(grp)
    dur = np.array([float(sweep[s]["port_block_longest"]) for s in seeds])
    pers = np.array([grp[s] == "PERSISTENT" for s in seeds])

    def kdr_vec(m):
        out = np.full(len(seeds), np.nan)
        for i, s in enumerate(seeds):
            n, k = diag.get((m, s), (0, 0))
            if n:
                out[i] = k / n
        return out

    rng = np.random.default_rng(BOOT_SEED)
    draws = rng.integers(0, len(seeds), size=(N_BOOT, len(seeds)))

    def cboot(stat, kdr):
        point = stat(kdr, dur, pers)
        vals = np.array([stat(kdr[d], dur[d], pers[d]) for d in draws])
        vals = vals[~np.isnan(vals)]
        lo, hi = np.percentile(vals, [2.5, 97.5])
        return point, float(lo), float(hi), vals

    print(f"seeds with defined KDR per model:",
          {SHORT[m]: int((~np.isnan(kdr_vec(m))).sum()) for m in MODELS})

    for fam, stat, label in (
            ("F6", lambda k, d, p: spearman(k, d), "Spearman KDR~port_block_longest"),
            ("F7", partial_assoc, "partial PERSISTENT assoc | duration")):
        rows, pvals = [], []
        for m in MODELS:
            point, lo, hi, vals = cboot(stat, kdr_vec(m))
            pvals.append(boot_p(vals))
            rows.append((SHORT[m], point, lo, hi))
        for (name, point, lo, hi), p, ph in zip(rows, pvals, holm(pvals)):
            print(f"{fam} {label} {name}: {point:+.3f} [{lo:+.3f},{hi:+.3f}] "
                  f"p={p:.2g} holm={ph:.2g}")

    # descriptive: mean KDR by duration tercile (pooled weeks per seed-mean)
    terc = np.digitize(dur, np.percentile(dur, [33.3, 66.7]))
    for m in MODELS:
        kdr = kdr_vec(m)
        means = [np.nanmean(kdr[terc == t]) for t in range(3)]
        print(f"desc {SHORT[m]} KDR by duration tercile (short/mid/long): "
              + " / ".join(f"{x:.3f}" for x in means))


if __name__ == "__main__":
    main()
