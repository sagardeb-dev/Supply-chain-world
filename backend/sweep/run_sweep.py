"""Task 1 of the seed-sweep plan: one CSV row per seed, computed on a process
pool, combining cheap reference-policy costs (report_oracle.py), the k=50
lookahead oracle (oracle_policy.py), tape-derived stress features (a passive
empty-action replay), and fog features (filters.py's exact per-factor HMM
forward filters, replayed over the SAME tape).

Nothing here reimplements report_oracle / oracle_policy / filters logic --
it only imports and reads their outputs, per the plan's global constraints.

Run:
    uv run python -m sweep.run_sweep --n 200
    uv run python -m sweep.run_sweep --n 4 --workers 2
"""

import argparse
import csv
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

# Columns, in write order.
FIELDS = [
    "seed", "cost_suez", "cost_cape", "cost_basestock", "cost_oracle",
    "headroom", "best_fixed",
    "stress_disruption", "stress_freight", "stress_port", "stress_quality",
    "stress_supplier", "stress_demand",
    "max_overlap", "overlap_weeks", "spot_died", "port_block_longest",
    "fog_disruption", "fog_freight", "fog_port", "fog_quality",
    "fog_supplier", "fog_demand", "fog",
]


def _tape_features(seed: int, cfg) -> dict:
    """Stressed-week counts / overlap / port-block-run stats from one passive
    (empty-action) replay of the seed's tape, read straight off
    World.trace[i]['hidden_states'] via filters.py's own hidden-state reader
    (_true_regime) so the roster/nested-key handling matches filters.py
    exactly instead of being re-derived here."""
    from src.world.engine import World
    from src.world.registry import RICH
    import filters as filt_mod

    w = World(cfg, registry=RICH)
    w.reset(seed)
    while not w.done:
        w.step({})

    factors = ["disruption", "freight", "port", "quality", "supplier", "demand"]
    counts = {f: 0 for f in factors}
    max_overlap = 0
    overlap_weeks = 0
    spot_died = 0
    port_block_run = 0
    port_block_longest = 0

    for rec in w.trace:
        stressed_now = set()
        for f in factors:
            true = filt_mod._true_regime(rec, f)
            if f == "disruption":
                is_stressed = true == "disruption"       # active canal event
            elif f == "freight":
                is_stressed = true == "spike"
            elif f == "port":
                is_stressed = true in ("congested", "customs_hold")
            elif f == "quality":
                is_stressed = true == "out_of_control"
            elif f == "supplier":
                is_stressed = true in ("degraded", "defunct")
                if true == "defunct":
                    spot_died = 1
            else:  # demand
                is_stressed = true != "normal"
            if is_stressed:
                counts[f] += 1
                stressed_now.add(f)

        n_stressed = len(stressed_now)
        max_overlap = max(max_overlap, n_stressed)
        if n_stressed >= 2:
            overlap_weeks += 1

        if "port" in stressed_now:
            port_block_run += 1
            port_block_longest = max(port_block_longest, port_block_run)
        else:
            port_block_run = 0

    return {
        "stress_disruption": counts["disruption"],
        "stress_freight": counts["freight"],
        "stress_port": counts["port"],
        "stress_quality": counts["quality"],
        "stress_supplier": counts["supplier"],
        "stress_demand": counts["demand"],
        "max_overlap": max_overlap,
        "overlap_weeks": overlap_weeks,
        "spot_died": spot_died,
        "port_block_longest": port_block_longest,
    }


def _fog_features(seed: int, cfg) -> dict:
    """Per-factor mean detection lag (weeks from a true regime change to the
    filter's posterior argmax first agreeing) from filters.py's own replay()
    + detection_lags() -- reused, not re-derived. fog = mean of the per-factor
    mean lags, over factors that had >=1 regime change on this seed's tape."""
    import filters as filt_mod

    run = filt_mod.replay(seed, cfg=cfg)
    factors = list(filt_mod.FACTORS)
    out = {}
    lag_means = []
    for f in factors:
        lags = filt_mod.detection_lags(run.weeks, f)
        m = (sum(lags) / len(lags)) if lags else float("nan")
        out[f"fog_{f}"] = m
        if lags:
            lag_means.append(m)
    out["fog"] = (sum(lag_means) / len(lag_means)) if lag_means else float("nan")
    return out


def _one_seed(seed: int) -> dict:
    """Top-level (picklable) worker: everything a single CSV row needs. Each
    worker process imports the world itself (module import cost is fine --
    the run_oracle/replay CPU cost dwarfs it, which is exactly why the pool
    is worth it)."""
    from src.world.config import WorldConfig
    from src.world.registry import RICH
    from report_oracle import fixed_policy_cost, base_stock_cost
    from oracle_policy import run_oracle

    cfg = WorldConfig(sup_mask_otif=True)

    cost_suez = fixed_policy_cost(seed, "suez", cfg, registry=RICH)
    cost_cape = fixed_policy_cost(seed, "cape", cfg, registry=RICH)
    cost_basestock = base_stock_cost(seed, cfg, registry=RICH)
    cost_oracle = run_oracle(seed, k=50, cfg=cfg, trace=False)

    headroom = cost_basestock - cost_oracle
    best_fixed = min(cost_suez, cost_cape)

    row = {
        "seed": seed,
        "cost_suez": cost_suez,
        "cost_cape": cost_cape,
        "cost_basestock": cost_basestock,
        "cost_oracle": cost_oracle,
        "headroom": headroom,
        "best_fixed": best_fixed,
    }
    row.update(_tape_features(seed, cfg))
    row.update(_fog_features(seed, cfg))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--out", type=str, default=os.path.join(
        os.path.dirname(__file__), "results.csv"))
    args = ap.parse_args()

    seeds = list(range(args.n))
    t0 = time.time()
    rows = {}
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_one_seed, s): s for s in seeds}
        for fut in as_completed(futs):
            s = futs[fut]
            rows[s] = fut.result()
            done += 1
            if done % 20 == 0 or done == len(seeds):
                elapsed = time.time() - t0
                print(f"[{done}/{len(seeds)}] elapsed={elapsed:.1f}s "
                      f"({elapsed / done:.1f}s/seed)")

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for s in seeds:
            w.writerow(rows[s])

    total = time.time() - t0
    print(f"wrote {len(seeds)} rows to {args.out} in {total:.1f}s "
          f"({total / len(seeds):.1f}s/seed avg)")


if __name__ == "__main__":
    main()
