"""The quality module's emission: a noisy DISCRETE AQL inspection result
(accept/marginal/reject). The hidden process state is filtered from a stream of
these noisy samples -- no single reading identifies it. The EFFECT is on usable
inventory: a defective fraction of arriving units don't stock (effective
shortfall) and incur rework. A pure reward coupling, so the belief stays
factored."""

from ...config import WorldConfig
from .factor import QualityState


def emit(q: QualityState, cfg: WorldConfig) -> dict:
    """Passive weekly emission: the noisy incoming-inspection AQL band."""
    return {"aql_result": q.sample_band}


def effect(q: QualityState, cfg: WorldConfig) -> dict:
    """Substrate effect: this week's NOISY realized batch defect fraction (a
    finite-batch sample around the regime's true rate). round(gross*frac) is a
    noisy defective count, so the agent cannot read the hidden regime off the
    arrived/rework delta -- it must filter it like every other channel. The one
    place quality touches cost."""
    return {"defect_fraction": q.realized_defect,
            "rework_rate": cfg.quality_rework_cost}


def view(cfg: WorldConfig) -> dict:
    return {"aql_result": {"role": "category", "label": "aql_result"}}
