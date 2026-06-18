"""The module contract: one record per latent factor, so the engine iterates
a registry instead of wiring each factor by hand and by literal instance name.
Each module is the EXISTING (state, kernel, emission) trio made explicit -- no
new logic, just a declaration.

NOT an ABC/Protocol hierarchy: the factors are pure functions + frozen
dataclasses, so a record + a tuple registry is the whole machinery.

Two budgets are baked into the record up front:
  kind -- oracle cost (latent-factor = +1 belief marginal, cheap iff
          noiseless; action-lever = action cross-product blowup;
          standing-choice = occasional index; observed = state dim, no
          belief). Documentation now, a future guard.
  view -- frontend cost. view(cfg) -> {obs_key: {role, label}}: each obs key
          declares a display ROLE so the frontend renders generically (a new
          passive module appears with zero new JS). Read in _build_obs; a
          presentation manifest, never the values.

Dependency direction: registry imports the modules and BUILDS their records.
The modules never import registry. That one-way edge is what keeps the
sealed-box files free of a circular import. Adding a latent module = a new
modules/<name>/ package + its record + one REGISTRY entry here.
"""

from dataclasses import dataclass
from typing import Callable

from .modules import disruption, supplier


@dataclass(frozen=True)
class Module:
    id: str                       # "disruption" | "supplier"
    kind: str                     # latent-factor | action-lever | standing-choice | observed
    state_cls: type | None        # HiddenState / SupplierState
    kernel: Callable | None       # step(state, rng, cfg) -> state ; None if no hidden state
    emit: Callable                # observe(...) -> {obs_key: value}  -- FLAT, byte-identical to today
    view: Callable                # (cfg) -> {obs_key: {"role", "label"}}  -- presentation manifest
    drives: tuple[str, ...]       # roster instance ids it advances
    init: Callable | None = None  # (cfg) -> initial state (singleton) | {id: state} (roster).
                                  # None falls back to state_cls(). The module owns its own
                                  # reset, so the engine stays factor-agnostic.


def _init_disruption(cfg):
    return disruption.HiddenState()


def _init_supplier(cfg):
    # the full roster (all suppliers); the kernel advances only drifting ids.
    return {sid: supplier.SupplierState() for sid in supplier.SUPPLIERS}


DISRUPTION = Module(
    id="disruption", kind="latent-factor",
    state_cls=disruption.HiddenState, kernel=disruption.step_hidden,
    emit=disruption.emit, view=disruption.view, drives=disruption.DRIVES,
    init=_init_disruption,
)

SUPPLIER = Module(
    id="supplier", kind="latent-factor",
    state_cls=supplier.SupplierState, kernel=supplier.step_supplier,
    emit=supplier.emit, view=supplier.view, drives=supplier.DRIVES,
    init=_init_supplier,
)


# ORDER IS LOAD-BEARING: kernels consume rng in this order, so the hidden
# trajectory is a function of the seed (exogeneity). Disruption first, then
# supplier -- the same order engine.step drew in before the refactor.
REGISTRY: tuple[Module, ...] = (DISRUPTION, SUPPLIER)


# ponytail: the paid analyst_briefing is deliberately NOT in any module's emit
# -- it is action-gated (request_briefing), not a passive weekly emission, and
# the contract has no paid-probe slot in v1. Folding it in would need a probe
# slot; add that when a second paid probe appears.
