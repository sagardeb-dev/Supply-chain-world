"""Tier 1 — the disruption latent module (sealed box).

The event HMM (state+age), the disruption type drawn at onset, and the iid
cape_local coin: one stochastic root, visible to the agent as transit counts
plus a trade-press bulletin. Everything this factor owns lives here — its
hidden state, its kernel, its emission, its text vocabulary, and the Module
record the registry composes.

SEALED BOX: this file NEVER imports the supplier module (transition +
observation independence => the joint belief stays factored, Becker Def. 2).
It imports only config (shared knobs/tables) — config is not a tier-1 peer.
"""

import random
from dataclasses import dataclass, asdict

from ..config import CAPE_LOCAL_EXTRA, REGIME_COUNTS, WorldConfig

EVENT_STATES = ("calm", "watch", "disruption", "recovery", "false_alarm")
DISRUPTION_TYPES = ("short", "long")


# --- state ----------------------------------------------------------------

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


# --- kernel ---------------------------------------------------------------

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


# --- text vocabulary (two parallel semantics; identical information) -------
# R1 - bulletins are a pure function of HiddenState.regime, so the shared
#      "crash" regime makes false_alarm and week-0 of either disruption type
#      byte-identical, mirroring the count ambiguity exactly.
# R2 - no duration or probability language: the duration prior IS the domain
#      knowledge being measured.
# R3 - both modes carry identical information (same revelation timing).

BULLETINS = {
    "real": {
        "calm": ("Shipping lanes normal. Suez Canal and Bab-el-Mandeb "
                 "transits at seasonal levels; Cape routing remains a "
                 "niche choice."),
        "watch": ("Carriers report elevated tensions in the Red Sea "
                  "corridor. Some operators are holding sailings or "
                  "adding war-risk surcharges; transits have dipped."),
        "crash": ("BREAKING: incident reported in the Suez/Red Sea "
                  "corridor. Carriers are pausing transits pending "
                  "assessment; details remain unconfirmed."),
        "blockage": ("A grounded container vessel is blocking the Suez "
                     "Canal. Salvage crews are on site; the waterway is "
                     "impassable and convoys are anchored at both ends."),
        "crisis": ("Armed attacks on commercial shipping continue in the "
                   "Red Sea. Major carriers have suspended Suez transits "
                   "and are diverting around the Cape of Good Hope."),
        "recovery": ("The Suez corridor is reopening. The queued backlog "
                     "is being cleared in convoys; schedules remain "
                     "disrupted."),
    },
    "anon": {
        "calm": ("Shipping lanes normal. Waterway One and its approach "
                 "strait show seasonal transit levels; Waterway Two "
                 "remains a niche choice."),
        "watch": ("Carriers report elevated risk indicators on the "
                  "Waterway One corridor. Some operators are holding "
                  "sailings; transits have dipped."),
        "crash": ("ALERT: incident reported on the Waterway One corridor. "
                  "Carriers are pausing transits pending assessment; "
                  "details remain unconfirmed."),
        "blockage": ("Waterway One is closed by a Class-A incident. The "
                     "waterway is impassable and vessels are anchored at "
                     "both ends."),
        "crisis": ("A Class-B incident is ongoing on the Waterway One "
                   "corridor. Major carriers have suspended transits and "
                   "are diverting via Waterway Two."),
        "recovery": ("The Waterway One corridor is reopening. The queued "
                     "backlog is being cleared; schedules remain "
                     "disrupted."),
    },
}

# Briefing keys: event_state, except disruption uses the hidden type -
# the type reveal is the briefing entire value at the crash week.
BRIEFINGS = {
    "real": {
        "calm": "Assessment: no unusual activity on the lane.",
        "watch": ("Assessment: the elevated risk is genuine; an incident "
                  "on the corridor is plausible."),
        "false_alarm": ("Assessment: the reported incident is a false "
                        "alarm - no physical disruption on the ground."),
        "short": ("Assessment: this is a vessel-grounding-class blockage "
                  "of the Suez Canal."),
        "long": ("Assessment: this is a security-crisis-class disruption "
                 "of the Red Sea corridor."),
        "recovery": ("Assessment: the disruption has ended; the transit "
                     "backlog is clearing."),
    },
    "anon": {
        "calm": "Assessment: no unusual activity on the lane.",
        "watch": ("Assessment: the elevated risk is genuine; an incident "
                  "on the corridor is plausible."),
        "false_alarm": ("Assessment: the reported incident is a false "
                        "alarm - no physical disruption."),
        "short": "Assessment: this is a Class-A incident on Waterway One.",
        "long": "Assessment: this is a Class-B incident on Waterway One.",
        "recovery": ("Assessment: the disruption has ended; the transit "
                     "backlog is clearing."),
    },
}

# The count-key rename for the anon ablation (this factor's own keys).
COUNT_KEYS = {
    "real": {"suez_count": "suez_count", "bab_count": "bab_count",
             "cape_count": "cape_count"},
    "anon": {"suez_count": "waterway1_count", "bab_count": "strait_count",
             "cape_count": "waterway2_count"},
}


# --- emission (noiseless: counts are an exact lookup on the visible regime) -

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


# --- the module's emit/view (registry composes them into a Module record) --
# This file does NOT import the registry (which imports this file): modules are
# pure state+kernel+emission, and registry.py is the sole place that knows the
# Module record shape. That one-way dependency is what breaks the cycle.

def emit(h: HiddenState, cfg: WorldConfig) -> dict:
    """Exactly the slice _build_obs assembled by hand: the count keys
    (renamed through the per-semantics map) plus the bulletin."""
    keymap = COUNT_KEYS[cfg.semantics]
    counts = observe_counts(h, cfg)
    obs = {keymap[k]: v for k, v in counts.items()}
    obs["bulletin"] = news_bulletin(h, cfg)
    return obs


def view(cfg: WorldConfig) -> dict:
    keymap = COUNT_KEYS[cfg.semantics]
    v = {keymap[k]: {"role": "scalar", "label": keymap[k]}
         for k in ("suez_count", "bab_count", "cape_count")}
    v["bulletin"] = {"role": "series", "label": "bulletin"}
    return v


# drives=("",): the singleton world-state, not a roster id.
DRIVES = ("",)
