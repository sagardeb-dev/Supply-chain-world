"""Clairvoyant oracle. The hidden trajectory is a function of the seed
alone (actions never consume the rng), so the oracle replays the seed
once to learn the entire future, then solves for the cost-minimizing
(qty, route) sequence exactly. It never buys briefings: it already
knows every regime and type. This is the luck-INCLUSIVE per-seed lower
bound; the benchmark anchor (causal-aware oracle, optimal expected
value with no future knowledge) comes next - see V1_CHANGE_LOG.md."""

from functools import lru_cache

from ..config import WorldConfig
from ..engine import World
from ..modules.disruption import HiddenState


def hidden_trajectory(seed: int, cfg: WorldConfig) -> list[HiddenState]:
    """Replay the seed to recover h_1..h_H. Action-independent, so one
    no-op playthrough exposes the whole exogenous trajectory."""
    w = World(cfg)
    w.reset(seed)
    while not w.done:
        w.step({"qty": 0})
    return [HiddenState(r["hidden"]["event_state"],
                        r["hidden"]["event_age"],
                        r["hidden"]["disruption_type"],
                        r["hidden"]["cape_local_congestion"])
            for r in w.trace[1:]]


def arrival_week(route: str, dispatch: int, traj: list[HiddenState],
                 cfg: WorldConfig) -> int | None:
    """Deterministic arrival under transit-week causality, given the full
    trajectory. None = unresolved/at sea past the horizon. Mirrors
    logistics._advance exactly; test_world.py pins the agreement."""
    H = len(traj)

    def state(w: int) -> HiddenState:
        return traj[w - 1]

    if route == "cape":
        cw = dispatch + cfg.cape_chokepoint_offset
        if cw > H:
            return None
        h = state(cw)
        congested = (h.cape_local_congestion
                     or (h.event_state == "disruption" and h.disruption_type == "long"))
        extra = cfg.cape_congested_extra_weeks if congested else 0
        return dispatch + cfg.cape_total_weeks + extra

    cw = dispatch + cfg.suez_chokepoint_offset
    if cw > H:
        return None
    h = state(cw)
    if not h.canal_blocked:
        extra = cfg.recovery_queue_extra_weeks if h.event_state == "recovery" else 0
        return dispatch + cfg.suez_total_weeks + extra
    if cw + 1 > H:
        return None  # queued at the horizon
    if state(cw + 1).canal_blocked:
        return cw + 1 + cfg.divert_extra_weeks
    return cw + 1 + (cfg.suez_total_weeks - cfg.suez_chokepoint_offset)


def optimal_plan_for(trajectory: list[HiddenState], cfg: WorldConfig):
    """Exact DP over (qty, route). State = (week, inventory, pending),
    pending = sorted tuple of (arrival_week, qty) for in-flight orders.
    In-transit holding is charged up-front at dispatch (qty x weeks on
    the water, horizon-truncated), which sums to the same total the
    engine charges weekly. Returns (min_cost, [(qty, route_or_None)])."""
    H = len(trajectory)
    arr = {(r, t): arrival_week(r, t, trajectory, cfg)
           for r in ("suez", "cape") for t in range(1, H + 1)}
    actions = [(0, None)] + [(q, r) for q in cfg.order_quantities if q
                             for r in ("suez", "cape")]

    @lru_cache(maxsize=None)
    def solve(week: int, inventory: int, pending: tuple) -> tuple:
        if week > H:
            return (0.0, ())
        best = None
        for qty, route in actions:
            if qty:
                a = arr[(route, week)]
                # qualified-supplier economics: the clairvoyant plan replays
                # the engine, which sources qualified, so it pays the premium.
                unit = (cfg.suez_unit_cost if route == "suez"
                        else cfg.cape_unit_cost) + cfg.qualified_premium
                lands = a is not None and a <= H
                transit_weeks = (a if lands else H + 1) - week
                dispatch_cost = (qty * unit
                                 + cfg.holding_cost * qty * transit_weeks)
                if route == "suez":
                    cw = week + cfg.suez_chokepoint_offset
                    diverted = (cw + 1 <= H
                                and trajectory[cw - 1].canal_blocked
                                and trajectory[cw].canal_blocked)
                    if diverted:
                        # diverted voyage billed at the Cape rate; the
                        # engine charges this at the diversion week, the
                        # DP up-front - same total (cf. in-transit holding)
                        dispatch_cost += ((cfg.cape_unit_cost
                                           - cfg.suez_unit_cost) * qty)
            else:
                lands, dispatch_cost = False, 0.0

            new_pending = list(pending)
            if qty and lands:
                new_pending.append((a, qty))
            arrived = sum(q for (x, q) in new_pending if x == week)
            new_pending = tuple(sorted((x, q) for (x, q) in new_pending
                                       if x > week))

            inv = inventory + arrived
            served = min(inv, cfg.weekly_demand)
            shortfall = cfg.weekly_demand - served
            inv -= served

            step_cost = (dispatch_cost + cfg.holding_cost * inv
                         + cfg.stockout_cost * shortfall)
            future_cost, future_plan = solve(week + 1, inv, new_pending)
            total = step_cost + future_cost
            if best is None or total < best[0]:
                best = (total, ((qty, route),) + future_plan)
        return best

    cost, plan = solve(1, cfg.initial_inventory, ())
    return cost, list(plan)


def oracle_cost(seed: int, cfg: WorldConfig | None = None) -> float:
    cfg = cfg or WorldConfig()
    cost, _ = optimal_plan_for(hidden_trajectory(seed, cfg), cfg)
    return cost


def oracle_plan(seed: int, cfg: WorldConfig | None = None):
    """(cost, plan) - plan entries are (qty, route|None), replayable on
    the live engine."""
    cfg = cfg or WorldConfig()
    return optimal_plan_for(hidden_trajectory(seed, cfg), cfg)
