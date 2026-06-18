"""The supplier module's noiseless emission: an OTIF scorecard over the
whole roster, one row per supplier, fully profile-driven (no instance-name
branch). It reads ONLY the supplier states -- never the disruption state
(observation independence). emit/view are what the registry composes into
the Module record."""

from ...config import WorldConfig
from .config import SUPPLIER_SCORECARD, SUPPLIERS
from .factor import SupplierState


def _supplier_row(sid: str, sup: SupplierState, cfg: WorldConfig) -> dict:
    """One scorecard row, fully driven by the supplier's profile (SUPPLIERS)
    -- no instance-name branch. A drifting supplier reads its OTIF/lead/band
    from the visible band of its reliability chain (the deliberate 1-week
    'slipping' ambiguity, A5); a frozen supplier shows the constants its
    profile declares. NEVER reads the disruption state (observation
    independence). Adding supplier #4 is one SUPPLIERS entry."""
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


def emit(suppliers: dict, cfg: WorldConfig) -> dict:
    """The module's passive weekly emission: the scorecard slice,
    {"suppliers": [...]}, byte-identical to observe_scorecard."""
    return observe_scorecard(suppliers, cfg)


def view(cfg: WorldConfig) -> dict:
    # the "suppliers" key is the whole roster (rows carry their own ids), so
    # its label is a fixed UI word, not an instance name -- inherently leak-
    # free in both semantics modes. Per-row labels come from the row data.
    return {"suppliers": {"role": "roster-row", "label": "scorecard"}}
