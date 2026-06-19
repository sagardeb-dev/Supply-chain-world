"""The disruption module's noiseless emission: counts are an exact lookup
on the visible regime, so every deviation from baseline is signal. The
only ambiguity is the deliberate one -- the shared "crash" fingerprint,
mirrored byte-for-byte in the news bulletin (R1). emit/view are what the
registry composes into the Module record."""

from ...config import WorldConfig
from .config import CAPE_LOCAL_EXTRA, REGIME_COUNTS
from .factor import HiddenState
from .text import BRIEFINGS, BULLETINS, COUNT_KEYS


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


def emit(h: HiddenState, cfg: WorldConfig) -> dict:
    """The module's passive weekly emission: the count keys (renamed through
    the per-semantics map) plus the bulletin. Flat, byte-identical to the
    hand-built obs slice."""
    keymap = COUNT_KEYS[cfg.semantics]
    counts = observe_counts(h, cfg)
    obs = {keymap[k]: v for k, v in counts.items()}
    obs["bulletin"] = news_bulletin(h, cfg)
    return obs


def view(cfg: WorldConfig) -> dict:
    """Presentation manifest: each obs key's display role + label."""
    keymap = COUNT_KEYS[cfg.semantics]
    v = {keymap[k]: {"role": "scalar", "label": keymap[k]}
         for k in ("suez_count", "bab_count", "cape_count")}
    v["bulletin"] = {"role": "series", "label": "bulletin"}
    return v
