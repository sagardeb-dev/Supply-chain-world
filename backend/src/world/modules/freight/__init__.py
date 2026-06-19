"""Freight module — a hidden semi-Markov ocean-rate regime (slack/normal/
tightening/spike) visible as a NOISY spot-index print + a NOISY forward outlook,
with a GRI-onset ambiguity (tightening vs spike share the `jump` band). Its cost
EFFECT is a multiplier on the route base rate. The fourth latent factor; rich
worlds only.

drives=("",): a singleton module-state."""

from .config import FREIGHT_MEANS
from .emission import effect, emit, view
from .factor import (FREIGHT_REGIMES, FreightState, freight_band, step_freight)

DRIVES = ("",)

__all__ = [
    "FreightState", "step_freight", "freight_band", "FREIGHT_REGIMES",
    "effect", "emit", "view", "FREIGHT_MEANS", "DRIVES",
]
