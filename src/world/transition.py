"""Hidden-state evolution. Pure function of (state, rng, cfg); never reads
actions, so the trajectory is a function of the seed alone (exogeneity)."""

import random

from .config import WorldConfig
from .state import HiddenState


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
