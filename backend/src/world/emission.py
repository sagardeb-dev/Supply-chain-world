"""What the world shows the agent. Noiseless: counts are an exact lookup
on the visible regime, so every deviation from baseline is signal. The
only ambiguity is the deliberate one: the shared "crash" fingerprint,
mirrored byte-for-byte in the news bulletin (R1)."""

from .config import (CAPE_LOCAL_EXTRA, REGIME_COUNTS, SUPPLIERS,
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


def _supplier_row(sid: str, sup: SupplierState, cfg: WorldConfig) -> dict:
    """One scorecard row, fully driven by the supplier's profile (config.
    SUPPLIERS) -- no instance-name branch. A drifting supplier reads its
    OTIF/lead/band from the visible band of its reliability chain (the
    deliberate 1-week 'slipping' ambiguity, A5); a frozen supplier shows the
    constants its profile declares. NEVER reads the disruption state
    (observation independence). Adding supplier #4 is one SUPPLIERS entry."""
    prof = SUPPLIERS[sid]
    if prof["drifts"]:
        band = sup.regime  # ontime|slipping|failing|defunct (Lever 1)
        otif, lead = SUPPLIER_SCORECARD[band]
    else:
        band, otif, lead = "ontime", prof["otif"], prof["lead"]
    row = {"id": sid, "otif": otif, "lead_days": lead, "band": band,
           "onboard_lead": prof["onboard_weeks"]}
    # unit economics, per supplier. The profile names the cfg field holding
    # the magnitude (cfg stays the single source of truth -- no number is
    # duplicated here) plus the sign and the optional extra display key. A
    # discount shows unit_discount, a premium shows unit_premium; backup shows
    # neither, just the signed delta.
    econ = prof["econ"]
    magnitude = getattr(cfg, econ["attr"])
    if econ["key"]:
        row[econ["key"]] = magnitude
    row["unit_delta"] = econ["sign"] * magnitude
    return row


def observe_scorecard(suppliers: dict, cfg: WorldConfig) -> dict:
    """The supplier factor's emission: a noiseless OTIF scorecard over the
    whole roster {id: SupplierState}, one row per supplier (A5). Order is
    fixed (registry order) so the readout is stable for the agent."""
    return {"suppliers": [_supplier_row(sid, suppliers[sid], cfg)
                          for sid in SUPPLIERS if sid in suppliers]}
