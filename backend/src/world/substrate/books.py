"""The agent's books: shipments, inventory, demand. Deterministic given
the weekly hidden states - no randomness in this module.

Transit-week causality: a chokepoint affects the ships that are AT it
that week, never the ships merely ordered that week. A Suez ship meets
the canal at dispatch+suez_chokepoint_offset; the canal's state THAT
week decides through / backlog / queue. A queued ship waits one week,
then proceeds if clear or diverts around the Cape. A Cape ship meets
its congestion point at dispatch+cape_chokepoint_offset."""

from dataclasses import dataclass

from ..config import WorldConfig
from ..modules.disruption import HiddenState
from ..products import structure


@dataclass
class Shipment:
    qty: int
    route: str
    dispatched_week: int
    supplier: str = "qualified"       # which supplier dispatched it (attribution)
    component: str = "unit"           # which component this shipment carries (assembly)
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
                "supplier": self.supplier, "component": self.component,
                "dispatched_week": self.dispatched_week,
                "status": self.status, "eta": self.eta(cfg)}


@dataclass
class FreightLock:
    """A forward freight buy: the multiplier is FIXED at `rate` for the next
    `weeks_left` weeks, regardless of the realized spot. Observed commercial
    state (no hidden dimension); decremented per week in engine.step (an unused
    window still burns - the commitment teeth)."""
    rate: float
    weeks_left: int


class Books:
    """Per-component physical books. `components` maps component id -> on-hand
    int (the assembly substrate). Back-compat by construction: the legacy scalar
    calls `Books(80)` / `Books(inventory=80)` still work (they seed the sole
    `unit` component), and the `inventory` property still reads the total on-hand
    -- so a single-component (`single`-product) world is byte-identical to the
    old scalar-inventory world for every legacy caller/test."""

    def __init__(self, components=None, inventory: int | None = None):
        if inventory is not None:            # legacy: Books(inventory=N)
            components = {"unit": inventory}
        elif isinstance(components, int):     # legacy: Books(N) positional scalar
            components = {"unit": components}
        self.components: dict[str, int] = dict(components)  # component id -> on-hand
        self.staged_orders: list = []  # within-week staged order lines (order_component)
        self.pipeline: list[Shipment] = []
        self.contracts = []  # list[Contract]; an INSTANCE list, so holding two
                             # live contracts at once (dual-sourcing, R6) is legal
                             # by data shape, not a special case.
        self.freight_lock = None  # FreightLock | None: a live forward freight buy
        self.air_inbound = 0  # units flown in this week (expedite_air), landed at the next resolve
        self.inspected = False  # inspect_batch flag for this week; consumed at the next resolve

    @property
    def inventory(self) -> int:
        """Back-compat scalar: total on-hand across all components. For a
        single-component (`single`) product this equals the legacy inventory."""
        return sum(self.components.values())


def _advance(s: Shipment, h: HiddenState, week: int, cfg: WorldConfig) -> float:
    """Resolve one in-flight shipment against this week's world. Returns
    the diversion surcharge billed this week: a diverted voyage is a Cape
    voyage, so the carrier passes through the Cape price differential -
    otherwise ordering Suez into a known crisis and letting the carrier
    divert would be cheaper than booking Cape outright."""
    if s.arrives_week is not None:
        return 0.0
    # production/handling lead for this component, ADDED to the sea transit (the
    # scarce chip takes longer to make). `single`'s `unit` has lead_extra=0, so
    # every arrival week is byte-identical to the legacy scalar world.
    lead_extra = structure(cfg.product).components[s.component].lead_extra
    elapsed = week - s.dispatched_week
    if s.route == "suez":
        if s.status == "queued_at_suez":
            if h.canal_blocked:
                s.status = "diverted_via_cape"
                s.arrives_week = week + cfg.divert_extra_weeks + lead_extra
                return (cfg.cape_unit_cost - cfg.suez_unit_cost) * s.qty
            else:
                s.status = "at_sea"
                s.arrives_week = (week + (cfg.suez_total_weeks
                                          - cfg.suez_chokepoint_offset) + lead_extra)
        elif elapsed == cfg.suez_chokepoint_offset:
            if h.canal_blocked:
                s.status = "queued_at_suez"
            else:
                extra = (cfg.recovery_queue_extra_weeks
                         if h.event_state == "recovery" else 0)
                s.arrives_week = (s.dispatched_week + cfg.suez_total_weeks
                                  + extra + lead_extra)
    else:  # cape
        if elapsed == cfg.cape_chokepoint_offset:
            congested = (h.cape_local_congestion
                         or (h.event_state == "disruption"
                             and h.disruption_type == "long"))
            extra = cfg.cape_congested_extra_weeks if congested else 0
            s.arrives_week = (s.dispatched_week + cfg.cape_total_weeks
                              + extra + lead_extra)
    return 0.0
