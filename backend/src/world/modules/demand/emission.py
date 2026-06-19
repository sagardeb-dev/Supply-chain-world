"""The demand module's emission: this week's NOISY realized POS (what sold /
what's consumed) plus a NOISY forward forecast (the demand-sensing channel).
Two noisy reads of the same hidden mean -> the agent must filter the regime
over several weeks; neither reading alone identifies it. The hidden regime/age
never leave the module (observation independence).

`demand_units` is the substrate's consumption value for the week (= the realized
POS, since POS is what actually sold). The engine threads it into resolve_week
when the demand module is in the registry; otherwise the world falls back to the
constant cfg.weekly_demand."""

from ...config import WorldConfig
from .factor import DemandState


def demand_units(d: DemandState, cfg: WorldConfig) -> int:
    """This week's realized demand units consumed = the noisy realized POS."""
    return d.realized


def effect(d: DemandState, cfg: WorldConfig) -> dict:
    """Substrate effect: this week's demand replaces the constant weekly_demand
    in resolve_week. The one place the demand factor touches the physics."""
    return {"demand": d.realized}


def emit(d: DemandState, cfg: WorldConfig) -> dict:
    """Passive weekly emission: the noisy realized POS the agent observes, plus
    a noisy forward forecast of underlying demand (demand sensing)."""
    return {"pos_units": d.realized, "demand_forecast": d.forecast}


def view(cfg: WorldConfig) -> dict:
    return {"pos_units": {"role": "scalar", "label": "pos_units"},
            "demand_forecast": {"role": "scalar", "label": "demand_forecast"}}
