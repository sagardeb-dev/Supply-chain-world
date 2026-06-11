"""What the world shows the agent. Noiseless: counts are exact
deterministic functions of the hidden state — every deviation from
baseline is signal, and the traps (dip, suppression, cape_local) are
the only sources of ambiguity."""

from .config import WorldConfig
from .state import HiddenState


def observe_counts(h: HiddenState, cfg: WorldConfig) -> dict:
    dip = cfg.seasonal_dip_mult if h.seasonal_dip else 1.0
    rel = cfg.suppressed_mult if h.signal_reliability == "suppressed" else 1.0

    suez_mult = {
        "degraded": cfg.suez_degraded_mult,
        "recovering": cfg.recovering_mult,
        "normal": 1.0,
    }[h.suez_regime]
    bab_mult = {
        "degraded": cfg.bab_degraded_mult,
        "recovering": cfg.recovering_mult,
        "normal": 1.0,
    }[h.bab_regime]
    cape_mult = {
        "high": cfg.cape_high_mult,
        "medium": cfg.cape_medium_mult,
        "low": 1.0,
    }[h.cape_congestion]

    return {
        "suez_count": round(cfg.suez_base * suez_mult * dip * rel),
        "bab_count": round(cfg.bab_base * bab_mult * dip * rel),
        "cape_count": round(cfg.cape_base * cape_mult),
    }


def probe_result(h: HiddenState) -> str:
    if h.event_state in ("watch", "disruption"):
        return "likely_disruption"
    if h.event_state == "false_alarm":
        return "likely_false_alarm"
    return "all_clear"
