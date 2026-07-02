"""Cost sweep: fixed-policy baselines across seeds. Baselines:
always-20-via-suez, always-20-via-cape, base-stock (order-up-to-S via
critical ratio, Suez).
"""

from statistics import NormalDist

from src.world.config import WorldConfig
from src.world.engine import World
from src.world.products import structure
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


# --- assembly (multi-component) baselines ------------------------------------

def _component_demand_mean(cfg: WorldConfig, prod) -> dict:
    """Mean weekly demand for each component = sum over the finished goods that
    use it of (that model's mean demand x its BOM qty). Phase 1: per-FG demand
    params are shared (cfg.weekly_demand), so each model contributes the same
    mean through the BOM."""
    return {cid: sum(cfg.weekly_demand * prod.bom[fg][cid]
                     for fg in prod.finished_goods if cid in prod.bom[fg])
            for cid in prod.component_ids}


def _component_S(cfg: WorldConfig, prod) -> dict:
    """Per-component order-up-to level from the newsvendor critical ratio. Each
    component covers its own demand mean over its own lead (Suez transit + one
    review week + the component's production lead_extra) plus a safety buffer
    z*sigma*sqrt(L); sigma combines the independent per-model demand noise
    feeding that component through the BOM. NOT hardcoded -- read off cfg/products."""
    p, h = cfg.stockout_cost, cfg.holding_cost
    z = NormalDist().inv_cdf(p / (p + h))
    mu = _component_demand_mean(cfg, prod)
    out = {}
    for cid in prod.component_ids:
        lead = cfg.suez_total_weeks + 1 + prod.components[cid].lead_extra
        var = sum((cfg.demand_noise_sd * prod.bom[fg][cid]) ** 2
                  for fg in prod.finished_goods if cid in prod.bom[fg])
        out[cid] = round(mu[cid] * lead + z * (var ** 0.5) * (lead ** 0.5))
    return out


def _fill_by_fg(world) -> dict:
    """Per-finished-good fill rate over the run: sum of served / sum of demand
    (served + shortfall) per model, read off the trace's explicit served map."""
    prod = structure(world.cfg.product)
    served = {fg: 0 for fg in prod.finished_goods}
    demand = {fg: 0 for fg in prod.finished_goods}
    for rec in world.trace[1:]:                       # skip week 0 (no step yet)
        s = rec["obs"].get("served", {})
        d = rec["obs"].get("demand")                  # per-model emission (earbuds)
        for fg in prod.finished_goods:
            served[fg] += s.get(fg, 0)
            demand[fg] += (d[fg]["pos_units"] if d else world.cfg.weekly_demand)
    return {fg: (1.0 if demand[fg] == 0 else served[fg] / demand[fg])
            for fg in prod.finished_goods}


def drive_component_base_stock(seed: int, cfg: WorldConfig, registry=None):
    """Per-component order-up-to-S base-stock for an assembly world: each week,
    stage one order per component to lift its inventory position to S_c, then
    place_order on Suez/qualified with a FREE quantity. The competent
    material-requirements planner's non-adaptive policy; S_c from the critical
    ratio, not a hardcoded constant. Returns the driven World."""
    w = World(cfg, registry=CORE if registry is None else registry)
    w.reset(seed)
    prod = structure(cfg.product)
    S = _component_S(cfg, prod)
    while not w.done:
        for cid in prod.component_ids:
            pos = (w.books.components[cid]
                   + sum(s.qty for s in w.books.pipeline if s.component == cid))
            qty = max(0, min(S[cid] - pos, cfg.order_max))
            if qty:
                w.stage_order(cid, qty, "qualified")
        w.step({"route": "suez"})
    return w


def flat_component_policy_cost(seed: int, cfg: WorldConfig, registry=None) -> float:
    """The foil baseline: order EACH component at its mean every week (no
    position feedback), Suez/qualified. A demand-blind flat ladder the adaptive
    base-stock should beat on cost under noisy demand + lead times."""
    w = World(cfg, registry=CORE if registry is None else registry)
    w.reset(seed)
    prod = structure(cfg.product)
    mu = _component_demand_mean(cfg, prod)
    while not w.done:
        for cid in prod.component_ids:
            w.stage_order(cid, round(mu[cid]), "qualified")
        w.step({"route": "suez"})
    return w.total_cost


# --- Phase 2 gate probe: does the sourcing bet have teeth? -------------------
# Two non-adaptive sourcing policies on the v2 scored world (earbuds + all three
# suppliers drifting). Both reuse the per-component order-up-to-S sizing above;
# they differ only in WHO they source from. Keep it simple -- a gate probe, not
# a benchmark harness.

def _teeth_cfg() -> WorldConfig:
    """The v2 scored world the sourcing bet lives in: earbuds assembly + all
    three suppliers drifting, masked like the agent's world (spot incumbent)."""
    return WorldConfig(product="earbuds", sup_all_drift=True, sup_mask_otif=True)


def _spot_band(obs) -> str:
    """spot's current VISIBLE scorecard band (ontime/slipping/failing/defunct)
    -- the reactive policy's only supplier signal (masked, so it lags)."""
    return next(r for r in obs["suppliers"] if r["id"] == "spot")["band"]


def _source_all_from(w, target: str, S: dict, prod, obs):
    """Stage each component's order-up-to-S qty from `target` and step, signing a
    fresh contract for target first if we don't already hold a live one. If the
    target is un-sourceable (defunct -> its contract is open and it cannot be
    re-signed), skip ordering this week (a do-nothing step) -- the starvation IS
    the teeth. Mirrors drive_component_base_stock's staging + free-qty sizing.
    Returns the step's obs (or the passed obs on a skipped week).
    ponytail: never lapses the OLD contract after a switch, so dual-source
    overhead (~4/wk) accrues for the rest of the run -- biases AGAINST the
    switching policy, so a positive teeth result survives it; add a lapse
    sub-action if the gate ever reads marginal."""
    action = {"route": "suez"}
    if target not in w._contracted_suppliers():
        if w._alive().get(target):        # signable only if not defunct
            action["contract"] = {"action": "sign", "supplier": target,
                                  "terms": None}
        else:
            return w.step({"qty": 0})[0]   # dead target: cannot source it now
    for cid in prod.component_ids:
        pos = (w.books.components[cid]
               + sum(s.qty for s in w.books.pipeline if s.component == cid))
        qty = max(0, min(S[cid] - pos, w.cfg.order_max))
        if qty:
            w.stage_order(cid, qty, target)
    return w.step(action)[0]


def drive_greedy_cheap(seed: int, cfg: WorldConfig = None):
    """Always source every component from the cheapest supplier (spot), same
    per-component order-up-to sizing as drive_component_base_stock. The naive
    cost-chaser: great while spot is healthy, exposed when it wobbles/dies."""
    cfg = cfg or _teeth_cfg()
    w = World(cfg, registry=CORE)
    obs = w.reset(seed)
    prod = structure(cfg.product)
    S = _component_S(cfg, prod)
    while not w.done:
        obs = _source_all_from(w, "spot", S, prod, obs)
    return w


def drive_reactive_switch(seed: int, cfg: WorldConfig = None):
    """Source spot while its scorecard band reads 'ontime'; the moment it reads
    slipping/failing/defunct, source qualified instead (and switch back when spot
    recovers to ontime). Same order-up-to sizing. The band-reactive hedger."""
    cfg = cfg or _teeth_cfg()
    w = World(cfg, registry=CORE)
    obs = w.reset(seed)
    prod = structure(cfg.product)
    S = _component_S(cfg, prod)
    while not w.done:
        target = "spot" if _spot_band(obs) == "ontime" else "qualified"
        obs = _source_all_from(w, target, S, prod, obs)
    return w


def sourcing_teeth(seeds: list) -> dict:
    """Run both sourcing policies over the seeds; return mean total cost + mean
    fill for each. The 'sourcing bet has teeth' gate: reactive_switch should buy
    materially better fill (and/or cost) than blind greedy_cheap when suppliers
    drift -- if the two are indistinguishable, the bet is toothless."""
    from statistics import mean
    out = {}
    for name, driver in (("greedy_cheap", drive_greedy_cheap),
                         ("reactive_switch", drive_reactive_switch)):
        runs = [driver(s) for s in seeds]
        out[name] = {"mean_cost": mean(w.total_cost for w in runs),
                     "mean_fill": mean(w.fill_rate for w in runs)}
    return out


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
    # Phase 2 gate: the sourcing bet's teeth on the earbuds + all-drift world.
    teeth = sourcing_teeth(list(range(1, 21)))
    print("\nsourcing-teeth gate (earbuds + all-drift, seeds 1..20):")
    for name, m in teeth.items():
        print(f"  {name:>16}: mean_cost {m['mean_cost']:>9.0f}  "
              f"mean_fill {m['mean_fill']:.3f}")


if __name__ == "__main__":
    main()
