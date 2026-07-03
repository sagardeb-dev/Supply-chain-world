"""Phase 2 of the Bayes-filter oracle: a rolling-horizon (receding-horizon MPC)
ACTING policy on top of filters.py's exact per-factor HMM forward filters.

Each week:
  1. update all 6 filters with the current observation (filters.py's own
     predict/correct step -- reused verbatim, not re-derived);
  2. sample K joint hidden trajectories for the remaining weeks: per factor
     independently, sample this week's state from that filter's own posterior,
     then roll forward using the SAME transition tables the filter uses
     (filt.trans, built by filters.py's build_*_filter);
  3. enumerate a small candidate action set for THIS week;
  4. for every candidate, simulate cost out to the true week 26 under every
     sampled trajectory (common random numbers: the same K trajectories are
     reused for every candidate this week), using a simple order-up-to
     continuation policy for the weeks after this one;
  5. execute the argmin candidate on the REAL world via world.step (built the
     same way src/agent/service.py's svc_step builds it).

The lookahead simulator in `simulate()` is a SURROGATE of the real engine
(logistics.py / books.py) -- every deliberate simplification vs the real
mechanics is marked with a `# ponytail:` comment. It never reads the real
world's future hidden tape (only this week's already-realized obs feed the
filters; everything after that is sampled, not looked up).

Run:
    uv run python oracle_policy.py --seed 7
    uv run python oracle_policy.py --seeds 7,8,19,64
    uv run python oracle_policy.py --seed 7 --k 50   (also runs k=100,200)
"""

import argparse
import random
from statistics import NormalDist, mean

from filters import FACTORS

from report_oracle import base_stock_cost, fixed_policy_cost

from src.world.config import WorldConfig
from src.world.engine import World
from src.world.registry import RICH

from src.world.modules.freight.config import FREIGHT_MEANS
from src.world.modules.freight.factor import freight_band
from src.world.modules.port.config import PORT_WAIT
from src.world.modules.port.factor import port_band
from src.world.modules.quality.config import QUALITY_DEFECT
from src.world.modules.demand.config import DEMAND_MEANS
from src.world.modules.demand.factor import demand_band
from src.world.modules.supplier.config import SUPPLIER_FILL_MEAN, SUPPLIERS


# --------------------------------------------------------------------------
# Trajectory sampling: reuse each filter's OWN belief + trans table (built by
# filters.py's build_*_filter -- same transition probabilities the filter
# itself uses to predict, so the surrogate future is drawn from the exact
# same generative model as the exact filter, not a re-derived approximation).
# --------------------------------------------------------------------------
def _sample_state(belief: dict, rng: random.Random):
    r, cum, last = rng.random(), 0.0, None
    for s, p in belief.items():
        last = s
        cum += p
        if r < cum:
            return s
    return last  # numerical fallback (belief sums to ~1 already)


def _trans_sample(trans: dict, s, rng: random.Random):
    rows = trans[s]
    r, cum, last = rng.random(), 0.0, rows[-1][0]
    for s2, p in rows:
        cum += p
        if r < cum:
            return s2
    return last


def sample_trajectory(filts: dict, nxt: int, horizon: int, rng: random.Random) -> dict:
    """One joint sample of every factor's state for weeks nxt..horizon
    (inclusive), starting from THIS week's posterior and rolling forward
    through the filter's own transition table."""
    traj = {}
    for f, filt in filts.items():
        cur = _sample_state(filt.belief, rng)
        states = {}
        for t in range(nxt, horizon + 1):
            cur = _trans_sample(filt.trans, cur, rng)
            states[t] = cur
        traj[f] = states
    return traj


# --------------------------------------------------------------------------
# Generic (regime, age) unpack -- works for freight/port/demand/quality/
# supplier states, which are either a bare regime string or a (regime, age)
# tuple (exactly the state shapes filters.py's build_*_filter constructs).
# --------------------------------------------------------------------------
def _band_state(s):
    if isinstance(s, str):
        return s, 0
    return s[0], s[1]


def _disruption_info(s):
    """(event_state, canal_blocked, crisis_coupling_regime) for a disruption
    filter state -- mirrors HiddenState.canal_blocked and
    build_disruption_filter's local visible_band()/_CRISIS_REGIMES exactly
    (those are closures inside filters.py, not exported, so the same mapping
    is re-expressed here rather than re-derived)."""
    if isinstance(s, str):
        event_state = s
        canal_blocked = False
        visible = "crash" if s == "false_alarm" else s
    else:
        kind = s[0]
        event_state = kind
        if kind == "disruption":
            _, dtype, a = s
            canal_blocked = True
            visible = "crash" if a == 0 else ("blockage" if dtype == "short" else "crisis")
        else:  # recovery
            canal_blocked = False
            visible = "recovery"
    crisis = visible in ("watch", "crash", "blockage", "crisis")
    return event_state, canal_blocked, crisis


def _demand_mean_at(traj: dict, t: int) -> float:
    regime, age = _band_state(traj["demand"][t])
    return DEMAND_MEANS[demand_band(regime, age)]


def _expected_demand(filt) -> float:
    """Posterior-mean weekly demand this week (belief-weighted DEMAND_MEANS),
    used to size the order-up-to candidate grid."""
    e = 0.0
    for s, p in filt.belief.items():
        regime, age = _band_state(s)
        e += p * DEMAND_MEANS[demand_band(regime, age)]
    return e


def _critical_ratio_z(cfg: WorldConfig) -> float:
    p, h = cfg.stockout_cost, cfg.holding_cost
    return NormalDist().inv_cdf(p / (p + h))


# --------------------------------------------------------------------------
# Candidate action set for this week.
# --------------------------------------------------------------------------
def build_candidates(w, cfg: WorldConfig, exp_demand: float, freight_risk: bool,
                     port_risk: bool, quality_risk: bool, batch_arriving: bool) -> list:
    contracted = w._contracted_suppliers()
    position = w.books.inventory + sum(s.qty for s in w.books.pipeline)

    qty_levels = sorted({0} | {
        max(0, min(round(exp_demand * weeks) - position, cfg.order_max))
        for weeks in (4, 6)
    })

    supplier_opts = [(s, False) for s in contracted]
    if "qualified" not in contracted:
        supplier_opts.append(("qualified", True))

    lock_opts = [False, True] if freight_risk else [False]
    air_opts = [0, min(20, cfg.air_weekly_cap)] if port_risk else [0]
    inspect_opts = [False, True] if (quality_risk and batch_arriving) else [False]

    cands = []
    for qty in qty_levels:
        routes = ["suez", "cape"] if qty else [None]
        for route in routes:
            for sup, sign in supplier_opts:
                if qty == 0 and sign:
                    continue  # signing with nothing to ship is dominated (no lever)
                for lock in lock_opts:
                    for air in air_opts:
                        for insp in inspect_opts:
                            cands.append({
                                "qty": qty, "route": route,
                                "supplier": sup if qty else None,
                                "sign_qualified": sign,
                                "lock_freight": lock, "air_qty": air,
                                "inspect": insp,
                            })
    return cands


# --------------------------------------------------------------------------
# Lookahead surrogate simulator. Approximates logistics.py/books.py's
# mechanics using each trajectory's sampled hidden path; every simplification
# vs the real engine is flagged `# ponytail:`.
# --------------------------------------------------------------------------
def simulate(cfg: WorldConfig, inv0: int, pipe0: list, cand: dict, traj: dict,
            nxt: int, horizon: int, contracted0: set) -> float:
    inv = inv0
    pipe = [list(p) for p in pipe0]        # [qty, arrive_week]
    contracted = set(contracted0)
    if cand.get("sign_qualified"):
        contracted.add("qualified")

    route_persist = cand["route"] or "suez"
    supplier_persist = ("qualified" if "qualified" in contracted
                        else "spot" if "spot" in contracted
                        else next(iter(contracted)))
    z = _critical_ratio_z(cfg)

    lock_rate, lock_left = None, 0
    if cand["lock_freight"]:
        fr_regime, fr_age = _band_state(traj["freight"][nxt])
        # ponytail: lock_freight() really reads the CURRENT realized freight
        # multiplier at call time (a real, observed number, since the return
        # value discloses it); the surrogate approximates it with this
        # trajectory's sampled next-week mean band rate instead of carrying an
        # extra "last realized" state through the loop.
        lock_rate = FREIGHT_MEANS[freight_band(fr_regime, fr_age)]
        lock_left = 4

    air_incoming = {nxt: cand["air_qty"]} if cand["air_qty"] else {}

    total = 0.0
    for t in range(nxt, horizon + 1):
        first = t == nxt
        dmean = _demand_mean_at(traj, t)

        if first:
            qty, route, supplier = cand["qty"], cand["route"], cand["supplier"]
        else:
            # ponytail: continuation weeks run a plain order-up-to-S base-stock
            # policy (same critical-ratio sizing as report_oracle's
            # base_stock_cost) on this trajectory's own demand mean, holding
            # route/supplier fixed -- the lookahead only optimizes THIS week's
            # decision; future weeks get a competent but non-adaptive filler.
            lead = cfg.suez_total_weeks if route_persist == "suez" else cfg.cape_total_weeks
            position = inv + sum(q for q, _ in pipe)
            S = round(dmean * (lead + 1) + z * cfg.demand_noise_sd * ((lead + 1) ** 0.5))
            qty = max(0, min(S - position, cfg.order_max))
            route = route_persist if qty else None
            supplier = supplier_persist if qty else None

        fr_regime, fr_age = _band_state(traj["freight"][t])
        fmean = FREIGHT_MEANS[freight_band(fr_regime, fr_age)]
        fmult = lock_rate if lock_left > 0 else fmean

        if supplier == "spot":
            sup_regime, _ = _band_state(traj["supplier"][t])
            # ponytail: uses the trajectory's TRUE rel_state fill-fraction MEAN
            # (SUPPLIER_FILL_MEAN), not a further noisy per-week draw -- the
            # per-week noise around that mean is already implicitly averaged
            # out over the K trajectories via the outer Monte-Carlo loop.
            frac = SUPPLIER_FILL_MEAN[sup_regime]
        else:
            frac = 1.0  # qualified/backup: frozen (not drifting) in this world

        shipped = round(qty * frac) if qty else 0
        short_units = (qty - shipped) if qty else 0

        shipping_cost = 0.0
        if shipped:
            base = cfg.suez_unit_cost if route == "suez" else cfg.cape_unit_cost
            econ = SUPPLIERS[supplier]["econ"]
            unit = base * fmult + econ["sign"] * getattr(cfg, econ["attr"])
            shipping_cost = shipped * unit

        dis_event, canal_blocked, crisis_band = _disruption_info(traj["disruption"][t])
        if shipped:
            base_lead = cfg.suez_total_weeks if route == "suez" else cfg.cape_total_weeks
            # ponytail: the real engine's diversion adds cfg.divert_extra_weeks
            # (a full extra Cape-length detour) plus a queue week, only for a
            # ship actually AT the chokepoint the week the canal is blocked.
            # The surrogate approximates any suez dispatch into a
            # canal-blocked trajectory week as "+1 week", not the full
            # queued-then-diverted delay -- a deliberately coarser lead-time
            # bump, per the spec.
            diverted = canal_blocked if route == "suez" else False
            lead = base_lead + (1 if diverted else 0)
            pipe.append([shipped, t + lead])

        port_regime, _ = _band_state(traj["port"][t])
        port_blocked = port_regime in ("congested", "customs_hold")
        quality_regime, _ = _band_state(traj["quality"][t])
        defect_frac = QUALITY_DEFECT[quality_regime]
        if first and cand["inspect"]:
            defect_frac *= (1.0 - cfg.inspect_catch_rate)

        arriving = [p for p in pipe if p[1] == t]
        demurrage_cost = rework_cost = 0.0
        if port_blocked and arriving:
            for p in arriving:
                p[1] = t + 1
            demurrage_cost = cfg.port_demurrage_rate * sum(p[0] for p in arriving)
        else:
            for p in arriving:
                defective = round(p[0] * defect_frac)
                usable = p[0] - defective
                inv += usable
                rework_cost += cfg.quality_rework_cost * defective
            pipe = [p for p in pipe if p[1] != t]

        air_land = air_incoming.pop(t, 0)
        if air_land:
            # ponytail: real expedite_air units bypass BOTH the port-block and
            # the quality-inspection stage (they land straight into
            # book.components); the surrogate mirrors that (no port/quality
            # deduction on air units).
            inv += air_land

        served = min(inv, dmean)
        shortfall = dmean - served
        inv -= served

        holding_cost = cfg.holding_cost * (inv + sum(p[0] for p in pipe))
        stockout_cost = cfg.stockout_cost * shortfall
        couple = cfg.crisis_backorder_kappa * short_units if (short_units and crisis_band) else 0.0
        # ponytail: dual_source_overhead here assumes any newly-signed 2nd
        # contract stays live for the REST of the simulated horizon (the real
        # engine would let the agent lapse it later); a conservative
        # overstatement of the sign-qualified candidate's cost.
        dual = cfg.dual_source_overhead if len(contracted) >= 2 else 0.0
        inspect_cost = cfg.inspect_fee if (first and cand["inspect"]) else 0.0
        air_cost = cfg.air_unit_cost * cand["air_qty"] if (first and cand["air_qty"]) else 0.0

        total += (shipping_cost + holding_cost + stockout_cost + couple + dual
                 + demurrage_cost + rework_cost + inspect_cost + air_cost)

        if lock_left > 0:
            lock_left -= 1

    return total


def execute(w, cand: dict) -> float:
    """Commit the chosen candidate on the REAL world, built the same way
    src/agent/service.py's svc_step/svc_lock/svc_expedite/svc_inspect do."""
    if cand["lock_freight"]:
        w.lock_freight(4)
    if cand["air_qty"]:
        w.expedite_air(cand["air_qty"])
    if cand["inspect"]:
        w.inspect_batch()
    action = {"qty": cand["qty"], "route": cand["route"],
             "supplier": cand["supplier"] if cand["qty"] else None}
    if cand.get("sign_qualified"):
        action["contract"] = {"action": "sign", "supplier": "qualified", "terms": None}
    obs, cost, done, _info = w.step(action)
    return cost


# --------------------------------------------------------------------------
# Weekly driver.
# --------------------------------------------------------------------------
def run_oracle(seed: int, k: int = 100, cfg: WorldConfig = None, trace: bool = False) -> float:
    cfg = cfg or WorldConfig(sup_mask_otif=True)
    w = World(cfg, registry=RICH)
    w.reset(seed)
    filts = {f: build(cfg) for f, (build, _) in FACTORS.items()}
    mc_rng = random.Random(seed * 7919 + 13 + k)  # separate stream; never touches world.rng
    cum = 0.0

    while not w.done:
        obs = w.trace[-1]["obs"]
        for filt in filts.values():
            filt.step(obs)

        exp_demand = _expected_demand(filts["demand"])
        fpost = filts["freight"].regime_posterior()
        freight_risk = fpost.get("tightening", 0.0) + fpost.get("spike", 0.0) > 0.3
        ppost = filts["port"].regime_posterior()
        port_risk = ppost.get("congested", 0.0) + ppost.get("customs_hold", 0.0) > 0.3
        qpost = filts["quality"].regime_posterior()
        quality_risk = qpost.get("out_of_control", 0.0) > 0.5
        batch_arriving = any(s.eta(cfg) == w.week + 1 for s in w.books.pipeline)

        cands = build_candidates(w, cfg, exp_demand, freight_risk, port_risk,
                                 quality_risk, batch_arriving)

        nxt = w.week + 1
        trajs = [sample_trajectory(filts, nxt, cfg.horizon_weeks, mc_rng) for _ in range(k)]
        inv0 = w.books.inventory
        pipe0 = [[s.qty, s.eta(cfg)] for s in w.books.pipeline]
        contracted0 = w._contracted_suppliers()

        best_cand, best_cost = None, float("inf")
        for cand in cands:
            avg = mean(simulate(cfg, inv0, pipe0, cand, traj, nxt, cfg.horizon_weeks, contracted0)
                       for traj in trajs)
            if avg < best_cost:
                best_cost, best_cand = avg, cand

        cost = execute(w, best_cand)
        cum += cost

        if trace:
            argmaxes = " ".join(f"{f}={filts[f].argmax_regime()[0]}" for f in FACTORS)
            c = best_cand
            print(f"wk {w.week:>2} | {argmaxes} | "
                  f"qty={c['qty']:>3} route={str(c['route']):>4} sup={str(c['supplier']):>9} "
                  f"lock={int(c['lock_freight'])} air={c['air_qty']:>2} insp={int(c['inspect'])} "
                  f"signQ={int(c['sign_qualified'])} | cost={cost:>7.1f} cum={cum:>8.1f}")

    return w.total_cost


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--seeds", type=str, default=None)
    ap.add_argument("--k", type=int, default=None)
    args = ap.parse_args()

    if args.seeds:
        seeds = [int(x) for x in args.seeds.split(",")]
        cfg = WorldConfig(sup_mask_otif=True)
        print(f"{'seed':>5} {'oracle':>9} {'suez20':>9} {'cape20':>9} {'bstock':>9}")
        for s in seeds:
            oc = run_oracle(s, k=100, cfg=cfg, trace=False)
            suez = fixed_policy_cost(s, "suez", cfg, registry=RICH)
            cape = fixed_policy_cost(s, "cape", cfg, registry=RICH)
            bs = base_stock_cost(s, cfg, registry=RICH)
            print(f"{s:>5} {oc:>9.0f} {suez:>9.0f} {cape:>9.0f} {bs:>9.0f}")
        return

    seed = args.seed if args.seed is not None else 7

    if args.k is not None:
        for k in (50, 100, 200):
            total = run_oracle(seed, k=k, trace=False)
            print(f"k={k:>4}: total={total:.0f}")
        return

    total = run_oracle(seed, k=100, trace=True)
    print(f"TOTAL: {total:.0f}")


if __name__ == "__main__":
    main()
