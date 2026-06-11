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


@dataclass(frozen=True)
class WorldConfig:
    horizon_weeks: int = 26

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
    order_qty: int = 20
    initial_inventory: int = 80
    suez_unit_cost: float = 4.0
    cape_unit_cost: float = 6.0           # ~1.5x Suez operating cost
    holding_cost: float = 1.0             # per unit per week, on-hand AND in-transit
    stockout_cost: float = 20.0           # scarcity premium (crisis rates 3-5x)
    probe_cost: float = 30.0              # paid intelligence: regime + type, now
