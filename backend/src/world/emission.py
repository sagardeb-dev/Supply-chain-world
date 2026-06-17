"""What the world shows the agent. Noiseless: counts are an exact lookup
on the visible regime, so every deviation from baseline is signal. The
only ambiguity is the deliberate one: the shared "crash" fingerprint,
mirrored byte-for-byte in the news bulletin (R1)."""

from .config import (CAPE_LOCAL_EXTRA, REGIME_COUNTS,
                     SUPPLIER_SCORECARD, WorldConfig)
from .semantics import BRIEFINGS, BULLETINS
from .state import HiddenState, SupplierState


def observe_counts(h: HiddenState, cfg: WorldConfig) -> dict:
    suez, bab, cape = REGIME_COUNTS[h.regime]
    if h.cape_local_congestion:
        cape += CAPE_LOCAL_EXTRA
    return {"suez_count": suez, "bab_count": bab, "cape_count": cape}


def news_bulletin(h: HiddenState, cfg: WorldConfig) -> str:
    """Weekly trade-press bulletin: pure function of the visible regime,
    so the crash week is textually ambiguous by construction (R1)."""
    return BULLETINS[cfg.semantics][h.regime]


def analyst_briefing(h: HiddenState, cfg: WorldConfig) -> str:
    """Paid intelligence: honest assessment of the CURRENT hidden state,
    including the disruption type - the one thing neither counts nor
    bulletin reveal at the crash week."""
    key = h.disruption_type if h.event_state == "disruption" else h.event_state
    return BRIEFINGS[cfg.semantics][key]


def observe_scorecard(sup: SupplierState, cfg: WorldConfig) -> dict:
    """The supplier factor's emission: a noiseless OTIF scorecard, exactly
    like observe_counts is for the disruption factor. A table lookup on the
    spot supplier's visible band -- it NEVER reads the disruption state
    (observation independence). Qualified (Q) is constant; spot (S) reflects
    its hidden regime, with the deliberate 1-week 'slipping' ambiguity (A5)."""
    s_otif, s_lead = SUPPLIER_SCORECARD[sup.regime]
    return {
        "suppliers": [
            {"id": "qualified", "otif": 99, "lead_days": 14,
             "unit_premium": cfg.qualified_premium},
            {"id": "spot", "otif": s_otif, "lead_days": s_lead,
             "unit_discount": cfg.spot_unit_discount},
        ]
    }
