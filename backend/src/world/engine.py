"""reset()/step() orchestrator, plus the pre-decision briefing stage.
The only module that knows the sequence: (optional briefing on the
current week) -> evolve hidden -> resolve logistics -> emit observation.
Engine internals are canonically named; anon presentation is applied
only in _build_obs (R4)."""

import random

from .config import WorldConfig
from .modules.disruption import HiddenState, analyst_briefing
from .modules.supplier import (Contract, SUPPLIER_DISPLAY, SUPPLIERS,
                               SupplierState, TERM_MENU, contract_open,
                               terms_for)
from .substrate import Books, resolve_week
from .substrate.semantics import ROUTE_DISPLAY, STATUS_DISPLAY
from .registry import REGISTRY

HIDDEN_KEYS = {"event_state", "event_age", "disruption_type",
               "cape_local_congestion", "regime", "canal_blocked",
               "rel_state", "rel_age"}  # supplier factor internals


class World:
    def __init__(self, cfg: WorldConfig | None = None, registry=None):
        self.cfg = cfg or WorldConfig()
        # a World is parameterized by (config, registry): different registries
        # are different worlds. Default = the canonical 2-factor REGISTRY.
        self.registry = REGISTRY if registry is None else registry

    # self.hidden / self.suppliers are thin aliases into module_states, so the
    # disruption/supplier-specific engine code and the trace stay untouched
    # while new singleton factors live in module_states under their own id.
    @property
    def hidden(self):
        return self.module_states["disruption"]

    @hidden.setter
    def hidden(self, value):
        self.module_states["disruption"] = value

    @property
    def suppliers(self):
        return self.module_states["supplier"]

    @suppliers.setter
    def suppliers(self, value):
        self.module_states["supplier"] = value

    def reset(self, seed: int) -> dict:
        self.rng = random.Random(seed)
        self.week = 0
        # generic per-module state: each module's init() owns its reset (a
        # singleton state, or a {id: state} roster), so the engine is
        # factor-agnostic and a new module needs no edit here.
        self.module_states = {
            m.id: (m.init(self.cfg) if m.init
                   else m.state_cls() if m.state_cls else None)
            for m in self.registry}
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

    def _new_contract(self, supplier: str, start: int, terms: str | None = None):
        """Mint a contract from a negotiation-menu selection (R5). Defaults to
        the 'strict'-length mid profile when no terms are chosen; qualified is
        always evergreen."""
        if terms is None:
            # default: the standard length at base price (no menu choice)
            end = None if supplier == "qualified" else start + self.cfg.contract_weeks
            return Contract(supplier=supplier, start_week=start, end_week=end,
                            unit_price=self.cfg.suez_unit_cost,
                            otif_floor=self.cfg.contract_otif_floor,
                            break_fee=self.cfg.contract_break_fee)
        f = terms_for(terms, supplier, start, self.cfg)
        return Contract(supplier=supplier, start_week=start, **f)

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
        # one built from the chosen menu terms (the negotiation, R5).
        alive = self._alive()
        self.books.contracts = [
            c for c in self.books.contracts
            if not (c.supplier == sup and contract_open(c, self.week, alive))]
        self.books.contracts.append(
            self._new_contract(sup, start=self.week, terms=ca.get("terms")))

    def _advance_modules(self):
        """Advance every latent factor by iterating REGISTRY -- no literal
        instance name. REGISTRY order IS the rng draw order, so the hidden
        trajectory stays a function of the seed alone (exogeneity); actions
        never consume rng. A module with drives=("",) is the singleton
        world-state (self.hidden); a roster module advances self.suppliers[sid]
        for each id its profile marks drifts=True."""
        for m in self.registry:
            if m.kernel is None:
                continue
            for sid in m.drives:
                if sid == "":  # a singleton module-state
                    self.module_states[m.id] = m.kernel(
                        self.module_states[m.id], self.rng, self.cfg)
                else:          # a drifting roster member
                    self.module_states[m.id][sid] = m.kernel(
                        self.module_states[m.id][sid], self.rng, self.cfg)

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
        self._advance_modules()
        arrived, costs = resolve_week(
            self.books, qty, supplier if qty else None,
            route if qty else None, self.hidden, self.suppliers["spot"],
            self.week, self.cfg)
        if briefed:
            costs["briefing"] = self.cfg.briefing_cost
        # Lever 3: carrying >=2 live contracts costs a weekly overhead. Counted
        # AFTER the kernel step so a contract whose supplier just died this week
        # no longer counts (it is now open).
        live = len(self._contracted_suppliers())
        if live >= 2:
            costs["dual_source"] = self.cfg.dual_source_overhead

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
        # the latent factors emit their own slices (counts+bulletin, scorecard)
        # by iterating REGISTRY -- no hand-listed observe_* call. The engine
        # only owns the logistics/contract keys below.
        obs = {
            "week": self.week,
            "inventory": self.books.inventory,
            "arrived": arrived,
            "pipeline": [self._display_shipment(s) for s in self.books.pipeline],
            "cost_breakdown": dict(costs),
            "contracts": [self._display_contract(c) for c in self.books.contracts],
            "contract_open": self._open_supplier_ids(),  # the auto-renewal prompt
            "term_menu": list(TERM_MENU),  # the negotiation options (R5)
        }
        view = {}
        for m in self.registry:
            obs.update(m.emit(self._module_state(m), self.cfg))
            view.update(m.view(self.cfg))
        # presentation manifest: each obs key's display role + label, so the
        # frontend renders generically (a new passive module needs zero new
        # JS). NOT a value channel -- the oracle's raw obs readers ignore it,
        # and the leak guard skips it (labels come through the per-semantics
        # maps, so anon never leaks a real name here either).
        leakable = obs.keys() - {"_view"}
        assert not (HIDDEN_KEYS & leakable), "hidden state leaked into observation"
        obs["_view"] = view
        return obs

    def _module_state(self, m):
        """The live state a module's emit reads: its entry in module_states
        (a singleton state, or the roster dict)."""
        return self.module_states[m.id]

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
