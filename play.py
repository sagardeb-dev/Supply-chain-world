"""Play the world by hand, or run a baseline policy.

  uv run python play.py --seed 7                     # interactive
  uv run python play.py --seed 7 --policy suez       # always 20 via Suez
  uv run python play.py --seed 7 --policy cape       # always 20 via Cape
  uv run python play.py --seed 7 --policy basestock  # order-up-to-80, Suez
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
    return (f"wk{obs['week']:>2}  suez={obs['suez_count']:>3} bab={obs['bab_count']:>3} "
            f"cape={obs['cape_count']:>3}  inv={obs['inventory']:>3} arr={obs['arrived']:>2}  "
            f"pipe[{pipe}]  cost[{cost_s}]\n"
            f"      news: {obs['bulletin']}")


def ask_order(world) -> dict:
    while True:
        raw = input("  [b]riefing or order 'QTY s|c' (e.g. '40 c', '0'): ").strip().lower()
        if raw == "b":
            print(f"  briefing(30): {world.request_briefing()}")
            continue
        parts = raw.split()
        try:
            qty = int(parts[0])
        except (ValueError, IndexError):
            print("  ? e.g. 'b', '0', '20 s', '40 c'")
            continue
        if qty == 0:
            return {"qty": 0}
        if len(parts) == 2 and parts[1] in ("s", "c") and qty in (20, 40):
            return {"qty": qty, "route": "suez" if parts[1] == "s" else "cape"}
        print("  ? qty must be 0/20/40 with route s or c")


def base_stock_action(world, target: int = 80) -> dict:
    position = world.books.inventory + sum(s.qty for s in world.books.pipeline)
    deficit = target - position
    qty = 0 if deficit <= 0 else (20 if deficit <= 20 else 40)
    return {"qty": qty, "route": "suez"} if qty else {"qty": 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--policy", choices=["manual", "suez", "cape", "basestock"],
                    default="manual")
    args = ap.parse_args()

    world = World()
    obs = world.reset(args.seed)
    print(fmt_obs(obs))

    while not world.done:
        if args.policy == "manual":
            action = ask_order(world)
        elif args.policy == "basestock":
            action = base_stock_action(world)
        else:
            action = {"qty": 20, "route": args.policy}
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
