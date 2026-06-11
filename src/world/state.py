"""Hidden state. Two free factors (event HMM + cape_local); everything
else derives deterministically from them."""

from dataclasses import dataclass, asdict

EVENT_STATES = ("calm", "watch", "disruption", "recovery", "false_alarm")


@dataclass(frozen=True)
class HiddenState:
    event_state: str = "calm"
    event_age: int = 0
    cape_local_congestion: bool = False

    @property
    def suez_regime(self) -> str:
        if self.event_state == "disruption":
            return "degraded"
        if self.event_state == "recovery":
            return "recovering"
        return "normal"

    @property
    def bab_regime(self) -> str:
        return self.suez_regime

    @property
    def cape_congestion(self) -> str:
        if self.event_state == "disruption" or self.cape_local_congestion:
            return "high"
        if self.event_state == "recovery":
            return "medium"
        return "low"

    @property
    def signal_reliability(self) -> str:
        return "suppressed" if self.event_state == "false_alarm" else "normal"

    @property
    def seasonal_dip(self) -> bool:
        return self.event_state in ("watch", "false_alarm")

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(
            suez_regime=self.suez_regime,
            bab_regime=self.bab_regime,
            cape_congestion=self.cape_congestion,
            signal_reliability=self.signal_reliability,
            seasonal_dip=self.seasonal_dip,
        )
        return d
