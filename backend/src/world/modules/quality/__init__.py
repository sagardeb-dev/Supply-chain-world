"""Quality module — a hidden semi-Markov process-quality state (in_control/
drifting/out_of_control) observed only through a NOISY DISCRETE AQL sample
(accept/marginal/reject). Its EFFECT removes a defective fraction of arriving
units from usable inventory + charges rework. The sixth latent factor; rich
worlds only. The one noisy-emission factor -> the belief never collapses ->
the full world needs the bracket anchor, not an exact DP.

drives: legacy (cfg.quality_per_supplier off) -- ("",), a singleton
module-state (byte-identical trajectory). Phase 3 (flag on) -- one quality
chain per supplier ("spot","qualified","backup"), same drive order as the
supplier module, each on its own personality kernel."""

from .config import AQL_BANDS, QUALITY_BAND_PROBS, QUALITY_DEFECT
from .emission import effect, emit, view
from .factor import (QUALITY_REGIMES, QualityState, step_quality)


def _drives(cfg):
    """A callable roster selector (mirrors supplier._drives): WHO runs their
    own quality chain this world. Legacy default advances only the singleton
    ("") -- unchanged rng prefix, byte-identical trajectories/goldens. Phase 3
    (cfg.quality_per_supplier) advances all three roster members, in the same
    order supplier.DRIVES uses. A module-level function (NOT a lambda) so the
    World stays picklable for agent-run resume."""
    return ("spot", "qualified", "backup") if cfg.quality_per_supplier else ("",)


DRIVES = _drives

__all__ = [
    "QualityState", "step_quality", "QUALITY_REGIMES",
    "effect", "emit", "view", "QUALITY_DEFECT", "QUALITY_BAND_PROBS",
    "AQL_BANDS", "DRIVES",
]
