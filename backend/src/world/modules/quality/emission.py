"""The quality module's emission: a noisy DISCRETE AQL inspection result
(accept/marginal/reject). The hidden process state is filtered from a stream of
these noisy samples -- no single reading identifies it. The EFFECT is on usable
inventory: a defective fraction of arriving units don't stock (effective
shortfall) and incur rework. A pure reward coupling, so the belief stays
factored."""

from ...config import WorldConfig
from .config import QUALITY_DEFECT
from .factor import QualityState


def emit(q: QualityState, cfg: WorldConfig) -> dict:
    """Passive weekly emission: the noisy incoming-inspection AQL band."""
    return {"aql_result": q.sample_band}


def effect(q: QualityState, cfg: WorldConfig) -> dict:
    """Substrate effect: the true defective FRACTION of arriving units (don't
    stock + rework) by the hidden regime. The one place quality touches cost."""
    return {"defect_fraction": QUALITY_DEFECT[q.regime],
            "rework_rate": cfg.quality_rework_cost}


def view(cfg: WorldConfig) -> dict:
    return {"aql_result": {"role": "category", "label": "aql_result"}}
