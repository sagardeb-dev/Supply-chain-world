"""Uncertainty quantification for ladder-v1 skill scores.

Paired bootstrap CIs + Wilcoxon signed-rank tests on the frozen
skill_scores.csv. Purely additive: reads canonical files, writes
uq.csv + uq.md next to them. Run:

    uv run --with numpy,scipy python analysis/uq.py
"""
import csv
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

RUNS = Path(__file__).resolve().parent.parent / "runs" / "ladder-v1"
MODELS = [  # canonical four; stray gemini row is dropped
    "openai-gpt-5.4",
    "anthropic-claude-sonnet-5",
    "x-ai-grok-4.5",
    "deepseek-deepseek-v4-pro",
]
SHORT = {"openai-gpt-5.4": "gpt-5.4",
         "anthropic-claude-sonnet-5": "claude-sonnet-5",
         "x-ai-grok-4.5": "grok-4.5",
         "deepseek-deepseek-v4-pro": "deepseek-v4-pro"}
# frozen ALL-group means from report.md — sanity gate
FROZEN = {"openai-gpt-5.4": 0.62, "anthropic-claude-sonnet-5": 0.49,
          "x-ai-grok-4.5": -0.13, "deepseek-deepseek-v4-pro": -0.23}
N_BOOT = 10_000
BOOT_SEED = 20260728


def load():
    all_rows = [r for r in csv.DictReader(open(RUNS / "skill_scores.csv"))
                if r["model"] in MODELS]
    rows = [r for r in all_rows if r["skill"] != ""]
    seeds = {m: {r["seed"] for r in rows if r["model"] == m} for m in MODELS}
    ref = seeds[MODELS[0]]
    assert all(s == ref for s in seeds.values()), "seed sets differ across models"
    assert len(ref) == 49, f"expected 49 scoreable seeds, got {len(ref)}"
    order = sorted(ref, key=int)
    group = {r["seed"]: r["group"] for r in all_rows}
    skill = {m: np.array([next(float(r["skill"]) for r in rows
                               if r["model"] == m and r["seed"] == s)
                          for s in order]) for m in MODELS}
    for m in MODELS:  # sanity gate vs frozen report.md
        assert round(skill[m].mean(), 2) == FROZEN[m], \
            f"{m}: mean {skill[m].mean():.4f} != frozen {FROZEN[m]}"
    return order, group, skill, rows


def boot_ci(values, idx_draws):
    means = values[idx_draws].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return values.mean(), lo, hi


def holm(pvals):
    order = np.argsort(pvals)
    adj = np.empty_like(pvals)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, pvals[i] * (len(pvals) - rank))
        adj[i] = min(1.0, running)
    return adj


def main():
    order, group, skill, rows = load()
    rng = np.random.default_rng(BOOT_SEED)
    out = []

    def emit(scope, quantity, mean, lo, hi, p=None, p_holm=None, n=None):
        out.append({"scope": scope, "quantity": quantity, "n": n,
                    "mean": round(mean, 3), "ci_lo": round(lo, 3),
                    "ci_hi": round(hi, 3),
                    "p_wilcoxon": None if p is None else float(f"{p:.2g}"),
                    "p_holm": None if p_holm is None else float(f"{p_holm:.2g}")})

    # per-model overall: paired bootstrap (same seed draws for every model)
    draws = rng.integers(0, 49, size=(N_BOOT, 49))
    for m in MODELS:
        mean, lo, hi = boot_ci(skill[m], draws)
        p = wilcoxon(skill[m]).pvalue  # vs 0 = the floor
        emit("ALL", f"{SHORT[m]} mean skill", mean, lo, hi, p=p, n=49)

    # per-group CIs
    for g in ["ISOLATED", "PERSISTENT", "COMPOUND"]:
        mask = np.array([group[s] == g for s in order])
        gdraws = rng.integers(0, mask.sum(), size=(N_BOOT, mask.sum()))
        for m in MODELS:
            v = skill[m][mask]
            mean, lo, hi = boot_ci(v, gdraws)
            emit(g, f"{SHORT[m]} mean skill", mean, lo, hi, n=int(mask.sum()))

    # pairwise contrasts, ALL, Holm over the 6 pairs
    pairs = list(combinations(MODELS, 2))
    pvals, rows_tmp = [], []
    for a, b in pairs:
        d = skill[a] - skill[b]
        mean, lo, hi = boot_ci(d, draws)
        p = wilcoxon(d).pvalue
        pvals.append(p)
        rows_tmp.append((f"{SHORT[a]} - {SHORT[b]}", mean, lo, hi, p))
    for (name, mean, lo, hi, p), ph in zip(rows_tmp, holm(np.array(pvals))):
        emit("ALL", name, mean, lo, hi, p=p, p_holm=ph, n=49)

    # the 3-vs-1 COMPOUND claim: sonnet vs each other model, Holm over 3
    cmask = np.array([group[s] == "COMPOUND" for s in order])
    cdraws = rng.integers(0, cmask.sum(), size=(N_BOOT, cmask.sum()))
    son = "anthropic-claude-sonnet-5"
    pvals, rows_tmp = [], []
    for m in [x for x in MODELS if x != son]:
        d = skill[m][cmask] - skill[son][cmask]
        mean, lo, hi = boot_ci(d, cdraws)
        p = wilcoxon(d).pvalue
        pvals.append(p)
        rows_tmp.append((f"{SHORT[m]} - {SHORT[son]}", mean, lo, hi, p))
    for (name, mean, lo, hi, p), ph in zip(rows_tmp, holm(np.array(pvals))):
        emit("COMPOUND", name, mean, lo, hi, p=p, p_holm=ph, n=int(cmask.sum()))

    # benchmark resolution: median CI half-width across the 6 ALL contrasts
    widths = [(r["ci_hi"] - r["ci_lo"]) / 2 for r in out
              if r["scope"] == "ALL" and " - " in r["quantity"]]
    emit("ALL", "resolution (median contrast CI half-width)",
         float(np.median(widths)), min(widths), max(widths), n=6)

    # ---- belief-side claims (beliefs.csv weeks + belief_metrics.csv) ----
    weeks = [r for r in csv.DictReader(open(RUNS / "beliefs.csv"))
             if r["model"] in MODELS]
    bm = {(r["model"], r["seed"]): r
          for r in csv.DictReader(open(RUNS / "belief_metrics.csv"))
          if r["model"] in MODELS}
    all_seeds = sorted({s for m, s in bm}, key=int)
    assert len(all_seeds) == 50

    def diag(r):  # week is a diagnosed stress week
        true = set(r["factors_stressed_true"].split(";")) - {""}
        named = set(r["factors_named"].split(";")) - {""}
        return bool(true), bool(true & named), int(r["stockout"])

    # per (model,seed): [diagnosed weeks, diag stockouts, undiag weeks, undiag stockouts]
    wk = {(m, s): [0, 0, 0, 0] for m in MODELS for s in all_seeds}
    for r in weeks:
        # DEFECT FIX 2026-07-30 (D2a): week 26 carries no rationale (the run
        # ends before another decision), so its stress weeks are unknowable,
        # not undiagnosed -- excluded from the diag/undiag pools.
        if int(r["week"]) >= 26:
            continue
        stressed, hit, so = diag(r)
        if not stressed:
            continue
        c = wk[(r["model"], r["seed"])]
        if hit:
            c[0] += 1; c[1] += so
        else:
            c[2] += 1; c[3] += so
    # sanity vs corrected confound table (air-stockout regrade 2026-07-30:
    # stockout flags now engine truth from cost_weeks.csv; pre-fix values
    # were sonnet (0.34,.19) gpt (0.26,.14) dpsk (0.26,.11) grok (0.24,.12))
    # (with D2a week-26 exclusion: undiag pools shrink by the 38 unknowable
    # final-week stress rows per model)
    CONF = {"anthropic-claude-sonnet-5": (0.18, 515, 0.06, 124),
            "openai-gpt-5.4": (0.11, 502, 0.04, 137),
            "deepseek-deepseek-v4-pro": (0.17, 469, 0.02, 170),
            "x-ai-grok-4.5": (0.14, 544, 0.02, 95)}
    for m in MODELS:
        d = [sum(wk[(m, s)][i] for s in all_seeds) for i in range(4)]
        exp = CONF[m]
        assert (d[0], d[2]) == (exp[1], exp[3]), f"{m} week counts {d} != {exp}"
        assert round(d[1] / d[0], 2) == exp[0] and round(d[3] / d[2], 2) == exp[2], \
            f"{m} confound rates {d} != {exp}"

    bdraws = rng.integers(0, 50, size=(N_BOOT, 50))  # paired seed clusters

    def cluster_stat(m, idx, num_i, den_i, seeds=all_seeds):
        num = np.array([wk[(m, s)][num_i] for s in seeds], float)
        den = np.array([wk[(m, s)][den_i] for s in seeds], float)
        tot_n, tot_d = num[idx].sum(axis=-1), den[idx].sum(axis=-1)
        return np.where(tot_d > 0, tot_n / np.maximum(tot_d, 1), np.nan)

    def boot_p(dist, point):  # two-sided bootstrap p for point != 0
        return min(1.0, 2 * min((dist <= 0).mean(), (dist >= 0).mean()))

    # detection rate: pooled 1 - never/episodes, paired cluster bootstrap
    det = {m: (np.array([int(bm[(m, s)]["n_episodes"]) for s in all_seeds], float),
               np.array([int(bm[(m, s)]["n_never_detected"]) for s in all_seeds], float))
           for m in MODELS}
    for m in MODELS:
        eps, nev = det[m]
        # D2b fix: 266 detectable episodes (283 minus the 17 final-week onsets
        # that are undetectable by construction, excluded at the grader)
        assert eps.sum() == 266
        point = 1 - nev.sum() / eps.sum()
        dist = 1 - nev[bdraws].sum(axis=1) / eps[bdraws].sum(axis=1)
        lo, hi = np.percentile(dist, [2.5, 97.5])
        emit("ALL", f"{SHORT[m]} detection rate", point, lo, hi, n=50)
    pvals, rows_tmp = [], []
    for a, b in combinations(MODELS, 2):
        da = 1 - det[a][1][bdraws].sum(axis=1) / det[a][0][bdraws].sum(axis=1)
        db = 1 - det[b][1][bdraws].sum(axis=1) / det[b][0][bdraws].sum(axis=1)
        pa = 1 - det[a][1].sum() / det[a][0].sum()
        pb = 1 - det[b][1].sum() / det[b][0].sum()
        dist = da - db
        lo, hi = np.percentile(dist, [2.5, 97.5])
        pvals.append(boot_p(dist, pa - pb))
        rows_tmp.append((f"det rate {SHORT[a]} - {SHORT[b]}", pa - pb, lo, hi))
    for (name, mean, lo, hi), ph in zip(rows_tmp, holm(np.array(pvals))):
        emit("ALL", name, mean, lo, hi, p=None, p_holm=ph, n=50)

    # detection lag: episode-weighted pooled mean; tier contrast + pairwise
    lag = {m: np.array([float(bm[(m, s)]["mean_detection_lag"]) for s in all_seeds])
           for m in MODELS}
    ndet = {m: det[m][0] - det[m][1] for m in MODELS}
    def pooled_lag(m, idx):
        w = ndet[m][idx]
        return (lag[m][idx] * w).sum(axis=-1) / w.sum(axis=-1)
    for m in MODELS:
        point = pooled_lag(m, np.arange(50))
        dist = pooled_lag(m, bdraws)
        lo, hi = np.percentile(dist, [2.5, 97.5])
        emit("ALL", f"{SHORT[m]} detection lag (wk)", point, lo, hi, n=50)
    pvals, rows_tmp = [], []
    for a, b in combinations(MODELS, 2):
        dist = pooled_lag(a, bdraws) - pooled_lag(b, bdraws)
        point = pooled_lag(a, np.arange(50)) - pooled_lag(b, np.arange(50))
        lo, hi = np.percentile(dist, [2.5, 97.5])
        pvals.append(boot_p(dist, point))
        rows_tmp.append((f"det lag {SHORT[a]} - {SHORT[b]}", point, lo, hi))
    for (name, mean, lo, hi), ph in zip(rows_tmp, holm(np.array(pvals))):
        emit("ALL", name, mean, lo, hi, p=None, p_holm=ph, n=50)

    # KDR by group + "peaks on PERSISTENT" per model (Holm over 4).
    # Corrected table (air-stockout regrade 2026-07-30); pre-fix values were
    # sonnet (0.24,0.43,0.30,0.34) gpt (0.08,0.37,0.22,0.26)
    # dpsk (0.07,0.40,0.22,0.26) grok (0.09,0.34,0.21,0.24).
    KDR_FROZEN = {"anthropic-claude-sonnet-5": (0.10, 0.22, 0.18, 0.18),
                  "openai-gpt-5.4": (0.05, 0.18, 0.08, 0.11),
                  "deepseek-deepseek-v4-pro": (0.05, 0.26, 0.14, 0.17),
                  "x-ai-grok-4.5": (0.06, 0.18, 0.13, 0.14)}
    gseeds = {g: [s for s in all_seeds if group.get(s) == g]
              for g in ["ISOLATED", "PERSISTENT", "COMPOUND"]}
    for m in MODELS:
        vals = []
        for g in ["ISOLATED", "PERSISTENT", "COMPOUND"]:
            ss = gseeds[g]
            gi = rng.integers(0, len(ss), size=(N_BOOT, len(ss)))
            point = cluster_stat(m, np.arange(len(ss)), 1, 0, ss)
            dist = cluster_stat(m, gi, 1, 0, ss)
            lo, hi = np.nanpercentile(dist, [2.5, 97.5])
            emit(g, f"{SHORT[m]} KDR", float(point), lo, hi, n=len(ss))
            vals.append(round(float(point), 2))
        allp = cluster_stat(m, np.arange(50), 1, 0)
        vals.append(round(float(allp), 2))
        assert tuple(vals) == KDR_FROZEN[m], f"{m} KDR {vals} != frozen"
    pvals, rows_tmp = [], []
    pers = np.array([group.get(s) == "PERSISTENT" for s in all_seeds])
    for m in MODELS:
        num = np.array([wk[(m, s)][1] for s in all_seeds], float)
        den = np.array([wk[(m, s)][0] for s in all_seeds], float)
        def kdr_split(idx):
            pm = pers[idx]
            p_rate = np.where(pm, num[idx], 0).sum(axis=-1) / \
                np.maximum(np.where(pm, den[idx], 0).sum(axis=-1), 1)
            o_rate = np.where(~pm, num[idx], 0).sum(axis=-1) / \
                np.maximum(np.where(~pm, den[idx], 0).sum(axis=-1), 1)
            return p_rate - o_rate
        point = float(kdr_split(np.arange(50)))
        dist = kdr_split(bdraws)
        lo, hi = np.percentile(dist, [2.5, 97.5])
        pvals.append(boot_p(dist, point))
        rows_tmp.append((f"{SHORT[m]} KDR persistent - rest", point, lo, hi))
    for (name, mean, lo, hi), ph in zip(rows_tmp, holm(np.array(pvals))):
        emit("PERSISTENT", name, mean, lo, hi, p=None, p_holm=ph, n=50)

    # confound: diagnosed - undiagnosed stockout rate per model (Holm over 4)
    pvals, rows_tmp = [], []
    for m in MODELS:
        d_diag = cluster_stat(m, bdraws, 1, 0)
        d_und = cluster_stat(m, bdraws, 3, 2)
        point = float(cluster_stat(m, np.arange(50), 1, 0)
                      - cluster_stat(m, np.arange(50), 3, 2))
        dist = d_diag - d_und
        lo, hi = np.percentile(dist, [2.5, 97.5])
        pvals.append(boot_p(dist, point))
        rows_tmp.append((f"{SHORT[m]} stockout diag - undiag", point, lo, hi))
    for (name, mean, lo, hi), ph in zip(rows_tmp, holm(np.array(pvals))):
        emit("ALL", name, mean, lo, hi, p=None, p_holm=ph, n=50)

    # oracle-reference noise vs seed-to-seed spread (delta method per seed)
    per_seed = {(r["model"], r["seed"]): r for r in rows}
    ratios = []
    for m in MODELS:
        for s in order:
            r = per_seed[(m, s)]
            h = float(r["headroom"])
            se = abs(float(r["basestock"]) - float(r["llm_cost"])) \
                * float(r["oracle_se"]) / h**2
            ratios.append(se)
        sd = skill[m].std(ddof=1)
    emit("ALL", "median per-seed skill SE from oracle noise",
         float(np.median(ratios)), float(np.percentile(ratios, 25)),
         float(np.percentile(ratios, 75)), n=len(ratios))
    print(f"seed-to-seed skill SD (per model): "
          f"{[round(skill[m].std(ddof=1), 2) for m in MODELS]}")

    with open(RUNS / "uq.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out[0].keys())
        w.writeheader()
        w.writerows(out)
    with open(RUNS / "uq.md", "w") as f:
        f.write(f"# UQ — paired bootstrap ({N_BOOT} draws, seed {BOOT_SEED}), "
                f"Wilcoxon signed-rank, Holm-corrected\n\n"
                "| scope | quantity | n | mean | 95% CI | p | p(Holm) |\n"
                "|---|---|---|---|---|---|---|\n")
        for r in out:
            f.write(f"| {r['scope']} | {r['quantity']} | {r['n']} | "
                    f"{r['mean']:+.3f} | [{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}] | "
                    f"{r['p_wilcoxon'] if r['p_wilcoxon'] is not None else ''} | "
                    f"{r['p_holm'] if r['p_holm'] is not None else ''} |\n")
    print(f"wrote {RUNS/'uq.csv'} and uq.md ({len(out)} rows)")


if __name__ == "__main__":
    sys.exit(main())
