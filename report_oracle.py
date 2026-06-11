"""Cost sweep: oracle vs naive fixed-route baselines across seeds.
Also self-checks that each oracle plan replays on the live engine to exactly
the DP's predicted cost (the DP must agree with resolve_week)."""

from src.world.config import WorldConfig
from src.world.engine import World
from src.world.oracle import oracle_plan


def fixed_route_cost(seed: int, route: str, cfg: WorldConfig) -> float:
    w = World(cfg)
    w.reset(seed)
    while not w.done:
        w.step({"route": route, "probe": False})
    return w.total_cost


def replay_cost(seed: int, routes: list[str], cfg: WorldConfig) -> float:
    w = World(cfg)
    w.reset(seed)
    for r in routes:
        w.step({"route": r, "probe": False})
    return w.total_cost


def main():
    cfg = WorldConfig()
    seeds = range(1, 21)
    print(f"{'seed':>4} {'oracle':>8} {'suez':>8} {'cape':>8} "
          f"{'naive_min':>9} {'gap':>7} {'disrupt_wks':>11}")
    rows = []
    for seed in seeds:
        cost, routes = oracle_plan(seed, cfg)
        replayed = replay_cost(seed, routes, cfg)
        assert abs(replayed - cost) < 1e-6, (
            f"seed {seed}: DP cost {cost} != engine replay {replayed}")
        suez = fixed_route_cost(seed, "suez", cfg)
        cape = fixed_route_cost(seed, "cape", cfg)
        naive_min = min(suez, cape)
        gap = naive_min - cost

        w = World(cfg); w.reset(seed)
        while not w.done:
            w.step({"route": "suez", "probe": False})
        disrupt_wks = sum(1 for r in w.trace[1:]
                          if r["hidden"]["event_state"] == "disruption")

        rows.append((seed, cost, suez, cape, naive_min, gap, disrupt_wks))
        print(f"{seed:>4} {cost:>8.0f} {suez:>8.0f} {cape:>8.0f} "
              f"{naive_min:>9.0f} {gap:>7.0f} {disrupt_wks:>11}")

    gaps = [r[5] for r in rows]
    print(f"\ngap (naive_min - oracle): "
          f"min={min(gaps):.0f} max={max(gaps):.0f} "
          f"mean={sum(gaps)/len(gaps):.0f}")
    discriminative = sum(1 for g in gaps if g > 0)
    print(f"seeds where adaptive routing beats both fixed policies: "
          f"{discriminative}/{len(rows)}")


if __name__ == "__main__":
    main()
