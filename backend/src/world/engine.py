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
                               supplier_audit, terms_for)
from .substrate import Books, FreightLock, resolve_week
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
        # pre-contracted to the incumbent (evergreen anchor): you don't start a
        # supply chain with no supplier. Masked task: the incumbent is SPOT --
        # the supplier whose silent decline the agent must detect from the books
        # and migrate off (so reading the masked signals actually has a stake).
        # Legacy: the safe qualified. Both byte-identical in shape; only the
        # supplier id differs, and the legacy path matches _new_contract exactly.
        incumbent = "spot" if self.cfg.sup_mask_otif else "qualified"
        self.books.contracts = [Contract(
            supplier=incumbent, start_week=0, end_week=None,
            unit_price=self.cfg.suez_unit_cost,
            otif_floor=self.cfg.contract_otif_floor,
            break_fee=self.cfg.contract_break_fee)]
        self.done = False
        self.total_cost = 0.0
        self.trace = []
        self._briefing = None  # paid assessment bought at this decision point
        self._audit = None     # paid supplier audit (masked task), same pattern
        obs = self._build_obs(arrived=0, costs={})
        self.trace.append({"week": 0, "hidden": self.hidden.to_dict(),
                           "hidden_states": self._hidden_full(),
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

    def request_audit(self) -> str:
        """Paid supplier audit (masked task): a sharpened read of the CURRENT
        hidden supplier reliability the lagging OTIF scorecard hides. Bought
        pre-decision like request_briefing; charged once per week (repeat calls
        return the same text without re-charging)."""
        if self.done:
            raise RuntimeError("episode is done; call reset()")
        if self._audit is None:
            self._audit = supplier_audit(self.suppliers, self.cfg)
        return self._audit

    def lock_freight(self, weeks: int) -> dict:
        """Forward-buy this week's freight rate: FIX the cost multiplier at the
        current observable rate for `weeks` weeks. A within-week action (does
        NOT advance, like request_briefing) - captured BEFORE the world steps so
        a lock placed this week prices this week's order. Only meaningful when a
        freight market exists (rich worlds)."""
        if self.done:
            raise RuntimeError("episode is done; call reset()")
        if weeks < 1:
            raise ValueError("weeks must be >= 1")
        rate = self._effects().get("freight_mult")
        if rate is None:
            raise ValueError("no freight market to lock in this world")
        self.books.freight_lock = FreightLock(rate, weeks)
        return {"rate": rate, "weeks_left": weeks}

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
        audited = self._audit is not None
        self._audit = None

        self.week += 1
        self._advance_modules()
        # a live freight lock OVERRIDES this week's realized rate (you pay the
        # locked rate, up or down), then its window decrements -- per week, even
        # if you do not ship (an unused lock still burns).
        eff = self._effects()
        lock = self.books.freight_lock
        if lock:
            eff["freight_mult"] = lock.rate
        arrived, costs = resolve_week(
            self.books, qty, supplier if qty else None,
            route if qty else None, self.hidden, self.suppliers["spot"],
            self.week, self.cfg, effects=eff)
        if lock:
            lock.weeks_left -= 1
            if lock.weeks_left <= 0:
                self.books.freight_lock = None
        if briefed:
            costs["briefing"] = self.cfg.briefing_cost
        if audited:
            costs["audit"] = self.cfg.audit_cost
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
        # masked task: the realized fill on THIS week's spot order -- a real,
        # honest books signal (you ordered, this much actually shipped). Present
        # only when you sourced the drifting supplier, so it accrues as you buy
        # from it (history-forced). Observed fact, not a hidden readout.
        if self.cfg.sup_mask_otif and qty and supplier == "spot":
            obs["realized_fill"] = self.suppliers["spot"].fulfilled_fraction
        info = {"hidden": self.hidden.to_dict()}  # for replay/oracle, never the agent
        self.trace.append({"week": self.week, "hidden": info["hidden"],
                           "hidden_states": self._hidden_full(),
                           "action": {"qty": qty, "route": route if qty else None,
                                      "supplier": supplier if qty else None,
                                      "contract": action.get("contract"),
                                      "briefing": briefed, "audited": audited,
                                      "freight_locked": bool(lock)},
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
        if self.books.freight_lock:  # the agent's own forward freight buy (observed)
            obs["freight_lock"] = {"rate": self.books.freight_lock.rate,
                                   "weeks_left": self.books.freight_lock.weeks_left}
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

    def _hidden_full(self) -> dict:
        """Every module's hidden state for the trace tape / x-ray. The
        disruption slice also stays under trace['hidden'] for the oracle's
        replay reader; this is the complete picture (supplier roster + any rich
        factors) the agent never sees but a debugger wants. ponytail: additive
        -- the existing 'hidden' key is untouched."""
        out = {}
        for m in self.registry:
            st = self.module_states[m.id]
            if st is None:
                continue
            if isinstance(st, dict):  # a roster module (supplier): {sid: state}
                out[m.id] = {sid: s.to_dict() for sid, s in st.items()}
            else:
                out[m.id] = st.to_dict()
        return out

    def _effects(self):
        """Merge every module's substrate effect (demand units, freight mult,
        ...) into one dict for resolve_week. Modules with no effect (the base
        disruption/supplier, passed explicitly as h/sup) contribute nothing, so
        the default world yields {} and resolve_week uses its constants."""
        eff = {}
        for m in self.registry:
            if m.effect:
                eff.update(m.effect(self.module_states[m.id], self.cfg))
        return eff

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
