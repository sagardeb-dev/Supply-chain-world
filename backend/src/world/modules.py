"""The module contract: one record per latent factor, so the engine
iterates a registry instead of wiring each factor by hand and by literal
instance name. Each module is the EXISTING (state, kernel, emission) trio
made explicit -- no new logic, just a declaration.

NOT an ABC/Protocol hierarchy: the factors are pure functions + frozen
dataclasses, so a record + a tuple registry is the whole machinery.

Two budgets are baked into the record up front:
  kind -- oracle cost (latent-factor = +1 belief marginal, cheap iff
          noiseless; action-lever = action cross-product blowup;
          standing-choice = occasional index; observed = state dim, no
          belief). Documentation now, a future guard.
  view -- frontend cost. view(cfg) -> {obs_key: {role, label}}: each obs
          key declares a display ROLE so the frontend renders generically
          (a new passive module appears with zero new JS). Read in
          _build_obs (Task 4); a presentation manifest, never the values.
"""

from dataclasses import dataclass
from typing import Callable

from .config import SUPPLIERS, WorldConfig
from .emission import news_bulletin, observe_counts, observe_scorecard
from .semantics import COUNT_KEYS
from .state import HiddenState, SupplierState
from .transition import step_hidden, step_supplier


@dataclass(frozen=True)
class Module:
    id: str                       # "disruption" | "supplier"
    kind: str                     # latent-factor | action-lever | standing-choice | observed
    state_cls: type | None        # HiddenState / SupplierState
    kernel: Callable | None       # step(state, rng, cfg) -> state ; None if no hidden state
    emit: Callable                # observe(...) -> {obs_key: value}  -- FLAT, byte-identical to today
    view: Callable                # (cfg) -> {obs_key: {"role", "label"}}  -- presentation manifest
    drives: tuple[str, ...]       # roster instance ids it advances


# --- disruption: the event HMM + the iid cape-local coin (one stochastic
# root visible to the agent as counts + a bulletin). drives the singleton
# world-state (not a roster id), so its drive key is the empty string. ---

def _disruption_emit(h: HiddenState, cfg: WorldConfig) -> dict:
    """Exactly the slice _build_obs assembled by hand: the count keys
    (renamed through the per-semantics map) plus the bulletin."""
    keymap = COUNT_KEYS[cfg.semantics]
    counts = observe_counts(h, cfg)
    obs = {keymap[k]: v for k, v in counts.items()}
    obs["bulletin"] = news_bulletin(h, cfg)
    return obs


def _disruption_view(cfg: WorldConfig) -> dict:
    keymap = COUNT_KEYS[cfg.semantics]
    view = {keymap[k]: {"role": "scalar", "label": keymap[k]}
            for k in ("suez_count", "bab_count", "cape_count")}
    view["bulletin"] = {"role": "series", "label": "bulletin"}
    return view


DISRUPTION = Module(
    id="disruption", kind="latent-factor",
    state_cls=HiddenState, kernel=step_hidden,
    emit=_disruption_emit, view=_disruption_view,
    drives=("",),  # the singleton world-state, not a roster id
)


# --- supplier: the spot reliability chain (second stochastic root, visible
# as a noiseless OTIF scorecard). drives the roster ids whose profile sets
# drifts=True (only spot in R1). ---

def _supplier_emit(suppliers: dict, cfg: WorldConfig) -> dict:
    """The scorecard slice: {"suppliers": [...]}, byte-identical to today."""
    return observe_scorecard(suppliers, cfg)


def _supplier_view(cfg: WorldConfig) -> dict:
    # the "suppliers" key is the whole roster (rows carry their own ids), so
    # its label is a fixed UI word, not an instance name -- inherently leak-
    # free in both semantics modes. Per-row labels come from the row data.
    return {"suppliers": {"role": "roster-row", "label": "scorecard"}}


SUPPLIER = Module(
    id="supplier", kind="latent-factor",
    state_cls=SupplierState, kernel=step_supplier,
    emit=_supplier_emit, view=_supplier_view,
    drives=tuple(sid for sid, p in SUPPLIERS.items() if p["drifts"]),
)


# ORDER IS LOAD-BEARING: kernels consume rng in this order, so the hidden
# trajectory is a function of the seed (exogeneity). Disruption first, then
# supplier -- the same order engine.step drew in before the refactor.
REGISTRY: tuple[Module, ...] = (DISRUPTION, SUPPLIER)


# ponytail: the paid analyst_briefing is deliberately NOT in any module's
# emit -- it is action-gated (request_briefing), not a passive weekly
# emission, and the contract has no paid-probe slot in v1. Folding it in
# would need a probe slot; add that when a second paid probe appears.
