"""The demand module's noiseless emission: the realized weekly POS units
(an exact lookup on the visible band). The hidden regime is inferred from the
level + its trajectory + the deliberate 1-week `surge` ambiguity.

`demand_units` is also the substrate's consumption value for the week -- the
observable IS the realized demand (POS = what sold), so the channel is
noiseless. The engine threads it into resolve_week when the demand module is
in the registry; otherwise the world falls back to the constant cfg.weekly_demand."""

from ...config import WorldConfig
from .config import DEMAND_LEVELS
from .factor import DemandState


def demand_units(d: DemandState, cfg: WorldConfig) -> int:
    """This week's realized demand units = the visible band's level."""
    return DEMAND_LEVELS[d.band]


def emit(d: DemandState, cfg: WorldConfig) -> dict:
    """Passive weekly emission: the POS units the agent observes."""
    return {"pos_units": DEMAND_LEVELS[d.band]}


def view(cfg: WorldConfig) -> dict:
    return {"pos_units": {"role": "scalar", "label": "pos_units"}}
