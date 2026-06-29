"""Cost sweep: fixed-policy baselines across seeds. Baselines:
always-20-via-suez, always-20-via-cape, base-stock (order-up-to-S via
critical ratio, Suez).
"""

from statistics import NormalDist

from src.world.config import WorldConfig
from src.world.engine import World
from src.world.registry import CORE


def _qualified_action(w, base: dict) -> dict:
    """Attach a one-time qualified sign if we don't already hold a live
    qualified contract (the masked world starts you on spot). The contract
    resolves before the order, so sign + source happen in one step."""
    if "qualified" not in w._contracted_suppliers():
        base = dict(base)
        base["contract"] = {"action": "sign", "supplier": "qualified",
                            "terms": None}
    return base


def fixed_policy_cost(seed: int, route: str, cfg: WorldConfig,
                      registry=None) -> float:
    w = World(cfg, registry=CORE if registry is None else registry)
    w.reset(seed)
    while not w.done:
        w.step(_qualified_action(
            w, {"qty": 20, "route": route, "supplier": "qualified"}))
    return w.total_cost


def _service_level_S(cfg: WorldConfig) -> int:
    """Order-up-to level from the newsvendor critical ratio. The cost structure
    (stockout vs holding) implies a service target p/(p+h); S covers mean demand
    over the lead time plus a safety buffer z*sigma*sqrt(L) for that service."""
    p, h = cfg.stockout_cost, cfg.holding_cost
    z = NormalDist().inv_cdf(p / (p + h))          # ~1.668 at 20/(20+1)
    lead = cfg.suez_total_weeks + 1                # order-to-arrival + one review
    mu = cfg.weekly_demand
    sigma = cfg.demand_noise_sd
    return round(mu * lead + z * sigma * (lead ** 0.5))


def drive_base_stock(seed: int, cfg: WorldConfig, registry=None):
    """Run the order-up-to-S base-stock policy to completion and return the
    driven World (read .total_cost and .fill_rate off it). Order-up-to-S via
    Suez/qualified with a FREE quantity -- the textbook base-stock policy a
    competent non-adaptive planner runs; S is the service-level target from the
    critical ratio, NOT a hardcoded constant. Migrates to qualified up front
    (the competent naive play vs a masked spot)."""
    w = World(cfg, registry=CORE if registry is None else registry)
    w.reset(seed)
    S = _service_level_S(cfg)
    while not w.done:
        position = w.books.inventory + sum(s.qty for s in w.books.pipeline)
        qty = max(0, min(S - position, cfg.order_max))
        base = ({"qty": qty, "route": "suez", "supplier": "qualified"}
                if qty else {"qty": 0})
        w.step(_qualified_action(w, base))
    return w


def base_stock_cost(seed: int, cfg: WorldConfig, registry=None) -> float:
    return drive_base_stock(seed, cfg, registry).total_cost


def replay_cost(seed: int, plan, cfg: WorldConfig) -> float:
    w = World(cfg)
    w.reset(seed)
    for qty, route in plan:
        w.step({"qty": qty, "route": route, "supplier": "qualified"}
               if qty else {"qty": 0})
    return w.total_cost


def main():
    cfg = WorldConfig(sup_mask_otif=True)   # match the scored CORE+masked world
    print(f"{'seed':>4} {'suez20':>8} {'cape20':>8} {'bstock':>8} "
          f"{'bs_fill':>8} {'naive_min':>9}")
    for seed in range(1, 21):
        suez = fixed_policy_cost(seed, "suez", cfg)
        cape = fixed_policy_cost(seed, "cape", cfg)
        w = drive_base_stock(seed, cfg)      # single base-stock driver
        bstock = w.total_cost
        print(f"{seed:>4} {suez:>8.0f} {cape:>8.0f} {bstock:>8.0f} "
              f"{w.fill_rate:>8.2f} {min(suez, cape, bstock):>9.0f}")


if __name__ == "__main__":
    main()
