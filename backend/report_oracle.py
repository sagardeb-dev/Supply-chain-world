"""Cost sweep: clairvoyant oracle vs causal-aware oracle vs naive
baselines across seeds. Baselines: always-20-via-suez, always-20-via-
cape, base-stock (order-up-to 80, Suez). Self-checks that each
clairvoyant plan replays on the live engine to exactly the DP's
predicted cost, and that the causal oracle never beats the clairvoyant
bound (it cannot: clairvoyance is luck-inclusive).

Regret decomposition per seed:
  agent - causal      = skill deficit (information was available)
  causal - clairvoyant = luck premium (information was NOT available)
"""

from src.world.oracle.causal import CausalOracle, causal_play
from src.world.config import WorldConfig
from src.world.engine import World
from src.world.oracle.clairvoyant import oracle_plan


def fixed_policy_cost(seed: int, route: str, cfg: WorldConfig) -> float:
    w = World(cfg)
    w.reset(seed)
    while not w.done:
        w.step({"qty": 20, "route": route})
    return w.total_cost


def base_stock_cost(seed: int, cfg: WorldConfig, target: int = 80) -> float:
    """Order-up-to-target inventory position via Suez - the textbook
    naive policy a competent non-adaptive planner would run.
    target = demand x (suez lead + 1)."""
    w = World(cfg)
    w.reset(seed)
    while not w.done:
        position = w.books.inventory + sum(s.qty for s in w.books.pipeline)
        deficit = target - position
        qty = 0 if deficit <= 0 else (20 if deficit <= 20 else 40)
        w.step({"qty": qty, "route": "suez"} if qty else {"qty": 0})
    return w.total_cost


def replay_cost(seed: int, plan, cfg: WorldConfig) -> float:
    w = World(cfg)
    w.reset(seed)
    for qty, route in plan:
        w.step({"qty": qty, "route": route} if qty else {"qty": 0})
    return w.total_cost


def main():
    cfg = WorldConfig()
    causal = CausalOracle(cfg)
    print(f"causal-aware oracle expected cost (ex ante): "
          f"{causal.value():.1f}\n")
    seeds = range(1, 21)
    print(f"{'seed':>4} {'clairv':>8} {'causal':>8} {'luck':>6} {'briefs':>6} "
          f"{'suez20':>8} {'cape20':>8} {'bstock':>8} {'naive_min':>9} "
          f"{'gap':>7} {'disrupt_wks':>11}")
    rows = []
    for seed in seeds:
        cost, plan = oracle_plan(seed, cfg)
        replayed = replay_cost(seed, plan, cfg)
        assert abs(replayed - cost) < 1e-6, (
            f"seed {seed}: DP cost {cost} != engine replay {replayed}")
        ccost, crows = causal_play(seed, cfg, causal)
        assert ccost >= cost - 1e-6, (
            f"seed {seed}: causal {ccost} beat the clairvoyant bound {cost}")
        briefs = sum(1 for r in crows if r["briefed"])
        suez = fixed_policy_cost(seed, "suez", cfg)
        cape = fixed_policy_cost(seed, "cape", cfg)
        bstock = base_stock_cost(seed, cfg)
        naive_min = min(suez, cape, bstock)
        gap = naive_min - ccost

        w = World(cfg)
        w.reset(seed)
        while not w.done:
            w.step({"qty": 0})
        disrupt_wks = sum(1 for r in w.trace[1:]
                          if r["hidden"]["event_state"] == "disruption")

        rows.append((seed, cost, ccost, suez, cape, bstock, naive_min,
                     gap, disrupt_wks))
        print(f"{seed:>4} {cost:>8.0f} {ccost:>8.0f} {ccost - cost:>6.0f} "
              f"{briefs:>6} {suez:>8.0f} {cape:>8.0f} {bstock:>8.0f} "
              f"{naive_min:>9.0f} {gap:>7.0f} {disrupt_wks:>11}")

    gaps = [r[7] for r in rows]
    lucks = [r[2] - r[1] for r in rows]
    causal_mean = sum(r[2] for r in rows) / len(rows)
    print(f"\ncausal mean over seeds: {causal_mean:.0f} "
          f"(ex-ante expected {causal.value():.1f})")
    print(f"luck premium (causal - clairvoyant): "
          f"min={min(lucks):.0f} max={max(lucks):.0f} "
          f"mean={sum(lucks)/len(lucks):.0f}")
    print(f"gap (naive_min - causal): min={min(gaps):.0f} "
          f"max={max(gaps):.0f} mean={sum(gaps)/len(gaps):.0f}")
    discriminative = sum(1 for g in gaps if g > 0)
    print(f"seeds where the causal oracle beats every naive policy: "
          f"{discriminative}/{len(rows)}")


if __name__ == "__main__":
    main()
