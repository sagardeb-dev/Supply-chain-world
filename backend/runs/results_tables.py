"""Compute every number for research/results.md from canonical CSVs. Prints markdown tables."""
import csv, statistics as st, sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B))
import bench_config as C

RUNS = B / "runs/ladder-v1"
FACTORS = ["disruption", "freight", "port", "quality", "supplier", "demand"]
SHORT = {"anthropic-claude-sonnet-5": "sonnet-5", "openai-gpt-5.4": "gpt-5.4",
         "deepseek-deepseek-v4-pro": "deepseek-v4-pro", "x-ai-grok-4.5": "grok-4.5"}
# models still mid-run (no full 50-seed set) stay out of every table
SKIP = set(C.MODELS) - set(SHORT)

rows = list(csv.DictReader(open(RUNS / "skill_scores.csv")))

# --- Table 1: skill per group ---
print("## T1 skill")
print("| model | " + " | ".join(f"{g}" for g in list(C.GROUPS) + ["ALL"]) + " | neg | skill>0 |")
for mdir in C.MODELS:
    if mdir in SKIP: continue
    mr = [r for r in rows if r["model"] == mdir]
    cells = []
    for g in list(C.GROUPS) + ["ALL"]:
        gr = [float(r["skill"]) for r in mr if (g == "ALL" or r["group"] == g) and r["skill"] != ""]
        cells.append(f"{st.mean(gr):+.2f} (med {st.median(gr):+.2f}, n={len(gr)})")
    allv = [float(r["skill"]) for r in mr if r["skill"] != ""]
    beat = sum(1 for r in mr if float(r["llm_cost"]) < float(r["basestock"]))  # denominator-free, all seeds
    print(f"| {SHORT[mdir]} | " + " | ".join(cells) +
          f" | {sum(1 for x in allv if x < 0)} | {beat}/{len(mr)} |")

# --- headroom distribution ---
hr = sorted(set((int(r["seed"]), float(r["headroom"])) for r in rows))
hvals = [h for _, h in hr]
print(f"\nheadroom over {len(hr)} seeds: min {min(hvals):.0f}, median {st.median(hvals):.0f}, "
      f"max {max(hvals):.0f}; negative: {[s for s,h in hr if h<=0]}; "
      f"thin(<{C.THIN_HEADROOM}): {sorted(s for s,h in hr if 0<h<C.THIN_HEADROOM)}")
print("group sizes:", {g: len(v) for g, v in C.GROUPS.items()})

# --- beliefs: detection + KDR + confound ---
cells = {}
for r in csv.DictReader(open(RUNS / "beliefs.csv")):
    m, s = r["model"], int(r["seed"])
    if m in SKIP:
        continue
    if C.MODELS[m] is not None and s not in C.MODELS[m]:
        continue
    cells.setdefault((m, s), []).append(r)

print("\n## T2 detection (episode-pooled, all models n=50)")
print("| model | missed/episodes | mean lag (detected) |")
det = {}
for (m, s), rws in cells.items():
    rws.sort(key=lambda r: int(r["week"]))
    weeks = [int(r["week"]) for r in rws]
    stressed = {int(r["week"]): set(x for x in r["factors_stressed_true"].split(";") if x) for r in rws}
    named = {int(r["week"]): set(x for x in r["factors_named"].split(";") if x) for r in rws}
    so = {int(r["week"]): int(r["stockout"]) for r in rws}
    d = det.setdefault(m, {"eps": 0, "miss": 0, "lags": [],
                           "kdr": {}, "conf": {}})
    g = C.group_of(s)
    for f in FACTORS:
        prev = False
        for i, wk in enumerate(weeks):
            cur = f in stressed[wk]
            if cur and not prev:
                d["eps"] += 1
                dw = next((w2 for w2 in weeks if w2 >= wk and f in named[w2]), None)
                if dw is None: d["miss"] += 1
                else: d["lags"].append(dw - wk)
            prev = cur
    for wk in weeks:
        if not stressed[wk]:
            continue
        diag = bool(named[wk] & stressed[wk])
        k = d["kdr"].setdefault(g, {"dw": 0, "dso": 0, "uw": 0, "uso": 0})
        if diag:
            k["dw"] += 1; k["dso"] += so[wk]
        else:
            k["uw"] += 1; k["uso"] += so[wk]
for m in C.MODELS:
    if m in SKIP: continue
    d = det[m]
    print(f"| {SHORT[m]} | {d['miss']}/{d['eps']} | {st.mean(d['lags']):.2f} |")

print("\n## T3 KDR pooled weeks (stockout rate on correctly-diagnosed stress weeks) per group")
print("| model | " + " | ".join(C.GROUPS) + " | all |")
for m in C.MODELS:
    if m in SKIP: continue
    k = det[m]["kdr"]
    cells_ = []
    tot = {"dw": 0, "dso": 0}
    for g in C.GROUPS:
        v = k.get(g, {"dw": 0, "dso": 0})
        tot["dw"] += v["dw"]; tot["dso"] += v["dso"]
        cells_.append(f"{v['dso']/v['dw']:.2f} (n={v['dw']})" if v["dw"] else "--")
    print(f"| {SHORT[m]} | " + " | ".join(cells_) + f" | {tot['dso']/tot['dw']:.2f} (n={tot['dw']}) |")

print("\n## T4 confound: stockout rate diagnosed vs UNdiagnosed stress weeks")
print("| model | group | diagnosed | undiagnosed |")
for m in C.MODELS:
    if m in SKIP: continue
    for g in list(C.GROUPS) + ["ALL"]:
        if g == "ALL":
            v = {kk: sum(vv[kk] for vv in det[m]["kdr"].values()) for kk in ["dw","dso","uw","uso"]}
        else:
            v = det[m]["kdr"].get(g)
        if not v: continue
        dr = f"{v['dso']/v['dw']:.2f} (n={v['dw']})" if v["dw"] else "--"
        ur = f"{v['uso']/v['uw']:.2f} (n={v['uw']})" if v["uw"] else "--"
        print(f"| {SHORT[m]} | {g} | {dr} | {ur} |")
