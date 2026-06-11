"""Hidden state. Three free factors: event HMM (state+age), disruption
type (drawn at onset), and the iid cape_local coin. The visible-regime
label derives deterministically and keys the emission table."""

from dataclasses import dataclass, asdict

EVENT_STATES = ("calm", "watch", "disruption", "recovery", "false_alarm")
DISRUPTION_TYPES = ("short", "long")


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
