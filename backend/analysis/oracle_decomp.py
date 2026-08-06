"""Oracle reference column for the cost decomposition: compare each model's
per-week spend on ITS OWN diagnosed weeks against the fair oracle's spend on
those same (seed, week) cells (rep-mean over the 20-rep oracle_refs protocol).
Pre-registered contrasts F3/F4/F5 (see research/STATS-GUIDELINES.md,
2026-07-30 block). Reads runs/ladder-v1/{oracle_cost_weeks,cost_weeks,
beliefs,oracle_refs}.csv, writes oracle_decomp.csv + oracle_decomp.md.

    cd backend && uv run --with numpy python analysis/oracle_decomp.py
"""
import csv
import sys
from pathlib import Path

import numpy as np

RUNS = Path(__file__).resolve().parent.parent / "runs" / "ladder-v1"
MODELS = [
    "openai-gpt-5.4",
    "anthropic-claude-sonnet-5",
    "x-ai-grok-4.5",
    "deepseek-deepseek-v4-pro",
]
SHORT = {"openai-gpt-5.4": "gpt-5.4",
         "anthropic-claude-sonnet-5": "claude-sonnet-5",
         "x-ai-grok-4.5": "grok-4.5",
         "deepseek-deepseek-v4-pro": "deepseek-v4-pro"}
N_BOOT = 10_000
BOOT_SEED = 20260728

COST_KEYS = ["shipping", "surcharge", "holding", "in_transit", "stockout",
             "couple", "demurrage", "rework", "briefing", "audit", "air",
             "inspect", "dual_source"]
BUCKETS = {
    "procurement": ["shipping", "surcharge"],
    "holding_total": ["holding", "in_transit"],
    "stockout_total": ["stockout", "couple"],
    "levers": ["air", "inspect", "briefing", "audit", "dual_source"],
    "incident": ["demurrage", "rework"],
}


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


def main():
    # ---- oracle weekly cells: rep-mean per (seed, week) ----
    acc = {}   # (seed, week) -> {key: [values over reps]}
    rep_totals = {}  # seed -> {k: total}
    for r in csv.DictReader(open(RUNS / "oracle_cost_weeks.csv")):
        seed, k, wk = int(r["seed"]), int(r["k"]), int(r["week"])
        cell = acc.setdefault((seed, wk), {key: [] for key in COST_KEYS})
        for key in COST_KEYS:
            cell[key].append(float(r[key]))
        rep_totals.setdefault(seed, {}).setdefault(k, 0.0)
        rep_totals[seed][k] += float(r["total"])

    seeds = sorted(rep_totals)
    assert len(seeds) == 50, f"expected 50 seeds, got {len(seeds)}"
    for (seed, wk), cell in acc.items():
        for key in COST_KEYS:
            assert len(cell[key]) == 20, f"seed {seed} wk {wk}: {len(cell[key])} reps"

    # gate: rep-mean totals reproduce oracle_refs.csv
    refs = {int(r["seed"]): float(r["mean"])
            for r in csv.DictReader(open(RUNS / "oracle_refs.csv"))}
    for seed in seeds:
        got = np.mean(list(rep_totals[seed].values()))
        want = refs[seed]
        # tolerance = refs rounded to $0.1 (+-0.05) + weekly totals rounded
        # to cents accumulated over 26 weeks (+-0.13)
        assert abs(got - want) <= 0.25, f"seed {seed}: {got:.2f} != refs {want:.2f}"
    print(f"GATE PASS: 50 seeds x 20 reps x 26 weeks; rep-mean totals match "
          f"oracle_refs.csv within $0.25")

    ocell = {sw: {key: float(np.mean(v)) for key, v in cell.items()}
             for sw, cell in acc.items()}

    def obucket(sw, keys):
        return sum(ocell[sw][k] for k in keys)

    # ---- LLM weekly cells + belief classes (same join/classify as
    # cost_decomp.py, D2a rule included) ----
    cw = {}
    for r in csv.DictReader(open(RUNS / "cost_weeks.csv")):
        cw[(r["model"], r["seed"], int(r["week"]))] = {
            key: float(r[key]) for key in COST_KEYS}

    def classify(r):
        true = set(r["factors_stressed_true"].split(";")) - {""}
        named = set(r["factors_named"].split(";")) - {""}
        if not true:
            return "CALM"
        if int(r["week"]) >= 26:
            return None  # D2a: final week unknowable
        return "DIAG" if (true & named) else "UNDIAG"

    joined = []
    for r in csv.DictReader(open(RUNS / "beliefs.csv")):
        if r["model"] not in MODELS:
            continue
        key = (r["model"], r["seed"], int(r["week"]))
        rec = cw[key]
        joined.append({"model": r["model"], "seed": r["seed"],
                       "week": int(r["week"]), "class": classify(r), **rec})
    assert len(joined) == 5200, f"joined {len(joined)} weeks, expected 5200"

    seeds_s = sorted({r["seed"] for r in joined}, key=int)
    assert [int(s) for s in seeds_s] == seeds

    rng = np.random.default_rng(BOOT_SEED)
    draws = rng.integers(0, len(seeds_s), size=(N_BOOT, len(seeds_s)))

    # per (model, class): per-seed mean of (model bucket, oracle bucket, diff)
    by_mc = {}
    for r in joined:
        by_mc.setdefault((r["model"], r["class"]), {}).setdefault(
            r["seed"], []).append(r)

    def seed_means(model, cls, keys, side):
        d = by_mc.get((model, cls), {})
        out = np.full(len(seeds_s), np.nan)
        for i, s in enumerate(seeds_s):
            rows_s = d.get(s, [])
            if not rows_s:
                continue
            if side == "model":
                out[i] = np.mean([sum(r[k] for k in keys) for r in rows_s])
            elif side == "oracle":
                out[i] = np.mean([obucket((int(r["seed"]), r["week"]), keys)
                                  for r in rows_s])
            else:  # diff
                out[i] = np.mean([sum(r[k] for k in keys)
                                  - obucket((int(r["seed"]), r["week"]), keys)
                                  for r in rows_s])
        return out

    def cboot(vals):
        sub = vals[draws]
        with np.errstate(invalid="ignore"):
            means = np.nanmean(sub, axis=1)
        point = float(np.nanmean(vals))
        lo, hi = np.nanpercentile(means, [2.5, 97.5])
        return point, float(lo), float(hi), means[~np.isnan(means)]

    out_rows = []

    def emit(scope, quantity, mean, lo, hi, n, p=None, p_holm=None):
        out_rows.append({"scope": scope, "quantity": quantity, "n": n,
                         "mean": round(mean, 3), "ci_lo": round(lo, 3),
                         "ci_hi": round(hi, 3),
                         "p": None if p is None else float(f"{p:.2g}"),
                         "p_holm": None if p_holm is None else float(f"{p_holm:.2g}")})

    # descriptive: oracle bucket means on each model's DIAG/UNDIAG/CALM cells
    desc = {}
    for m in MODELS:
        for cls in ["DIAG", "UNDIAG", "CALM"]:
            n_weeks = sum(len(v) for v in by_mc.get((m, cls), {}).values())
            for bname, keys in BUCKETS.items():
                for side in ("model", "oracle"):
                    point, lo, hi, _ = cboot(seed_means(m, cls, keys, side))
                    desc[(m, cls, bname, side)] = (point, lo, hi)
                    emit(f"{SHORT[m]}/{cls}/{side}", f"{bname} $/wk",
                         point, lo, hi, n_weeks)
            for side in ("model", "oracle"):
                point, lo, hi, _ = cboot(seed_means(m, cls, COST_KEYS, side))
                desc[(m, cls, "total", side)] = (point, lo, hi)
                emit(f"{SHORT[m]}/{cls}/{side}", "total $/wk", point, lo, hi, n_weeks)

    # ---- F3: per model, holding_total DIAG diff (Holm-4) ----
    # ---- F4: per model, procurement DIAG diff (Holm-4) ----
    for fam, bname in (("F3", "holding_total"), ("F4", "procurement")):
        pvals, tmp = [], []
        for m in MODELS:
            point, lo, hi, means = cboot(seed_means(m, "DIAG", BUCKETS[bname], "diff"))
            pvals.append(boot_p(means))
            tmp.append((f"{SHORT[m]} {bname} DIAG model-oracle $/wk", point, lo, hi))
        for (name, point, lo, hi), p, pp in zip(tmp, pvals, holm(pvals)):
            emit(fam, name, point, lo, hi, n=len(seeds_s), p=p, p_holm=pp)

    # ---- F5: sonnet air DIAG diff (single test) ----
    son = "anthropic-claude-sonnet-5"
    point, lo, hi, means = cboot(seed_means(son, "DIAG", ["air"], "diff"))
    emit("F5", "sonnet air DIAG model-oracle $/wk", point, lo, hi,
         n=len(seeds_s), p=boot_p(means), p_holm=boot_p(means))

    with open(RUNS / "oracle_decomp.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["scope", "quantity", "n", "mean",
                                          "ci_lo", "ci_hi", "p", "p_holm"])
        w.writeheader()
        w.writerows(out_rows)
    print(f"wrote {RUNS/'oracle_decomp.csv'} ({len(out_rows)} rows)")

    # ---- markdown report ----
    lines = ["# Oracle reference for the cost decomposition\n",
             "Fair-oracle per-week engine cost_breakdown under the exact "
             "oracle_refs protocol (20 reps, k=191..210), rep-mean per "
             "(seed, week), compared against each model's spend on its own "
             "diagnosed weeks. Seed-cluster paired bootstrap, "
             f"N_BOOT={N_BOOT}, rng seed {BOOT_SEED}. Caveat: week-t books "
             "reflect each policy's earlier decisions; this is spend on the "
             "same tape weeks, not a one-decision counterfactual.\n"]

    lines.append("## Model vs oracle, bucket $/wk on the model's own weeks (95% CI)\n")
    lines.append("| model | class | side | procurement | holding | stockout "
                 "| levers | incident | total |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for m in MODELS:
        for cls in ["DIAG", "UNDIAG", "CALM"]:
            for side in ("model", "oracle"):
                def fmt(b):
                    p, lo, hi = desc[(m, cls, b, side)]
                    return f"{p:.0f} [{lo:.0f},{hi:.0f}]"
                lines.append(f"| {SHORT[m]} | {cls} | {side} | "
                             f"{fmt('procurement')} | {fmt('holding_total')} | "
                             f"{fmt('stockout_total')} | {fmt('levers')} | "
                             f"{fmt('incident')} | {fmt('total')} |")

    lines.append("\n## Pre-registered contrasts (STATS-GUIDELINES 2026-07-30)\n")
    for fam, label in (("F3", "holding_total DIAG, model - oracle (Holm-4)"),
                       ("F4", "procurement DIAG, model - oracle (Holm-4)"),
                       ("F5", "sonnet air DIAG, model - oracle (single)")):
        lines.append(f"\n{fam}: {label}\n")
        lines.append("| contrast | mean | 95% CI | p | p(Holm) |")
        lines.append("|---|---|---|---|---|")
        for r in out_rows:
            if r["scope"] == fam:
                lines.append(f"| {r['quantity']} | {r['mean']:+.2f} | "
                             f"[{r['ci_lo']:+.2f}, {r['ci_hi']:+.2f}] | "
                             f"{r['p']} | {r['p_holm']} |")

    (RUNS / "oracle_decomp.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {RUNS/'oracle_decomp.md'}")


if __name__ == "__main__":
    sys.exit(main())
