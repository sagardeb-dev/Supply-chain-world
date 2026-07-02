# Inventory-Management Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the *inventory* decision the scored skill — size a free-quantity order/buffer against uncertain weekly demand over an uncertain lead time, at minimum cost — by turning the demand module on in the scored world, freeing the order quantity, and deleting the legacy disruption-only oracle.

**Architecture:** The world is a factored POMDP with a module registry. Today the scored harness runs the 2-factor `REGISTRY` (disruption + supplier) with flat demand and a `{0,20,40}` order menu. This plan adds a 3-factor `CORE = (disruption, supplier, demand)` registry, frees the order quantity to a capped integer, surfaces `inventory_position` + a fill-rate metric, replaces the deleted oracle's `/benchmark` payload with order-up-to-S base-stock and fixed-policy baselines, and de-hardcodes the `"spot"` supplier magic-string so sourcing reads each supplier's profile.

**Tech Stack:** Python 3, FastAPI + Pydantic (HTTP), pytest (`uv run pytest`), `statistics.NormalDist` (newsvendor critical ratio). No new dependencies.

## Global Constraints

Copied verbatim from `config.py` — every prompt number and test must match these:

- Holding cost: **$1/unit/week** (on-hand AND in-transit). Stockout: **$20/unit** (lost sale, no backorder ledger).
- Critical ratio: `stockout/(stockout+holding) = 20/21 = 0.952` → implied service target **~95%**.
- Mean weekly demand: **20**; realized-POS noise sd `demand_noise_sd = 4.0`; forecast noise sd `demand_forecast_sd = 6.0`.
- Suez lead `suez_total_weeks = 3`; Cape lead `cape_total_weeks = 4`. Start inventory **80**, horizon **26** weeks.
- **Never hardcode the factor count.** The scored world is 3-factor `CORE`; the world is genuinely 6-factor (`RICH`) with a multi-SKU future. Drive behavior off the registry + the module/supplier profiles, never off a literal factor list or a literal `"spot"`.
- The legacy `CausalOracle` is **deleted**, not preserved. Do not reintroduce a pinned oracle value or a `resolve_rel` mirror.

## Scope decision (resolved)

The scored `CORE` world keeps **`sup_mask_otif = True`** — the masked-distress supplier task stays ON, now combined with the demand factor: the agent must size inventory under noisy demand AND detect/migrate off a silently-failing incumbent. `masked` does **not** gate the supplier factor (the reliability chain + scorecard are in `CORE` regardless); it gates the *deception layer* (lagging scorecard, noisy `realized_fill`/`lead_slip` channels, `buy_audit`, starting on `spot`). That layer is the task we built, so it stays on.

To keep the bar comparable, the order-up-to-S **baseline migrates to `qualified` on its first step** (signs the contract in the same step, then sources it) — the competent naive play: buy reliability, then size inventory. The agent beats it by riding cheap `spot` while it is healthy and migrating only when it turns. `/benchmark` builds its baselines with `sup_mask_otif=True` to match the scored world. (`masked=False` stays a valid config for an inventory-only variant; the `test_base_stock_beats_flat_ladder_under_demand` test uses it to isolate the pure demand effect.)

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `src/world/config.py` | `order_quantities` tuple → `order_max` int cap | 1 |
| `src/world/engine.py` | qty range-check; `inventory_position`/`on_order` in obs; fill-rate accumulation; pass the *chosen* supplier's state to `resolve_week`; `realized_fill` via `drifts`; `HIDDEN_KEYS` += demand | 1,3,4 |
| `src/world/substrate/logistics.py` | short-ship + unit-economics read the supplier **profile**, not `"spot"` | 4 |
| `src/world/registry.py` | add `CORE = (DISRUPTION, SUPPLIER, DEMAND)` | 2 |
| `src/agent/runner.py` | `AgentRun` defaults → `registry=CORE`, `masked=False` | 2 |
| `src/agent/play_agent.py` | default world → `CORE`; `--masked` opt-in | 2 |
| `src/api/app.py` | `qty` Pydantic `Literal`→`conint(ge=0)`; `/benchmark` baseline-only; drop oracle imports | 1,6 |
| `report_oracle.py` | `base_stock_cost` orders free-qty up to derived `S` on `CORE` + fill rate; `fixed_policy_cost` on `CORE`; `main()` drops oracle columns | 5,6 |
| `src/agent/tools.py` | `place_order` default supplier → incumbent; qty docstring | 1,7 |
| `src/agent/prompt.py` | remove anti-buffer steer; add ~95% service framing; gate the freight lever when absent | 7 |
| `src/world/oracle/` | **deleted** | 6 |
| `test_world.py` | add CORE/free-qty/inventory-position/fill/base-stock/non-spot tests; remove oracle-pin/2-factor/qty-menu tests | 1–7 |

**Task order is load-bearing for a green suite:** 1 → 2 → 3 → 4 → 5 → 6 → 7. The oracle (and its passing tests) survive untouched until Task 6 deletes the code and its tests together; the new `/benchmark` in Task 6 depends on the baselines from Task 5, which depend on `CORE` (Task 2), free qty (Task 1), and fill rate (Task 3).

Run the suite from `backend/`: `cd backend && uv run pytest test_world.py -q`.

---

### Task 1: Free order quantity

**Files:**
- Modify: `src/world/config.py:143`
- Modify: `src/world/engine.py:209-211`
- Modify: `src/api/app.py:92-96`
- Modify: `src/agent/tools.py:67-69` (docstring only)
- Test: `test_world.py` — `test_step_validation` (~line 265), `test_world.py:465`, add `test_free_quantity_accepts_and_bounds`

**Interfaces:**
- Produces: `WorldConfig.order_max: int` (replaces `order_quantities`). Engine accepts any `0 <= qty <= order_max`.

- [ ] **Step 1: Write the failing test**

Add to `test_world.py` (near `test_step_validation`):

```python
def test_free_quantity_accepts_and_bounds():
    """Order qty is a free non-negative integer capped at order_max -- the
    {0,20,40} menu is gone; off-grid quantities are legal, out-of-range raise."""
    world = World()
    world.reset(1)
    world.step({"qty": 30, "route": "suez", "supplier": "qualified"})  # off-grid: legal now
    assert world.books.pipeline[-1].qty == 30
    with pytest.raises(ValueError):
        world.step({"qty": -5, "route": "suez", "supplier": "qualified"})
    with pytest.raises(ValueError):
        world.step({"qty": world.cfg.order_max + 1, "route": "suez",
                    "supplier": "qualified"})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest test_world.py::test_free_quantity_accepts_and_bounds -q`
Expected: FAIL — `qty=30` raises "qty must be one of (0, 20, 40)" (and `order_max` does not exist yet).

- [ ] **Step 3: Replace the menu with a cap**

`config.py:143` — replace the line:

```python
    order_quantities: tuple = (0, 20, 40)  # no order / one ship / two ships
```

with:

```python
    order_max: int = 100  # free order-qty cap; ~5 weeks of mean demand, generous
                          # enough not to bind a sane base-stock. Calibration knob.
```

`engine.py:209-211` — replace:

```python
        qty = action["qty"]
        if qty not in self.cfg.order_quantities:
            raise ValueError(f"qty must be one of {self.cfg.order_quantities}")
```

with:

```python
        qty = action["qty"]
        if not (0 <= qty <= self.cfg.order_max):
            raise ValueError(f"qty must be in 0..{self.cfg.order_max}, got {qty}")
```

- [ ] **Step 4: Fix the two existing tests that encode the menu**

`test_world.py` `test_step_validation` — replace the `qty: 30` line:

```python
    with pytest.raises(ValueError):
        world.step({"qty": 30, "route": "suez"})
```

with an out-of-range case (30 is valid now):

```python
    with pytest.raises(ValueError):
        world.step({"qty": -5, "route": "suez", "supplier": "qualified"})
```

`test_world.py:465` — replace `rng.choice(CFG.order_quantities)`:

```python
            qty = rng.choice((0, 20, 40))
```

- [ ] **Step 5: Free the API and update the tool docstring**

`app.py:92-96` — change the field:

```python
class ActionRequest(BaseModel):
    qty: int = Field(ge=0)   # free non-negative qty; engine enforces the order_max cap
    route: str | None = None  # vocabulary depends on episode semantics
    supplier: str | None = None  # qualified|spot|backup (or anon source_*)
    contract: ContractAction | None = None  # sign/switch/renew/lapse a contract
```

Add `Field` to the pydantic import at `app.py:23`:

```python
from pydantic import BaseModel, Field
```

`tools.py:67-69` — in the `place_order` docstring, replace:

```python
        Ordering: qty must be 0, 20, or 40. If qty > 0 you MUST pass route
```

with:

```python
        Ordering: qty is a whole number of units (0 means order nothing; the
        cap is order_max). If qty > 0 you MUST pass route
```

- [ ] **Step 6: Run the suite**

Run: `cd backend && uv run pytest test_world.py -q`
Expected: PASS (the new test green; `test_step_validation` and the randomized test green).

- [ ] **Step 7: Commit**

```bash
git add backend/src/world/config.py backend/src/world/engine.py backend/src/api/app.py backend/src/agent/tools.py backend/test_world.py
git commit -m "feat(world): free order quantity (order_max cap replaces the {0,20,40} menu)"
```

---

### Task 2: CORE registry — the scored 3-factor world

**Files:**
- Modify: `src/world/registry.py:121-129` (add `CORE`)
- Modify: `src/agent/runner.py:47-58` (`AgentRun` defaults)
- Modify: `src/agent/play_agent.py:42-43, 121-123, 287-288`
- Modify: `src/world/engine.py:18-20` (`HIDDEN_KEYS`)
- Test: `test_world.py` — add `test_core_registry_runs_stochastic_demand`; remove `test_registry_covers_exactly_the_two_factors`, `test_demand_only_in_rich_registry`, `test_default_world_demand_inert`

**Interfaces:**
- Consumes: `DISRUPTION, SUPPLIER, DEMAND` modules (already defined in `registry.py`).
- Produces: `registry.CORE: tuple[Module, ...]`. `AgentRun(...)` and `play_agent` default world = `CORE`; masking stays ON (`sup_mask_otif=True`, the default) — only the registry default changes.

- [ ] **Step 1: Write the failing test**

```python
def test_core_registry_runs_stochastic_demand():
    """CORE = (disruption, supplier, demand): the scored world emits a NOISY
    weekly POS that varies week to week (demand is no longer flat), and never
    leaks the hidden demand regime."""
    from src.world.registry import CORE
    assert [m.id for m in CORE] == ["disruption", "supplier", "demand"]
    w = World(WorldConfig(), registry=CORE)
    w.reset(7)
    pos = []
    while not w.done:
        obs, *_ = w.step({"qty": 0})
        assert "pos_units" in obs               # demand channel is live
        assert not (HIDDEN_KEYS & obs.keys())   # regime stays hidden
        pos.append(obs["pos_units"])
    assert len(set(pos)) > 1                     # stochastic, not the flat constant
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest test_world.py::test_core_registry_runs_stochastic_demand -q`
Expected: FAIL — `ImportError: cannot import name 'CORE'`.

- [ ] **Step 3: Add the CORE registry**

`registry.py` — after the `REGISTRY` definition (line 121), add:

```python
# SCORED world: the 3-factor inventory-management core. Demand is ON so the
# order-sizing decision carries weight; disruption + supplier keep the lead-time
# and sourcing pressure. Factors stay in REGISTRY order (rng draw order); the
# remaining RICH factors (freight, port, quality) APPEND after these.
CORE: tuple[Module, ...] = (DISRUPTION, SUPPLIER, DEMAND)
```

- [ ] **Step 4: Point the agent harness at CORE (masking stays ON)**

Keep `masked=True` everywhere — only the **registry** default changes from the 2-factor world to `CORE`.

`runner.py:53-58` — replace the world construction so `registry=None` means CORE (leave the `masked: bool = True` signature at line 47 untouched):

```python
        # registry=None -> the scored 3-factor CORE world (disruption + supplier
        # + demand, with the masked supplier task on); pass registry=RICH for the
        # full six-factor stretch. The choice lives in the pickled World, so
        # resume restores the same world.
        from src.world.registry import CORE
        self.world = World(WorldConfig(semantics=semantics, sup_mask_otif=masked),
                           registry=CORE if registry is None else registry)
```

`play_agent.py:24` — add `CORE` to the registry import:

```python
from src.world.registry import CORE, RICH
```

`play_agent.py:42-43` — change the agent-world construction (`registry=RICH if rich else None`) to default CORE:

```python
                   registry=RICH if rich else CORE)
```

`play_agent.py:121-123` — same for the no-LLM policy world; keep `sup_mask_otif=True`, only flip the registry default:

```python
    world = World(WorldConfig(semantics=semantics, sup_mask_otif=True),
                  registry=RICH if rich else CORE)
```

`play_agent.py:55` — update the banner so it reads CORE when not rich:

```python
    emit(f"{model} on seed {seed} ({'RICH 6-factor' if rich else 'CORE 3-factor'})\n")
```

- [ ] **Step 5: Extend the hidden-leak guard for demand**

`engine.py:18-20` — `HIDDEN_KEYS` already lists `"regime"` (shared key name). Add the demand factor's other internal so the guard stays exhaustive:

```python
HIDDEN_KEYS = {"event_state", "event_age", "disruption_type",
               "cape_local_congestion", "regime", "canal_blocked",
               "rel_state", "rel_age",          # supplier factor internals
               "regime_age"}                     # demand factor internal
```

- [ ] **Step 6: Remove the now-stale framing tests**

Delete these three tests from `test_world.py` (they encode "demand is benched / 2-factor is the world", now false for the scored harness):
- `test_registry_covers_exactly_the_two_factors` (~line 1280)
- `test_demand_only_in_rich_registry` (~line 1426)
- `test_default_world_demand_inert` (~line 1516)

Keep `test_same_seed_same_two_factor_trace` (`REGISTRY` is unchanged) and the demand-mechanics tests (`test_demand_band_onset_ambiguity`, `test_demand_realized_is_noisy_around_the_mean`, etc.).

- [ ] **Step 7: Run the suite**

Run: `cd backend && uv run pytest test_world.py -q`
Expected: PASS. The `AgentRun` plumbing tests (`masked=False`, no registry) now run on CORE and still pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/world/registry.py backend/src/agent/runner.py backend/src/agent/play_agent.py backend/src/world/engine.py backend/test_world.py
git commit -m "feat(world): scored CORE registry (disruption+supplier+demand), masking off by default"
```

---

### Task 3: inventory_position + fill-rate metric

**Files:**
- Modify: `src/world/engine.py` — `reset` (~line 72), `step` (~line 259), `_build_obs` (~line 285), add a `fill_rate` property
- Test: `test_world.py` — add `test_inventory_position_and_fill_rate`

**Interfaces:**
- Produces: `obs["inventory_position"] = on_hand + on_order` and `obs["on_order"]`; `World.fill_rate` (float in `[0,1]`), `World.served_total`, `World.demand_total`.

- [ ] **Step 1: Write the failing test**

```python
def test_inventory_position_and_fill_rate():
    """inventory_position = on_hand + on_order (lost-sales, no backorders); the
    run-level fill_rate = served/demanded is well-formed."""
    from src.world.registry import CORE
    w = World(WorldConfig(), registry=CORE)
    obs = w.reset(7)
    assert obs["inventory_position"] == obs["inventory"] + obs["on_order"] == 80
    while not w.done:
        obs, *_ = w.step({"qty": 20, "route": "suez", "supplier": "qualified"})
        on_order = sum(s["qty"] for s in obs["pipeline"])
        assert obs["on_order"] == on_order
        assert obs["inventory_position"] == obs["inventory"] + on_order
    assert 0.0 <= w.fill_rate <= 1.0
    assert w.demand_total > 0 and w.served_total <= w.demand_total
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest test_world.py::test_inventory_position_and_fill_rate -q`
Expected: FAIL — `KeyError: 'inventory_position'`.

- [ ] **Step 3: Initialise the fill accumulators in reset**

`engine.py` `reset` — after `self.total_cost = 0.0` (~line 73), add:

```python
        self.served_total = 0      # units served across the run (for fill rate)
        self.demand_total = 0      # units demanded across the run
```

- [ ] **Step 4: Accumulate served/demanded in step**

`engine.py` `step` — right after the `resolve_week(...)` call returns and the lock window is decremented (after line ~247, before the `briefed` cost lines), add. The week's demand is `eff["demand"]` (or the constant), and the unmet units are recoverable from the stockout cost line (no `resolve_week` signature change):

```python
        # fill rate (lost-sales): demand is eff["demand"] in a demand world,
        # else the constant; unmet units = stockout cost / unit stockout cost.
        dem = eff.get("demand", self.cfg.weekly_demand)
        shortfall = round(costs.get("stockout", 0.0) / self.cfg.stockout_cost)
        self.demand_total += dem
        self.served_total += dem - shortfall
```

- [ ] **Step 5: Surface inventory_position + on_order; add the property**

`engine.py` `_build_obs` — in the `obs = { ... }` literal (after the `"inventory"` line, ~line 287), add:

```python
            "on_order": sum(s.qty for s in self.books.pipeline),
            "inventory_position": (self.books.inventory
                                   + sum(s.qty for s in self.books.pipeline)),
```

Add the property to the `World` class (next to the other properties, after the `suppliers` setter ~line 47):

```python
    @property
    def fill_rate(self) -> float:
        """Served / demanded across the run so far (1.0 before any demand)."""
        return 1.0 if self.demand_total == 0 else self.served_total / self.demand_total
```

- [ ] **Step 6: Run the suite**

Run: `cd backend && uv run pytest test_world.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/src/world/engine.py backend/test_world.py
git commit -m "feat(world): inventory_position + on_order in obs, run-level fill_rate"
```

---

### Task 4: De-hardcode the supplier `"spot"` magic-string

**Files:**
- Modify: `src/world/substrate/logistics.py:14, 36-48`
- Modify: `src/world/engine.py:240-243, 268-269`
- Test: `test_world.py` — add `test_supplier_economics_read_profile_not_spot_literal`

**Interfaces:**
- Consumes: `SUPPLIERS[sid]["drifts"]` (bool) and `SUPPLIERS[sid]["econ"] = {"attr","sign","key"}` (already in `modules/supplier/config.py`).
- Produces: `resolve_week` short-ships when the chosen supplier's profile `drifts`, and prices via its `econ` profile (fixes the latent `backup` mispricing). Engine passes the **chosen** supplier's state.

- [ ] **Step 1: Write the failing test**

```python
def test_supplier_economics_read_profile_not_spot_literal():
    """resolve_week keys off the supplier PROFILE, not the "spot" literal:
    backup prices via its econ delta (+0.3, previously mis-billed as qualified's
    +1.0), and a drifting supplier still short-ships per its fulfilled_fraction."""
    from src.world.substrate.logistics import resolve_week
    from src.world.substrate.books import Books
    from src.world.modules.disruption import HiddenState
    from src.world.modules.supplier import SupplierState
    cfg = WorldConfig()
    # backup: non-drifting, econ delta +0.3 over the Suez base (4.0) -> 4.3/unit.
    books = Books(inventory=80)
    _arrived, costs = resolve_week(books, 20, "backup", "suez", HiddenState(),
                                   SupplierState(), week=0, cfg=cfg)
    assert costs["shipping"] == 20 * (cfg.suez_unit_cost + cfg.backup_unit_delta)
    # a drifting supplier (degraded) ships short, driven by its state, not "spot".
    books2 = Books(inventory=80)
    degraded = SupplierState(rel_state="degraded")     # fulfilled_fraction 0.0
    _a2, _c2 = resolve_week(books2, 20, "spot", "suez", HiddenState(),
                            degraded, week=0, cfg=cfg)
    assert books2.pipeline == []                        # 0 units shipped
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest test_world.py::test_supplier_economics_read_profile_not_spot_literal -q`
Expected: FAIL — backup is billed `20*(4.0+1.0)` (the `else` qualified branch), not `20*4.3`.

- [ ] **Step 3: Drive logistics off the supplier profile**

`logistics.py:14` — add `SUPPLIERS` to the supplier import:

```python
from ..modules.supplier import SUPPLIERS, SupplierState
```

`logistics.py:36-48` — replace the `if qty:` block:

```python
    if qty:
        frac = sup.fulfilled_fraction if supplier == "spot" else 1.0
        shipped = round(qty * frac)
        shortfall_units = qty - shipped
        if shipped:
            # freight regime (rich world) scales the route base rate; default 1.0
            fmult = eff.get("freight_mult", 1.0)
            base = ((cfg.suez_unit_cost if route == "suez" else cfg.cape_unit_cost)
                    * fmult)
            # unit economics (A8.1): spot undercuts the lane, qualified adds a premium
            unit = (base - cfg.spot_unit_discount if supplier == "spot"
                    else base + cfg.qualified_premium)
            books.pipeline.append(Shipment(shipped, route, week, supplier))
            shipping = shipped * unit
```

with the profile-driven version:

```python
    if qty:
        prof = SUPPLIERS[supplier]
        # a drifting supplier may leave the dock short (its noisy fulfilled
        # fraction); a non-drifting one always ships full -- read the PROFILE,
        # never the "spot" literal, so a second drifting supplier just works.
        frac = sup.fulfilled_fraction if prof["drifts"] else 1.0
        shipped = round(qty * frac)
        shortfall_units = qty - shipped
        if shipped:
            fmult = eff.get("freight_mult", 1.0)
            base = ((cfg.suez_unit_cost if route == "suez" else cfg.cape_unit_cost)
                    * fmult)
            # unit economics: base + sign*magnitude from the supplier's econ
            # profile (qualified +premium, spot -discount, backup +delta). cfg
            # stays the single source of truth for the magnitude.
            econ = prof["econ"]
            unit = base + econ["sign"] * getattr(cfg, econ["attr"])
            books.pipeline.append(Shipment(shipped, route, week, supplier))
            shipping = shipped * unit
```

- [ ] **Step 4: Engine passes the chosen supplier's state and reads its profile**

`engine.py:240-243` — replace the `resolve_week` call's `self.suppliers["spot"]` with the chosen supplier's state:

```python
        arrived, costs = resolve_week(
            self.books, qty, supplier if qty else None,
            route if qty else None, self.hidden,
            self.suppliers[supplier] if qty else None,
            self.week, self.cfg, effects=eff)
```

`engine.py:268-269` — replace the `supplier == "spot"` realized-fill gate with the profile's `drifts` flag (so realized_fill accrues for *any* drifting supplier you source):

```python
        if self.cfg.sup_mask_otif and qty and SUPPLIERS[supplier]["drifts"]:
            obs["realized_fill"] = self.suppliers[supplier].fulfilled_fraction
```

(`SUPPLIERS` is already imported in `engine.py:11`.)

- [ ] **Step 5: Run the suite**

Run: `cd backend && uv run pytest test_world.py -q`
Expected: PASS — the new test green, and the existing masked/spot tests (`test_realized_fill_present_only_on_spot_order`, `test_masked_fill_is_noisy_not_deterministic`) still green (spot still drifts; the gate is now profile-driven but `spot.drifts == True`).

- [ ] **Step 6: Commit**

```bash
git add backend/src/world/substrate/logistics.py backend/src/world/engine.py backend/test_world.py
git commit -m "fix(world): supplier short-ship + unit economics read the profile, not the spot literal"
```

---

### Task 5: Order-up-to-S base-stock baseline (free qty, service-level S, on CORE)

**Files:**
- Modify: `report_oracle.py:19-39` (`fixed_policy_cost`, `base_stock_cost`)
- Test: `test_world.py` — add `test_base_stock_beats_flat_ladder_under_demand`

**Interfaces:**
- Consumes: `registry.CORE`, `statistics.NormalDist`.
- Produces: `base_stock_cost(seed, cfg, registry=None) -> float` (orders a free quantity up to `S` derived from the newsvendor critical ratio); `fixed_policy_cost(seed, route, cfg, registry=None) -> float`. Both default to the `CORE` world. The driving `World` exposes `fill_rate` (Task 3) for callers that want it.

- [ ] **Step 1: Write the failing test**

```python
def test_base_stock_beats_flat_ladder_under_demand():
    """On the CORE world (noisy demand), the order-up-to-S base-stock policy
    (free qty, service-level S) costs less than the flat always-20 ladder --
    the whole point of making the inventory decision carry weight."""
    from report_oracle import base_stock_cost, fixed_policy_cost
    cfg = WorldConfig()
    seeds = range(1, 11)
    bstock = sum(base_stock_cost(s, cfg) for s in seeds) / 10
    flat = sum(fixed_policy_cost(s, "suez", cfg) for s in seeds) / 10
    assert bstock < flat
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest test_world.py::test_base_stock_beats_flat_ladder_under_demand -q`
Expected: FAIL — current `base_stock_cost` runs the flat 2-factor world (no demand) with a `{0,20,40}`-clamped target=80; on CORE it raises or does not beat flat.

- [ ] **Step 3: Rewrite the baselines for CORE + free-qty service-level S**

`report_oracle.py` — add imports at the top (after the existing imports, ~line 16):

```python
from statistics import NormalDist

from src.world.registry import CORE
```

Both baselines source `qualified`. Under the masked world you start on `spot`, so they must **migrate to `qualified` on the first step** (the contract sub-action resolves before the order in the same `step`, so signing + ordering happen in one call). A tiny `_qualified_action` helper folds the one-time sign in.

Replace `fixed_policy_cost` (lines 19-24):

```python
def _qualified_action(w, base: dict) -> dict:
    """Attach a one-time qualified sign if we don't already hold a live
    qualified contract (the masked world starts you on spot). The contract
    resolves before the order, so sign + source happen in one step."""
    if "qualified" not in w._contracted_suppliers():
        base = dict(base)
        base["contract"] = {"action": "sign", "supplier": "qualified",
                            "terms": None}
    return base


def fixed_policy_cost(seed: int, route: str, cfg: WorldConfig,
                      registry=None) -> float:
    w = World(cfg, registry=CORE if registry is None else registry)
    w.reset(seed)
    while not w.done:
        w.step(_qualified_action(
            w, {"qty": 20, "route": route, "supplier": "qualified"}))
    return w.total_cost
```

Replace `base_stock_cost` (lines 27-39):

```python
def _service_level_S(cfg: WorldConfig) -> int:
    """Order-up-to level from the newsvendor critical ratio. The cost structure
    (stockout vs holding) implies a service target p/(p+h); S covers mean demand
    over the lead time plus a safety buffer z*sigma*sqrt(L) for that service."""
    p, h = cfg.stockout_cost, cfg.holding_cost
    z = NormalDist().inv_cdf(p / (p + h))          # ~1.668 at 20/(20+1)
    lead = cfg.suez_total_weeks + 1                # order-to-arrival + one review
    mu = cfg.weekly_demand
    sigma = cfg.demand_noise_sd
    return round(mu * lead + z * sigma * (lead ** 0.5))


def drive_base_stock(seed: int, cfg: WorldConfig, registry=None):
    """Run the order-up-to-S base-stock policy to completion and return the
    driven World (read .total_cost and .fill_rate off it). Order-up-to-S via
    Suez/qualified with a FREE quantity -- the textbook base-stock policy a
    competent non-adaptive planner runs; S is the service-level target from the
    critical ratio, NOT a hardcoded constant. Migrates to qualified up front
    (the competent naive play vs a masked spot)."""
    w = World(cfg, registry=CORE if registry is None else registry)
    w.reset(seed)
    S = _service_level_S(cfg)
    while not w.done:
        position = w.books.inventory + sum(s.qty for s in w.books.pipeline)
        qty = max(0, min(S - position, cfg.order_max))
        base = ({"qty": qty, "route": "suez", "supplier": "qualified"}
                if qty else {"qty": 0})
        w.step(_qualified_action(w, base))
    return w


def base_stock_cost(seed: int, cfg: WorldConfig, registry=None) -> float:
    return drive_base_stock(seed, cfg, registry).total_cost
```

> Note: `_qualified_action` adds the contract whenever no live qualified contract exists. On a `qty: 0` step it still signs (contracts resolve regardless of qty). Under `masked=False` (the test's `WorldConfig()`), qualified is the evergreen incumbent from week 0, so the helper is a no-op and the comparison is pure inventory sizing. `drive_base_stock` is the single base-stock driver — `/benchmark` and `report_oracle.main()` reuse it for the fill rate (no duplicated loop).

- [ ] **Step 4: Run the suite**

Run: `cd backend && uv run pytest test_world.py::test_base_stock_beats_flat_ladder_under_demand -q`
Expected: PASS. If base-stock does not beat flat, the lead/σ in `_service_level_S` is the calibration knob (raise `lead` toward `suez_total_weeks + 2`); record the change.

- [ ] **Step 5: Commit**

```bash
git add backend/report_oracle.py backend/test_world.py
git commit -m "feat(baseline): order-up-to-S base-stock (free qty, critical-ratio S) on the CORE world"
```

---

### Task 6: Delete the legacy oracle; baseline-only /benchmark

**Files:**
- Delete: `src/world/oracle/` (`__init__.py`, `causal.py`, `clairvoyant.py`)
- Modify: `report_oracle.py:13-16, 51-105` (`main()` drops oracle columns)
- Modify: `src/api/app.py:26-27, 31, 198-241` (drop oracle, baseline-only `/benchmark`)
- Test: `test_world.py` — remove the oracle/pin/DP/mirror/benchmark-endpoint tests; add `test_benchmark_returns_baselines_no_oracle`

**Interfaces:**
- Produces: `GET /benchmark/{seed}` → `{seed, suez20, cape20, basestock, basestock_fill, naive_min}`. No `clairvoyant` / `causal` / `luck_premium`. Synchronous (no background solve thread).

- [ ] **Step 1: Remove the oracle code**

```bash
git rm -r backend/src/world/oracle
```

- [ ] **Step 2: Write the failing/guard test**

Replace the deleted `test_benchmark_endpoint` with a baseline-only check (uses FastAPI `TestClient`):

```python
def test_benchmark_returns_baselines_no_oracle():
    """/benchmark serves base-stock + fixed-policy baselines and a fill rate,
    synchronously, with no oracle fields."""
    from fastapi.testclient import TestClient
    from src.api.app import app
    with TestClient(app) as client:
        r = client.get("/benchmark/7")
        assert r.status_code == 200
        body = r.json()
        assert {"basestock", "suez20", "cape20", "naive_min",
                "basestock_fill"} <= body.keys()
        assert "causal" not in body and "luck_premium" not in body
```

- [ ] **Step 3: Remove the oracle-coupled tests**

Delete from `test_world.py` (they pin the deleted oracle / DP / mirror):
- `test_oracle_arrivals_match_engine` (~339)
- `test_oracle_dp_matches_engine_replay` (~357)
- `test_oracle_uses_quantity_lever` (~369)
- `test_transition_dist_matches_sampler` (~431)
- `test_resolve_rel_mirrors_resolve_week` (~455)
- `test_causal_oracle_within_bounds` (~478)
- `test_causal_oracle_value_pinned` (~490)
- `test_causal_cost_pinned` (~500)
- `test_benchmark_endpoint` (~540, replaced in Step 2)

Also remove the module-level `causal` pytest fixture if it is now unused (grep `def causal(` and `causal)` in `test_world.py`; delete the fixture and any remaining param if no test references it).

- [ ] **Step 4: Decouple report_oracle.main() from the oracle**

`report_oracle.py:13-16` — delete the three oracle imports:

```python
from src.world.oracle import CausalOracle, causal_play
...
from src.world.oracle import oracle_plan
```

Replace `main()` (lines 51-105) with a baseline-only sweep (drop the clairvoyant/causal columns and the self-checks; keep the baselines + fill rate):

```python
def main():
    cfg = WorldConfig(sup_mask_otif=True)   # match the scored CORE+masked world
    print(f"{'seed':>4} {'suez20':>8} {'cape20':>8} {'bstock':>8} "
          f"{'bs_fill':>8} {'naive_min':>9}")
    for seed in range(1, 21):
        suez = fixed_policy_cost(seed, "suez", cfg)
        cape = fixed_policy_cost(seed, "cape", cfg)
        w = drive_base_stock(seed, cfg)      # single base-stock driver
        bstock = w.total_cost
        print(f"{seed:>4} {suez:>8.0f} {cape:>8.0f} {bstock:>8.0f} "
              f"{w.fill_rate:>8.2f} {min(suez, cape, bstock):>9.0f}")
```

- [ ] **Step 5: Rewrite /benchmark and drop oracle wiring in app.py**

`app.py:26-27` — delete:

```python
from src.world.oracle import CausalOracle, causal_play
from src.world.oracle import oracle_plan
```

`app.py:198-241` — delete the `_bench` dict, `_solve_oracle`, and the oracle-gated `benchmark`; replace with a synchronous baseline endpoint:

```python
@app.get("/benchmark/{seed}")
def benchmark(seed: int) -> JSONResponse:
    if not (0 <= seed <= 1_000_000_000):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "seed out of range")
    cfg = WorldConfig(sup_mask_otif=True)   # match the scored CORE+masked world
    suez20 = fixed_policy_cost(seed, "suez", cfg)
    cape20 = fixed_policy_cost(seed, "cape", cfg)
    w = drive_base_stock(seed, cfg)         # single base-stock driver
    basestock = w.total_cost
    return JSONResponse(content={
        "seed": seed, "suez20": suez20, "cape20": cape20,
        "basestock": basestock, "basestock_fill": round(w.fill_rate, 3),
        "naive_min": min(suez20, cape20, basestock)})
```

`app.py:31` — update the `report_oracle` import to bring in `drive_base_stock`:

```python
from report_oracle import fixed_policy_cost, base_stock_cost, drive_base_stock
```

Remove the now-unused `import threading` at `app.py:8` if nothing else uses it (grep `threading` in `app.py` first).

- [ ] **Step 6: Run the suite**

Run: `cd backend && uv run pytest test_world.py -q`
Expected: PASS (oracle tests gone; the new benchmark test green). Also confirm no import errors: `cd backend && uv run python -c "import src.api.app"`.

- [ ] **Step 7: Commit**

```bash
git add -A backend/src/world/oracle backend/report_oracle.py backend/src/api/app.py backend/test_world.py
git commit -m "refactor: delete the legacy CausalOracle; /benchmark serves base-stock + fixed-policy baselines"
```

---

### Task 7: Prompt reframe (buffer sizing, ~95% service) + place_order default supplier

**Files:**
- Modify: `src/agent/prompt.py` — `SYSTEM_PROMPT` anti-buffer lines; `build_system_prompt` freight gating + honesty line
- Modify: `src/agent/tools.py:55-86` (`place_order` default supplier → incumbent)
- Test: `test_world.py` — add `test_prompt_reframes_buffer_and_default_supplier`

**Interfaces:**
- Consumes: `world.registry`, `world.cfg.sup_mask_otif`.
- Produces: a CORE prompt that states the ~95% service target, removes the "don't carry a buffer" steer, omits the `lock_freight(weeks)` lever signature when freight is not registered (+ an honesty note for residual rich-channel mentions), and a `place_order` that defaults an omitted supplier to the world's incumbent.

- [ ] **Step 1: Write the failing test**

```python
def test_prompt_reframes_buffer_and_default_supplier():
    """The CORE prompt sizes a buffer toward the implied service target, no
    longer steers against buffers, and does not offer the freight lever it
    lacks; an omitted supplier defaults to the incumbent instead of raising."""
    from src.world.registry import CORE
    from src.agent.prompt import build_system_prompt
    w = World(WorldConfig(), registry=CORE); w.reset(7)
    p = build_system_prompt(w)
    assert "do not carry a big buffer" not in p          # anti-buffer steer gone
    assert "95%" in p                                    # service target stated
    assert "lock_freight(weeks)" not in p                # freight lever stripped (CORE)
    # default supplier resolves to the incumbent (qualified here) -> no raise
    class _Run:
        world = w
        def record(self, *a, **k): pass
    from src.agent.tools import make_tools
    place = next(t for t in make_tools(_Run()) if t.name == "place_order")
    out = place.invoke({"rationale": "buffer up", "qty": 20, "route": "suez"})
    assert "supplier=qualified" in out
```

Note: the test checks the lever *signature* `lock_freight(weeks)` is gone (the one call-inviting form). Incidental passive mentions of the word are covered by the honesty note in Step 4 (full channel-strip is deferred — see the note there).

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest test_world.py::test_prompt_reframes_buffer_and_default_supplier -q`
Expected: FAIL — the prompt still contains "do not carry a big buffer", the `lock_freight(weeks)` lever, and no "95%"; the default supplier is the literal `"qualified"` (passes here by luck but the magic-string is wrong for masked worlds — see Step 5).

- [ ] **Step 3: Remove the anti-buffer steer, add the service target (always-on)**

`prompt.py` — in `SYSTEM_PROMPT`, replace the stockout cost line (~99-101):

```python
- stockout: 20 per unit of unmet demand in a week -- by far the heaviest cost. \
Running out is expensive; but over-ordering bleeds holding every week. Hold \
enough buffer to survive a disruption, not more.
```

with the service-target framing:

```python
- stockout: 20 per unit of unmet demand in a week -- 20x the holding cost, by \
far the heaviest cost. Because a stockout costs ~20x a unit-week of holding, \
the economics imply keeping demand satisfied about 95% of weeks: size your \
safety buffer to cover demand over the order lead time (mean demand x lead, \
plus a margin for demand swings and delays), not more.
```

Replace the quiet-weeks playbook bullet (~161-162):

```python
- In quiet weeks keep ordering lean to demand; do not carry a big buffer you \
pay holding on every week for no reason.
```

with:

```python
- Even in quiet weeks keep a safety buffer sized to demand variability over the \
lead time -- enough that a normal demand swing or a short shipping delay will \
not stock you out (stockouts cost ~20x holding). Trim it only when demand and \
the lane are genuinely calm.
```

- [ ] **Step 4: Gate the freight lever + add the absent-channel honesty line**

`prompt.py` — add `import re` as the first line of the module (the file currently has no imports).

In `build_system_prompt`, replace the early `if not world.cfg.sup_mask_otif: return SYSTEM_PROMPT` with the gating below. It strips the freight **lever bullet** when freight is absent (the one genuine hazard — a tool *signature* that invites a call to a tool `make_tools` doesn't provide), with a self-policing assert so a future prompt reword that breaks the anchor fails loudly instead of silently leaving the lever. A short DOTALL regex is used because `SYSTEM_PROMPT`'s backslash line-continuations mean the runtime string has **no newlines mid-bullet** — full-text `.replace()` with embedded `\n` would silently no-op.

```python
    present = {m.id for m in world.registry}
    base = SYSTEM_PROMPT
    if "freight" not in present:
        # lock_freight is gated out of make_tools without the freight module --
        # strip its lever bullet so the prompt never offers a tool the agent
        # can't call. Short DOTALL anchor (lever start -> "in the report."),
        # robust to the prompt's backslash line-continuations.
        stripped = re.sub(r"- lock_freight\(weeks\):.*?in the report\.\n", "",
                          base, flags=re.DOTALL)
        assert stripped != base, (
            "freight-lever anchor stopped matching SYSTEM_PROMPT")
        base = stripped
    if not {"freight", "port", "quality"} <= present:
        # honesty: a CORE/partial world doesn't emit every channel/cost below.
        base = base.replace(
            "- cost_breakdown: what last week cost you, by category.",
            "- cost_breakdown: what last week cost you, by category.\n"
            "Some channels and levers described above (freight rate-locking, "
            "PORT, QUALITY) exist only in richer worlds; if a tool isn't "
            "offered or a channel isn't in your weekly report, it does not "
            "apply this run.")
    if not world.cfg.sup_mask_otif:
        return base
    p = base
```

Then keep the rest of the masked-overlay edits, operating on `p` (= `base`). **Important:** the masked overlay's first edit currently anchors on `"- lock_freight(weeks): forward-buy"` (line ~197). When masking runs on a freight-less world (e.g. CORE) that anchor was just stripped above, so guard it — anchor the `buy_audit` insertion on `"- buy_briefing(): pay"` instead. Replace the existing hardcoded `p.replace("- lock_freight(weeks): forward-buy", ...)` block with:

```python
    audit_anchor = ("- lock_freight(weeks): forward-buy" if "freight" in present
                    else "- buy_briefing(): pay")
    p = p.replace(audit_anchor,
        f"- buy_audit(): pay {world.cfg.audit_cost:.0f} for a direct read of "
        "your spot supplier's current reliability state, before you order. "
        f"Optional.\n{audit_anchor}")
```

(Leave the other three masked replaces and the closing `assert` unchanged.)

> **ponytail / deferral:** this strips only the freight **lever signature** (the call-inviting form) plus an honesty note — the one real hazard is offering a tool the agent doesn't have, and `make_tools` already gates `lock_freight` out, so even a stray call from a residual passive mention errors gracefully rather than misleading. Full per-channel surgery (stripping every FREIGHT/PORT/QUALITY readout bullet, the LOOP mention, and the demurrage/rework cost lines) is deferred: those are passive descriptions the agent won't see values for, the honesty note covers them, and the existing prompt already ships them to the masked task today — not a regression. Revisit if eval traces show the agent chasing absent channels.

- [ ] **Step 5: Default place_order's supplier to the incumbent**

`tools.py` — add a small incumbent helper inside `make_tools` (mirrors `engine.reset`'s incumbent rule; ponytail: a 1-line mirror beats threading a new world attribute):

```python
    def _incumbent() -> str:
        # the supplier you start contracted to (engine.reset): spot in the
        # masked task, else qualified. Used when place_order omits supplier.
        return "spot" if run.world.cfg.sup_mask_otif else "qualified"
```

Change the `place_order` signature default (line ~56) from `supplier: str = "qualified"` to `supplier: str = ""`, and the body line (~80) `sup = supplier if qty else None` to:

```python
        sup = (supplier or _incumbent()) if qty else None
```

Also fix the contract default at line ~84 (`"supplier": contract_supplier or supplier`) so an omitted `supplier` there resolves too:

```python
            contract = {"action": contract_action,
                        "supplier": contract_supplier or sup or _incumbent(),
                        "terms": contract_terms or None}
```

(Move the `contract` block to AFTER `sup` is computed if it is currently above it.)

- [ ] **Step 6: Run the suite**

Run: `cd backend && uv run pytest test_world.py -q`
Expected: PASS. Also re-run the masked prompt guard: `cd backend && uv run pytest test_world.py -q -k "mask or prompt"`.

- [ ] **Step 7: Commit**

```bash
git add backend/src/agent/prompt.py backend/src/agent/tools.py backend/test_world.py
git commit -m "feat(agent): reframe prompt around buffer sizing + ~95% service; default order supplier to incumbent; gate freight lever"
```

---

### Task 8: Smoke verification + minor cleanups

**Files:**
- Modify: `src/world/modules/demand/emission.py:16-18` (remove dead `demand_units`), `modules/demand/__init__.py` (drop the export)
- Modify: `src/agent/factory.py` (docstring "three world tools" → accurate count)
- Modify: `src/agent/tools.py:103` (drop the stale "and the oracle never sees it" comment)

**Interfaces:** none (cleanups + a manual smoke run).

- [ ] **Step 1: Drop the dead demand_units helper**

`demand/emission.py` — `demand_units()` (lines 16-18) is dead (`effect()` supplies the substrate value; grep confirms nothing imports `demand_units` outside the package re-export). Remove the function. In `demand/__init__.py`, remove `demand_units` from the `from .emission import ...` line and from `__all__`.

Verify: `cd backend && grep -rn "demand_units" src/ test_world.py` returns nothing.

- [ ] **Step 2: Fix stale comments**

`agent/factory.py` — if the docstring says "three world tools", correct it to reflect that `make_tools` returns 2–4 tools depending on the world.

`tools.py:103` — drop the trailing "(and the oracle never sees it)" from the `lock_freight` gating comment (the oracle is gone).

- [ ] **Step 2b: Routed cleanups (Minor findings from the task reviews)**

These were flagged Minor during Tasks 4/6/7 and deferred here (this is the cleanup task). All are non-behavioral hygiene:

1. `src/world/substrate/logistics.py` — the `resolve_week` `sup` param now receives `None` when `qty == 0` (Task 4). Update the annotation `sup: SupplierState` → `sup: SupplierState | None`.
2. `src/world/substrate/logistics.py` (docstring ~lines 24-26) — still says "a spot order ships round(qty * fulfilled_fraction) -- a degraded spot order may leave the dock SHORT". Reword to the profile-driven framing, e.g. "a drifting supplier's order ships round(qty * fulfilled_fraction) -- a degraded one may leave the dock SHORT". (Don't say "spot".)
3. `report_oracle.py` — `replay_cost(seed, plan, cfg)` is now dead (the old oracle `main()` used it; the new one uses `drive_base_stock`). Remove the function. Verify nothing imports it: `cd backend && grep -rn "replay_cost" src/ report_oracle.py test_world.py` → nothing.
4. `test_world.py` — in `test_benchmark_returns_baselines_no_oracle`, remove the redundant local `from fastapi.testclient import TestClient` / `from src.api.app import app` (both are already module-level imports), and add `"seed"` to the key-subset assertion (`{"seed", "basestock", "suez20", "cape20", "naive_min", "basestock_fill"} <= body.keys()`).
5. `src/agent/prompt.py` — the honesty-note `.replace()` has no drift guard (unlike the freight-lever strip). Add one so a future reword of the `cost_breakdown` anchor fails loudly:
   ```python
       _before = base
       base = base.replace(
           "- cost_breakdown: what last week cost you, by category.", ...)
       assert base != _before, "cost_breakdown honesty-note anchor drifted"
   ```

- [ ] **Step 3: Full suite + import check**

Run: `cd backend && uv run pytest test_world.py -q`
Expected: PASS (all green).
Run: `cd backend && uv run python -c "import src.api.app; import report_oracle"`
Expected: no output (imports clean).

- [ ] **Step 4: Manual smoke run (records the demand-stress behavior)**

Run a no-LLM base-stock-ish policy and the report to eyeball free-qty orders + a fill-rate line:

Run: `cd backend && uv run python report_oracle.py`
Expected: a table with `bstock` < `suez20` on most seeds and a `bs_fill` column near ~0.95.

(Optional, needs a model key) Run: `cd backend && uv run python -m src.agent.play_agent --seed 7 --model openai/gpt-5.4`
Expected: the agent issues free-quantity `place_order` calls (not only 0/20/40) and the weekly report shows `inventory_position`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/world/modules/demand backend/src/agent/factory.py backend/src/agent/tools.py \
        backend/src/world/substrate/logistics.py backend/report_oracle.py \
        backend/src/agent/prompt.py backend/test_world.py
git commit -m "chore: drop dead code (demand_units, replay_cost), fix stale comments + annotations, guard honesty note"
```

---

## Self-Review

**Spec coverage** (each spec §4 component → task):
- §4.1 CORE registry → Task 2. §4.2 free qty → Task 1. §4.3 inventory_position + lost-sales → Task 3. §4.4 de-hardcode "spot" → Task 4. §4.5 metric + base-stock S + decoupled /benchmark → Tasks 5–6. §4.6 prompt → Task 7. §4.7 delete oracle → Task 6. §4.8 cleanups → Task 8. §5 HIDDEN_KEYS demand → Task 2. §6 tests → folded into each task (one meaningful test each, per the "no test bloat" instruction). §8 acceptance criteria 1–5 → Tasks 2/1, 3/5/6, 6, 7, 4 respectively.
- **Decision:** scored world runs `masked=True` (Scope decision section) — the supplier task stays on, baselines migrate to qualified. Prompt gating is the *light* version (Task 7 ponytail note) — full section-strip deferred.

**Placeholder scan:** no TBD/TODO; every code step shows the exact replacement.

**Type consistency:** `order_max: int` used identically in config/engine/api/baselines. `_service_level_S(cfg) -> int` defined in Task 5, reused by name in Task 6. `World.fill_rate` defined in Task 3, read in Tasks 5–6. `registry=CORE if registry is None else registry` pattern identical across runner/baselines.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-29-inventory-management-redesign.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
