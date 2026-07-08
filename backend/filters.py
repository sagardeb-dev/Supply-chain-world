"""Phase 1 of the Bayes-filter oracle: exact per-factor HMM forward filters for
the four RICH latent modules (freight, port, quality, demand), validated
against the world's hidden tape.

Each factor's kernel is semi-Markov (regime + regime_age). Where a kernel's
transition probabilities depend on regime_age, the filter STATE is the pair
(regime, age) so the filter stays an exact discrete HMM (no age -> no belief
smearing across a hazard that's actually rising/falling). Ages are capped at
the point the kernel's own behaviour saturates (documented per factor below).

Every transition probability is pulled from WorldConfig / the module's config
table at import time -- nothing is hardcoded (project rule); each derived
number is commented with the cfg constant it came from.

Run:
    uv run python filters.py --seed 7
    uv run python filters.py --calib 20
"""

import argparse
import math
from dataclasses import dataclass

from src.world.config import WorldConfig
from src.world.engine import World
from src.world.registry import RICH

from src.world.modules.freight.config import FREIGHT_MEANS
from src.world.modules.freight.factor import freight_band
from src.world.modules.port.config import PORT_WAIT
from src.world.modules.port.factor import port_band
from src.world.modules.quality.config import QUALITY_BAND_PROBS, AQL_BANDS
from src.world.modules.demand.config import DEMAND_MEANS
from src.world.modules.demand.factor import demand_band

from src.world.modules.disruption.config import REGIME_COUNTS, CAPE_LOCAL_EXTRA

from src.world.modules.supplier.config import (SUPPLIER_SCORECARD_MASKED,
                                                SUPPLIER_LEAD_SLIP,
                                                SUPPLIER_FILL_MEAN)


# --------------------------------------------------------------------------
# Generic forward filter: predict (transition matrix) -> correct (likelihood)
# -> normalize. States are opaque labels; the caller supplies a transition
# table {state: [(next_state, prob), ...]} and a likelihood(state, obs) fn.
# --------------------------------------------------------------------------
class ForwardFilter:
    def __init__(self, states, trans, likelihood_fn, regime_of, init=None):
        self.states = states
        self.trans = trans            # {state: [(next_state, prob), ...]}
        self.likelihood_fn = likelihood_fn   # (state, obs) -> float >= 0
        self.regime_of = regime_of    # state -> regime name (for reporting)
        if init is None:
            init = {s: 1.0 / len(states) for s in states}
        self.belief = dict(init)

    def predict(self):
        nxt = {s: 0.0 for s in self.states}
        for s, p in self.belief.items():
            if p == 0.0:
                continue
            for s2, tp in self.trans[s]:
                nxt[s2] += p * tp
        self.belief = nxt

    def correct(self, obs):
        unnorm = {s: p * self.likelihood_fn(s, obs) for s, p in self.belief.items()}
        z = sum(unnorm.values())
        if z <= 0:
            # numerical dead end (shouldn't happen with Gaussian likelihoods,
            # which are always > 0) -- fall back to the predict-only belief.
            self.belief = unnorm
            return
        self.belief = {s: v / z for s, v in unnorm.items()}

    def step(self, obs):
        self.predict()
        self.correct(obs)

    def regime_posterior(self):
        """Collapse the (regime, age) belief onto regime-only mass."""
        out = {}
        for s, p in self.belief.items():
            r = self.regime_of[s]
            out[r] = out.get(r, 0.0) + p
        return out

    def argmax_regime(self):
        post = self.regime_posterior()
        r = max(post, key=post.get)
        return r, post[r]


def _norm_pdf(x, mean, sd):
    z = (x - mean) / sd
    return math.exp(-0.5 * z * z) / (sd * math.sqrt(2 * math.pi))


# --------------------------------------------------------------------------
# FREIGHT: regimes slack/normal/tightening/spike. Transition depends on age
# only for tightening (cap fr_tighten_max) and spike (cap fr_spike_max) --
# both kernels force a deterministic exit at age+1 >= cap, so ages beyond
# cap-1 never occur; we track ages 0..cap-1 exactly (no truncation needed).
# --------------------------------------------------------------------------
def build_freight_filter(cfg: WorldConfig) -> ForwardFilter:
    tmax = cfg.fr_tighten_max   # tightening ages 0..tmax-1
    smax = cfg.fr_spike_max     # spike ages 0..smax-1

    states = ["slack", "normal"]
    states += [("tightening", a) for a in range(tmax)]
    states += [("spike", a) for a in range(smax)]

    regime_of = {}
    for s in states:
        regime_of[s] = s if isinstance(s, str) else s[0]

    trans = {s: [] for s in states}

    # slack: step_freight -- r < fr_slack_persist -> slack, else normal.
    trans["slack"] = [("slack", cfg.fr_slack_persist),
                       ("normal", 1 - cfg.fr_slack_persist)]

    # normal: r < fr_tighten_onset -> tightening(age0);
    #         r < +fr_slack_onset  -> slack; else normal.
    trans["normal"] = [(("tightening", 0), cfg.fr_tighten_onset),
                        ("slack", cfg.fr_slack_onset),
                        ("normal", 1 - cfg.fr_tighten_onset - cfg.fr_slack_onset)]

    # tightening(age): r < fr_spike_onset -> spike(0);
    #   elif r < +fr_tighten_recover OR age+1>=tmax -> normal;
    #   else -> tightening(age+1).
    for a in range(tmax):
        last = (a + 1) >= tmax
        if last:
            trans[("tightening", a)] = [
                (("spike", 0), cfg.fr_spike_onset),
                ("normal", 1 - cfg.fr_spike_onset)]
        else:
            trans[("tightening", a)] = [
                (("spike", 0), cfg.fr_spike_onset),
                ("normal", cfg.fr_tighten_recover),
                (("tightening", a + 1),
                 1 - cfg.fr_spike_onset - cfg.fr_tighten_recover)]

    # spike(age): over = age+1>=smax OR r>fr_spike_persist (short-circuit, so
    # the rng draw --and hence this probability-- only matters when age+1<smax).
    for a in range(smax):
        last = (a + 1) >= smax
        if last:
            trans[("spike", a)] = [("normal", 1.0)]
        else:
            trans[("spike", a)] = [(("spike", a + 1), cfg.fr_spike_persist),
                                    ("normal", 1 - cfg.fr_spike_persist)]

    def mean_of(s):
        regime = regime_of[s]
        age = 0 if isinstance(s, str) else s[1]
        return FREIGHT_MEANS[freight_band(regime, age)] * 100  # index scale (x100)

    def likelihood(s, obs):
        m = mean_of(s)
        li = _norm_pdf(obs["freight_index"], m, cfg.fr_noise_sd * 100)
        lo = _norm_pdf(obs["freight_outlook"], m, cfg.fr_outlook_sd * 100)
        return li * lo

    return ForwardFilter(states, trans, likelihood, regime_of)


# --------------------------------------------------------------------------
# PORT: regimes clear/building/congested/customs_hold. congested's transition
# depends on age (cap port_congest_max); customs_hold's transition does NOT
# depend on age (short 1-event kernel) but its BAND does (age0 "slow" vs
# age>=1 "congested", same collapse as congested) -- so we keep two
# customs_hold states: age0 and a "persisting" absorber for age>=1 (same
# transition law + same band for every age>=1, so no need to track exact age).
# --------------------------------------------------------------------------
def build_port_filter(cfg: WorldConfig) -> ForwardFilter:
    cmax = cfg.port_congest_max  # congested ages 0..cmax-1

    states = ["clear", "building"]
    states += [("congested", a) for a in range(cmax)]
    states += [("customs_hold", 0), ("customs_hold", "persist")]

    regime_of = {}
    for s in states:
        regime_of[s] = s if isinstance(s, str) else s[0]

    trans = {s: [] for s in states}

    # clear: r < port_build_onset -> building; r < +port_customs_onset ->
    # customs_hold(age0); else clear.
    trans["clear"] = [("building", cfg.port_build_onset),
                       (("customs_hold", 0), cfg.port_customs_onset),
                       ("clear", 1 - cfg.port_build_onset - cfg.port_customs_onset)]

    # building: r < port_congest_onset -> congested(0);
    #   r < +port_build_clear -> clear; else building.
    trans["building"] = [(("congested", 0), cfg.port_congest_onset),
                          ("clear", cfg.port_build_clear),
                          ("building",
                           1 - cfg.port_congest_onset - cfg.port_build_clear)]

    # congested(age): over = age+1>=cmax OR r>port_congest_persist
    # (short-circuit: rng only drawn when age+1<cmax).
    for a in range(cmax):
        last = (a + 1) >= cmax
        if last:
            trans[("congested", a)] = [("clear", 1.0)]
        else:
            trans[("congested", a)] = [
                (("congested", a + 1), cfg.port_congest_persist),
                ("clear", 1 - cfg.port_congest_persist)]

    # customs_hold: r < port_customs_persist -> customs_hold (stays); else
    # clear. Age-independent transition; age0 and "persist" share this law.
    trans[("customs_hold", 0)] = [(("customs_hold", "persist"),
                                    cfg.port_customs_persist),
                                   ("clear", 1 - cfg.port_customs_persist)]
    trans[("customs_hold", "persist")] = [(("customs_hold", "persist"),
                                            cfg.port_customs_persist),
                                           ("clear", 1 - cfg.port_customs_persist)]

    def mean_of(s):
        regime = regime_of[s]
        if isinstance(s, str):
            age = 0
        else:
            age = 0 if s[1] == 0 else 1   # only age==0 vs age>=1 changes the band
        return PORT_WAIT[port_band(regime, age)]

    def likelihood(s, obs):
        m = mean_of(s)
        li = _norm_pdf(obs["berth_wait"], m, cfg.port_wait_noise_sd)
        lo = _norm_pdf(obs["wait_outlook"], m, cfg.port_outlook_sd)
        return li * lo

    return ForwardFilter(states, trans, likelihood, regime_of)


# --------------------------------------------------------------------------
# QUALITY: regimes in_control/drifting/out_of_control. drifting's hazard to
# out_of_control rises with age: hazard = min(1, out_base + out_age_slope*age).
# It saturates to 1.0 (deterministic exit) at
#   age >= ceil((1 - out_base) / out_age_slope)
# so we track drifting ages 0..cap exactly (cap = the first saturating age);
# age cap absorbs (transition law is identical for every age >= cap).
# Observation is the discrete AQL band -- likelihood is the exact table
# entry from QUALITY_BAND_PROBS[regime][band] (age-independent).
# --------------------------------------------------------------------------
def build_quality_filter(cfg: WorldConfig) -> ForwardFilter:
    # first age at which hazard saturates to >= 1.0
    cap = math.ceil((1.0 - cfg.q_out_base) / cfg.q_out_age_slope)

    states = ["in_control"]
    states += [("drifting", a) for a in range(cap + 1)]  # 0..cap, cap absorbs
    states += ["out_of_control"]

    regime_of = {}
    for s in states:
        regime_of[s] = s if isinstance(s, str) else s[0]

    trans = {s: [] for s in states}

    # in_control: r < q_drift_onset -> drifting(0); else in_control.
    trans["in_control"] = [(("drifting", 0), cfg.q_drift_onset),
                            ("in_control", 1 - cfg.q_drift_onset)]

    # drifting(age): hazard = min(1, out_base + out_age_slope*age).
    #   r < hazard -> out_of_control
    #   r < hazard + q_drift_recover -> in_control
    #   else -> drifting(age+1), capped at `cap` (absorbing: same law repeats).
    for a in range(cap + 1):
        hazard = min(1.0, cfg.q_out_base + cfg.q_out_age_slope * a)
        recover = min(cfg.q_drift_recover, 1 - hazard)  # hazard=1 leaves 0 left
        stay = max(0.0, 1 - hazard - recover)
        nxt_age = a if a == cap else a + 1  # cap absorbs into itself
        row = [("out_of_control", hazard), ("in_control", recover)]
        if stay > 0:
            row.append((("drifting", nxt_age), stay))
        trans[("drifting", a)] = row

    # out_of_control: r < q_out_recover -> in_control; else out_of_control.
    trans["out_of_control"] = [("in_control", cfg.q_out_recover),
                                ("out_of_control", 1 - cfg.q_out_recover)]

    band_idx = {b: i for i, b in enumerate(AQL_BANDS)}

    def likelihood(s, obs):
        regime = regime_of[s]
        band = obs["aql_result"]
        return QUALITY_BAND_PROBS[regime][band_idx[band]]

    return ForwardFilter(states, trans, likelihood, regime_of)


# --------------------------------------------------------------------------
# DEMAND: regimes normal/promo_spike/seasonal_lift/structural_decline.
# promo_spike is a DETERMINISTIC fixed-length event (age+1>=demand_promo_max
# forces normal, no rng draw at all) -- ages 0..promo_max-1.
# seasonal_lift has an age-capped hazard (short-circuit like port/freight) --
# ages 0..seasonal_max-1. structural_decline's persistence does not depend on
# age -> a single absorbing-ish state.
# --------------------------------------------------------------------------
def build_demand_filter(cfg: WorldConfig) -> ForwardFilter:
    pmax = cfg.demand_promo_max
    smax = cfg.demand_seasonal_max

    states = ["normal", "structural_decline"]
    states += [("promo_spike", a) for a in range(pmax)]
    states += [("seasonal_lift", a) for a in range(smax)]

    regime_of = {}
    for s in states:
        regime_of[s] = s if isinstance(s, str) else s[0]

    trans = {s: [] for s in states}

    # normal: r < demand_promo_onset -> promo_spike(0);
    #   r < +demand_seasonal_onset -> seasonal_lift(0);
    #   r < +demand_decline_onset -> structural_decline; else normal.
    p_on, s_on, d_on = (cfg.demand_promo_onset, cfg.demand_seasonal_onset,
                         cfg.demand_decline_onset)
    trans["normal"] = [(("promo_spike", 0), p_on),
                        (("seasonal_lift", 0), s_on),
                        ("structural_decline", d_on),
                        ("normal", 1 - p_on - s_on - d_on)]

    # promo_spike(age): deterministic countdown, no rng -- age+1>=pmax->normal.
    for a in range(pmax):
        if a + 1 >= pmax:
            trans[("promo_spike", a)] = [("normal", 1.0)]
        else:
            trans[("promo_spike", a)] = [(("promo_spike", a + 1), 1.0)]

    # seasonal_lift(age): over = age+1>=smax OR r>demand_seasonal_persist
    # (short-circuit: rng only drawn when age+1<smax).
    for a in range(smax):
        if a + 1 >= smax:
            trans[("seasonal_lift", a)] = [("normal", 1.0)]
        else:
            trans[("seasonal_lift", a)] = [
                (("seasonal_lift", a + 1), cfg.demand_seasonal_persist),
                ("normal", 1 - cfg.demand_seasonal_persist)]

    # structural_decline: r < demand_decline_persist -> stays; else normal.
    trans["structural_decline"] = [
        ("structural_decline", cfg.demand_decline_persist),
        ("normal", 1 - cfg.demand_decline_persist)]

    def mean_of(s):
        regime = regime_of[s]
        age = 0 if isinstance(s, str) else s[1]
        return DEMAND_MEANS[demand_band(regime, age)]

    def likelihood(s, obs):
        m = mean_of(s)
        li = _norm_pdf(obs["pos_units"], m, cfg.demand_noise_sd)
        lo = _norm_pdf(obs["demand_forecast"], m, cfg.demand_forecast_sd)
        return li * lo

    return ForwardFilter(states, trans, likelihood, regime_of)


# --------------------------------------------------------------------------
# DISRUPTION: event_state calm/watch/disruption/recovery/false_alarm, plus
# disruption_type (short/long, drawn at onset) and event_age. The kernel is
# Markov in (event_state, disruption_type, event_age); we track exactly the
# age resolution each branch's transition law actually needs:
#   - calm/watch/false_alarm: no age dependence -> single state each.
#   - disruption/short: transition depends on age (cap max_short_weeks) ->
#     explicit ages 0..max_short_weeks-1, forced exit at the cap (same
#     short-circuit pattern as freight/port's capped regimes above).
#   - disruption/long: NO age cap in the kernel (pure geometric persistence,
#     rng.random() > long_persist_prob every week) -> transition law is
#     identical for every age, so (like port's customs_hold) we collapse to
#     age0 (emits "crash", shares the week-1 ambiguity with false_alarm and
#     short's age0) and a "persist" absorber for age>=1 (emits "crisis").
#   - recovery: transition depends on age (cap max_recovery_weeks) -> tracked
#     explicitly 0..max_recovery_weeks-1, same pattern as freight/tightening.
#
# cape_local_congestion is a SECOND hidden bit (an iid weekly coin, rng.random()
# < cape_local_prob) that the kernel draws every step but which is otherwise
# stateless: it never feeds back into event_state/type/age, and the emission
# code reads only the CURRENT week's draw. Because it carries no memory, we do
# NOT add it as a persistent filter-state coordinate (that would double the
# state space for no gain); instead we marginalize it EXACTLY inside the
# emission likelihood every step: given the true regime's baseline
# (suez, bab, cape) count triple, cape_count must equal either the baseline
# (prob 1 - cape_local_prob, coin off) or baseline + CAPE_LOCAL_EXTRA (prob
# cape_local_prob, coin on) -- any other observed cape_count is impossible
# under that regime hypothesis (weight 0). This is mathematically identical
# to carrying the bit as an explicit iid factor and summing it out at every
# correct() step; we just do the sum in closed form instead of doubling the
# state list. suez_count/bab_count are noiseless exact lookups on the regime
# (REGIME_COUNTS), so they gate with a hard 0/1 match. The bulletin string is
# a pure function of the SAME visible regime the counts already key off of
# (R1 in emission.py's docstring), so it carries zero additional discriminating
# information beyond the counts and is not separately scored.
# --------------------------------------------------------------------------
def build_disruption_filter(cfg: WorldConfig) -> ForwardFilter:
    smax = cfg.max_short_weeks     # disruption/short ages 0..smax-1
    rmax = cfg.max_recovery_weeks  # recovery ages 0..rmax-1

    states = ["calm", "watch", "false_alarm"]
    states += [("disruption", "short", a) for a in range(smax)]
    states += [("disruption", "long", 0), ("disruption", "long", "persist")]
    states += [("recovery", a) for a in range(rmax)]

    def event_state_of(s):
        """Collapse to the raw event_state -- the ground-truth granularity
        recorded as hidden_states['disruption']['event_state'] (NOT the
        visible-regime 'crash'/'blockage'/'crisis' collapse, which is a
        strictly finer emission-table key computed separately below)."""
        if isinstance(s, str):
            return s
        return s[0]  # "disruption" or "recovery"

    regime_of = {s: event_state_of(s) for s in states}

    trans = {s: [] for s in states}

    # calm: r < onset_prob -> watch; else calm.
    trans["calm"] = [("watch", cfg.onset_prob), ("calm", 1 - cfg.onset_prob)]

    # watch: r < watch_to_disruption_prob -> disruption(type, age0), type
    #   drawn short w.p. short_disruption_prob else long (second rng draw,
    #   independent of the first -- exact joint probability is the product);
    #   r < +watch_to_false_alarm_prob -> false_alarm;
    #   r < +watch_to_calm_prob -> calm; else watch.
    p_dis, p_fa, p_calm = (cfg.watch_to_disruption_prob,
                            cfg.watch_to_false_alarm_prob,
                            cfg.watch_to_calm_prob)
    trans["watch"] = [
        (("disruption", "short", 0), p_dis * cfg.short_disruption_prob),
        (("disruption", "long", 0), p_dis * (1 - cfg.short_disruption_prob)),
        ("false_alarm", p_fa),
        ("calm", p_calm),
        ("watch", 1 - p_dis - p_fa - p_calm),
    ]

    # false_alarm: resolves within the week -> calm, deterministic.
    trans["false_alarm"] = [("calm", 1.0)]

    # disruption/short(age): over = age+1>=smax OR r>short_persist_prob
    # (short-circuit: rng only drawn when age+1<smax) -> recovery(age0).
    for a in range(smax):
        last = (a + 1) >= smax
        if last:
            trans[("disruption", "short", a)] = [(("recovery", 0), 1.0)]
        else:
            trans[("disruption", "short", a)] = [
                (("disruption", "short", a + 1), cfg.short_persist_prob),
                (("recovery", 0), 1 - cfg.short_persist_prob)]

    # disruption/long: no age cap -- r > long_persist_prob -> recovery(age0);
    # else stays (collapses to the "persist" absorber, same law both ages).
    for s in [("disruption", "long", 0), ("disruption", "long", "persist")]:
        trans[s] = [(("disruption", "long", "persist"), cfg.long_persist_prob),
                    (("recovery", 0), 1 - cfg.long_persist_prob)]

    # recovery(age): over = age+1>=rmax OR r>recovery_persist_prob
    # (short-circuit) -> calm.
    for a in range(rmax):
        last = (a + 1) >= rmax
        if last:
            trans[("recovery", a)] = [("calm", 1.0)]
        else:
            trans[("recovery", a)] = [
                (("recovery", a + 1), cfg.recovery_persist_prob),
                ("calm", 1 - cfg.recovery_persist_prob)]

    def visible_band(s):
        """The finer emission-table key (HiddenState.regime): the "crash"
        ambiguity is where false_alarm, disruption/short age0, and
        disruption/long age0 all share one counts fingerprint."""
        if isinstance(s, str):
            return "crash" if s == "false_alarm" else s  # calm/watch/false_alarm
        kind = s[0]
        if kind == "recovery":
            return "recovery"
        _, dtype, a = s
        if a == 0:
            return "crash"
        return "blockage" if dtype == "short" else "crisis"

    def likelihood(s, obs):
        band = visible_band(s)
        suez, bab, cape = REGIME_COUNTS[band]
        if obs["suez_count"] != suez or obs["bab_count"] != bab:
            return 0.0
        p = cfg.cape_local_prob
        if obs["cape_count"] == cape:
            return 1 - p          # cape_local coin off (marginalized exactly)
        if obs["cape_count"] == cape + CAPE_LOCAL_EXTRA:
            return p              # cape_local coin on
        return 0.0

    return ForwardFilter(states, trans, likelihood, regime_of)


# --------------------------------------------------------------------------
# SUPPLIER (spot only): rel_state reliable/wobbling/degraded/defunct, rel_age
# (used only within "degraded", capped at sup_max_degraded -- same
# short-circuit forced-exit pattern as the factors above). In the default
# masked CORE/RICH world (sup_all_drift=False, the flag replay() always
# sets), DRIVES(cfg) == ("spot",) -- qualified/backup are frozen and never
# drift, so they carry no filterable signal; we filter spot only.
#
# Two emission channels, both read off SPOT's row in obs["suppliers"]:
#   - "band": cfg.sup_mask_otif routes the TRUE visible band (ontime/
#     slipping/failing/defunct, from SupplierState.regime -- itself already
#     collapsing wobbling and degraded-age0 into "slipping") through
#     SUPPLIER_SCORECARD_MASKED, a fixed, noiseless (not random) lookup that
#     LAGS the true band by ~one severity step. Because that lookup is
#     deterministic, the band term is a hard 0/1 gate on the true regime
#     hypothesis -- not a noisy likelihood -- and it is the mechanism that
#     manufactures ambiguity: SCORECARD_MASKED sends BOTH "ontime" (true
#     reliable) and "slipping" (true wobbling, i.e. degraded-age0 too) to the
#     displayed band "ontime", so the band alone cannot separate
#     reliable/wobbling -- exactly what the noisy realized_lead_slip channel
#     below is for.
#   - "realized_lead_slip": present every week (masked task), a Gaussian
#     sensor around SUPPLIER_LEAD_SLIP[rel_state] (mean depends on rel_state
#     only, not rel_age -- the table has no age axis).
#   - "realized_fill" (top-level obs key, NOT in the scorecard row): present
#     ONLY on weeks the agent actually sourced spot this week (engine.py
#     gates it on `qty and supplier and supplier in DRIVES(cfg)`). In the
#     passive replay() tape (empty {} actions every week -> qty is always
#     falsy) this key is therefore absent every week, so its likelihood term
#     never fires here. When grading a real LLM agent trace, which DOES place
#     spot orders, this term activates on exactly those weeks and should
#     sharpen the posterior on ordering weeks -- .step()/likelihood() below
#     already handle that generically (skip the term iff the key is absent).
# --------------------------------------------------------------------------
def build_supplier_filter(cfg: WorldConfig) -> ForwardFilter:
    dmax = cfg.sup_max_degraded  # degraded ages 0..dmax-1

    states = ["reliable", "wobbling", "defunct"]
    states += [("degraded", a) for a in range(dmax)]

    def rel_state_of(s):
        return s if isinstance(s, str) else s[0]

    regime_of = {s: rel_state_of(s) for s in states}

    trans = {s: [] for s in states}

    # reliable: r < sup_onset_prob -> wobbling; else reliable.
    trans["reliable"] = [("wobbling", cfg.sup_onset_prob),
                          ("reliable", 1 - cfg.sup_onset_prob)]

    # wobbling: r < sup_wobble_to_degraded -> degraded(age0);
    #   r < +sup_wobble_to_reliable -> reliable; else wobbling.
    w_deg, w_rel = cfg.sup_wobble_to_degraded, cfg.sup_wobble_to_reliable
    trans["wobbling"] = [(("degraded", 0), w_deg),
                          ("reliable", w_rel),
                          ("wobbling", 1 - w_deg - w_rel)]

    # defunct: Lever 1, absorbing for the episode.
    trans["defunct"] = [("defunct", 1.0)]

    # degraded(age): first hazard to defunct (df); of the remaining mass,
    # over = age+1>=dmax OR r>degraded_persist (short-circuit, same law as
    # the capped regimes above) -> reliable, else -> degraded(age+1).
    df, persist = cfg.sup_defunct_from_degraded, cfg.sup_degraded_persist
    for a in range(dmax):
        last = (a + 1) >= dmax
        row = [("defunct", df)]
        if last:
            row.append(("reliable", 1 - df))
        else:
            row.append(("reliable", (1 - df) * (1 - persist)))
            row.append((("degraded", a + 1), (1 - df) * persist))
        trans[("degraded", a)] = row

    def true_band(s):
        """SupplierState.regime for this filter-state hypothesis: the
        wobbling/degraded-age0 collapse into 'slipping' the masking table
        keys off."""
        rs = rel_state_of(s)
        if rs == "reliable":
            return "ontime"
        if rs == "wobbling":
            return "slipping"
        if rs == "defunct":
            return "defunct"
        _, a = s
        return "slipping" if a == 0 else "failing"

    def spot_row(obs):
        for row in obs["suppliers"]:
            if row["id"] == "spot":
                return row
        return None

    def likelihood(s, obs):
        rs = rel_state_of(s)
        row = spot_row(obs)
        if row is None:
            return 1.0  # no spot row this week (shouldn't happen; defensive)
        # band: deterministic (noiseless) lookup -> hard 0/1 gate.
        apparent, _otif, _lead = SUPPLIER_SCORECARD_MASKED[true_band(s)]
        if row["band"] != apparent:
            return 0.0
        lik = 1.0
        # realized_lead_slip: Gaussian around the TRUE rel_state's mean.
        if "realized_lead_slip" in row:
            lik *= _norm_pdf(row["realized_lead_slip"],
                             SUPPLIER_LEAD_SLIP[rs], cfg.sup_lead_slip_sd)
        # realized_fill: only present on weeks spot was actually sourced from
        # (conditional observation -- absent in the passive replay() tape,
        # present on an LLM agent's ordering weeks). Skip gracefully if
        # missing rather than treating the absence itself as a value.
        if "realized_fill" in obs:
            lik *= _norm_pdf(obs["realized_fill"],
                             SUPPLIER_FILL_MEAN[rs], cfg.sup_fill_sd)
        return lik

    return ForwardFilter(states, trans, likelihood, regime_of)


FACTORS = {
    "freight": (build_freight_filter, "freight"),
    "port": (build_port_filter, "port"),
    "quality": (build_quality_filter, "quality"),
    "demand": (build_demand_filter, "demand"),
    "disruption": (build_disruption_filter, "disruption"),
    "supplier": (build_supplier_filter, "supplier"),
}


def _true_regime(rec, factor):
    """Ground-truth regime for `factor` at this trace record. Quality/demand
    are stored as rosters ({id: state}); the RICH single-product world runs
    a singleton id under each ("" for quality, the one finished good for
    demand) -- filter to it. disruption/supplier don't use the generic
    "regime" key: disruption's raw ground truth is "event_state" (the
    filter's regime_of collapses to this same granularity, NOT the finer
    "regime" band-collapse key used only for emission); supplier is a roster
    keyed by supplier id ("spot" here, matching build_supplier_filter's
    spot-only scope), and its raw ground truth is "rel_state"."""
    hs = rec["hidden_states"][factor]
    if factor == "quality":
        return hs["regime"]
    if factor == "demand":
        (_fg, st), = hs.items()
        return st["regime"]
    if factor == "disruption":
        return hs["event_state"]
    if factor == "supplier":
        return hs["spot"]["rel_state"]
    return hs["regime"]


@dataclass
class Run:
    weeks: list          # per-week dicts: {factor: (pred_regime, prob, true_regime)}
    n_weeks: int


def replay(seed: int, cfg: WorldConfig = None) -> Run:
    # match the agent harness (runner.AgentRun): masked task. The supplier
    # module draws extra rng per week when masked, so a plain WorldConfig()
    # replay walks a DIFFERENT tape than the LLM runs on the same seed.
    cfg = cfg or WorldConfig(sup_mask_otif=True)
    w = World(cfg, registry=RICH)
    w.reset(seed)
    while not w.done:
        w.step({})

    filters = {f: build(cfg) for f, (build, _) in FACTORS.items()}
    weeks = []
    # trace[0] is the week-0 reset record (no action yet, week counter 0);
    # the filter should consume every observation the same way the world
    # emits them, one record per elapsed week (skip the seed record, whose
    # obs is week-0's initial draw -- it IS a real observation).
    for rec in w.trace:
        obs = rec["obs"]
        row = {}
        for f in FACTORS:
            filters[f].step(obs)
            pred, prob = filters[f].argmax_regime()
            true = _true_regime(rec, f)
            row[f] = (pred, prob, true)
        weeks.append(row)
    return Run(weeks=weeks, n_weeks=len(weeks))


def detection_lags(weeks, factor):
    """Weeks from each TRUE regime change to the first week the posterior
    argmax matches the new regime (censored changes near the tape end are
    dropped)."""
    lags = []
    prev_true = None
    change_week = None
    for i, row in enumerate(weeks):
        pred, _, true = row[factor]
        if prev_true is not None and true != prev_true:
            change_week = i
        if change_week is not None and pred == true:
            lags.append(i - change_week)
            change_week = None
        prev_true = true
    return lags


def accuracy(weeks, factor):
    correct = sum(1 for row in weeks if row[factor][0] == row[factor][2])
    return correct / len(weeks)


def print_seed_table(run: Run, seed: int):
    factors = list(FACTORS)
    header = f"{'wk':>3} | " + " | ".join(f"{f:^28}" for f in factors)
    print(f"--- seed {seed}: weekly posterior-argmax vs true regime ---")
    print(header)
    print("-" * len(header))
    for i, row in enumerate(run.weeks):
        cells = []
        for f in factors:
            pred, prob, true = row[f]
            mark = "" if pred == true else " <-- MISMATCH"
            cells.append(f"{pred}({prob:.2f}) true={true}{mark}")
        print(f"{i:>3} | " + " | ".join(f"{c:<28}" for c in cells))
    print()
    for f in factors:
        acc = accuracy(run.weeks, f) * 100
        lags = detection_lags(run.weeks, f)
        lag_str = f"mean={sum(lags)/len(lags):.2f} (n={len(lags)})" if lags else "n/a"
        print(f"{f:>8}: argmax accuracy {acc:5.1f}%   detection lag {lag_str}")


def calibrate(n_seeds: int, base_seed: int = 100):
    factors = list(FACTORS)
    accs = {f: [] for f in factors}
    lags = {f: [] for f in factors}
    for i in range(n_seeds):
        run = replay(base_seed + i)
        for f in factors:
            accs[f].append(accuracy(run.weeks, f))
            lags[f].extend(detection_lags(run.weeks, f))
    print(f"--- calibration over {n_seeds} seeds ---")
    for f in factors:
        mean_acc = sum(accs[f]) / len(accs[f]) * 100
        mean_lag = sum(lags[f]) / len(lags[f]) if lags[f] else float("nan")
        print(f"{f:>8}: mean argmax accuracy {mean_acc:5.1f}%   "
              f"mean detection lag {mean_lag:.2f} (n={len(lags[f])} regime changes)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--calib", type=int, nargs="?", const=20, default=None)
    args = ap.parse_args()

    if args.calib is not None:
        calibrate(args.calib)
        return

    seed = args.seed if args.seed is not None else 7
    run = replay(seed)
    print_seed_table(run, seed)


if __name__ == "__main__":
    main()
