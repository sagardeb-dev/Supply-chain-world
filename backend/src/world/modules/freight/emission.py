"""The freight module's emission: a noisy weekly spot-index PRINT plus a noisier
forward rate OUTLOOK. The hidden rate regime is filtered from both. The cost
EFFECT (the multiplier on the route base rate) is the only way freight touches
the physics -- a pure reward coupling, so the belief stays factored."""

from ...config import WorldConfig
from .factor import FreightState


def emit(f: FreightState, cfg: WorldConfig) -> dict:
    """Passive weekly emission: a published spot-index print (mult x100, like a
    real index level) + a noisier forward outlook (carrier guidance / GRI)."""
    return {"freight_index": round(f.realized_mult * 100),
            "freight_outlook": round(f.outlook * 100)}


def effect(f: FreightState, cfg: WorldConfig) -> dict:
    """Substrate effect: the multiplier resolve_week applies to the route base
    rate (base_eff = base_route * freight_mult). The one place freight touches
    cost."""
    return {"freight_mult": f.realized_mult}


def view(cfg: WorldConfig) -> dict:
    return {"freight_index": {"role": "scalar", "label": "freight_index"},
            "freight_outlook": {"role": "scalar", "label": "freight_outlook"}}
