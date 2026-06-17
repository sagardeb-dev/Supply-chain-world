"""reset()/step() orchestrator, plus the pre-decision briefing stage.
The only module that knows the sequence: (optional briefing on the
current week) -> evolve hidden -> resolve logistics -> emit observation.
Engine internals are canonically named; anon presentation is applied
only in _build_obs (R4)."""

import random

from .config import SUPPLIERS, WorldConfig
from .emission import (analyst_briefing, news_bulletin, observe_counts,
                       observe_scorecard)
from .contracts import Contract, contract_open
from .logistics import Books, resolve_week
from .state import SupplierState
from .semantics import (COUNT_KEYS, ROUTE_DISPLAY, STATUS_DISPLAY,
                        SUPPLIER_DISPLAY)
from .state import HiddenState
from .transition import step_hidden, step_supplier

HIDDEN_KEYS = {"event_state", "event_age", "disruption_type",
               "cape_local_congestion", "regime", "canal_blocked",
               "rel_state", "rel_age"}  # supplier factor internals


class World:
    def __init__(self, cfg: WorldConfig | None = None):
        self.cfg = cfg or WorldConfig()

    def reset(self, seed: int) -> dict:
        self.rng = random.Random(seed)
        self.week = 0
        self.hidden = HiddenState()
        # factor-2 roster: one reliability chain per supplier. qualified &
        # backup are frozen-reliable in R1; only spot drifts (R2 adds defunct).
        self.suppliers = {sid: SupplierState() for sid in SUPPLIERS}
        self.books = Books(inventory=self.cfg.initial_inventory)
        # pre-contracted to the qualified incumbent: you don't start a
        # supply chain with no supplier. Default length cfg.contract_weeks.
        self.books.contracts = [self._new_contract("qualified", start=0)]
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

    def _new_contract(self, supplier: str, start: int, weeks: int | None = None):
        """Mint a contract with default terms (R5 makes terms negotiable)."""
        weeks = weeks if weeks is not None else self.cfg.contract_weeks
        base = self.cfg.suez_unit_cost
        # the incumbent relationship is evergreen (never lapses); spot/backup
        # contracts are time-boxed bets that expire and must be renewed.
        end = None if supplier == "qualified" else start + weeks
        return Contract(supplier=supplier, start_week=start,
                        end_week=end, unit_price=base,
                        otif_floor=self.cfg.contract_otif_floor,
                        break_fee=self.cfg.contract_break_fee)

    def _alive(self) -> dict:
        """Which suppliers are alive (not defunct). Derived from the VISIBLE
        scorecard band (defunct shows on the scorecard), so no hidden leak."""
        return {sid: s.rel_state != "defunct" for sid, s in self.suppliers.items()}

    def _open_supplier_ids(self) -> list:
        """Standing rule applied to every live contract: which suppliers have an
        OPEN contract (expired or counterparty dead) needing renewal."""
        alive = self._alive()
        return [c.supplier for c in self.books.contracts
                if contract_open(c, self.week, alive)]

    def _contracted_suppliers(self) -> set:
        """Suppliers the agent may currently source from: those with a live
        (not-open) contract. Per-contract sourcing mask."""
        alive = self._alive()
        return {c.supplier for c in self.books.contracts
                if not contract_open(c, self.week, alive)}

    def _apply_contract_action(self, ca: dict):
        """Process a sign/switch/lapse sub-action. R4 minimal: sign adds a new
        contract from this week; lapse drops open contracts for a supplier;
        switch = sign a new one (the old open one is dropped on renewal)."""
        act, sup = ca.get("action"), ca.get("supplier")
        if act not in ("sign", "switch", "renew", "lapse"):
            raise ValueError(f"unknown contract action {act!r}")
        if act == "lapse":
            alive = self._alive()
            self.books.contracts = [
                c for c in self.books.contracts
                if not (c.supplier == sup
                        and contract_open(c, self.week, alive))]
            return
        if sup not in self.suppliers:
            raise ValueError(f"cannot contract unknown supplier {sup!r}")
        # sign/switch/renew: drop any open contract for that supplier, add fresh
        alive = self._alive()
        self.books.contracts = [
            c for c in self.books.contracts
            if not (c.supplier == sup and contract_open(c, self.week, alive))]
        self.books.contracts.append(self._new_contract(sup, start=self.week))

    def step(self, action: dict):
        """action = {"qty": 0|20|40, "supplier": "qualified"|"spot",
        "route": "suez"|"cape"} - supplier AND route required iff qty > 0
        (no fallback). Canonical names; the API layer translates anon
        vocabularies (R4)."""
        if self.done:
            raise RuntimeError("episode is done; call reset()")
        # contract sub-action (sign/switch/renew/lapse) resolves first, so a
        # freshly-signed supplier is immediately sourceable this week.
        if action.get("contract"):
            self._apply_contract_action(action["contract"])

        qty = action["qty"]
        if qty not in self.cfg.order_quantities:
            raise ValueError(f"qty must be one of {self.cfg.order_quantities}")
        route = action.get("route")
        if qty and route not in ("suez", "cape"):
            raise ValueError(f"qty {qty} needs route suez or cape, got {route!r}")
        supplier = action.get("supplier")
        if qty and supplier not in self.suppliers:
            raise ValueError(
                f"qty {qty} needs a known supplier, got {supplier!r}")
        # per-contract mask: you may only source from a supplier you hold a
        # live contract with (no fallback).
        if qty and supplier not in self._contracted_suppliers():
            raise ValueError(
                f"no live contract with {supplier!r}; sign one first "
                f"(contracted: {sorted(self._contracted_suppliers())})")

        briefed = self._briefing is not None
        self._briefing = None

        self.week += 1
        self.hidden = step_hidden(self.hidden, self.rng, self.cfg)
        # only spot drifts in R1; advance it, leave qualified/backup frozen.
        self.suppliers["spot"] = step_supplier(
            self.suppliers["spot"], self.rng, self.cfg)
        arrived, costs = resolve_week(
            self.books, qty, supplier if qty else None,
            route if qty else None, self.hidden, self.suppliers["spot"],
            self.week, self.cfg)
        if briefed:
            costs["briefing"] = self.cfg.briefing_cost

        cost = float(sum(costs.values()))
        self.total_cost += cost
        self.done = self.week >= self.cfg.horizon_weeks

        obs = self._build_obs(arrived=arrived, costs=costs)
        info = {"hidden": self.hidden.to_dict()}  # for replay/oracle, never the agent
        self.trace.append({"week": self.week, "hidden": info["hidden"],
                           "action": {"qty": qty, "route": route if qty else None,
                                      "supplier": supplier if qty else None,
                                      "contract": action.get("contract"),
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
            **observe_scorecard(self.suppliers, self.cfg),  # {"suppliers": [...]}
            "contracts": [self._display_contract(c) for c in self.books.contracts],
            "contract_open": self._open_supplier_ids(),  # the auto-renewal prompt
        }
        assert not (HIDDEN_KEYS & obs.keys()), "hidden state leaked into observation"
        return obs

    def _display_contract(self, c) -> dict:
        return {"supplier": SUPPLIER_DISPLAY[self.cfg.semantics][c.supplier],
                "start_week": c.start_week, "end_week": c.end_week,
                "unit_price": c.unit_price, "otif_floor": c.otif_floor,
                "break_fee": c.break_fee}

    def _display_shipment(self, s) -> dict:
        d = s.to_dict(self.cfg)
        mode = self.cfg.semantics
        d["route"] = ROUTE_DISPLAY[mode][d["route"]]
        d["status"] = STATUS_DISPLAY[mode][d["status"]]
        d["supplier"] = SUPPLIER_DISPLAY[mode][d["supplier"]]
        return d
