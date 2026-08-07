"""Tier 2 — voyage + assembly resolution. Dispatch this week's order lines
(one per component), move every in-flight ship one week, land arrivals into
their component bins, ASSEMBLE finished goods from the bill of materials, serve
per-finished-good demand, total the cost. Deterministic given the weekly hidden
states.

The kappa cost-coupling (a supplier shortfall during a brewing disruption) is
NOT computed here -- it is the one tier-3 term, in couplings.crisis_backorder.
This file only calls it, keeping the two-factor read in its one auditable home.

Assemble-to-order: components are the only buffer. Each week we build each
finished good up to `min` over its BOM of (allocated component // bom qty),
bounded by that model's demand; the build serves demand directly and is not
stored (no finished-goods inventory).
"""

from ..config import WorldConfig
from ..couplings import crisis_backorder
from ..modules.disruption import HiddenState
from ..modules.supplier import DRIVES, SUPPLIERS
from ..products import structure
from .books import Books, Shipment, _advance


def _largest_remainder(total: int, weights: dict) -> dict:
    """Split `total` integer units across the keys of `weights` in proportion to
    the weights, using the largest-remainder method; ties break by insertion
    order. Used to allocate a shared component across the finished goods that
    consume it, in proportion to their demand.
    ponytail: this proportional-allocation rule is a calibration knob -- the
    tuning workstream may swap it (e.g. priority to the pricier model)."""
    wsum = sum(weights.values())
    if wsum <= 0 or total <= 0:
        return {k: 0 for k in weights}
    exact = {k: total * w / wsum for k, w in weights.items()}
    floor = {k: int(v) for k, v in exact.items()}
    remainder = total - sum(floor.values())
    keys = list(weights)
    order = sorted(keys, key=lambda k: (-(exact[k] - floor[k]), keys.index(k)))
    for k in order[:remainder]:
        floor[k] += 1
    return floor


def _assemble(books: Books, prod, demand: dict):
    """Assemble-to-order. Allocate each component across the finished goods that
    use it (demand-proportional, largest-remainder), then build each finished
    good up to min over its BOM of alloc // bom_qty, bounded by its demand.
    Consume only the components actually used (unused allocation carries).
    Returns (build, served, shortfall) keyed by finished good."""
    alloc = {fg: {} for fg in prod.finished_goods}
    for cid in prod.component_ids:
        users = [fg for fg in prod.finished_goods if cid in prod.bom[fg]]
        split = _largest_remainder(books.components[cid],
                                   {fg: demand[fg] for fg in users})
        for fg in users:
            alloc[fg][cid] = split[fg]
    build = {}
    for fg in prod.finished_goods:
        cap = min(alloc[fg][cid] // prod.bom[fg][cid] for cid in prod.bom[fg])
        build[fg] = min(demand[fg], cap)
    for cid in prod.component_ids:
        used = sum(build[fg] * prod.bom[fg][cid]
                   for fg in prod.finished_goods if cid in prod.bom[fg])
        books.components[cid] -= used
    served = dict(build)
    shortfall = {fg: demand[fg] - build[fg] for fg in prod.finished_goods}
    return build, served, shortfall


def resolve_week(books: Books, orders, route: str | None, h: HiddenState,
                 suppliers: dict, week: int, cfg: WorldConfig,
                 effects: dict | None = None):
    """Dispatch this week's component order lines, move every in-flight ship one
    week, land arrivals per component, assemble finished goods, serve per-model
    demand. Returns (arrived, served, shortfall, costs):
      arrived  -- {component: usable units that stocked this week}
      served   -- {finished_good: units built and served}
      shortfall-- {finished_good: demand - served}  (EXPLICIT, not back-derived)
      costs    -- the weekly cost breakdown

    `orders` is a list of {"component","qty","supplier"} lines (empty if none);
    `route` is the shared lane for this week's dispatch (or None); `suppliers` is
    the full {sid: SupplierState} roster (each line names its supplier).

    The supplier stage (factor 2) resolves at DISPATCH: a drifting supplier's
    line ships round(qty * fulfilled_fraction) -- a degraded one may leave the
    dock SHORT. A non-drifting supplier ships full. Once at sea the voyage stage
    is untouched (it honours each shipment's component production lead)."""
    eff = effects or {}
    prod = structure(cfg.product)
    shipping = 0.0
    shortfall_units = 0  # supplier short-ship across all lines (feeds the coupling)
    for line in orders or []:
        qty = line["qty"]
        if qty <= 0:
            continue
        comp, sid = line["component"], line["supplier"]
        prof = SUPPLIERS[sid]
        # a supplier that DRIFTS IN THIS WORLD may leave the dock short (its
        # noisy fulfilled fraction); a frozen one always ships full. WHO drifts
        # is DRIVES(cfg) -- spot always, qualified/backup too under
        # sup_all_drift -- never a "spot" literal, so all-drift just works.
        frac = (suppliers[sid].fulfilled_fraction
                if sid in DRIVES(cfg) else 1.0)
        shipped = round(qty * frac)
        shortfall_units += qty - shipped
        if shipped:
            fmult = eff.get("freight_mult", 1.0)
            # contract terms scale the route base (D17-audit fix 2026-08-06:
            # the negotiated unit_price was quoted off the Suez base and
            # DISPLAYED but never billed -- the "price-lock" was decoration).
            # One contract per supplier post-replace-fix; no contract -> 1.0
            # (unreachable for shipped lines: sourcing requires a contract).
            tmult = next((c.unit_price / cfg.suez_unit_cost
                          for c in books.contracts if c.supplier == sid), 1.0)
            base = ((cfg.suez_unit_cost if route == "suez" else cfg.cape_unit_cost)
                    * tmult * fmult)
            # unit economics: route base + supplier econ sign*magnitude + the
            # component's own cost delta (the pricey ANC chip). cfg / products
            # stay the single source of truth for every magnitude.
            econ = prof["econ"]
            unit = (base + econ["sign"] * getattr(cfg, econ["attr"])
                    + prod.components[comp].cost_delta)
            books.pipeline.append(Shipment(shipped, route, week, sid, component=comp))
            shipping += shipped * unit

    surcharge = 0.0
    for s in books.pipeline:
        surcharge += _advance(s, h, week, cfg)

    # destination-port stage (rich world): when the port is blocked (congestion
    # / customs hold), this week's arrivals are HELD a week and accrue demurrage.
    # The default world has no port effect -> the original arrival logic, exact.
    landing = [s for s in books.pipeline if s.arrives_week == week]
    demurrage = 0.0
    defective_total = 0
    arrived = {cid: 0 for cid in prod.component_ids}
    if eff.get("port_blocked") and landing:
        for s in landing:
            s.arrives_week = week + 1
        demurrage = eff.get("demurrage_rate", 0.0) * sum(s.qty for s in landing)
    else:
        df = eff.get("defect_fraction", 0.0)
        for s in landing:
            # quality (rich world): a defective fraction of arrivals don't stock
            # (effective shortfall) and incur rework; default world -> fraction 0.
            # DECISION (Phase 1 review): defects round PER SHIPMENT, not on the
            # summed landing as legacy did -- required for Phase 3's per-supplier
            # attribution (each batch owns its defects). RICH single-product
            # traces shift slightly in multi-landing defective weeks; accepted.
            # Phase 3: `defect_fraction` may be a per-supplier {sid: frac} map
            # (cfg.quality_per_supplier) -- each shipment already carries its
            # `.supplier`, so it's charged its OWN shipper's fraction, not a
            # global one; a plain scalar (legacy/singleton) applies to everyone.
            frac = df[s.supplier] if isinstance(df, dict) else df
            defective = round(s.qty * frac)
            usable = s.qty - defective
            books.components[s.component] += usable
            arrived[s.component] += usable
            defective_total += defective
        books.pipeline = [s for s in books.pipeline if s.arrives_week != week]
    rework = eff.get("rework_rate", 0.0) * defective_total

    # weekly per-finished-good demand from the demand module (rich/scored world),
    # else the flat constant for every finished good (default world).
    demand = eff.get("demand") or {fg: cfg.weekly_demand for fg in prod.finished_goods}
    _build, served, shortfall = _assemble(books, prod, demand)

    on_hand = sum(books.components.values())
    in_transit = sum(s.qty for s in books.pipeline)
    # The Becker JV coupling (A8.2): reads BOTH factors (disruption regime +
    # supplier shortfall) but lives in the reward, so the belief stays factored.
    # The two-factor read is sealed in couplings.py.
    couple = crisis_backorder(shortfall_units, h, cfg)
    costs = {
        "shipping": shipping,
        "surcharge": surcharge,  # diverted voyages billed at the Cape rate
        "holding": cfg.holding_cost * on_hand,
        "in_transit": cfg.holding_cost * in_transit,  # capital cost on the water
        "stockout": cfg.stockout_cost * sum(shortfall.values()),
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
    return arrived, served, shortfall, costs
