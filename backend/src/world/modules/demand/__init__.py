"""Demand module — a hidden semi-Markov demand regime (normal / promo_spike /
seasonal_lift / structural_decline) visible as a NOISY weekly POS reading plus a
NOISY forward forecast, with a 1-week onset ambiguity (promo vs seasonal share
the `surge` mean). The agent must FILTER the regime over weeks, not read it in
one. The third latent factor; NOT in the default registry (rich worlds only).

drives=("",): a singleton module-state."""

from .config import DEMAND_MEANS
from .emission import demand_units, effect, emit, view
from .factor import (DEMAND_REGIMES, DemandState, demand_band, step_demand)

DRIVES = ("",)

__all__ = [
    "DemandState", "step_demand", "demand_band", "DEMAND_REGIMES",
    "demand_units", "effect", "emit", "view", "DEMAND_MEANS", "DRIVES",
]
