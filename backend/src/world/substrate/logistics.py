"""Tier 2 — voyage resolution. Dispatch this week's order, move every
in-flight ship one week, land arrivals, consume demand, total the cost.
Deterministic given the weekly hidden states.

The kappa cost-coupling (a spot shortfall during a brewing disruption) is
NOT computed here -- it is the one tier-3 term, in couplings.crisis_backorder.
This file only calls it, keeping the two-factor read in its one auditable home.
"""

from ..config import WorldConfig
from ..couplings import crisis_backorder
from ..modules.disruption import HiddenState
from ..modules.supplier import SUPPLIERS, SupplierState
from .books import Books, Shipment, _advance


def resolve_week(books: Books, qty: int, supplier: str | None,
                 route: str | None, h: HiddenState, sup: SupplierState | None,
                 week: int, cfg: WorldConfig, effects: dict | None = None):
    """Dispatch this week's order (if any), move every in-flight ship one
    week, land arrivals, consume demand. Returns (arrived_qty, cost_breakdown).

    The supplier stage (factor 2) resolves at DISPATCH: a drifting supplier's
    order ships round(qty * fulfilled_fraction) -- a degraded one may leave
    the dock SHORT (or not at all). Qualified always ships full. Once at sea the
    voyage stage is untouched: stage 1 (sourcing) output feeds stage 2."""
    eff = effects or {}
    shipping = 0.0
    shortfall_units = 0
    if qty:
        prof = SUPPLIERS[supplier]
        # a drifting supplier may leave the dock short (its noisy fulfilled
        # fraction); a non-drifting one always ships full -- read the PROFILE,
        # never the "spot" literal, so a second drifting supplier just works.
        frac = sup.fulfilled_fraction if prof["drifts"] else 1.0
        shipped = round(qty * frac)
        shortfall_units = qty - shipped
        if shipped:
            fmult = eff.get("freight_mult", 1.0)
            base = ((cfg.suez_unit_cost if route == "suez" else cfg.cape_unit_cost)
                    * fmult)
            # unit economics: base + sign*magnitude from the supplier's econ
            # profile (qualified +premium, spot -discount, backup +delta). cfg
            # stays the single source of truth for the magnitude.
            econ = prof["econ"]
            unit = base + econ["sign"] * getattr(cfg, econ["attr"])
            books.pipeline.append(Shipment(shipped, route, week, supplier))
            shipping = shipped * unit

    surcharge = 0.0
    for s in books.pipeline:
        surcharge += _advance(s, h, week, cfg)

    # destination-port stage (rich world): when the port is blocked (congestion
    # / customs hold), this week's arrivals are HELD a week and accrue demurrage.
    # The default world has no port effect -> the original arrival logic, exact.
    landing = [s for s in books.pipeline if s.arrives_week == week]
    demurrage = 0.0
    defective = 0
    if eff.get("port_blocked") and landing:
        for s in landing:
            s.arrives_week = week + 1
        demurrage = eff.get("demurrage_rate", 0.0) * sum(s.qty for s in landing)
        arrived = 0
    else:
        gross = sum(s.qty for s in landing)
        # quality (rich world): a defective fraction of arrivals don't stock
        # (effective shortfall) and incur rework; default world -> fraction 0.
        defective = round(gross * eff.get("defect_fraction", 0.0))
        arrived = gross - defective
        books.pipeline = [s for s in books.pipeline if s.arrives_week != week]
        books.inventory += arrived
    rework = eff.get("rework_rate", 0.0) * defective

    # weekly demand from the demand module (rich world), else the constant.
    dem = eff.get("demand", cfg.weekly_demand)
    served = min(books.inventory, dem)
    shortfall = dem - served
    books.inventory -= served

    in_transit = sum(s.qty for s in books.pipeline)
    # The Becker JV coupling (A8.2): reads BOTH factors (disruption regime +
    # spot shortfall) but lives in the reward, so the belief stays factored.
    # The two-factor read is sealed in couplings.py.
    couple = crisis_backorder(shortfall_units, h, cfg)
    costs = {
        "shipping": shipping,
        "surcharge": surcharge,  # diverted voyages billed at the Cape rate
        "holding": cfg.holding_cost * books.inventory,
        "in_transit": cfg.holding_cost * in_transit,  # capital cost on the water
        "stockout": cfg.stockout_cost * shortfall,
        "couple": couple,
    }
    # Emit these keys whenever the MODULE is active (its effect key is present),
    # NOT only when the value is nonzero -- otherwise the mere presence/absence of
    # a cost line is a clean boolean readout of the hidden port/quality state
    # (a side channel that bypasses the noisy emission). In the default 2-factor
    # world neither effect key is present, so the cost_breakdown is byte-identical.
    if "port_blocked" in eff:
        costs["demurrage"] = demurrage  # 0.0 unless the port held arrivals
    if "defect_fraction" in eff:
        costs["rework"] = rework        # 0.0 unless a defective batch landed
    return arrived, costs
