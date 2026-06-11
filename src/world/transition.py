"""Hidden-state evolution. Pure function of (state, rng, cfg)."""

import random

from .config import WorldConfig
from .state import HiddenState


def step_hidden(h: HiddenState, rng: random.Random, cfg: WorldConfig) -> HiddenState:
    s, age = h.event_state, h.event_age

    if s == "calm":
        r = rng.random()
        if r < cfg.false_alarm_prob:
            nxt = "false_alarm"
        elif r < cfg.false_alarm_prob + cfg.onset_prob:
            nxt = "watch"
        else:
            nxt = "calm"
    elif s == "watch":
        r = rng.random()
        if r < cfg.watch_to_disruption_prob:
            nxt = "disruption"
        elif r < cfg.watch_to_disruption_prob + cfg.watch_to_calm_prob:
            nxt = "calm"
        else:
            nxt = "watch"
    elif s == "disruption":
        timeout = age + 1 >= cfg.max_disruption_weeks
        nxt = "recovery" if timeout or rng.random() > cfg.disruption_persist_prob else "disruption"
    elif s == "recovery":
        nxt = "calm" if rng.random() > cfg.recovery_persist_prob else "recovery"
    else:  # false_alarm
        nxt = "calm" if age + 1 >= cfg.max_false_alarm_weeks else "false_alarm"

    return HiddenState(
        event_state=nxt,
        event_age=0 if nxt != s else age + 1,
        cape_local_congestion=rng.random() < cfg.cape_local_prob,
    )
