"""Play the world by hand, or run a fixed-route baseline.

  uv run python play.py --seed 7                 # interactive
  uv run python play.py --seed 7 --policy suez   # always-Suez baseline
  uv run python play.py --seed 7 --policy cape   # always-Cape baseline
"""

import argparse

from src.world import World

STATUS_MARK = {"at_sea": "", "queued_at_suez": "Q", "diverted_via_cape": "D"}


def fmt_obs(obs: dict) -> str:
    pipe = ", ".join(
        f"{s['qty']}@wk{s['eta']}({s['route'][0]}{STATUS_MARK[s['status']]})"
        for s in obs["pipeline"]) or "-"
    costs = obs["cost_breakdown"]
    cost_s = " ".join(f"{k}={v:.0f}" for k, v in costs.items() if v) or "-"
    probe = f"  probe={obs['probe_result']}" if obs["probe_result"] else ""
    return (f"wk{obs['week']:>2}  suez={obs['suez_count']:>3} bab={obs['bab_count']:>3} "
            f"cape={obs['cape_count']:>3}  inv={obs['inventory']:>3} arr={obs['arrived']:>2}  "
            f"pipe[{pipe}]  cost[{cost_s}]{probe}")


def ask_action() -> dict:
    while True:
        raw = input("  action route=[s]uez/[c]ape, add p to probe (e.g. 's', 'cp'): ").strip().lower()
        route = "suez" if raw.startswith("s") else "cape" if raw.startswith("c") else None
        if route:
            return {"route": route, "probe": "p" in raw}
        print("  ? need s or c")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--policy", choices=["manual", "suez", "cape"], default="manual")
    args = ap.parse_args()

    world = World()
    obs = world.reset(args.seed)
    print(fmt_obs(obs))

    while not world.done:
        if args.policy == "manual":
            action = ask_action()
        else:
            action = {"route": args.policy, "probe": False}
        obs, cost, done, info = world.step(action)
        print(fmt_obs(obs))

    print(f"\nTOTAL COST: {world.total_cost:.0f}")
    print("\nhidden trajectory (the reveal):")
    for rec in world.trace:
        h = rec["hidden"]
        flags = []
        if h["disruption_type"]:
            flags.append(h["disruption_type"])
        if h["cape_local_congestion"]:
            flags.append("cape_local")
        print(f"  wk{rec['week']:>2}  {h['event_state']:<12} age={h['event_age']}  "
              f"{' '.join(flags)}")


if __name__ == "__main__":
    main()
