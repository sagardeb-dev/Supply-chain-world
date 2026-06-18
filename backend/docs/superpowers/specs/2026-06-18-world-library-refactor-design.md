# World Library Refactor — Design Spec

**Branch:** `feat/world-library-refactor` (off `dev` @ `d05e28b`)
**Date:** 2026-06-18
**Scope:** Sub-project 1 of 2. Goal-2 (six grounded latent modules) gets its own spec.

## Goal

Reorganize `src/world/` from a **by-function** layout (each file holds *both*
factors mixed — `state.py` has both states, `transition.py` both kernels,
`emission.py` all emissions) into **by-module sealed boxes** (each latent module
owns its state + kernel + emission + text + config in one self-contained
package). The world directory becomes usable "like a library": adding a module =
adding a folder + one registry line, not editing six shared files.

Hard constraint: **behavior is byte-identical.** The exact causal oracle and its
pinned value are preserved untouched; this is a pure relocation + import rewrite.

### Success criteria

1. `CausalOracle().value()` is unchanged vs the empirically-captured golden value
   (pinned in a test *before* any code moves).
2. Full test suite green at **92/0** (current baseline is 90/2 → fix the 1
   pre-existing failure + keep the AST sealed-box guard).
3. Adding a latent module touches: its own new folder + 1 line in `registry.py`.
   No edits to `engine.py`, `_build_obs`, the leak guard, or the frontend
   role-renderer for a passive module.
4. `claude-mds/architecture.md` + `dependency-graph.md` updated to the new layout
   (they currently describe the flat layout = stale-on-arrival risk).

### Out of scope (deferred to goal 2)

- Making the causal oracle N-factor generic (user chose **Incremental**).
- Splitting the flat `WorldConfig` dataclass into nested per-module sub-configs
  (would touch every `cfg.X` read in the oracle — deferred to the goal-2 oracle
  rework). We relocate module *data tables* now, not the scalar-knob dataclass.
- Any new module, new mechanic, or new economics.

## Background: what's already done on dev

dev is further along than the docs imply. `modules.py` already declares the
`Module` record + `REGISTRY`, `engine._build_obs` is already emit-driven and
registry-driven, and the `_view` presentation manifest already exists. The
**oracle is single-factor** (disruption only): `causal_play` always sources
`qualified`, and `resolve_rel` uses `unit = base + qualified_premium` with no
supplier marginal and no coupling term. So the supplier factor lives in the
engine but is invisible to the oracle — and that is consistent, because under a
qualified-only policy `shortfall_units == 0` so the `couple` term is always 0.

The refactor therefore is **relocation, not redesign.**

## Target structure

```
src/world/
  __init__.py
  config.py              # GLOBAL: the flat WorldConfig dataclass + global cost/geometry knobs
  registry.py            # Module record + REGISTRY = (DISRUPTION, SUPPLIER)  ← the one ordered list
  engine.py              # World.reset/step (already registry-driven); imports updated
  couplings.py           # TIER 3: crisis_backorder — the ONLY code reading two factors
  substrate/             # module-agnostic logistics substrate
    __init__.py
    books.py             # Books, Shipment, _advance (transit-week causality)
    logistics.py         # resolve_week (calls couplings.crisis_backorder)
    semantics.py         # ROUTE_DISPLAY, STATUS_DISPLAY (voyage presentation maps)
  modules/
    __init__.py
    disruption/
      __init__.py        # builds & exports MODULE (the Module record) + public names
      factor.py          # HiddenState + step_hidden  (the latent generator)
      emission.py        # observe_counts, news_bulletin, analyst_briefing, emit, view
      text.py            # BULLETINS, BRIEFINGS, COUNT_KEYS  (this module's vocabulary)
      config.py          # REGIME_COUNTS, CAPE_LOCAL_EXTRA  (this module's data tables)
    supplier/
      __init__.py        # builds & exports MODULE + public names
      factor.py          # SupplierState + step_supplier
      emission.py        # observe_scorecard, _supplier_row, emit, view
      text.py            # SUPPLIER_DISPLAY, SUPPLIER_PARSE, SUPPLIER_BAND_DISPLAY (this module's vocab)
      contracts.py       # Contract, contract_open, TERM_MENU, terms_for
      config.py          # SUPPLIERS, SUPPLIER_SCORECARD  (this module's data tables)
  oracle/
    __init__.py
    clairvoyant.py       # was oracle.py            (logic unchanged)
    causal.py            # was causal_oracle.py     (logic unchanged; imports updated)
```

### Tier discipline (preserved from the design intent)

- **Tier 1 — modules/** are sealed boxes: a module NEVER imports a sibling
  module. It imports only `config` (global) + its own `config.py`/`text.py`.
  Guarded by the existing AST `test_modules_are_sealed_boxes_no_cross_import`.
- **Tier 2 — substrate/** is module-agnostic: it knows shipments and inventory,
  not "disruption" or "supplier" by name. (It does import the module *state
  classes* for type hints today; acceptable — it reads `h.regime` /
  `sup.fulfilled_fraction` as opaque visible properties, not module internals.)
- **Tier 3 — couplings.py** is the ONLY file allowed to read two factors at
  once, and only in the reward. Extracted verbatim from the current inline
  `logistics.resolve_week` block (Becker JV term).

### `semantics.py` splits three ways

dev's single `semantics.py` carries three independent vocabularies; they move to
where they belong: disruption text (`BULLETINS`, `BRIEFINGS`, `COUNT_KEYS`) →
`modules/disruption/text.py`; supplier vocab (`SUPPLIER_DISPLAY`,
`SUPPLIER_PARSE`, `SUPPLIER_BAND_DISPLAY`) → `modules/supplier/text.py`; voyage
presentation (`ROUTE_DISPLAY`, `STATUS_DISPLAY`) → `substrate/semantics.py`. The
real↔anon ablation is preserved byte-for-byte.

### Where each module builds its record

Each `modules/<name>/__init__.py` constructs and exports `MODULE = Module(...)`.
`registry.py` does `from .modules.disruption import MODULE as DISRUPTION` etc. and
`REGISTRY = (DISRUPTION, SUPPLIER)`. The **order is load-bearing** (it is the rng
draw order → exogeneity), so it stays an explicit, commented tuple in one place.

### Config split (the "separate config per module" wish, incrementally)

- `modules/disruption/config.py`: `REGIME_COUNTS`, `CAPE_LOCAL_EXTRA`.
- `modules/supplier/config.py`: `SUPPLIERS`, `SUPPLIER_SCORECARD`.
- Global `config.py`: the flat `WorldConfig` dataclass (all scalar knobs) stays,
  so the oracle's `cfg.onset_prob`/`cfg.qualified_premium` reads are byte-
  identical. Each module's knobs are documented (comment block) in its own
  `config.py` even though the field lives on the unified dataclass — full nested
  config-dataclass split is a goal-2 change (it touches the oracle).

## Safety net (TDD / verification-first — do this FIRST)

1. **Empirically pin the golden value.** Add `test_causal_oracle_value_pinned`:
   capture `CausalOracle().value()` from the *current* code and assert equality
   to that literal. Add `test_causal_cost_pinned` for ~3 seeds. Commit this
   BEFORE moving any code. (No test pins the value today — this is the guard.)
2. **Fix the pre-existing failure** so green == safe: `report_oracle.py`
   baselines call `World.step({"qty":20,"route":route})` with no supplier →
   `ValueError`. Add `supplier="qualified"`. Gets the suite to 92/0.
3. Relocate in small commits; at each commit boundary run the **full** suite
   (~3.5 min, oracle-solve dominated) + the golden pin. During iteration, run a
   fast subset that skips the slow `benchmark_endpoint`.

## Commit ladder

1. `test(world): pin causal-oracle golden value + fix report_oracle baseline` → 92/0.
2. `refactor(world): substrate/ package (books, logistics, semantics)`.
3. `refactor(world): couplings.py — extract crisis_backorder from logistics`.
4. `refactor(world): modules/disruption/ sealed-box package`.
5. `refactor(world): modules/supplier/ sealed-box package (incl contracts)`.
6. `refactor(world): registry.py — each module owns its MODULE record`.
7. `refactor(world): oracle/ package (clairvoyant, causal); update all importers`.
8. `docs: refresh architecture.md + dependency-graph.md to the by-module layout`.

Each step keeps imports resolving and tests green before the next.

## Import-rewrite surface (the blast radius)

Files that import from `world.*` and will need import-path updates:
`engine.py`, `oracle/causal.py`, `oracle/clairvoyant.py`, `report_oracle.py`,
`src/api/app.py`, `src/agent/*`, `test_world.py`. The public *names* (`World`,
`CausalOracle`, `Contract`, `REGISTRY`, …) stay the same — only their module
paths move. A `world/__init__.py` re-export shim can absorb most external
churn (`from .engine import World`, `from .oracle.causal import CausalOracle`,
etc.), minimizing edits outside `world/`.

## Risks

- **Silent oracle corruption** (the only dangerous failure mode — wrong value,
  no crash). Mitigated by the golden pin captured *before* moving code + the
  `causal_play` per-step cross-check + full-suite green at every commit.
- **rng draw-order drift** → would change the seed-fixed trajectory. Mitigated:
  `REGISTRY` order is preserved exactly; `test_exogeneity` / determinism tests
  stay green.
- **Circular imports** from the folder split. Mitigated by the one-way edge:
  `registry` imports `modules`, modules never import `registry`; substrate never
  imports modules' emission/text.

## Forward note for goal 2 (anchor strategy)

Per user steer (2026-06-18): do not let exact-oracle tractability constrain how
rich/noisy the 6 modules can be. When exact expectimax stops scaling, bracket
the optimum instead — information-relaxation duality (Brown–Smith–Sun) for a
provable bound, DESPOT/POMCP/SARSOP for a near-optimal policy + bound, with the
clairvoyant DP as the loose bracket end. The library structure here is designed
so the oracle is a *consumer* of the registry, swappable without touching
modules.
