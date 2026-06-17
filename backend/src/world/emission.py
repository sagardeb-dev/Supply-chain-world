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
    """One scorecard row. Drifting suppliers (spot) read their OTIF/lead from
    the visible band of their reliability chain (the deliberate 1-week
    'slipping' ambiguity lives here, A5); frozen suppliers show constants.
    NEVER reads the disruption state (observation independence)."""
    prof = SUPPLIERS[sid]
    if prof["drifts"]:
        otif, lead = SUPPLIER_SCORECARD[sup.regime]
    elif sid == "qualified":
        otif, lead = prof["otif"], prof["lead"]
    else:  # backup
        otif, lead = cfg.backup_base_otif, cfg.backup_lead_days
    row = {"id": sid, "otif": otif, "lead_days": lead,
           "onboard_lead": prof["onboard_weeks"]
           if prof["onboard_weeks"] is not None else cfg.backup_onboard_weeks}
    # unit economics, per supplier: spot discounts, qualified/backup add a delta
    if sid == "spot":
        row["unit_discount"] = cfg.spot_unit_discount
        row["unit_delta"] = -cfg.spot_unit_discount
    elif sid == "qualified":
        row["unit_premium"] = cfg.qualified_premium
        row["unit_delta"] = cfg.qualified_premium
    else:  # backup
        row["unit_delta"] = cfg.backup_unit_delta
    return row


def observe_scorecard(suppliers: dict, cfg: WorldConfig) -> dict:
    """The supplier factor's emission: a noiseless OTIF scorecard over the
    whole roster {id: SupplierState}, one row per supplier (A5). Order is
    fixed (registry order) so the readout is stable for the agent."""
    return {"suppliers": [_supplier_row(sid, suppliers[sid], cfg)
                          for sid in SUPPLIERS if sid in suppliers]}
