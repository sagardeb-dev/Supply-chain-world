"""reset()/step() orchestrator, plus the pre-decision briefing stage.
The only module that knows the sequence: (optional briefing on the
current week) -> evolve hidden -> resolve logistics -> emit observation.
Engine internals are canonically named; anon presentation is applied
only in _build_obs (R4)."""

import random

from . import products
from .config import WorldConfig
from .modules.disruption import HiddenState, analyst_briefing
from .modules.supplier import (Contract, DRIVES as SUPPLIER_DRIVES,
                               SUPPLIER_DISPLAY, SUPPLIERS,
                               SupplierState, TERM_MENU, contract_open,
                               supplier_audit, terms_for)
from .substrate import Books, FreightLock, resolve_week
from .substrate.semantics import ROUTE_DISPLAY, STATUS_DISPLAY
from .registry import REGISTRY

HIDDEN_KEYS = {"event_state", "event_age", "disruption_type",
               "cape_local_congestion", "regime", "canal_blocked",
               "rel_state", "rel_age",          # supplier factor internals
               "regime_age"}                     # demand factor internal


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

    @property
    def fill_rate(self) -> float:
        """Served / demanded across the run so far (1.0 before any demand)."""
        return 1.0 if self.demand_total == 0 else self.served_total / self.demand_total

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
        # per-component initial stock. `single` seeds its sole component from
        # cfg.initial_inventory (legacy physics preserved byte-for-byte); a real
        # assembly product (earbuds) seeds each component from its own initial.
        prod = products.structure(self.cfg.product)
        if self.cfg.product == "single":
            components = {prod.component_ids[0]: self.cfg.initial_inventory}
        else:
            components = {cid: comp.initial
                          for cid, comp in prod.components.items()}
        self.books = Books(components=components)
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
        self.served_total = 0      # units served across the run (for fill rate)
        self.demand_total = 0      # units demanded across the run
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

    def expedite_air(self, qty: int) -> dict:
        """Fly `qty` units in on the air fast-lane: they land in inventory NEXT
        week, bypassing the blocked port, at cfg.air_unit_cost/unit. A within-week
        action (does NOT advance, like lock_freight) -- a batch flown this week
        covers next week's demand. Capped at cfg.air_weekly_cap. Only meaningful
        where a destination port exists (rich worlds). The guard does NOT check
        whether the port is actually blocked (that is hidden) -- the agent bets
        from the noisy berth-wait signals; a wrong bet just overpays."""
        if self.done:
            raise RuntimeError("episode is done; call reset()")
        if qty < 1:
            raise ValueError("qty must be >= 1")
        if "port_blocked" not in self._effects():
            raise ValueError("no port to expedite around in this world")
        flown = min(qty, self.cfg.air_weekly_cap)
        self.books.air_inbound = flown
        return {"qty": flown, "unit_cost": self.cfg.air_unit_cost}

    def inspect_batch(self) -> dict:
        """Run an incoming inspection on THIS week's arriving batch: sort and rework
        its defects so most are recovered before they hit the books, at a flat
        cfg.inspect_fee. A within-week action (does NOT advance, like expedite_air).
        Only meaningful where a quality process exists (rich worlds). Does NOT check
        whether quality is actually drifting (that is hidden) -- the agent bets from
        the noisy aql_result; a wrong bet just wastes the fee."""
        if self.done:
            raise RuntimeError("episode is done; call reset()")
        if "defect_fraction" not in self._effects():
            raise ValueError("no incoming quality to inspect in this world")
        self.books.inspected = True
        return {"fee": self.cfg.inspect_fee, "catch_rate": self.cfg.inspect_catch_rate}

    def stage_order(self, component: str, qty: int, supplier: str) -> dict:
        """Stage one component order line for THIS week's dispatch (assembly
        world). A within-week action (does NOT advance, like inspect_batch): the
        staged lines all ship together when place_order/step advances, on the
        step's shared route. Validates the component, the qty bound, and that the
        supplier is known. The CONTRACT mask is deliberately NOT checked here:
        step applies the week's contract sub-action before validating lines, so
        you can stage from a supplier and sign it in the same week's place_order
        (the legacy sign+source-in-one-step affordance). An unsigned staged
        supplier fails step's validation, which preserves the staged lines."""
        if self.done:
            raise RuntimeError("episode is done; call reset()")
        prod = products.structure(self.cfg.product)
        if component not in prod.component_ids:
            raise ValueError(f"unknown component {component!r}; "
                             f"choose from {list(prod.component_ids)}")
        if not (0 <= qty <= self.cfg.order_max):
            raise ValueError(f"qty must be in 0..{self.cfg.order_max}, got {qty}")
        if supplier not in self.suppliers:
            raise ValueError(f"unknown supplier {supplier!r}")
        self.books.staged_orders.append(
            {"component": component, "qty": qty, "supplier": supplier})
        return {"component": component, "qty": qty, "supplier": supplier,
                "staged": len(self.books.staged_orders)}

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
            # drives may be a static tuple or a callable (cfg)->tuple (the demand
            # roster's ids depend on the product). Resolving it here keeps the
            # rng draw order = registry order (exogeneity) for any product.
            drives = m.drives(self.cfg) if callable(m.drives) else m.drives
            for sid in drives:
                if sid == "":  # a singleton module-state
                    self.module_states[m.id] = m.kernel(
                        self.module_states[m.id], self.rng, self.cfg)
                else:          # a drifting roster member
                    self.module_states[m.id][sid] = m.kernel(
                        self.module_states[m.id][sid], self.rng, self.cfg)

    def step(self, action: dict):
        """action carries this week's order lines and advances one week. Two
        paths, both valid:
          - LEGACY (single-component): {"qty", "route", "supplier"} -- supplier
            AND route required iff qty > 0 (no fallback). Mapped to one order
            line for the sole component (back-compat with report_oracle / the API
            / every scalar test).
          - STAGED (assembly): component lines placed via stage_order this week
            (consumed from books.staged_orders), dispatched together on the
            shared action["route"]; action["qty"] is then unused.
        Canonical names; the API layer translates anon vocabularies (R4)."""
        if self.done:
            raise RuntimeError("episode is done; call reset()")
        # contract sub-action (sign/switch/renew/lapse) resolves first, so a
        # freshly-signed supplier is immediately sourceable this week.
        if action.get("contract"):
            self._apply_contract_action(action["contract"])

        prod = products.structure(self.cfg.product)
        # this week's order lines: the staged component orders, else -- back-compat
        # -- one legacy line for the sole component synthesized from a bare
        # {qty, supplier}. Staged orders are cleared only AFTER validation passes:
        # a failed step (bad route, missing contract) must leave them staged so
        # the agent's corrected retry still dispatches them.
        staged = self.books.staged_orders
        qty = action.get("qty", 0)
        route = action.get("route")
        supplier = action.get("supplier")
        if staged and qty:
            raise ValueError(
                "component orders are staged; pass qty=0 (a bare qty would be "
                "silently ignored)")
        if staged:
            orders = staged
        elif qty:
            orders = [{"component": prod.component_ids[0],
                       "qty": qty, "supplier": supplier}]
        else:
            orders = []
        # validate every line (known component, qty bound, known + contracted
        # supplier). No fallback: a bad line raises, exactly like the old path.
        for line in orders:
            q = line["qty"]
            if not (0 <= q <= self.cfg.order_max):
                raise ValueError(f"qty must be in 0..{self.cfg.order_max}, got {q}")
            if line["component"] not in prod.component_ids:
                raise ValueError(f"unknown component {line['component']!r}")
            if q and line["supplier"] not in self.suppliers:
                raise ValueError(
                    f"qty {q} needs a known supplier, got {line['supplier']!r}")
            # per-contract mask: you may only source from a supplier you hold a
            # live contract with (no fallback).
            if q and line["supplier"] not in self._contracted_suppliers():
                raise ValueError(
                    f"no live contract with {line['supplier']!r}; sign one first "
                    f"(contracted: {sorted(self._contracted_suppliers())})")
        # a shipping line needs the week's shared route.
        if any(l["qty"] for l in orders) and route not in ("suez", "cape"):
            raise ValueError(f"a shipping order needs route suez or cape, "
                             f"got {route!r}")
        # validation passed: NOW consume the staged lines (like air_inbound).
        self.books.staged_orders = []

        briefed = self._briefing is not None
        self._briefing = None
        audited = self._audit is not None
        self._audit = None

        self.week += 1
        self._advance_modules()
        # air-expedite (port lever): units flown in at the last decision land NOW,
        # bypassing the blocked port -- added BEFORE resolve_week serves demand so
        # they cover this week's shortfall. Billed below with the other levers.
        # Single-component RICH worlds only (Phase 1): stocks into the sole component.
        air = self.books.air_inbound
        self.books.air_inbound = 0
        if air:
            # Phase-1 assumption, loud on purpose: flying in "units" only means
            # something when there is exactly one component to fly.
            assert len(prod.component_ids) == 1, \
                "expedite_air assumes a single-component product (Phase 1)"
            self.books.components[prod.component_ids[0]] += air
        # a live freight lock OVERRIDES this week's realized rate (you pay the
        # locked rate, up or down), then its window decrements -- per week, even
        # if you do not ship (an unused lock still burns).
        eff = self._effects()
        lock = self.books.freight_lock
        if lock:
            eff["freight_mult"] = lock.rate
        # incoming-inspection lever (quality): sorting/rework recovers a fraction of
        # a bad batch's defects before they stock -- scale THIS week's defect
        # fraction, mirroring the freight-lock override above. logistics.py untouched.
        inspected = self.books.inspected
        self.books.inspected = False
        if inspected and "defect_fraction" in eff:
            eff["defect_fraction"] *= (1.0 - self.cfg.inspect_catch_rate)
        arrived, served, shortfall, costs = resolve_week(
            self.books, orders, route, self.hidden, self.suppliers,
            self.week, self.cfg, effects=eff)
        if lock:
            lock.weeks_left -= 1
            if lock.weeks_left <= 0:
                self.books.freight_lock = None
        # fill rate (lost-sales): the explicit per-finished-good served/shortfall
        # returns (demand = served + shortfall per model). No back-derivation.
        self.served_total += sum(served.values())
        self.demand_total += sum(served.values()) + sum(shortfall.values())
        if briefed:
            costs["briefing"] = self.cfg.briefing_cost
        if audited:
            costs["audit"] = self.cfg.audit_cost
        if air:
            costs["air"] = self.cfg.air_unit_cost * air
        if inspected:
            costs["inspect"] = self.cfg.inspect_fee
        # Lever 3: carrying >=2 live contracts costs a weekly overhead. Counted
        # AFTER the kernel step so a contract whose supplier just died this week
        # no longer counts (it is now open).
        live = len(self._contracted_suppliers())
        if live >= 2:
            costs["dual_source"] = self.cfg.dual_source_overhead

        cost = float(sum(costs.values()))
        self.total_cost += cost
        self.done = self.week >= self.cfg.horizon_weeks

        obs = self._build_obs(arrived=arrived, costs=costs, served=served)
        # masked task: the realized fill on THIS week's spot order -- a real,
        # honest books signal (you ordered, this much actually shipped). Present
        # only when you sourced the drifting supplier on the legacy single-line
        # path, so it accrues as you buy from it (history-forced). Observed fact.
        if (self.cfg.sup_mask_otif and qty and supplier
                and supplier in SUPPLIER_DRIVES(self.cfg)):
            obs["realized_fill"] = self.suppliers[supplier].fulfilled_fraction
        info = {"hidden": self.hidden.to_dict()}  # for replay/oracle, never the agent
        self.trace.append({"week": self.week, "hidden": info["hidden"],
                           "hidden_states": self._hidden_full(),
                           "action": {"qty": qty, "route": route if (qty or staged) else None,
                                      "supplier": supplier if qty else None,
                                      "orders": staged or None,
                                      "contract": action.get("contract"),
                                      "briefing": briefed, "audited": audited,
                                      "freight_locked": bool(lock),
                                      "expedited": air},
                           "obs": obs, "cost": cost})
        return obs, cost, self.done, info

    def _build_obs(self, arrived, costs: dict, served=None) -> dict:
        # the latent factors emit their own slices (counts+bulletin, scorecard)
        # by iterating REGISTRY -- no hand-listed observe_* call. The engine
        # only owns the logistics/contract keys below.
        prod = products.structure(self.cfg.product)
        comps = self.books.components
        pipe = self.books.pipeline

        def _on_order(cid):
            return sum(s.qty for s in pipe if s.component == cid)

        on_hand = sum(comps.values())
        on_order = sum(s.qty for s in pipe)
        obs = {
            "week": self.week,
            # back-compat scalar keys: for a single-component product these equal
            # the legacy values byte-for-byte (inventory = sum of components).
            "inventory": on_hand,
            "on_order": on_order,
            "inventory_position": on_hand + on_order,
            # `arrived` from resolve_week is a per-component dict; the scalar total
            # stays the observed key (legacy readers), the per-component detail
            # lives in `components` below.
            "arrived": sum(arrived.values()) if isinstance(arrived, dict) else arrived,
            # per-component bins (assembly world): on-hand, in-flight, position,
            # and this week's usable arrivals (WHICH part landed, not just how many).
            "components": {cid: {"on_hand": comps[cid], "on_order": _on_order(cid),
                                 "inventory_position": comps[cid] + _on_order(cid),
                                 "arrived": (arrived.get(cid, 0)
                                             if isinstance(arrived, dict) else 0)}
                           for cid in prod.component_ids},
            # per-finished-good units built and served this week (assemble-to-order).
            "served": dict(served) if served is not None
                      else {fg: 0 for fg in prod.finished_goods},
            "pipeline": [self._display_shipment(s) for s in pipe],
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
