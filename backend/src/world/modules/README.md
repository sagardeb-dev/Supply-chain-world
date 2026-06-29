# `modules/` — Tier 1: the latent factors (sealed boxes)

Each subdirectory is **one latent factor**, a self-contained sealed box. A module
owns its hidden state, its transition kernel, its emission, its display
vocabulary, and its data tables. It imports **only** the global config
(`...config`) and its own files — **never a sibling module**.

That isolation *is* transition + observation independence (Becker, Def. 2): with
every factor's dynamics and signals independent, the joint belief stays a product
of per-factor marginals. The factors are allowed to interact only later, through
the cost — in `substrate/logistics.py` (via `effect`) and `couplings.py`.

`registry.py` composes these modules into `Module` records. **The modules never
import `registry`** — that one-way edge is what keeps the boxes free of a
circular import. Adding a latent factor = a new `modules/<name>/` package + one
`Module` record + one line in a registry tuple.

## Per-module file layout

Every module follows the same shape (some add an extra file for richer state):

| File | Contents |
|------|----------|
| `factor.py` | The frozen state dataclass, its visible `band`/property derivations, and the semi-Markov `step_*(state, rng, cfg) -> state` kernel. Per-week noisy draws are sampled here and stored on the state. |
| `emission.py` | `emit(state, cfg)` — the noiseless/noisy observation slice the agent sees. `effect(state, cfg)` — the substrate coupling (if any). `view(cfg)` — the frontend display manifest (role + label per obs key). |
| `config.py` | The module's own data tables (per-regime means/probabilities). |
| `__init__.py` | Re-exports the public surface + `DRIVES`. |
| `text.py` | Display strings / bulletins (disruption, supplier). |
| `contracts.py` | Contract + term-menu machinery (supplier only). |

`DRIVES` declares which roster instances the kernel advances. `("",)` means a
**singleton** world-state (e.g. `disruption`, `demand`); a roster module
(`supplier`) drives the ids whose profile sets `drifts=True`.

## The six modules

The first two are the **default** world (`REGISTRY`); all six form `RICH`. Every
factor is a **semi-Markov** hidden regime (state + age), modeled on the
disruption template, grounded in real supply-chain data.

| # | Module | Hidden regimes | What the agent sees (`emit`) | Substrate `effect` |
|---|--------|----------------|------------------------------|--------------------|
| ① | `disruption` | event HMM: calm / watch / disruption(short,long) / recovery / false_alarm | transit counts + a trade-press bulletin | — (passed explicitly as `h`); couples in the reward via `crisis_backorder` |
| ② | `supplier` | per-supplier OTIF reliability chain | a noiseless OTIF scorecard | — (passed explicitly as `sup`); a degraded spot order ships short |
| ③ | `demand` | normal / promo_spike / seasonal_lift / structural_decline | **noisy** realized POS + **noisy** forward forecast | `demand` — replaces the constant weekly demand |
| ④ | `freight` | spot-rate regime (slack…peak) | **noisy** spot index + **noisier** outlook | `freight_mult` — multiplies the route base rate |
| ⑤ | `port` | clear / building / congested / customs_hold | **noisy** berth-wait + outlook | `port_blocked` + `demurrage_rate` — holds arrivals a week, charges demurrage |
| ⑥ | `quality` | in_control / drifting / out_of_control | **noisy discrete** AQL band (accept/marginal/reject) | `defect_fraction` + `rework_rate` — defective arrivals don't stock |

## The two emission styles

- **Noiseless (legacy two-factor base).** `disruption` and `supplier` emit
  deterministic functions of the regime, so their reachable beliefs are finitely
  supported.
- **Noisy (rich modules ③–⑥).** Each new factor emits a *noisy* read plus a
  *forward channel*, with a deliberate one-week onset ambiguity (e.g. promo vs
  seasonal share the `surge` mean; congestion vs customs-hold share a band).
  `quality` is the strongest case: a noisy *discrete* AQL sample whose belief
  never fully collapses. The agent must **filter** the regime over weeks — no
  single reading identifies it. Its cost channel is matched: the realized batch
  `defect_fraction` is a noisy finite-batch draw around the regime mean (not the
  regime's exact rate), so the hidden state can't be inverted from the
  arrived/rework delta either.

## The `effect` interface

A module that touches the physics returns `effect(state, cfg) -> {name: value}`.
The engine (`_effects()`) merges every module's effect into one dict and threads
it into `resolve_week`, which reads each key **with a default** so absent factors
are inert:

| key | default (factor absent) |
|-----|-------------------------|
| `demand` | `cfg.weekly_demand` |
| `freight_mult` | `1.0` |
| `port_blocked` / `demurrage_rate` | `False` / `0.0` |
| `defect_fraction` / `rework_rate` | `0.0` |

Because every default reproduces the original constant, the **legacy two-factor
world is byte-identical** whether or not the effect machinery is present.
