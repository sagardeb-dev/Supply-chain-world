"""reset()/step() orchestrator, plus the pre-decision briefing stage.
The only module that knows the sequence: (optional briefing on the
current week) -> evolve hidden -> resolve logistics -> emit observation.
Engine internals are canonically named; anon presentation is applied
only in _build_obs (R4)."""

import random

from .config import WorldConfig
from .emission import analyst_briefing, news_bulletin, observe_counts
from .logistics import Books, resolve_week
from .state import SupplierState
from .semantics import COUNT_KEYS, ROUTE_DISPLAY, STATUS_DISPLAY
from .state import HiddenState
from .transition import step_hidden

HIDDEN_KEYS = {"event_state", "event_age", "disruption_type",
               "cape_local_congestion", "regime", "canal_blocked"}


class World:
    def __init__(self, cfg: WorldConfig | None = None):
        self.cfg = cfg or WorldConfig()

    def reset(self, seed: int) -> dict:
        self.rng = random.Random(seed)
        self.week = 0
        self.hidden = HiddenState()
        self.books = Books(inventory=self.cfg.initial_inventory)
        self.done = False
        self.total_cost = 0.0
        self.trace = []
        self._briefing = None  # paid assessment bought at this decision point
        obs = self._build_obs(arrived=0, costs={})
        self.trace.append({"week": 0, "hidden": self.hidden.to_dict(),
                           "action": None, "obs": obs, "cost": 0.0})
        return obs

    def request_briefing(self) -> str:
        """Paid analyst assessment of the CURRENT week's hidden state -
        bought while looking at this week's obs, BEFORE committing the
        order (R5). Charged once per week; repeat calls return the same
        text without re-charging."""
        if self.done:
            raise RuntimeError("episode is done; call reset()")
        if self._briefing is None:
            self._briefing = analyst_briefing(self.hidden, self.cfg)
        return self._briefing

    def step(self, action: dict):
        """action = {"qty": 0|20|40, "route": "suez"|"cape"} - route
        required iff qty > 0. Canonical route names; the API layer
        translates anon vocabularies (R4)."""
        if self.done:
            raise RuntimeError("episode is done; call reset()")
        qty = action["qty"]
        if qty not in self.cfg.order_quantities:
            raise ValueError(f"qty must be one of {self.cfg.order_quantities}")
        route = action.get("route")
        if qty and route not in ("suez", "cape"):
            raise ValueError(f"qty {qty} needs route suez or cape, got {route!r}")

        briefed = self._briefing is not None
        self._briefing = None

        self.week += 1
        self.hidden = step_hidden(self.hidden, self.rng, self.cfg)
        # ponytail: supplier hard-wired to qualified until T6 adds self.supplier.
        arrived, costs = resolve_week(self.books, qty, "qualified" if qty else None,
                                      route if qty else None, self.hidden,
                                      SupplierState(), self.week, self.cfg)
        if briefed:
            costs["briefing"] = self.cfg.briefing_cost

        cost = float(sum(costs.values()))
        self.total_cost += cost
        self.done = self.week >= self.cfg.horizon_weeks

        obs = self._build_obs(arrived=arrived, costs=costs)
        info = {"hidden": self.hidden.to_dict()}  # for replay/oracle, never the agent
        self.trace.append({"week": self.week, "hidden": info["hidden"],
                           "action": {"qty": qty, "route": route if qty else None,
                                      "briefing": briefed},
                           "obs": obs, "cost": cost})
        return obs, cost, self.done, info

    def _build_obs(self, arrived: int, costs: dict) -> dict:
        keymap = COUNT_KEYS[self.cfg.semantics]
        counts = observe_counts(self.hidden, self.cfg)
        obs = {
            "week": self.week,
            **{keymap[k]: v for k, v in counts.items()},
            "bulletin": news_bulletin(self.hidden, self.cfg),
            "inventory": self.books.inventory,
            "arrived": arrived,
            "pipeline": [self._display_shipment(s) for s in self.books.pipeline],
            "cost_breakdown": dict(costs),
        }
        assert not (HIDDEN_KEYS & obs.keys()), "hidden state leaked into observation"
        return obs

    def _display_shipment(self, s) -> dict:
        d = s.to_dict(self.cfg)
        mode = self.cfg.semantics
        d["route"] = ROUTE_DISPLAY[mode][d["route"]]
        d["status"] = STATUS_DISPLAY[mode][d["status"]]
        return d
