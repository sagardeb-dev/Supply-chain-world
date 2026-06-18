"""The disruption latent factor: hidden state + kernel.

Three free factors: event HMM (state+age), disruption type (drawn at
onset), and the iid cape_local coin. The visible-regime label derives
deterministically and keys the emission table. The kernel is a pure
function of (state, rng, cfg); it never reads actions, so the trajectory
is a function of the seed alone (exogeneity). It NEVER reads the supplier
factor -- one latent module per task, debuggable alone (Becker Def. 2)."""

import random
from dataclasses import dataclass, asdict

from ...config import WorldConfig

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


def step_hidden(h: HiddenState, rng: random.Random, cfg: WorldConfig) -> HiddenState:
    s, age, dtype = h.event_state, h.event_age, h.disruption_type
    ntype = None

    if s == "calm":
        nxt = "watch" if rng.random() < cfg.onset_prob else "calm"
    elif s == "watch":
        r = rng.random()
        if r < cfg.watch_to_disruption_prob:
            nxt = "disruption"
            ntype = "short" if rng.random() < cfg.short_disruption_prob else "long"
        elif r < cfg.watch_to_disruption_prob + cfg.watch_to_false_alarm_prob:
            nxt = "false_alarm"
        elif r < (cfg.watch_to_disruption_prob + cfg.watch_to_false_alarm_prob
                  + cfg.watch_to_calm_prob):
            nxt = "calm"
        else:
            nxt = "watch"
    elif s == "disruption":
        if dtype == "short":
            over = age + 1 >= cfg.max_short_weeks or rng.random() > cfg.short_persist_prob
        else:
            over = rng.random() > cfg.long_persist_prob
        nxt = "recovery" if over else "disruption"
        ntype = None if over else dtype
    elif s == "recovery":
        over = age + 1 >= cfg.max_recovery_weeks or rng.random() > cfg.recovery_persist_prob
        nxt = "calm" if over else "recovery"
    else:  # false_alarm: the scare resolves within the week
        nxt = "calm"

    return HiddenState(
        event_state=nxt,
        event_age=0 if nxt != s else age + 1,
        disruption_type=ntype,
        cape_local_congestion=rng.random() < cfg.cape_local_prob,
    )
