"""Grade LLM per-week rationales against ground-truth stress regimes.

Parses ladder-v1 trace files (runs/ladder-v1/<model-dir>/seedN-rich.chat.txt),
recovers the true per-week stressed factors by replaying the seed's tape
(same recipe as sweep/run_sweep.py's _tape_features), grades each week's
rationale text with a cheap LLM (openai/gpt-5-mini via OpenRouter) for which
of the 6 factors it names as CURRENTLY active/problematic, and writes two
CSVs: per-week beliefs and per-(model,seed) detection-lag/knowing-doing
metrics.

Run:
    uv run python runs/grade_beliefs.py --dry-run
    uv run python runs/grade_beliefs.py --models anthropic-claude-sonnet-5 --seeds 1
    uv run python runs/grade_beliefs.py
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

RUNS_DIR = Path(__file__).parent / "ladder-v1"
FACTORS = ["disruption", "freight", "port", "quality", "supplier", "demand"]
N_WEEKS = 26
GRADER_MODEL = "openai/gpt-5-mini"

WEEK0_RE = re.compile(r"^WEEK 0 SITUATION\s+inv (\d+).*demand (\d+)/(\d+)")
ADV_RE = re.compile(r"^WORLD ADVANCED -> week (\d+)\s+week cost \$(-?\d+)\s+cum \$(-?\d+)")
SIT_RE = re.compile(r"^\s*SITUATION\s+inv (\d+).*arrived (\d+).*demand (\d+)/(\d+)")
PLACE_ORDER_RE = re.compile(r"^\s*>> place_order\(")
RATIONALE_START_RE = re.compile(r"^\s*RATIONALE:\s*(.*)")


def parse_trace(path: Path):
    """Return list of week records: {week, rationale, week_cost, stockout}."""
    lines = path.read_text().splitlines()
    weeks = []
    prev_inv = None
    current_rationale = None
    in_rationale = False
    rationale_parts = []
    pending_week_cost = None
    pending_week_num = None

    for line in lines:
        m0 = WEEK0_RE.match(line)
        if m0:
            prev_inv = int(m0.group(1))
            continue

        if PLACE_ORDER_RE.match(line):
            in_rationale = False
            rationale_parts = []
            continue

        if in_rationale:
            stripped = line.strip()
            if not stripped or line.startswith("WORLD ADVANCED") or line.strip().startswith(">>"):
                in_rationale = False
                current_rationale = " ".join(rationale_parts)
            else:
                rationale_parts.append(stripped)
                continue

        mr = RATIONALE_START_RE.match(line)
        if mr:
            in_rationale = True
            rationale_parts = [mr.group(1)] if mr.group(1) else []
            continue

        madv = ADV_RE.match(line)
        if madv:
            if in_rationale:
                current_rationale = " ".join(rationale_parts)
                in_rationale = False
            # DECIDING WEEK W appears after ADV->W, so the rationale completed
            # here belongs to the LAST appended row (same-week alignment);
            # deciding-week-0 text has no row and is dropped.
            if current_rationale and weeks:
                weeks[-1]["rationale"] = current_rationale
            current_rationale = None
            pending_week_num = int(madv.group(1))
            pending_week_cost = int(madv.group(2))
            continue

        msit = SIT_RE.match(line)
        if msit and pending_week_num is not None:
            if any(w["week"] == pending_week_num for w in weeks):  # duplicated log line
                pending_week_num = None
                continue
            inv, arrived, demand_realized, _fc = (int(x) for x in msit.groups())
            available = (prev_inv or 0) + arrived
            stockout = 1 if available < demand_realized else 0
            weeks.append({
                "week": pending_week_num,
                "rationale": "",  # filled at the next ADV line (same-week alignment)
                "week_cost": pending_week_cost,
                "stockout": stockout,
            })
            prev_inv = inv
            pending_week_num = None

    return weeks


def true_regimes(seed: int):
    """Per-week set of stressed factors, replaying the tape (same recipe as
    sweep/run_sweep.py's _tape_features)."""
    from src.world.engine import World
    from src.world.config import WorldConfig
    from src.world.registry import RICH
    import filters as filt_mod

    w = World(WorldConfig(sup_mask_otif=True), registry=RICH)
    w.reset(seed)
    while not w.done:
        w.step({})

    per_week = []
    for rec in w.trace:
        stressed = set()
        for f in FACTORS:
            true = filt_mod._true_regime(rec, f)
            if f == "disruption":
                is_stressed = true == "disruption"
            elif f == "freight":
                is_stressed = true == "spike"
            elif f == "port":
                is_stressed = true in ("congested", "customs_hold")
            elif f == "quality":
                is_stressed = true == "out_of_control"
            elif f == "supplier":
                is_stressed = true in ("degraded", "defunct")
            else:
                is_stressed = true != "normal"
            if is_stressed:
                stressed.add(f)
        per_week.append({"week": rec["week"], "stressed": stressed})
    return per_week


GRADE_PROMPT = """You will be given one week's replenishment-decision rationale from a supply-chain manager. The fixed factor vocabulary is exactly these 6 names: disruption, freight, port, quality, supplier, demand.

Return STRICT JSON only, of the form: {{"factors_named": [subset of the 6 names]}}

Include a factor ONLY if the rationale asserts it is CURRENTLY active/problematic this week. Go through the 6 factors one by one and ask: does the text CLAIM this is a problem right now? Three rules, each with a real example:

1. RULED-OUT or BENIGN mentions do NOT count. "freight remains cheap" = no freight. "the weak fill looks noisy rather than confirmed deterioration" = no supplier. "lanes normal" = no disruption. Naming a factor to say it is fine is the OPPOSITE of naming it as a problem.
2. FACTUAL symptom reports DO count even without editorializing. "AQL reject -- inspected batch" = quality. "port congestion (berth_wait 16) delayed arrivals longer than expected" = port. The manager asserts a problem exists by reporting its symptom as the cause of something.
3. PRECAUTIONS without a current problem do NOT count. "I'll keep using the freight lock" alone = no freight. "avoiding spot until it stabilizes" after calling the data noise = no supplier. But acting BECAUSE of an asserted current problem ("air-expediting because the port is holding arrivals") = count that factor.

Worked example -- rationale: "Freight lock still active (1.19x) shielding us from the 179 spot index. AQL came back marginal causing a rework charge. Spot remains slipping (86 OTIF) so still avoiding it." -> {{"factors_named": ["freight", "quality", "supplier"]}} (index 179 asserted high; AQL/rework is a current quality symptom; "spot remains slipping" is a current supplier claim.)

Rationale:
\"\"\"{rationale}\"\"\"

JSON:"""


def grade_rationale(rationale, client_key, call_counter):
    import requests

    if not rationale.strip():
        return []

    body = {
        "model": GRADER_MODEL,
        "temperature": 0,
        # classification, not deliberation: cap reasoning so calls take ~1s not ~7s
        "reasoning": {"effort": "low"},
        "messages": [{"role": "user", "content": GRADE_PROMPT.format(rationale=rationale)}],
    }
    headers = {"Authorization": f"Bearer {client_key}", "Content-Type": "application/json"}

    for attempt in range(4):
        call_counter[0] += 1
        print(f"  LLM call #{call_counter[0]}", end="\r", flush=True)
        try:
            resp = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers=headers, json=body, timeout=60)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"\n  WARNING: API call failed ({e}), retrying")
            time.sleep(2 * (attempt + 1))
            continue
        try:
            m = re.search(r"\{.*\}", content, re.DOTALL)
            parsed = json.loads(m.group(0) if m else content)
            factors = [f for f in parsed.get("factors_named", []) if f in FACTORS]
            return factors
        except (json.JSONDecodeError, AttributeError, KeyError):
            continue
    # DEFECT FIX 2026-07-30 (D6): a grader that fails all retries must not be
    # silently indistinguishable from "named nothing". Fail the run loudly; the
    # resume logic makes rerunning cheap.
    raise RuntimeError(
        "grader failed 4 attempts on a non-empty rationale; aborting so the "
        "failure is not recorded as an empty factor list (resume to retry)")


def detection_lag_metrics(weeks_rows, tape):
    """weeks_rows: list of {week, factors_named(set), stockout}. tape: list of
    {week, stressed(set)} from true_regimes. Returns metrics dict."""
    named_by_week = {r["week"]: r["factors_named"] for r in weeks_rows}
    stockout_by_week = {r["week"]: r["stockout"] for r in weeks_rows}
    stressed_by_week = {t["week"]: t["stressed"] for t in tape}
    wk_sorted = sorted(stressed_by_week)

    # build episodes: maximal consecutive-week runs of a factor being stressed
    episodes = []  # (factor, start_week)
    active_since = {}
    for wk in wk_sorted:
        s = stressed_by_week[wk]
        for f in FACTORS:
            if f in s and f not in active_since:
                active_since[f] = wk
            elif f not in s and f in active_since:
                episodes.append((f, active_since.pop(f)))
        for f in list(active_since):
            pass
    for f, start in active_since.items():
        episodes.append((f, start))

    # DEFECT FIX 2026-07-30 (D2b): an episode whose onset is the FINAL week is
    # undetectable by construction -- the run ends before another rationale is
    # written -- so it is excluded from the detection denominator and counted
    # separately, never conflated with a miss.
    last_week = wk_sorted[-1]
    lags = []
    n_never = 0
    n_undetectable = 0
    for f, start in episodes:
        if start >= last_week:
            n_undetectable += 1
            continue
        detected_week = None
        for wk in wk_sorted:
            if wk < start:
                continue
            if f in named_by_week.get(wk, set()):
                detected_week = wk
                break
        if detected_week is None:
            n_never += 1
        else:
            lags.append(detected_week - start)

    mean_lag = sum(lags) / len(lags) if lags else None

    # DEFECT FIX 2026-07-30 (D2a): the final week has no rationale, so its
    # stress weeks are unknowable, not undiagnosed -- excluded from the KD
    # denominator (they could never enter the numerator's "correct" side).
    correct_weeks = 0
    correct_and_stockout = 0
    for wk in wk_sorted:
        if wk >= last_week:
            continue
        overlap = named_by_week.get(wk, set()) & stressed_by_week.get(wk, set())
        if overlap:
            correct_weeks += 1
            if stockout_by_week.get(wk):
                correct_and_stockout += 1
    knowing_doing_rate = (correct_and_stockout / correct_weeks) if correct_weeks else None

    return {
        "mean_detection_lag": mean_lag,
        "n_episodes": len(episodes) - n_undetectable,
        "n_never_detected": n_never,
        "knowing_doing_rate": knowing_doing_rate,
        "n_undetectable": n_undetectable,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--seeds", nargs="*", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_dotenv()
    api_key = os.environ.get("OPENROUTER_API_KEY")

    model_dirs = sorted(d.name for d in RUNS_DIR.iterdir() if d.is_dir())
    if args.models:
        model_dirs = [m for m in model_dirs if m in args.models]

    call_counter = [0]
    tape_cache = {}
    beliefs_path = RUNS_DIR / "beliefs.csv"

    # DEFECT FIX 2026-07-30 (D1, air-stockout): the trace-derived flag
    # (inv + arrived < demand) omits air-expedited arrivals and miscounted
    # 343 air-saved weeks as stockouts. Engine truth from cost_weeks.csv
    # (analysis/cost_decomp.py replay, checksum-verified) overrides it
    # whenever available; a trace-derived fallback is refused for models
    # that have replay data.
    engine_stockout = {}
    cw_path = RUNS_DIR / "cost_weeks.csv"
    if cw_path.exists():
        for r in csv.DictReader(open(cw_path)):
            engine_stockout[(r["model"], int(r["seed"]), int(r["week"]))] = \
                1 if float(r["stockout"]) > 0 else 0
    fieldnames = ["model", "seed", "week", "factors_stressed_true",
                  "factors_named", "week_cost", "stockout"]

    # resume: (model, seed) cells already fully graded in beliefs.csv are skipped
    done = set()
    if beliefs_path.exists():
        counts = {}
        for r in csv.DictReader(open(beliefs_path)):
            counts[(r["model"], int(r["seed"]))] = counts.get((r["model"], int(r["seed"])), 0) + 1
        done = {k for k, n in counts.items() if n >= N_WEEKS}
        print(f"resume: {len(done)} (model,seed) cells already graded, skipping", flush=True)

    out = open(beliefs_path, "a", newline="")
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    if out.tell() == 0:
        writer.writeheader()
        out.flush()

    for model_dir in model_dirs:
        traces = sorted((RUNS_DIR / model_dir).glob("seed*-rich.chat.txt"))
        for path in traces:
            m = re.match(r"seed(\d+)-rich", path.stem)
            seed = int(m.group(1))
            if args.seeds and seed not in args.seeds:
                continue
            if (model_dir, seed) in done:
                continue

            weeks = parse_trace(path)
            if len(weeks) != N_WEEKS:
                print(f"WARNING: {path} parsed to {len(weeks)} weeks (expected {N_WEEKS}), skipping", flush=True)
                continue

            if seed not in tape_cache:
                tape_cache[seed] = true_regimes(seed)
            stressed_by_week = {t["week"]: t["stressed"] for t in tape_cache[seed]}

            rows = []
            for wr in weeks:
                factors_named = [] if args.dry_run else grade_rationale(wr["rationale"], api_key, call_counter)
                key = (model_dir, seed, wr["week"])
                if key in engine_stockout:
                    so = engine_stockout[key]
                elif any(k[0] == model_dir for k in engine_stockout):
                    raise RuntimeError(
                        f"{key}: model has engine-replay stockouts but this week is "
                        "missing from cost_weeks.csv -- refusing the trace-derived flag")
                else:
                    print(f"WARNING: no engine replay for {model_dir}; stockout falls "
                          "back to trace arithmetic, which MISSES air-expedited "
                          "arrivals -- run analysis/cost_decomp.py first", flush=True)
                    so = wr["stockout"]
                rows.append({
                    "model": model_dir, "seed": seed, "week": wr["week"],
                    "factors_stressed_true": ";".join(sorted(stressed_by_week.get(wr["week"], set()))),
                    "factors_named": ";".join(sorted(factors_named)),
                    "week_cost": wr["week_cost"],
                    "stockout": so,
                })
            # one trace = one atomic append; a crash loses at most the trace in flight
            writer.writerows(rows)
            out.flush()
            print(f"{model_dir} seed{seed}: graded ({call_counter[0]} calls total)", flush=True)
    out.close()

    # metrics always recomputed from the full CSV, so resume runs stay consistent
    per_cell = {}
    for r in csv.DictReader(open(beliefs_path)):
        key = (r["model"], int(r["seed"]))
        per_cell.setdefault(key, []).append({
            "week": int(r["week"]),
            "factors_named": set(x for x in r["factors_named"].split(";") if x),
            "stockout": int(r["stockout"]),
        })
    metrics_rows = []
    for (model_dir, seed), wrows in sorted(per_cell.items()):
        if seed not in tape_cache:
            tape_cache[seed] = true_regimes(seed)
        m_metrics = detection_lag_metrics(wrows, tape_cache[seed])
        metrics_rows.append({"model": model_dir, "seed": seed, **m_metrics})

    metrics_path = RUNS_DIR / "belief_metrics.csv"
    with open(metrics_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["model", "seed", "mean_detection_lag",
                                          "n_episodes", "n_never_detected", "knowing_doing_rate",
                                          "n_undetectable"])
        w.writeheader()
        w.writerows(metrics_rows)
    print(f"wrote {metrics_path} ({len(metrics_rows)} rows)", flush=True)

    if not args.dry_run:
        print(f"total LLM calls this run: {call_counter[0]}", flush=True)


if __name__ == "__main__":
    main()
