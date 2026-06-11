"""What the world shows the agent. Noiseless: counts are an exact lookup
on the visible regime, so every deviation from baseline is signal. The
only ambiguity is the deliberate one: the shared "crash" fingerprint."""

from .config import CAPE_LOCAL_EXTRA, REGIME_COUNTS, WorldConfig
from .state import HiddenState


def observe_counts(h: HiddenState, cfg: WorldConfig) -> dict:
    suez, bab, cape = REGIME_COUNTS[h.regime]
    if h.cape_local_congestion:
        cape += CAPE_LOCAL_EXTRA
    return {"suez_count": suez, "bab_count": bab, "cape_count": cape}


def probe_result(h: HiddenState) -> str:
    """Paid intelligence briefing: ground-truth regime including the
    disruption type — the one thing counts cannot reveal at the crash week."""
    if h.event_state == "disruption":
        return ("blockage_short_term" if h.disruption_type == "short"
                else "crisis_long_term")
    return {
        "calm": "all_clear",
        "watch": "elevated_risk",
        "false_alarm": "false_alarm",
        "recovery": "recovering",
    }[h.event_state]
