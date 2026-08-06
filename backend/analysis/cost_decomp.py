"""Per-week cost decomposition of LLM agent episodes: replay logged actions
through the world engine, verify against the trace's WORLD ADVANCED banners,
then join with beliefs.csv to break out cost composition by DIAG/UNDIAG/CALM
weeks. Purely additive: reads runs/ladder-v1/*, writes cost_weeks.csv,
cost_decomp.csv, cost_decomp.md. Run:

    uv run --with numpy python analysis/cost_decomp.py
"""
import csv
import re
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.world.engine import World
from src.world.config import WorldConfig
from src.world.registry import RICH

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

ADV_RE = re.compile(
    r"^WORLD ADVANCED -> week (\d+)  week cost \$(-?\d+)  cum \$(-?\d+)")
CALL_RE = re.compile(r"^  >> (\w+)\((.*)\)$")
DECIDING_RE = re.compile(r"^=+ DECIDING WEEK \d+ =+$")


# ---------------------------------------------------------------- parsing --

def parse_kwargs(raw: str) -> dict:
    if not raw.strip():
        return {}
    out = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        out[k.strip()] = v.strip()
    return out


def parse_trace(path: Path):
    """Return list of (week, [ (tool, kwargs), ... ]) week bundles, plus the
    list of (week, cost, cum) verification targets, in engine order. Tolerates
    the one known logging artifact: a duplicate WORLD ADVANCED -> week k line
    (same week number repeated, from a malformed tool call that never reached
    the engine) -- such a line is not a real boundary and its surrounding
    calls fold into the eventual real advance to week k."""
    lines = path.read_text().splitlines()
    weeks = []          # (week, cost, cum)
    bundles = []         # list of [(tool, kwargs), ...] aligned with weeks
    pending = []
    week_ptr = 0
    for line in lines:
        m = CALL_RE.match(line)
        if m:
            pending.append((m.group(1), parse_kwargs(m.group(2))))
            continue
        m = ADV_RE.match(line)
        if not m:
            continue
        k, cost, cum = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if k == week_ptr + 1:
            weeks.append((k, cost, cum))
            bundles.append(pending)
            pending = []
            week_ptr = k
        elif k == week_ptr:
            # phantom duplicate advance: not a real engine step, keep
            # accumulating into the same pending bundle for the real one.
            continue
        else:
            raise ValueError(f"{path}: unexpected week jump {week_ptr} -> {k}")
    if week_ptr != 26:
        raise ValueError(f"{path}: trace ended at week {week_ptr}, expected 26")
    return weeks, bundles


# ------------------------------------------------------------------ replay --

def apply_lever(world, tool, kwargs):
    try:
        if tool == "buy_briefing":
            world.request_briefing()
        elif tool == "buy_audit":
            world.request_audit()
        elif tool == "lock_freight":
            world.lock_freight(int(kwargs["weeks"]))
        elif tool == "expedite_air":
            world.expedite_air(int(kwargs["qty"]), kwargs.get("component", ""))
        elif tool == "inspect_batch":
            world.inspect_batch(kwargs.get("supplier") or None)
        elif tool == "write_todos":
            pass  # agent-side bookkeeping, no engine effect
        elif tool == "place_order":
            pass  # handled separately: only the last one in the bundle steps
        else:
            raise ValueError(f"unrecognized tool {tool!r}")
    except (ValueError, RuntimeError):
        # a call that failed in the real run had no effect on the world.
        pass


def replay_episode(model, seed, path):
    weeks, bundles = parse_trace(path)
    world = World(WorldConfig(sup_mask_otif=True), registry=RICH)
    world.reset(seed)
    rows = []
    mismatches = []
    for (wk, want_cost, want_cum), bundle in zip(weeks, bundles):
        place_calls = [(t, kw) for t, kw in bundle if t == "place_order"]
        for t, kw in bundle:
            if t != "place_order":
                apply_lever(world, t, kw)
        if not place_calls:
            raise ValueError(f"{path}: week {wk} has no place_order call")
        tool, kw = place_calls[-1]  # only the last advanced the real world
        qty = int(kw.get("qty", 0) or 0)
        route = kw.get("route") or None
        supplier = (kw.get("supplier") or None) if qty else None
        contract = None
        if kw.get("contract_action"):
            contract = {"action": kw["contract_action"],
                        "supplier": kw.get("contract_supplier") or supplier,
                        "terms": kw.get("contract_terms") or None}
        action = {"qty": qty, "route": route, "supplier": supplier}
        if contract:
            action["contract"] = contract
        obs, cost, done, _info = world.step(action)  # must succeed
        got_cost_s = f"{cost:.0f}"
        got_cum_s = f"{world.total_cost:.0f}"
        if got_cost_s != str(want_cost) or got_cum_s != str(want_cum):
            mismatches.append((model, seed, wk, f"{got_cost_s}/{got_cum_s}",
                               f"{want_cost}/{want_cum}"))
        cb = obs["cost_breakdown"]
        row = {"model": model, "seed": seed, "week": wk}
        for key in COST_KEYS:
            row[key] = float(cb.get(key, 0.0))
        row["total"] = sum(row[k] for k in COST_KEYS)
        rows.append(row)
    return rows, mismatches


# --------------------------------------------------------------- bootstrap --

def boot_ci(values, idx_draws):
    means = values[idx_draws].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(values.mean()), float(lo), float(hi)


def boot_p(dist):
    return min(1.0, 2 * min((dist <= 0).mean(), (dist >= 0).mean()))


def holm(pvals):
    pvals = np.array(pvals, float)
    order = np.argsort(pvals)
    adj = np.empty_like(pvals)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, pvals[i] * (len(pvals) - rank))
        adj[i] = min(1.0, running)
    return adj


# --------------------------------------------------------------------- main --

def main():
    all_rows = []
    all_mismatches = []
    n_episodes = 0
    for model in MODELS:
        mdir = RUNS / model
        paths = sorted(mdir.glob("seed*-rich.chat.txt"),
                       key=lambda p: int(re.match(r"seed(\d+)", p.name).group(1)))
        for path in paths:
            seed = int(re.match(r"seed(\d+)", path.name).group(1))
            rows, mismatches = replay_episode(model, seed, path)
            all_rows.extend(rows)
            all_mismatches.extend(mismatches)
            n_episodes += 1

    print(f"replayed {n_episodes} episodes "
          f"({sum(1 for m in MODELS for _ in (RUNS/m).glob('seed*-rich.chat.txt'))} traces found)")

    if all_mismatches:
        print(f"CHECKSUM FAIL: {len(all_mismatches)} week mismatches")
        for model, seed, wk, got, want in all_mismatches:
            print(f"  {model} seed{seed} week{wk}: got {got} want {want}")
        sys.exit(1)
    print(f"CHECKSUM PASS: all {n_episodes} episodes x 26 weeks verified "
          f"against WORLD ADVANCED banners")

    # ---- Task 2: write cost_weeks.csv ----
    fieldnames = ["model", "seed", "week"] + COST_KEYS + ["total"]
    with open(RUNS / "cost_weeks.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_rows:
            out = dict(r)
            for k in COST_KEYS + ["total"]:
                out[k] = round(out[k], 2)
            w.writerow(out)
    print(f"wrote {RUNS/'cost_weeks.csv'} ({len(all_rows)} rows)")

    # ---- join with beliefs.csv ----
    cw = {(r["model"], str(r["seed"]), r["week"]): r for r in all_rows}
    beliefs = [r for r in csv.DictReader(open(RUNS / "beliefs.csv"))
               if r["model"] in MODELS]

    def classify(r):
        true = set(r["factors_stressed_true"].split(";")) - {""}
        named = set(r["factors_named"].split(";")) - {""}
        if not true:
            return "CALM"
        # DEFECT FIX 2026-07-30 (D2a): week 26 has no rationale, so a stressed
        # final week is unknowable, not undiagnosed -- excluded from both
        # belief-dependent classes (CALM is truth-only and keeps its wk26 rows).
        if int(r["week"]) >= 26:
            return None
        return "DIAG" if (true & named) else "UNDIAG"

    joined = []
    for r in beliefs:
        key = (r["model"], r["seed"], int(r["week"]))
        rec = cw.get(key)
        if rec is None:
            raise ValueError(f"beliefs.csv row {key} has no matching replayed week")
        got_total = f"{rec['total']:.0f}"
        want_total = f"{float(r['week_cost']):.0f}"
        assert got_total == want_total, (
            f"beliefs.csv/replay total mismatch {key}: {got_total} != {want_total}")
        joined.append({"model": r["model"], "seed": r["seed"], "week": int(r["week"]),
                        "class": classify(r), **{k: rec[k] for k in COST_KEYS},
                        "total": rec["total"]})
    print(f"joined {len(joined)} weeks against beliefs.csv (sanity gate passed)")

    seeds = sorted({r["seed"] for r in joined}, key=int)
    assert len(seeds) == 50
    for m in MODELS:
        ms = sorted({r["seed"] for r in joined if r["model"] == m}, key=int)
        assert ms == seeds, f"{m}: seed set differs from shared 50"

    def bucket(row, keys):
        return sum(row[k] for k in keys)

    BUCKETS = {
        "procurement": ["shipping", "surcharge"],
        "holding_total": ["holding", "in_transit"],
        "stockout_total": ["stockout", "couple"],
        "levers": ["air", "inspect", "briefing", "audit", "dual_source"],
        "incident": ["demurrage", "rework"],
    }
    LEVERS = ["air", "inspect", "briefing", "audit", "dual_source"]
    CLASSES = ["DIAG", "UNDIAG", "CALM"]

    # per (model, seed, class) list of weeks, and per-seed arrays for bootstrap
    by_ms_class = {}
    for r in joined:
        by_ms_class.setdefault((r["model"], r["class"]), {}).setdefault(
            r["seed"], []).append(r)

    def seed_means(model, cls, keys):
        """Per-seed mean $/week for `keys` bucket, restricted to (model,cls)
        weeks; NaN for a seed with zero such weeks (excluded from that draw)."""
        d = by_ms_class.get((model, cls), {})
        out = np.full(len(seeds), np.nan)
        for i, s in enumerate(seeds):
            rows_s = d.get(s, [])
            if rows_s:
                out[i] = np.mean([bucket(r, keys) for r in rows_s])
        return out

    def cluster_boot_mean(vals, idx_draws):
        """Mean over a bootstrap resample of seed clusters, ignoring seeds
        with no qualifying weeks (nan) within each resample."""
        sub = vals[idx_draws]  # (N_BOOT, n_seeds)
        with np.errstate(invalid="ignore"):
            means = np.nanmean(sub, axis=1)
        point = float(np.nanmean(vals))
        lo, hi = np.nanpercentile(means, [2.5, 97.5])
        return point, float(lo), float(hi), means

    rng = np.random.default_rng(BOOT_SEED)
    draws = rng.integers(0, len(seeds), size=(N_BOOT, len(seeds)))

    out_rows = []

    def emit(scope, quantity, mean, lo, hi, n, p=None, p_holm=None):
        out_rows.append({"scope": scope, "quantity": quantity, "n": n,
                          "mean": round(mean, 3), "ci_lo": round(lo, 3),
                          "ci_hi": round(hi, 3),
                          "p": None if p is None else float(f"{p:.2g}"),
                          "p_holm": None if p_holm is None else float(f"{p_holm:.2g}")})

    # descriptive: per model x class x bucket means with CIs
    bucket_means = {}  # (model,cls,bucket) -> (point,lo,hi,means_array)
    for m in MODELS:
        for cls in CLASSES:
            n_weeks = sum(len(v) for v in by_ms_class.get((m, cls), {}).values())
            for bname, keys in BUCKETS.items():
                vals = seed_means(m, cls, keys)
                point, lo, hi, _ = cluster_boot_mean(vals, draws)
                bucket_means[(m, cls, bname)] = (point, lo, hi)
                emit(f"{SHORT[m]}/{cls}", f"{bname} $/wk", point, lo, hi, n_weeks)
            # total too, for context
            vals = seed_means(m, cls, COST_KEYS)
            point, lo, hi, _ = cluster_boot_mean(vals, draws)
            bucket_means[(m, cls, "total")] = (point, lo, hi)
            emit(f"{SHORT[m]}/{cls}", "total $/wk", point, lo, hi, n_weeks)

    # descriptive: per-lever DIAG means
    lever_means = {}
    for m in MODELS:
        n_weeks = sum(len(v) for v in by_ms_class.get((m, "DIAG"), {}).values())
        for lv in LEVERS:
            vals = seed_means(m, "DIAG", [lv])
            point, lo, hi, _ = cluster_boot_mean(vals, draws)
            lever_means[(m, lv)] = (point, lo, hi)
            emit(f"{SHORT[m]}/DIAG", f"{lv} $/wk", point, lo, hi, n_weeks)

    # ---- Family 1: per model, levers$/wk DIAG - CALM (4 tests, Holm) ----
    pvals, tmp = [], []
    for m in MODELS:
        v_diag = seed_means(m, "DIAG", BUCKETS["levers"])
        v_calm = seed_means(m, "CALM", BUCKETS["levers"])
        d = v_diag - v_calm
        point = float(np.nanmean(d))
        sub = d[draws]
        with np.errstate(invalid="ignore"):
            means = np.nanmean(sub, axis=1)
        lo, hi = np.nanpercentile(means, [2.5, 97.5])
        p = boot_p(means[~np.isnan(means)])
        pvals.append(p)
        tmp.append((f"{SHORT[m]} levers DIAG - CALM $/wk", point, lo, hi))
    ph = holm(pvals)
    for (name, point, lo, hi), p, pp in zip(tmp, pvals, ph):
        emit("F1", name, point, lo, hi, n=len(seeds), p=p, p_holm=pp)

    # ---- Family 2 ----
    son, gpt = "anthropic-claude-sonnet-5", "openai-gpt-5.4"
    pvals2, tmp2 = [], []

    # (a) sonnet air$/DIAG-week - gpt air$/DIAG-week
    v_son = seed_means(son, "DIAG", ["air"])
    v_gpt = seed_means(gpt, "DIAG", ["air"])
    d = v_son - v_gpt
    point = float(np.nanmean(d))
    sub = d[draws]
    with np.errstate(invalid="ignore"):
        means = np.nanmean(sub, axis=1)
    lo, hi = np.nanpercentile(means, [2.5, 97.5])
    p = boot_p(means[~np.isnan(means)])
    pvals2.append(p)
    tmp2.append(("sonnet air$/DIAG-wk - gpt air$/DIAG-wk", point, lo, hi))

    # (b) gpt stockout_total share of DIAG-week total - sonnet's share
    def share_per_seed(model, num_keys, den_keys):
        d = by_ms_class.get((model, "DIAG"), {})
        out = np.full(len(seeds), np.nan)
        for i, s in enumerate(seeds):
            rows_s = d.get(s, [])
            if rows_s:
                num = sum(bucket(r, num_keys) for r in rows_s)
                den = sum(bucket(r, den_keys) for r in rows_s)
                out[i] = num / den if den else np.nan
        return out

    sh_gpt = share_per_seed(gpt, BUCKETS["stockout_total"], COST_KEYS)
    sh_son = share_per_seed(son, BUCKETS["stockout_total"], COST_KEYS)
    d = sh_gpt - sh_son
    point = float(np.nanmean(d))
    sub = d[draws]
    with np.errstate(invalid="ignore"):
        means = np.nanmean(sub, axis=1)
    lo, hi = np.nanpercentile(means, [2.5, 97.5])
    p = boot_p(means[~np.isnan(means)])
    pvals2.append(p)
    tmp2.append(("gpt stockout share DIAG - sonnet stockout share DIAG", point, lo, hi))

    ph2 = holm(pvals2)
    for (name, point, lo, hi), p, pp in zip(tmp2, pvals2, ph2):
        emit("F2", name, point, lo, hi, n=len(seeds), p=p, p_holm=pp)

    # ---- write cost_decomp.csv ----
    with open(RUNS / "cost_decomp.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["scope", "quantity", "n", "mean",
                                          "ci_lo", "ci_hi", "p", "p_holm"])
        w.writeheader()
        w.writerows(out_rows)
    print(f"wrote {RUNS/'cost_decomp.csv'} ({len(out_rows)} rows)")

    # ---- write cost_decomp.md ----
    lines = []
    lines.append("# Cost decomposition — per-week replay of ladder-v1 episodes\n")
    lines.append(f"{n_episodes} episodes x 26 weeks replayed through the world "
                 "engine and verified byte-for-byte against the trace's "
                 "`WORLD ADVANCED` cost/cum banners. Seed-cluster paired "
                 f"bootstrap, N_BOOT={N_BOOT}, rng seed {BOOT_SEED}.\n")

    lines.append("## Per-model x class bucket means ($/week, 95% CI)\n")
    lines.append("| model | class | n weeks | procurement | holding | "
                 "stockout | levers | incident | total |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for m in MODELS:
        for cls in CLASSES:
            n_weeks = sum(len(v) for v in by_ms_class.get((m, cls), {}).values())
            def fmt(b):
                p, lo, hi = bucket_means[(m, cls, b)]
                return f"{p:.0f} [{lo:.0f},{hi:.0f}]"
            lines.append(f"| {SHORT[m]} | {cls} | {n_weeks} | "
                         f"{fmt('procurement')} | {fmt('holding_total')} | "
                         f"{fmt('stockout_total')} | {fmt('levers')} | "
                         f"{fmt('incident')} | {fmt('total')} |")

    lines.append("\n## Per-lever DIAG-week means ($/week, 95% CI)\n")
    lines.append("| model | air | inspect | briefing | audit | dual_source |")
    lines.append("|---|---|---|---|---|---|")
    for m in MODELS:
        def fmtl(lv):
            p, lo, hi = lever_means[(m, lv)]
            return f"{p:.1f} [{lo:.1f},{hi:.1f}]"
        lines.append(f"| {SHORT[m]} | {fmtl('air')} | {fmtl('inspect')} | "
                     f"{fmtl('briefing')} | {fmtl('audit')} | "
                     f"{fmtl('dual_source')} |")

    lines.append("\n## Pre-registered contrasts\n")
    lines.append("Family 1 (per model, Holm-4): levers $/wk DIAG - CALM\n")
    lines.append("| model | mean | 95% CI | p | p(Holm) |")
    lines.append("|---|---|---|---|---|")
    for r in out_rows:
        if r["scope"] == "F1":
            lines.append(f"| {r['quantity']} | {r['mean']:+.2f} | "
                         f"[{r['ci_lo']:+.2f}, {r['ci_hi']:+.2f}] | "
                         f"{r['p']} | {r['p_holm']} |")
    lines.append("\nFamily 2 (Holm-2):\n")
    lines.append("| contrast | mean | 95% CI | p | p(Holm) |")
    lines.append("|---|---|---|---|---|")
    for r in out_rows:
        if r["scope"] == "F2":
            lines.append(f"| {r['quantity']} | {r['mean']:+.4f} | "
                         f"[{r['ci_lo']:+.4f}, {r['ci_hi']:+.4f}] | "
                         f"{r['p']} | {r['p_holm']} |")

    lines.append("\n## Summary (descriptive)\n")
    for m in MODELS:
        diag_total = bucket_means[(m, "DIAG", "total")][0]
        calm_total = bucket_means[(m, "CALM", "total")][0]
        diag_levers = bucket_means[(m, "DIAG", "levers")][0]
        calm_levers = bucket_means[(m, "CALM", "levers")][0]
        diag_stock = bucket_means[(m, "DIAG", "stockout_total")][0]
        calm_stock = bucket_means[(m, "CALM", "stockout_total")][0]
        lines.append(f"- **{SHORT[m]}**: DIAG-week total ${diag_total:.0f}/wk vs "
                     f"CALM-week total ${calm_total:.0f}/wk. Lever spend "
                     f"${diag_levers:.1f}/wk on DIAG vs ${calm_levers:.1f}/wk "
                     f"on CALM. Stockout-side cost ${diag_stock:.0f}/wk on DIAG "
                     f"vs ${calm_stock:.0f}/wk on CALM.")

    (RUNS / "cost_decomp.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {RUNS/'cost_decomp.md'}")


if __name__ == "__main__":
    sys.exit(main())
