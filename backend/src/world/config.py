"""All world numbers in one place. 1 tick = 1 week, Asia-Europe lane.
Every calibrated number traces to a real-world statistic pinned in
V1_CHANGE_LOG.md (2026-06-11 entry)."""

from dataclasses import dataclass

# Noiseless weekly transit counts (suez, bab, cape), keyed by visible regime.
# "crash" is shared by false_alarm AND the first week of either disruption
# type — the deliberate ambiguity. One week later the regimes separate.
REGIME_COUNTS = {
    "calm":     (70, 70, 60),
    "watch":    (63, 63, 60),   # caution dip ~10%
    "crash":    (28, 25, 66),   # news breaks: transits crash, small cape uptick
    "blockage": (0, 0, 72),     # short type, age>=1: canal physically shut
    "crisis":   (14, 10, 96),   # long type, age>=1: -75/-90% transits, cape +60%
    "recovery": (56, 56, 69),   # backlog clearing
}
CAPE_LOCAL_EXTRA = 21           # iid local Cape-port congestion, cape channel only

# OTIF scorecard bands: noiseless readout of SupplierState.regime (factor 2).
# "slipping" is SHARED by wobbling AND degraded-onset -- the supplier analogue
# of the disruption "crash" ambiguity. (otif_pct, lead_days_quoted)
SUPPLIER_SCORECARD = {
    "ontime":   (98, 14),
    "slipping": (82, 18),
    "failing":  (55, 28),
    "defunct":  (None, None),   # dead supplier: OTIF '-' on the scorecard
}


# Per-supplier display profile (factor-2 roster). Self-contained: each entry
# declares everything the scorecard row needs, so _supplier_row has no
# instance-name branch and adding supplier #4 is one entry ("Nth costs the
# same as 2nd").
#   drifts       -- True: OTIF/lead/band read from the SupplierState chain;
#                   False: show the constant otif/lead below, band "ontime".
#   otif/lead    -- frozen suppliers' constants (None for a drifting one).
#   onboard_weeks-- weeks before this supplier's FIRST order can ship.
#   econ         -- unit economics vs the route base cost. "attr" names the
#                   WorldConfig field holding the magnitude (cfg stays the
#                   single source of truth -- the cost arithmetic in
#                   logistics/oracle reads the SAME fields). "sign" is the
#                   direction of unit_delta; "key" is the extra display key
#                   (unit_discount / unit_premium), or None for just a delta.
SUPPLIERS = {
    "qualified": {"drifts": False, "otif": 99, "lead": 14, "onboard_weeks": 0,
                  "econ": {"attr": "qualified_premium", "sign": 1,
                           "key": "unit_premium"}},
    "spot":      {"drifts": True,  "otif": None, "lead": None, "onboard_weeks": 0,
                  "econ": {"attr": "spot_unit_discount", "sign": -1,
                           "key": "unit_discount"}},
    "backup":    {"drifts": False, "otif": 95, "lead": 16, "onboard_weeks": 1,
                  "econ": {"attr": "backup_unit_delta", "sign": 1, "key": None}},
}


@dataclass(frozen=True)
class WorldConfig:
    horizon_weeks: int = 26
    semantics: str = "real"             # "real" | "anon" - presentation layer only (R3/R4)

    # --- event semi-Markov kernel (stochastic root #1) ---
    onset_prob: float = 0.08              # calm -> watch; ~2 threat episodes/half-year
    watch_to_disruption_prob: float = 0.50
    watch_to_false_alarm_prob: float = 0.20
    watch_to_calm_prob: float = 0.15      # remainder stays watch
    short_disruption_prob: float = 0.70   # P(type=short | onset)
    short_persist_prob: float = 0.50      # Ever Given: ~1 weekly tick, sometimes 2
    max_short_weeks: int = 2
    long_persist_prob: float = 0.92       # Red Sea: mean ~12.5 wks, horizon-bounded
    recovery_persist_prob: float = 0.50
    max_recovery_weeks: int = 3
    cape_local_prob: float = 0.08         # stochastic root #2: iid weekly coin

    # --- supplier S reliability semi-Markov kernel (stochastic root #3) ---
    # Fully independent of the disruption kernel (Becker transition independence):
    # this factor's next state reads ONLY SupplierState. Its own latent module.
    sup_onset_prob: float = 0.10          # reliable -> wobbling; spot sources drift
    sup_wobble_to_degraded: float = 0.45  # the slip becomes real failure
    sup_wobble_to_reliable: float = 0.35  # the slip recovers (a false scare)
    sup_degraded_persist: float = 0.70    # degraded spells run ~3 wks
    sup_max_degraded: int = 4
    # Lever 1 (the defunct primitive): per-week hazard that a chronically
    # failing (degraded) supplier dies for good. ~16% tech-sector bankruptcy /
    # 14.5% of disruptions are supplier failures -> a few % per week from
    # degraded gives a realistic 'distressed -> dead' tail. Absorbing.
    sup_defunct_from_degraded: float = 0.06
    # --- supplier economics ---
    spot_unit_discount: float = 1.5       # S is 1.5/unit cheaper than Q's lane cost
    qualified_premium: float = 1.0        # Q adds 1.0/unit over the route base cost
    # --- backup supplier (Hangzhou) economics. OTIF/lead/onboarding live in
    # the SUPPLIERS profile (display facts); only the unit delta is a cost knob.
    backup_unit_delta: float = 0.3        # a small premium (dearer than spot, < Q)
    # --- contracts (R4): a timer + terms. Default length; menu of lengths R5 ---
    contract_weeks: int = 8               # ~3 renewal events per 26-wk horizon
    contract_otif_floor: int = 85         # penalty clause threshold (R5)
    contract_break_fee: float = 10.0      # early-exit cost (irreversibility teeth)
    # Lever 3: weekly overhead for carrying >=2 live contracts (managing two
    # supplier relationships). The ONLY thing authored for dual-sourcing; the
    # STRATEGY emerges as the agent's response to this vs spot's volatility.
    dual_source_overhead: float = 4.0
    # The cost COUPLING knob (Becker JV term): a spot shortfall during a
    # disruption-active week is back-ordered at the crisis spot rate. Set to
    # 3x the stockout cost so gambling on spot when the Red Sea is twitchy is
    # punishing -- this is the only calibration knob the hedge turns on.
    crisis_backorder_kappa: float = 60.0  # = 3.0 x stockout_cost

    # --- voyage geometry (transit-week causality) ---
    suez_total_weeks: int = 3             # ~28 days Shanghai-Rotterdam
    suez_chokepoint_offset: int = 2       # canal transit ~day 20 of 28
    recovery_queue_extra_weeks: int = 1   # post-blockage backlog
    divert_extra_weeks: int = 3           # queued ship reroutes around the Cape
    cape_total_weeks: int = 4             # ~40 days (+10-14 vs Suez)
    cape_chokepoint_offset: int = 2       # Cape rounding / SA port congestion point
    cape_congested_extra_weeks: int = 1

    # --- demand & costs ---
    weekly_demand: int = 20
    order_quantities: tuple = (0, 20, 40)  # no order / one ship / two ships
    initial_inventory: int = 80
    suez_unit_cost: float = 4.0
    cape_unit_cost: float = 6.0           # ~1.5x Suez operating cost
    holding_cost: float = 1.0             # per unit per week, on-hand AND in-transit
    stockout_cost: float = 20.0           # scarcity premium (crisis rates 3-5x)
    briefing_cost: float = 30.0           # paid analyst assessment, bought pre-decision
