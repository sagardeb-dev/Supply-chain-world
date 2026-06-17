"""Hidden-state evolution. Pure function of (state, rng, cfg); never reads
actions, so the trajectory is a function of the seed alone (exogeneity)."""

import random

from .config import WorldConfig
from .state import HiddenState, SupplierState


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


def step_supplier(sup: SupplierState, rng: random.Random,
                  cfg: WorldConfig) -> SupplierState:
    """Advance the spot supplier's reliability factor. Sibling of step_hidden,
    same rng (exogeneity: actions never consume it). Reads ONLY SupplierState
    -- never the disruption state -- so the two latent modules are transition
    independent (Becker Def. 2) and debuggable in isolation.

    Runs UNCONDITIONALLY every week (the supplier drifts whether or not you
    source from it), which is what makes the scorecard a free side-channel."""
    s, age = sup.rel_state, sup.rel_age
    if s == "reliable":
        nxt = "wobbling" if rng.random() < cfg.sup_onset_prob else "reliable"
    elif s == "wobbling":
        r = rng.random()
        if r < cfg.sup_wobble_to_degraded:
            nxt = "degraded"
        elif r < cfg.sup_wobble_to_degraded + cfg.sup_wobble_to_reliable:
            nxt = "reliable"
        else:
            nxt = "wobbling"
    elif s == "defunct":
        # Lever 1: absorbing. A dead supplier stays dead for the episode.
        return sup
    else:  # degraded
        # First check the death hazard (degraded is the only entry to defunct);
        # then the recover-or-persist branch as before.
        if rng.random() < cfg.sup_defunct_from_degraded:
            nxt = "defunct"
        else:
            over = (age + 1 >= cfg.sup_max_degraded
                    or rng.random() > cfg.sup_degraded_persist)
            nxt = "reliable" if over else "degraded"
    return SupplierState(rel_state=nxt, rel_age=0 if nxt != s else age + 1)
