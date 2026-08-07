"""Per-week counterfactual regret vs the oracle, from the agent's own states.

For each week w of an agent episode (replayed from its trace through the
engine -- reusing cost_decomp.py's verified parser/replay):

  V(s)      = mean over REPS oracle continuations of the cost from state s
              to episode end (oracle dropped into the agent's situation)
  regret_w  = [agent's week-w cost + V(state after the agent's week-w action)]
              - V(state before the agent's week-w action)

regret_w ~ 0 means the oracle, standing in the agent's shoes with the
agent's inventory/pipeline/contracts, would have bled the same dollars this
week (unavoidable physics -- the A2 correction); a large positive regret is
a genuine decision failure. Sum of regrets telescopes to
(agent total - V(week-0 state)) up to MC noise, which we report as a sanity
column. Writes runs/<exp>/regret_weeks.csv.

    uv run python analysis/regret.py --exp ladder-v1 --models <m> --seeds 1
    uv run python analysis/regret.py --exp ladder-v1          # full sweep (hours)
"""
import argparse
import copy
import csv
import random
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.cost_decomp import parse_trace, apply_lever  # noqa: E402
from oracle_policy import oracle_play, warm_filters  # noqa: E402
from src.world.engine import World  # noqa: E402
from src.world.config import WorldConfig  # noqa: E402
from src.world.registry import RICH  # noqa: E402

REPS = 5      # oracle continuations per state (mc_rng varies per rep)
ORACLE_K = 50  # lookahead samples per decision, matching the sweep's oracle


def V(world, reps: int, k: int, rep_base: int) -> float:
    """Mean oracle cost-to-go from this world's current state."""
    totals = []
    for r in range(reps):
        w = copy.deepcopy(world)
        filts = warm_filters(w)
        mc_rng = random.Random(rep_base * 104729 + r * 7919 + w.week)
        totals.append(oracle_play(w, filts, mc_rng, k))
    return mean(totals)


def episode_regret(model: str, seed: int, path: Path, reps=REPS, k=ORACLE_K):
    weeks, bundles = parse_trace(path)
    world = World(WorldConfig(sup_mask_otif=True), registry=RICH)
    world.reset(seed)
    rows = []
    v_start = V(world, reps, k, seed)
    v_before = v_start
    for (wk, want_cost, want_cum), bundle in zip(weeks, bundles):
        for t, kw in bundle:
            if t != "place_order":
                apply_lever(world, t, kw)
        tool, kw = [(t, kw) for t, kw in bundle if t == "place_order"][-1]
        qty = int(kw.get("qty", 0) or 0)
        supplier = (kw.get("supplier") or None) if qty else None
        action = {"qty": qty, "route": kw.get("route") or None,
                  "supplier": supplier}
        if kw.get("contract_action"):
            action["contract"] = {"action": kw["contract_action"],
                                  "supplier": kw.get("contract_supplier") or supplier,
                                  "terms": kw.get("contract_terms") or None}
        obs, cost, done, _ = world.step(action)
        assert f"{cost:.0f}" == str(want_cost), (
            f"{path} wk{wk}: replay cost {cost:.0f} != trace {want_cost}")
        v_after = 0.0 if world.done else V(world, reps, k, seed)
        rows.append({"model": model, "seed": seed, "week": wk,
                     "agent_cost": round(cost, 1),
                     "v_before": round(v_before, 1),
                     "v_after": round(v_after, 1),
                     "regret": round(cost + v_after - v_before, 1)})
        v_before = v_after
    agent_total = sum(r["agent_cost"] for r in rows)
    telescoped = sum(r["regret"] for r in rows)
    for r in rows:
        r["ep_agent_total"] = round(agent_total, 1)
        r["ep_regret_sum"] = round(telescoped, 1)
        r["ep_v_start"] = round(v_start, 1)  # sanity: regret_sum ~ total - v_start
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="ladder-v1")
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--seeds", nargs="*", type=int, default=None)
    ap.add_argument("--reps", type=int, default=REPS)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    exp_dir = Path(__file__).resolve().parent.parent / "runs" / a.exp
    out = Path(a.out) if a.out else exp_dir / "regret_weeks.csv"
    done = set()
    if out.is_file():  # resume: append, skip finished (model, seed) pairs
        done = {(r["model"], int(r["seed"]))
                for r in csv.DictReader(out.open())}
    mode = "a" if done else "w"
    with out.open(mode, newline="") as f:
        wcsv = None
        for trace in sorted(exp_dir.glob("*/seed*-rich.chat.txt")):
            model = trace.parent.name
            seed = int(trace.name.split("seed")[1].split("-")[0])
            if a.models and model not in a.models:
                continue
            if a.seeds and seed not in a.seeds:
                continue
            if (model, seed) in done:
                continue
            try:
                rows = episode_regret(model, seed, trace, reps=a.reps)
            except (ValueError, AssertionError) as e:
                print(f"SKIP {model} seed{seed}: {e}")
                continue
            if wcsv is None:
                wcsv = csv.DictWriter(f, fieldnames=list(rows[0]))
                if mode == "w":
                    wcsv.writeheader()
            wcsv.writerows(rows)
            f.flush()  # incremental: survive interruption, resume cheaply
            print(f"{model} seed{seed}: regret_sum={rows[0]['ep_regret_sum']} "
                  f"(total {rows[0]['ep_agent_total']} - v_start {rows[0]['ep_v_start']})",
                  flush=True)


if __name__ == "__main__":
    main()
