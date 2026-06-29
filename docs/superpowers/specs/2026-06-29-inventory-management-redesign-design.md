# Inventory-Management Redesign — Design Spec

**Date:** 2026-06-29
**Status:** approved design, pending implementation plan
**Supersedes the framing of:** the masked-distress supplier benchmark (now a sub-challenge)

## 1. Problem statement

You run **weekly replenishment** for an electronics brand that imports its hero
gadget (wireless earbuds) by sea from Asia. Each week you observe your **stock
position**, a **noisy read of recent sales + a forward demand forecast**, your
suppliers' scorecards, and the shipping lane's status — then decide **how much to
order, from whom, and by which route**.

- Demand is **uncertain** and shifts: quiet → launch/holiday surge → post-peak fade.
- Lead times are **uncertain**: the Red Sea lane can break and force a slower Cape reroute.
- The cheap incumbent supplier can **silently degrade** while its scorecard still reads healthy.
- Holding stock costs **$1/unit/week**; a stockout costs **$20/unit** (lost sale).

**Goal:** minimize total cost over the 26-week horizon — equivalently, hold *just
enough* buffer to keep service near the **~95%** the cost ratio implies
(`stockout / (stockout + holding) = 20/21 = 0.952`). The skill measured is sizing
the buffer under joint demand- and lead-time uncertainty, while sourcing and
routing around a hidden supplier failure and a lane disruption.

### Why now
Today the quantity decision is trivial: demand is a flat ~20/week, orders are a
coarse `{0,20,40}` menu, so a competent agent just runs a flat ladder and bumps
during trouble (see `runs/seed64`). All genuine difficulty lives in sourcing and
routing; the *inventory* decision — the heart of classical inventory management —
carries no weight. The demand machinery to fix this already exists
(`modules/demand/`) but is benched in the scored 2-factor world.

## 2. Scope

**In (v1):**
- Demand uncertainty in the **scored** task.
- Free order quantity (right-sized safety stock).
- Inventory-position readout + fill-rate metric.
- A real base-stock baseline as the bar to beat.
- Prompt reframed around buffer sizing (anti-buffer steer removed).
- Delete the legacy oracle; fix the `"spot"` magic-string.

**Out (deferred, named):**
- Multi-SKU / assembly (a substrate rewrite — `Books.inventory`→per-SKU map,
  per-SKU `Shipment`, a `resolve_week` SKU loop). The `"spot"` fix keeps the door open.
- Freight / port / quality in the *scored* task (built, available as later layers).
- Backorders (we keep lost-sales).
- Priming / scenario-bank, rich-world oracle.

## 3. Locked decisions

1. **Delete the legacy `CausalOracle`** (it's disruption-only; gates `/benchmark`
   behind a 122s solve; forces `resolve_rel` dual-maintenance; ~dozen tests pin it).
2. **Scored core = a NEW 3-factor registry** `CORE = (disruption, supplier, demand)`
   — not RICH. RICH (6-factor) stays the stretch.
3. **Fix the `"spot"` magic-string** in `logistics.py` + `engine.py` (real bug +
   multi-SKU blocker) — drive short-ship/discount off each supplier's profile.
4. **Lost-sales** (no backorder ledger) — already gives a clean fill-rate metric
   and a real buffer tradeoff.
5. **Free order quantity** with a cap (`cfg.order_max`).

## 4. Design, by component

Each unit below is independently understandable and testable.

### 4.1 Registry — the 3-factor core
- Add `CORE = (DISRUPTION, SUPPLIER, DEMAND)` to `registry.py`.
- The agent harness (`AgentRun`, `play_agent`, `/agent`) scores on `CORE`.
- The demand kernel is already factor-independent (reads only `DemandState`), so
  this is a registry/config change, not new physics.
- RNG note: adding demand to the scored tape changes trajectories vs the old
  2-factor world — expected (new task), not a regression. REGISTRY-order = rng-order
  invariant still holds.

### 4.2 Order quantity — free
- `config.py`: replace `order_quantities=(0,20,40)` with `order_max: int` (a cap,
  e.g. a few weeks of mean demand — generous enough not to bind a sane base-stock).
- `engine.py`: validate `0 <= qty <= cfg.order_max` (drop the menu membership check).
- `api/app.py`: `ActionRequest.qty: Literal[0,20,40]` → `conint(ge=0, le=order_max)`.
- Prompt + `place_order` tool docstring: describe a free non-negative integer.

### 4.3 Books / physical state
- Add **`inventory_position`** to the obs = `on_hand + on_order − backorders`
  (backorders ≡ 0 under lost-sales, so = `on_hand + Σ pipeline.qty`). Also surface
  `on_order`. This is the base-stock decision variable the agent currently sums by hand.
- Keep **lost-sales** (inventory floored at 0, stockout charged $20/unit). No ledger.
- Demand POS + forward forecast (`pos_units`, `demand_forecast`) come from the
  demand emission — present automatically once demand is in `CORE`.

### 4.4 De-hardcode the supplier `"spot"` magic-string
- `substrate/logistics.py`: the short-ship fraction and unit-economics branch
  keyed on `supplier == "spot"` (lines ~37, 46) → drive off the chosen supplier's
  **profile** (`SUPPLIERS[sid]["drifts"]` for fulfillment; the profile's unit
  field for pricing). Generic across any drifting/cheap supplier.
- `engine.py`: `realized_fill` (lines ~268-269) and `self.suppliers["spot"]` →
  use the chosen supplier id, gated on its `drifts` profile, not the literal.
- Result: a second drifting supplier (and later, per-SKU sourcing) works without error.

### 4.5 Metric + baseline
- Report **total cost AND fill rate** (`served / demanded`) for every run.
- Fix `report_oracle.base_stock_cost`: order **up to S** with a *free* quantity (no
  `{0,20,40}` clamp), `S` derived from demand mean + variability over the lead time
  at the implied ~95% service (critical ratio), not a hardcoded 80.
- `/benchmark`: **decouple from the deleted oracle**. Return base-stock +
  fixed-policy costs + fill rate as the reference scores; drop the `causal` /
  `luck_premium` (clairvoyant−causal) payload.

### 4.6 Prompt
- **Remove** the anti-buffer steer (`prompt.py` ~99-101, ~161-162).
- **Add** demand-uncertainty framing: state the mean + variability, the
  holding-vs-stockout tradeoff, the implied ~95% service, and "size safety stock to
  cover demand over the lead time."
- **Gate** the FREIGHT / PORT / QUALITY sections to worlds where those modules are
  registered (CORE has demand but not those), so the prompt never describes channels
  the scored world doesn't emit.
- Keep `build_system_prompt`'s masked-supplier overlay (`sup_mask_otif`) as the
  sub-challenge.
- **Fix** the `place_order` default `supplier="qualified"` bug: default to the
  world's **current incumbent** (the supplier it holds a live contract for / started
  on), not a hardcoded `"qualified"` — so an omitted supplier never silently raises.

### 4.7 Delete the legacy oracle
- Remove `src/world/oracle/` (`causal.py`, `clairvoyant.py`, `__init__.py`, `README.md`).
- Remove the `resolve_rel` mirror in `causal.py` and the **mirror obligation**
  (`resolve_week` is now free to change without a twin).
- Remove oracle imports + `/benchmark` oracle gating in `api/app.py`
  (`CausalOracle`, `causal_play`, `oracle_plan`, `_solve_oracle`).
- Keep `report_oracle.py`'s `base_stock_cost` + `fixed_policy_cost` (the baselines).

### 4.8 Known minor cleanups (low priority, from preplan)
- `modules/demand/emission.py`: `demand_units()` is dead code (`effect()` does the
  same; nothing calls it) — remove.
- `agent/factory.py`: docstring says "three world tools"; `make_tools` returns 2–4 — fix.
- `agent/tools.py`: `lock_freight` gating comment "(and the oracle never sees it)" is
  stale once the oracle is gone — drop it.
- The 5 human-facing READMEs (root, `backend/`, `src/world/`, `oracle/`, `modules/`)
  are stale (oracle pin, `{0,20,40}`, flat demand, "2-factor default") — rewrite once
  the code actually changes, to avoid editing twice.

## 5. Error handling / trust boundaries
- `qty` validated `0..order_max` at both the API (Pydantic) and the engine (raise) —
  keep the engine guard (defense in depth).
- Unknown supplier/route for `qty>0` still 422/raise (existing behavior, correct).
- Extend the **hidden-leak guard**: `HIDDEN_KEYS` must include the demand factor's
  hidden fields now that demand is in the scored obs (and note freight/port/quality
  for when they enter).

## 6. Testing
**Add:**
- `CORE` registry = `(disruption, supplier, demand)`; demand active in the scored world.
- Free qty: engine accepts arbitrary `0..order_max`, rejects negative / over-cap.
- `inventory_position` correctness (on_hand + on_order, lost-sales).
- Scored demand is **stochastic** (not constant) — a noisy draw, filtered.
- `base_stock_cost` orders up to S with free qty and **beats the flat ladder** on
  cost under noisy demand (the toy result).
- Fill-rate metric computed correctly.
- Magic-string fix: a **second** drifting supplier short-ships per its profile (no `"spot"` assumption).

**Remove (legacy oracle / frozen-world pins):**
- `test_causal_oracle_value_pinned`, `test_causal_cost_pinned`,
  `test_causal_oracle_within_bounds`, the DP-structural cluster
  (`test_oracle_dp_matches_engine_replay`, `test_transition_dist_matches_sampler`,
  `test_resolve_rel_mirrors_resolve_week`, `test_oracle_arrivals_match_engine`,
  `test_oracle_uses_quantity_lever`).
- `test_registry_covers_exactly_the_two_factors`, `test_demand_only_in_rich_registry`,
  `test_default_world_demand_inert`, the `qty=30 raises` / `qty∈{0,20,40}` menu tests.

**Verification:** `uv run pytest test_world.py -q` green; a `play_agent` smoke run on
a demand-stress seed shows the agent sizing free-quantity orders and a fill-rate line.

## 7. Risks / calibration
- **Discrimination** (the open worry, per `task-discriminates-low-end-only`): the
  task must *separate* models, not bunch them at the base-stock floor. The base-stock
  baseline is the bar; demand σ is the difficulty knob — **leave it a tunable config
  value** and validate discrimination on a seed grid before adding layers.
- **Demand calibration:** mean + variance set how hard sizing is; expose both in config.
- **Multi-SKU** stays deferred but unblocked (factored registry intact + `"spot"` fixed).

## 8. Acceptance criteria
1. Scored 3-factor `CORE` world with **stochastic demand**; agent issues free-qty orders.
2. `inventory_position` + **fill rate** surfaced; base-stock baseline (free, service-level)
   wired to `/benchmark`, **decoupled from any oracle**.
3. Legacy oracle + its pinned/structural tests **gone**; suite green.
4. Prompt no longer steers against buffers; states the service target.
5. A **second drifting supplier** works (the `"spot"` magic-string is gone).
