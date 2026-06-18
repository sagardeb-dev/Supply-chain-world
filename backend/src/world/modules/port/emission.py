"""The port module's emission: a noisy weekly berth-wait reading + a noisier
forward outlook. The hidden congestion/customs state is filtered from both. The
EFFECT is on LEAD TIME + cost: when the port is blocked, arrivals are held a week
and accrue demurrage (applied in resolve_week). A pure reward/timing coupling,
so the belief stays factored."""

from ...config import WorldConfig
from .factor import PortState


def emit(p: PortState, cfg: WorldConfig) -> dict:
    """Passive weekly emission: the noisy berth-wait days + a forward outlook."""
    return {"berth_wait": p.berth_wait, "wait_outlook": p.wait_outlook}


def effect(p: PortState, cfg: WorldConfig) -> dict:
    """Substrate effect: when blocked, resolve_week holds this week's arrivals a
    week and charges demurrage on the held units. The one place port touches the
    physics (lead time + cost)."""
    return {"port_blocked": p.blocked,
            "demurrage_rate": cfg.port_demurrage_rate}


def view(cfg: WorldConfig) -> dict:
    return {"berth_wait": {"role": "scalar", "label": "berth_wait"},
            "wait_outlook": {"role": "scalar", "label": "wait_outlook"}}
