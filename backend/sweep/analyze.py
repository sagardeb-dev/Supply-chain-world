"""Task 2 of the seed-sweep plan: turn sweep/results.csv into a markdown
analytics report (score spread, headroom distribution, what-kills-headroom
feature comparison, ladder candidates, correlations). stdlib only.

Run:
    uv run python -m sweep.analyze
    uv run python -m sweep.analyze --csv sweep/results.csv --out sweep/report.md
"""

import argparse
import csv
import math
import os
import statistics as st

NUMERIC_FIELDS = [
    "cost_suez", "cost_cape", "cost_basestock", "cost_oracle",
    "headroom", "best_fixed",
    "stress_disruption", "stress_freight", "stress_port", "stress_quality",
    "stress_supplier", "stress_demand",
    "max_overlap", "overlap_weeks", "spot_died", "port_block_longest",
    "fog_disruption", "fog_freight", "fog_port", "fog_quality",
    "fog_supplier", "fog_demand", "fog",
]

STRESS_FACTORS = ["disruption", "freight", "port", "quality", "supplier", "demand"]


def load(path):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            row = {"seed": int(r["seed"])}
            for k in NUMERIC_FIELDS:
                v = r[k]
                try:
                    row[k] = float(v)
                except ValueError:
                    row[k] = float("nan")
            rows.append(row)
    return rows


def _finite(vals):
    return [v for v in vals if not math.isnan(v)]


def pct(vals, p):
    vals = sorted(_finite(vals))
    if not vals:
        return float("nan")
    k = (len(vals) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return vals[int(k)]
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def pearson_r(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if not (math.isnan(x) or math.isnan(y))]
    if len(pairs) < 3:
        return float("nan")
    xs2, ys2 = zip(*pairs)
    if st.pstdev(xs2) == 0 or st.pstdev(ys2) == 0:
        return float("nan")
    mx, my = st.mean(xs2), st.mean(ys2)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den = math.sqrt(sum((x - mx) ** 2 for x in xs2) * sum((y - my) ** 2 for y in ys2))
    return num / den if den else float("nan")


def section_score_spread(rows):
    lines = ["## 1. Score spread", "",
             "| policy | mean | median | p10 | p90 |",
             "|---|---|---|---|---|"]
    for field, label in [("cost_suez", "suez (fixed 20)"),
                          ("cost_cape", "cape (fixed 20)"),
                          ("cost_basestock", "base-stock"),
                          ("cost_oracle", "oracle (k=50)")]:
        vals = [r[field] for r in rows]
        lines.append(f"| {label} | {st.mean(vals):.0f} | {st.median(vals):.0f} | "
                      f"{pct(vals, 0.10):.0f} | {pct(vals, 0.90):.0f} |")
    n = len(rows)
    oracle_beats_bs = sum(1 for r in rows if r["cost_oracle"] < r["cost_basestock"]) / n * 100
    bs_beats_fixed = sum(1 for r in rows
                          if r["cost_basestock"] < min(r["cost_suez"], r["cost_cape"])) / n * 100
    lines.append("")
    lines.append(f"- oracle beats base-stock: {oracle_beats_bs:.1f}% of seeds")
    lines.append(f"- base-stock beats both fixed policies: {bs_beats_fixed:.1f}% of seeds")
    return "\n".join(lines)


def section_headroom(rows):
    vals = [r["headroom"] for r in rows]
    lines = ["## 2. Headroom distribution", "",
             "| decile | headroom |", "|---|---|"]
    for d in range(1, 10):
        lines.append(f"| p{d*10} | {pct(vals, d/10):.1f} |")
    near_zero = sum(1 for r in rows
                     if r["cost_basestock"] and
                     abs(r["headroom"]) < 0.05 * r["cost_basestock"])
    lines.append("")
    lines.append(f"- near-zero-headroom seeds (|headroom| < 5% of basestock): "
                  f"{near_zero} / {len(rows)}")
    return "\n".join(lines)


def _decile_split(rows):
    ordered = sorted(rows, key=lambda r: r["headroom"])
    n = len(ordered)
    k = max(1, n // 10)
    return ordered[:k], ordered[-k:]


def section_kills_headroom(rows):
    bottom, top = _decile_split(rows)
    feats = ["stress_disruption", "stress_freight", "stress_port", "stress_quality",
              "stress_supplier", "stress_demand", "max_overlap", "overlap_weeks",
              "spot_died", "port_block_longest", "fog"]
    lines = ["## 3. What kills headroom (bottom-decile vs top-decile headroom seeds)", "",
             "| feature | bottom decile mean | top decile mean | gap |",
             "|---|---|---|---|"]
    gaps = []
    for f in feats:
        bmean = st.mean(_finite([r[f] for r in bottom])) if _finite([r[f] for r in bottom]) else float("nan")
        tmean = st.mean(_finite([r[f] for r in top])) if _finite([r[f] for r in top]) else float("nan")
        gap = tmean - bmean if not (math.isnan(bmean) or math.isnan(tmean)) else float("nan")
        gaps.append((f, bmean, tmean, gap))
    gaps_sorted = sorted(gaps, key=lambda t: (t[3] if not math.isnan(t[3]) else -1e18), reverse=True)
    for f, b, t, g in gaps_sorted:
        lines.append(f"| {f} | {b:.2f} | {t:.2f} | {g:.2f} |")
    if gaps_sorted:
        biggest = gaps_sorted[0]
        lines.append("")
        lines.append(f"- biggest feature gap: `{biggest[0]}` "
                      f"(bottom={biggest[1]:.2f}, top={biggest[2]:.2f})")
    return "\n".join(lines)


def _stress_summary(r):
    parts = [f"{f}={int(r[f'stress_{f}'])}" for f in STRESS_FACTORS if r[f"stress_{f}"] > 0]
    return ",".join(parts) if parts else "none"


def section_ladder(rows):
    lines = ["## 4. Ladder candidates", ""]

    def table(name, cands):
        lines.append(f"### {name}")
        lines.append("")
        lines.append("| seed | headroom | max_overlap | overlap_weeks | fog | stressed factors |")
        lines.append("|---|---|---|---|---|---|")
        for r in cands[:10]:
            fog = r["fog"] if not math.isnan(r["fog"]) else 0.0
            lines.append(f"| {int(r['seed'])} | {r['headroom']:.1f} | "
                          f"{int(r['max_overlap'])} | {int(r['overlap_weeks'])} | "
                          f"{fog:.2f} | {_stress_summary(r)} |")
        lines.append("")

    hvals = [r["headroom"] for r in rows]
    mid_lo, mid_hi = pct(hvals, 0.4), pct(hvals, 0.9)
    fog_vals = _finite([r["fog"] for r in rows])
    fog_hi_thresh = pct(fog_vals, 0.6) if fog_vals else 0.0

    easy = sorted([r for r in rows
                    if r["max_overlap"] <= 1 and mid_lo <= r["headroom"] <= mid_hi],
                   key=lambda r: -r["headroom"])
    medium = sorted([r for r in rows
                       if r["max_overlap"] == 2 and r["headroom"] > 0],
                      key=lambda r: -r["headroom"])
    hard = sorted([r for r in rows
                     if r["headroom"] > 0 and (
                         r["max_overlap"] >= 3 or
                         (r["overlap_weeks"] >= 4 and
                          (not math.isnan(r["fog"])) and r["fog"] >= fog_hi_thresh))],
                    key=lambda r: -r["headroom"])

    table("EASY (max_overlap<=1, mid-to-high headroom)", easy)
    table("MEDIUM (max_overlap==2, positive headroom)", medium)
    table("HARD (max_overlap>=3 or high-fog overlap>=4, positive headroom)", hard)
    return "\n".join(lines)


def section_correlations(rows):
    feats = [f for f in NUMERIC_FIELDS if f not in ("headroom",)]
    hvals = [r["headroom"] for r in rows]
    corrs = []
    for f in feats:
        r = pearson_r([row[f] for row in rows], hvals)
        corrs.append((f, r))
    corrs_sorted = sorted(corrs, key=lambda t: (t[1] if not math.isnan(t[1]) else -1e18), reverse=True)
    lines = ["## 5. Correlations (Pearson r vs headroom)", "",
             "| feature | r |", "|---|---|"]
    for f, r in corrs_sorted:
        rstr = f"{r:.3f}" if not math.isnan(r) else "nan"
        lines.append(f"| {f} | {rstr} |")
    return "\n".join(lines)


def build_report(rows):
    sections = [
        "# Seed sweep report",
        "",
        f"n = {len(rows)} seeds",
        "",
        section_score_spread(rows),
        "",
        section_headroom(rows),
        "",
        section_kills_headroom(rows),
        "",
        section_ladder(rows),
        "",
        section_correlations(rows),
        "",
    ]
    return "\n".join(sections)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=str, default=os.path.join(
        os.path.dirname(__file__), "results.csv"))
    ap.add_argument("--out", type=str, default=os.path.join(
        os.path.dirname(__file__), "report.md"))
    args = ap.parse_args()

    rows = load(args.csv)
    report = build_report(rows)
    with open(args.out, "w") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
