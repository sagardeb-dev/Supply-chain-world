"""The agent's books: shipments, inventory, demand. Deterministic given
the weekly hidden states - no randomness in this module.

Transit-week causality: a chokepoint affects the ships that are AT it
that week, never the ships merely ordered that week. A Suez ship meets
the canal at dispatch+suez_chokepoint_offset; the canal's state THAT
week decides through / backlog / queue. A queued ship waits one week,
then proceeds if clear or diverts around the Cape. A Cape ship meets
its congestion point at dispatch+cape_chokepoint_offset."""

from dataclasses import dataclass

from .config import WorldConfig
from .state import HiddenState, SupplierState


@dataclass
class Shipment:
    qty: int
    route: str
    dispatched_week: int
    supplier: str = "qualified"       # which supplier dispatched it (attribution)
    status: str = "at_sea"            # at_sea | queued_at_suez | diverted_via_cape
    arrives_week: int | None = None   # fixed once the chokepoint resolves

    def eta(self, cfg: WorldConfig) -> int:
        """Carrier schedule: the true arrival once known, else the
        no-incident baseline. May slip - that is the point."""
        if self.arrives_week is not None:
            return self.arrives_week
        base = cfg.suez_total_weeks if self.route == "suez" else cfg.cape_total_weeks
        return self.dispatched_week + base

    def to_dict(self, cfg: WorldConfig) -> dict:
        return {"qty": self.qty, "route": self.route,
                "supplier": self.supplier,
                "dispatched_week": self.dispatched_week,
                "status": self.status, "eta": self.eta(cfg)}


class Books:
    def __init__(self, inventory: int):
        self.inventory = inventory
        self.pipeline: list[Shipment] = []
        self.contracts = []  # list[Contract]; an INSTANCE list, so holding two
                             # live contracts at once (dual-sourcing, R6) is legal
                             # by data shape, not a special case.


def _advance(s: Shipment, h: HiddenState, week: int, cfg: WorldConfig) -> float:
    """Resolve one in-flight shipment against this week's world. Returns
    the diversion surcharge billed this week: a diverted voyage is a Cape
    voyage, so the carrier passes through the Cape price differential -
    otherwise ordering Suez into a known crisis and letting the carrier
    divert would be cheaper than booking Cape outright."""
    if s.arrives_week is not None:
        return 0.0
    elapsed = week - s.dispatched_week
    if s.route == "suez":
        if s.status == "queued_at_suez":
            if h.canal_blocked:
                s.status = "diverted_via_cape"
                s.arrives_week = week + cfg.divert_extra_weeks
                return (cfg.cape_unit_cost - cfg.suez_unit_cost) * s.qty
            else:
                s.status = "at_sea"
                s.arrives_week = week + (cfg.suez_total_weeks - cfg.suez_chokepoint_offset)
        elif elapsed == cfg.suez_chokepoint_offset:
            if h.canal_blocked:
                s.status = "queued_at_suez"
            else:
                extra = (cfg.recovery_queue_extra_weeks
                         if h.event_state == "recovery" else 0)
                s.arrives_week = s.dispatched_week + cfg.suez_total_weeks + extra
    else:  # cape
        if elapsed == cfg.cape_chokepoint_offset:
            congested = (h.cape_local_congestion
                         or (h.event_state == "disruption"
                             and h.disruption_type == "long"))
            extra = cfg.cape_congested_extra_weeks if congested else 0
            s.arrives_week = s.dispatched_week + cfg.cape_total_weeks + extra
    return 0.0


def resolve_week(books: Books, qty: int, supplier: str | None,
                 route: str | None, h: HiddenState, sup: SupplierState,
                 week: int, cfg: WorldConfig):
    """Dispatch this week's order (if any), move every in-flight ship one
    week, land arrivals, consume demand. Returns (arrived_qty, cost_breakdown).

    The supplier stage (factor 2) resolves at DISPATCH: a spot order ships
    round(qty * fulfilled_fraction) -- a degraded spot order may leave the
    dock SHORT (or not at all). Qualified always ships full. Once at sea the
    voyage stage is untouched: stage 1 (sourcing) output feeds stage 2.

    ponytail: unit economics (spot discount / qualified premium) and the
    disruption cost coupling land in T5; this task only wires the shortfall."""
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
    # The Becker JV coupling (A8.2): a spot shortfall is cheap in calm weeks but
    # punishing when a disruption is brewing -- the lost units must be back-ordered
    # at the crisis spot rate. Reads BOTH factors (disruption regime + spot
    # shortfall) but lives in the reward, so the belief stays factored.
    couple = (cfg.crisis_backorder_kappa * shortfall_units
              if shortfall_units and h.regime in
              ("watch", "crash", "blockage", "crisis") else 0.0)
    costs = {
        "shipping": shipping,
        "surcharge": surcharge,  # diverted voyages billed at the Cape rate
        "holding": cfg.holding_cost * books.inventory,
        "in_transit": cfg.holding_cost * in_transit,  # capital cost on the water
        "stockout": cfg.stockout_cost * shortfall,
        "couple": couple,
    }
    return arrived, costs
