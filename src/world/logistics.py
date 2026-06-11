"""The agent's own books: shipments, inventory, demand. Deterministic —
no randomness anywhere in this module."""

from dataclasses import dataclass, asdict

from .config import WorldConfig
from .state import HiddenState


@dataclass
class Shipment:
    qty: int
    route: str
    arrives_week: int

    def to_dict(self) -> dict:
        return asdict(self)


class Books:
    def __init__(self, inventory: int):
        self.inventory = inventory
        self.pipeline: list[Shipment] = []


def lead_time(route: str, h: HiddenState, cfg: WorldConfig) -> int:
    if route == "suez":
        if h.suez_regime == "degraded":
            return cfg.suez_disrupted_lead_weeks
        return cfg.suez_lead_weeks
    extra = cfg.cape_congested_extra_weeks if h.cape_congestion == "high" else 0
    return cfg.cape_lead_weeks + extra


def resolve_week(books: Books, route: str, h: HiddenState, week: int, cfg: WorldConfig):
    """Dispatch this week's order, land arrivals, consume demand.
    Returns (arrived_qty, cost_breakdown)."""
    unit = cfg.suez_unit_cost if route == "suez" else cfg.cape_unit_cost
    books.pipeline.append(Shipment(cfg.order_qty, route, week + lead_time(route, h, cfg)))
    shipping = cfg.order_qty * unit

    arrived = sum(s.qty for s in books.pipeline if s.arrives_week == week)
    books.pipeline = [s for s in books.pipeline if s.arrives_week > week]
    books.inventory += arrived

    served = min(books.inventory, cfg.weekly_demand)
    shortfall = cfg.weekly_demand - served
    books.inventory -= served

    costs = {
        "shipping": shipping,
        "holding": cfg.holding_cost * books.inventory,
        "stockout": cfg.stockout_cost * shortfall,
    }
    return arrived, costs
