"""Tier 2 — voyage resolution. Dispatch this week's order, move every
in-flight ship one week, land arrivals, consume demand, total the cost.
Deterministic given the weekly hidden states.

The kappa cost-coupling (a spot shortfall during a brewing disruption) is
NOT computed here -- it is the one tier-3 term, in couplings.crisis_backorder.
This file only calls it, keeping the two-factor read in its one auditable home.
"""

from ..config import WorldConfig
from ..couplings import crisis_backorder
from ..state import HiddenState, SupplierState
from .books import Books, Shipment, _advance


def resolve_week(books: Books, qty: int, supplier: str | None,
                 route: str | None, h: HiddenState, sup: SupplierState,
                 week: int, cfg: WorldConfig):
    """Dispatch this week's order (if any), move every in-flight ship one
    week, land arrivals, consume demand. Returns (arrived_qty, cost_breakdown).

    The supplier stage (factor 2) resolves at DISPATCH: a spot order ships
    round(qty * fulfilled_fraction) -- a degraded spot order may leave the
    dock SHORT (or not at all). Qualified always ships full. Once at sea the
    voyage stage is untouched: stage 1 (sourcing) output feeds stage 2.

    ponytail: PINNED MIRROR of oracle.causal.resolve_rel (the DP's relative-
    pipeline twin). Do NOT dedup -- different state reps; kept in lockstep by
    test_resolve_rel_mirrors_resolve_week + the causal_play cross-check. Touch
    cost arithmetic here (including the crisis_backorder coupling) and you MUST
    mirror it in resolve_rel."""
    shipping = 0.0
    shortfall_units = 0
    if qty:
        frac = sup.fulfilled_fraction if supplier == "spot" else 1.0
        shipped = round(qty * frac)
        shortfall_units = qty - shipped
        if shipped:
            base = cfg.suez_unit_cost if route == "suez" else cfg.cape_unit_cost
            # unit economics (A8.1): spot undercuts the lane, qualified adds a premium
            unit = (base - cfg.spot_unit_discount if supplier == "spot"
                    else base + cfg.qualified_premium)
            books.pipeline.append(Shipment(shipped, route, week, supplier))
            shipping = shipped * unit

    surcharge = 0.0
    for s in books.pipeline:
        surcharge += _advance(s, h, week, cfg)

    arrived = sum(s.qty for s in books.pipeline if s.arrives_week == week)
    books.pipeline = [s for s in books.pipeline if s.arrives_week != week]
    books.inventory += arrived

    served = min(books.inventory, cfg.weekly_demand)
    shortfall = cfg.weekly_demand - served
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
    return arrived, costs
