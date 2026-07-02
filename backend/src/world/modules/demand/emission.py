"""The demand module's emission: this week's NOISY realized POS (what sold /
what's consumed) plus a NOISY forward forecast (the demand-sensing channel).
Two noisy reads of the same hidden mean -> the agent must filter the regime
over several weeks; neither reading alone identifies it. The hidden regime/age
never leave the module (observation independence)."""

from ...config import WorldConfig
from ...products import structure
from .factor import DemandState


def effect(roster: dict, cfg: WorldConfig) -> dict:
    """Substrate effect: this week's per-finished-good demand replaces the
    constant weekly_demand in resolve_week's assembly step. The one place the
    demand factor touches the physics. `roster` is {finished_good: DemandState}."""
    return {"demand": {fg: s.realized for fg, s in roster.items()}}


def emit(roster: dict, cfg: WorldConfig) -> dict:
    """Passive weekly emission over the finished-good roster: each model's noisy
    realized POS plus a noisy forward forecast (demand sensing). A degenerate
    single-finished-good roster emits the FLAT legacy keys (pos_units /
    demand_forecast) byte-for-byte, so the scored single-SKU world is unchanged;
    a multi-model roster (earbuds) emits a nested per-model `demand` map."""
    if len(roster) == 1:
        (_fg, s), = roster.items()
        return {"pos_units": s.realized, "demand_forecast": s.forecast}
    return {"demand": {fg: {"pos_units": s.realized, "forecast": s.forecast}
                       for fg, s in roster.items()}}


def view(cfg: WorldConfig) -> dict:
    if len(structure(cfg.product).finished_goods) == 1:
        return {"pos_units": {"role": "scalar", "label": "pos_units"},
                "demand_forecast": {"role": "scalar", "label": "demand_forecast"}}
    return {"demand": {"role": "roster-row", "label": "demand"}}
