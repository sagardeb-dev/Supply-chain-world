"""The quality module's emission: a noisy DISCRETE AQL inspection result
(accept/marginal/reject). The hidden process state is filtered from a stream of
these noisy samples -- no single reading identifies it. The EFFECT is on usable
inventory: a defective fraction of arriving units don't stock (effective
shortfall) and incur rework. A pure reward coupling, so the belief stays
factored."""

from ...config import WorldConfig
from .factor import QualityState


def emit(q, cfg: WorldConfig) -> dict:
    """Passive weekly emission: the noisy incoming-inspection AQL band.
    Singleton (legacy, flag off) -> the flat scalar key, byte-identical.
    Phase 3 roster ({sid: QualityState}, cfg.quality_per_supplier) -> a
    per-supplier map, mirroring how the supplier scorecard emits its roster."""
    if isinstance(q, dict):
        return {"aql_result": {sid: s.sample_band for sid, s in q.items()}}
    return {"aql_result": q.sample_band}


def effect(q, cfg: WorldConfig) -> dict:
    """Substrate effect: this week's NOISY realized batch defect fraction (a
    finite-batch sample around the regime's true rate). round(gross*frac) is a
    noisy defective count, so the agent cannot read the hidden regime off the
    arrived/rework delta -- it must filter it like every other channel. The one
    place quality touches cost. Singleton -> unchanged scalar shape. Phase 3
    roster -> a per-supplier defect_fraction map; logistics.py looks each
    shipment's supplier up in it. rework_rate stays a flat scalar (shared cost
    knob) either way."""
    if isinstance(q, dict):
        return {"defect_fraction": {sid: s.realized_defect for sid, s in q.items()},
                "rework_rate": cfg.quality_rework_cost}
    return {"defect_fraction": q.realized_defect,
            "rework_rate": cfg.quality_rework_cost}


def view(cfg: WorldConfig) -> dict:
    if cfg.quality_per_supplier:
        return {"aql_result": {"role": "roster-row", "label": "aql_result"}}
    return {"aql_result": {"role": "category", "label": "aql_result"}}
