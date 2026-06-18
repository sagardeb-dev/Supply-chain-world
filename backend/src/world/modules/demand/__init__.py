"""Demand module — a hidden semi-Markov demand regime (normal / promo_spike /
seasonal_lift / structural_decline) visible as noiseless weekly POS units, with
a 1-week onset ambiguity (promo vs seasonal). The third latent factor; NOT in
the default registry (it appears only in a rich, multi-factor world).

drives=("",): a singleton module-state."""

from .config import DEMAND_LEVELS
from .emission import demand_units, emit, view
from .factor import DEMAND_REGIMES, DemandState, step_demand

DRIVES = ("",)

__all__ = [
    "DemandState", "step_demand", "DEMAND_REGIMES",
    "demand_units", "emit", "view", "DEMAND_LEVELS", "DRIVES",
]
