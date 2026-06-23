"""Seed scanner: which seeds are worth spending an LLM run on?

A seed is a good TEST when something happens that the agent must react to and
the choice actually matters -- a flat-calm episode where ordering 20/week via
Suez is optimal tests nothing. Two cheap, no-LLM signals say so:

  events   -- the hidden tape (disruption / spot health / demand / freight /
              port / quality). The latent trajectory is a function of the SEED
              ALONE (exogenous RNG), so a single rollout reveals every event,
              identical no matter what policy plays.
  spread   -- run the three fixed baselines (suez / cape / basestock). If they
              cost about the same, the world is indifferent to your choices
              (boring). A large spread means routing/buffering separates good
              play from bad -- that is where an agent's score is informative.

The score is a transparent heuristic (see `_score`) favouring a LONG disruption
that onsets mid-episode (room to front-load AND reroute) plus a wide spread.
The event columns are printed raw so you can override the ranking by eye.

  uv run python -m scan_seeds                 # seeds 0..49, RICH, top 15
  uv run python -m scan_seeds --lo 0 --hi 200 --top 25
  uv run python -m scan_seeds --no-rich       # the 2-factor default world
"""

import argparse

from src.agent.play_agent import run_policy, _regime

# rel_state severity ladder for the spot supplier (reliable is healthy)
_SPOT_RANK = {"reliable": 0, "wobbling": 1, "degraded": 2, "defunct": 3}
_SPOT_NAME = {v: k for k, v in _SPOT_RANK.items()}


def scan_events(trace) -> dict:
    """Pull the per-seed event profile off one rollout's hidden tape."""
    hard, onset, crisis = [], None, False  # disruption: blockage/crisis weeks
    worst_spot, worst_spot_wk = 0, None
    demand, freight, port, quality = set(), set(), set(), set()
    for rec in trace:
        wk, hs = rec["week"], rec.get("hidden_states", {})
        d = _regime(hs, "disruption")
        if d in ("crash", "blockage", "crisis") and onset is None:
            onset = wk
        if d in ("blockage", "crisis"):
            hard.append(wk)
        if d == "crisis":
            crisis = True
        sp = hs.get("supplier", {}).get("spot", {}).get("rel_state", "reliable")
        if _SPOT_RANK.get(sp, 0) > worst_spot:
            worst_spot, worst_spot_wk = _SPOT_RANK[sp], wk
        for fac, bucket, base in (("demand", demand, "normal"),
                                  ("freight", freight, "normal"),
                                  ("port", port, "clear"),
                                  ("quality", quality, "in_control")):
            r = _regime(hs, fac)
            if r not in (base, "slack", "-"):  # slack freight is calmer-than-normal
                bucket.add(r)
    return {"onset": onset, "hard": hard, "crisis": crisis,
            "worst_spot": worst_spot, "worst_spot_wk": worst_spot_wk,
            "demand": demand, "freight": freight, "port": port, "quality": quality}


def _score(ev, spread, weeks) -> float:
    """Higher = a more informative test. Long disruption with mid-episode onset
    dominates; spot failure and a wide policy spread add. ponytail: hand-tuned
    weights, transparent on purpose -- retune against real agent runs later."""
    s = spread / 400.0
    L = len(ev["hard"])
    s += (2.5 if ev["crisis"] else 1.0) * L            # disruption mass
    if ev["onset"] is not None:                        # room to prep AND recover
        s += 6.0 if 3 <= ev["onset"] <= weeks - 6 else 1.0
    s += 2.0 * ev["worst_spot"]                         # degraded/defunct spot
    s += 0.5 * sum(len(ev[f]) for f in ("demand", "freight", "port", "quality"))
    return s


def _fmt_ev(ev) -> str:
    if ev["hard"]:
        kind = "crisis" if ev["crisis"] else "short"
        disr = f"{kind} w{ev['hard'][0]}-{ev['hard'][-1]}"
    elif ev["onset"] is not None:
        disr = f"falsealarm w{ev['onset']}"
    else:
        disr = "-"
    spot = (f"{_SPOT_NAME[ev['worst_spot']]}@w{ev['worst_spot_wk']}"
            if ev["worst_spot"] else "-")
    extra = "".join(c for c, f in (("D", "demand"), ("F", "freight"),
                                   ("P", "port"), ("Q", "quality")) if ev[f])
    return disr, spot, extra or "-"


def scan(lo, hi, rich):
    rows = []
    for seed in range(lo, hi):
        wq = run_policy(seed, "suez", "real", rich)   # also the event source
        suez = wq.total_cost
        cape = run_policy(seed, "cape", "real", rich).total_cost
        bst = run_policy(seed, "basestock", "real", rich).total_cost
        spread = max(suez, cape, bst) - min(suez, cape, bst)
        ev = scan_events(wq.trace)
        rows.append((seed, _score(ev, spread, wq.week), suez, cape, bst,
                     spread, ev))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lo", type=int, default=0)
    ap.add_argument("--hi", type=int, default=50)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--no-rich", dest="rich", action="store_false",
                    help="2-factor default world (default: RICH 6-factor)")
    args = ap.parse_args()

    print(f"scanning seeds {args.lo}..{args.hi - 1} "
          f"({'RICH 6-factor' if args.rich else '2-factor'}), "
          f"3 fixed policies each...\n")
    rows = sorted(scan(args.lo, args.hi, args.rich), key=lambda r: -r[1])

    print(f"{'seed':>4} {'score':>6} {'suez':>7} {'cape':>7} {'bstock':>7} "
          f"{'spread':>7}  {'disruption':<16} {'spot':<14} extra")
    for seed, sc, suez, cape, bst, spread, ev in rows[:args.top]:
        disr, spot, extra = _fmt_ev(ev)
        print(f"{seed:>4} {sc:>6.1f} {suez:>7.0f} {cape:>7.0f} {bst:>7.0f} "
              f"{spread:>7.0f}  {disr:<16} {spot:<14} {extra}")
    print(f"\nshowing top {min(args.top, len(rows))} of {len(rows)} seeds. "
          "extra: D=demand F=freight P=port Q=quality regime active.")


if __name__ == "__main__":
    main()
