"""Disruption module — the event HMM + the iid cape-local coin, one
stochastic root visible to the agent as transit counts + a trade-press
bulletin. Public surface re-exported for the registry and importers.

drives=("",): this module advances the singleton world-state (self.hidden),
not a roster id."""

from .config import CAPE_LOCAL_EXTRA, REGIME_COUNTS
from .emission import (analyst_briefing, emit, news_bulletin, observe_counts,
                       view)
from .factor import (DISRUPTION_TYPES, EVENT_STATES, HiddenState, step_hidden)
from .text import BRIEFINGS, BULLETINS, COUNT_KEYS

DRIVES = ("",)

__all__ = [
    "HiddenState", "step_hidden", "EVENT_STATES", "DISRUPTION_TYPES",
    "observe_counts", "news_bulletin", "analyst_briefing", "emit", "view",
    "BULLETINS", "BRIEFINGS", "COUNT_KEYS",
    "REGIME_COUNTS", "CAPE_LOCAL_EXTRA", "DRIVES",
]
