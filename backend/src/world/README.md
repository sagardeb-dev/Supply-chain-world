# `world/` — the factored-POMDP supply-chain world

A weekly supply-chain decision problem expressed as a **factored POMDP**. The
agent orders stock (`qty ∈ {0, 20, 40}`), picks a supplier and a shipping route,
and manages supplier contracts, while several **hidden latent factors** evolve
underneath and leak only noisy or indirect signals. The world is the simulator
the agents and the oracles both run against.

A `World` is parameterized by `(config, registry)` — *a different registry is a
different world*. The default registry is the canonical two-factor world; `RICH`
is the full six-factor world.

```python
from src.world import World, WorldConfig
from src.world.registry import RICH

w = World()                     # default 2-factor world
w = World(WorldConfig(), RICH)  # 6-factor world
obs = w.reset(seed=1)
obs, cost, done, info = w.step({"qty": 20, "supplier": "qualified", "route": "suez"})
```

## Layout

| Path | Tier | What lives here |
|------|------|-----------------|
| `engine.py` | — | `World`: the `reset()/step()` orchestrator. The only file that knows the per-week *sequence*. |
| `config.py` | — | `WorldConfig`: one frozen dataclass of global scalar knobs. Per-module data tables live in each module's `config.py`. |
| `registry.py` | — | The `Module` record + the `REGISTRY` (default) and `RICH` tuples. Composing the modules. |
| `modules/` | 1 | The latent factors, each a self-contained sealed box. See `modules/README.md`. |
| `substrate/` | 2 | Module-agnostic logistics: the books and the weekly voyage resolution. See `substrate/README.md`. |
| `couplings.py` | 3 | The only code allowed to read two factors at once — and only in the reward. |
| `oracle/` | — | Anchors that sit *above* the engine and drive `World` instances. See `oracle/README.md`. |

## The three tiers

The design keeps the joint belief **factored** (a product of per-factor
marginals) by following the Becker TI-Dec-MDP result (JAIR 2004, Thm 1): keep
every factor's *transition* and *observation* independent, and let the factors
couple **only through the cost**.

- **Tier 1 — modules** (`modules/`): each latent factor owns its hidden state,
  kernel, emission, display vocabulary, and data tables. A module imports the
  global config and its own files — **never a sibling module**. That isolation
  is exactly transition + observation independence.
- **Tier 2 — substrate** (`substrate/`): the ships/inventory/demand machinery.
  Knows ships, not `"disruption"` or `"supplier"` by name; reads hidden states
  only through their public visible properties or through merged `effects`.
- **Tier 3 — couplings** (`couplings.py`): the single auditable home for any
  cost term that reads two factors. Today: `crisis_backorder` (a spot shortfall
  is punishing while a disruption is brewing). Putting every two-factor read in
  one file makes the "solve V1 and V2 separately and add them" mistake
  impossible to commit by accident.

## How a week resolves (`engine.step`)

1. Apply any contract sub-action (`sign`/`switch`/`renew`/`lapse`) first, so a
   freshly-signed supplier is sourceable the same week.
2. Validate the action (qty in the grid; route + a live-contracted supplier when
   `qty > 0`).
3. `_advance_modules()` — advance every latent factor by iterating `registry`.
4. `resolve_week(...)` — dispatch, sail, land, consume demand, total the cost.
   The merged per-module `effects` dict feeds the substrate (demand units,
   freight multiplier, port blocking, defect fraction).
5. `_build_obs(...)` — each module emits its own observation slice; the engine
   owns only the logistics/contract keys.

## Two invariants the engine guarantees

- **RNG exogeneity.** Kernels consume the rng in `registry` order; **actions
  never consume rng**. So the hidden trajectory is a function of the *seed
  alone* — which is what lets the clairvoyant oracle replay the future from one
  no-op playthrough. New factors are *appended* in `RICH`, so their draws come
  last and the disruption/supplier trajectories are unperturbed.
- **No hidden leak.** `_build_obs` asserts that no internal hidden-state key
  (`HIDDEN_KEYS`) ever appears in an observation. Each module's `emit` returns
  only the noisy/aggregate signals the agent is allowed to see.

## The golden pin

`CausalOracle().value() == 4251.9607875333395` is pinned as a test
(`test_world.py`). It is the silent-corruption guard for the default world:
any change that perturbs the two-factor dynamics or cost arithmetic moves this
number and fails the suite. The default world is kept **byte-identical** —
adding new modules to `RICH` never touches it.
