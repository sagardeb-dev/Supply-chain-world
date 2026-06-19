"""Quality module — a hidden semi-Markov process-quality state (in_control/
drifting/out_of_control) observed only through a NOISY DISCRETE AQL sample
(accept/marginal/reject). Its EFFECT removes a defective fraction of arriving
units from usable inventory + charges rework. The sixth latent factor; rich
worlds only. The one noisy-emission factor -> the belief never collapses ->
the full world needs the bracket anchor, not an exact DP.

drives=("",): a singleton module-state."""

from .config import AQL_BANDS, QUALITY_BAND_PROBS, QUALITY_DEFECT
from .emission import effect, emit, view
from .factor import (QUALITY_REGIMES, QualityState, step_quality)

DRIVES = ("",)

__all__ = [
    "QualityState", "step_quality", "QUALITY_REGIMES",
    "effect", "emit", "view", "QUALITY_DEFECT", "QUALITY_BAND_PROBS",
    "AQL_BANDS", "DRIVES",
]
