"""Hidden state. Three free factors: event HMM (state+age), disruption
type (drawn at onset), and the iid cape_local coin. The visible-regime
label derives deterministically and keys the emission table.

A SECOND, fully separate latent factor lives here too: SupplierState, the
spot supplier's reliability chain. It has its own states, its own visible
band, and (in transition.py) its own kernel -- it never reads HiddenState.
That isolation is the point: one latent module per task, debuggable alone."""

from dataclasses import dataclass, asdict

EVENT_STATES = ("calm", "watch", "disruption", "recovery", "false_alarm")
DISRUPTION_TYPES = ("short", "long")

SUPPLIER_STATES = ("reliable", "wobbling", "degraded")


@dataclass(frozen=True)
class HiddenState:
    event_state: str = "calm"
    event_age: int = 0
    disruption_type: str | None = None  # set iff event_state == "disruption"
    cape_local_congestion: bool = False

    @property
    def regime(self) -> str:
        """Emission-table key. false_alarm and week one of EITHER disruption
        type share "crash" — the agent cannot tell them apart from counts
        until the next week (or a probe)."""
        if self.event_state == "false_alarm":
            return "crash"
        if self.event_state == "disruption":
            if self.event_age == 0:
                return "crash"
            return "blockage" if self.disruption_type == "short" else "crisis"
        return self.event_state  # calm | watch | recovery

    @property
    def canal_blocked(self) -> bool:
        """Ships cannot transit Suez this week (closed or too dangerous)."""
        return self.event_state == "disruption"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["regime"] = self.regime
        return d


@dataclass(frozen=True)
class SupplierState:
    """The spot supplier's reliability factor -- the second latent module.
    Independent of HiddenState; its own kernel advances it (transition.py).

    Visible band (regime) collapses two states into one for exactly one week,
    mirroring the disruption "crash" ambiguity: a fresh "wobbling" and the
    onset week of "degraded" both read "slipping" on the scorecard, then
    separate the following week (degraded ages into "failing")."""

    rel_state: str = "reliable"
    rel_age: int = 0  # weeks the supplier has been in degraded

    @property
    def regime(self) -> str:
        """Scorecard-band key. wobbling and degraded-onset share "slipping"."""
        if self.rel_state == "reliable":
            return "ontime"
        if self.rel_state == "wobbling":
            return "slipping"
        # degraded
        return "slipping" if self.rel_age == 0 else "failing"

    @property
    def fulfilled_fraction(self) -> float:
        """Share of a spot order this supplier actually ships this week."""
        return {"reliable": 1.0, "wobbling": 0.5, "degraded": 0.0}[self.rel_state]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["regime"] = self.regime
        return d
