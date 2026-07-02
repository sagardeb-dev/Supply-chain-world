"""Demand module — a hidden semi-Markov demand regime (normal / promo_spike /
seasonal_lift / structural_decline) visible as a NOISY weekly POS reading plus a
NOISY forward forecast, with a 1-week onset ambiguity (promo vs seasonal share
the `surge` mean). The agent must FILTER the regime over weeks, not read it in
one. The third latent factor; NOT in the default registry (rich worlds only).

drives: the finished-good ids (a per-model roster), resolved from cfg.product --
so the degenerate `single` product drives ONE stream (identical RNG to the old
singleton) and earbuds drives one per model."""

from ...products import structure
from .config import DEMAND_MEANS
from .emission import effect, emit, view
from .factor import (DEMAND_REGIMES, DemandState, demand_band, step_demand)

def _drives(cfg):
    """A callable roster selector: the demand factor advances one DemandState per
    finished good. Resolved wherever `drives` is read (engine._advance_modules).
    A module-level function (NOT a lambda) so the World -- which holds the
    registry -- stays picklable for agent-run resume."""
    return structure(cfg.product).finished_goods


DRIVES = _drives

__all__ = [
    "DemandState", "step_demand", "demand_band", "DEMAND_REGIMES",
    "effect", "emit", "view", "DEMAND_MEANS", "DRIVES",
]
