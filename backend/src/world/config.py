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
    # --- supplier economics ---
    spot_unit_discount: float = 1.5       # S is 1.5/unit cheaper than Q's lane cost
    qualified_premium: float = 1.0        # Q adds 1.0/unit over the route base cost

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
