"""All world numbers in one place. Hand-set for the noiseless POC;
PortWatch calibration replaces the emission/transition numbers later."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorldConfig:
    horizon_weeks: int = 26

    # --- event HMM (the only stochastic root besides cape_local) ---
    onset_prob: float = 0.06            # calm -> watch
    false_alarm_prob: float = 0.04      # calm -> false_alarm
    watch_to_disruption_prob: float = 0.50
    watch_to_calm_prob: float = 0.25
    disruption_persist_prob: float = 0.85
    max_disruption_weeks: int = 8
    recovery_persist_prob: float = 0.50
    max_false_alarm_weeks: int = 2
    cape_local_prob: float = 0.08       # iid weekly local-congestion confound

    # --- noiseless weekly transit counts ---
    suez_base: int = 70
    bab_base: int = 70
    cape_base: int = 60
    suez_degraded_mult: float = 0.55
    bab_degraded_mult: float = 0.50
    recovering_mult: float = 0.80
    cape_high_mult: float = 1.35
    cape_medium_mult: float = 1.15
    seasonal_dip_mult: float = 0.90     # active during watch and false_alarm
    suppressed_mult: float = 0.55       # reporting outage during false_alarm

    # --- logistics ---
    weekly_demand: int = 20             # fixed for POC; becomes stochastic later
    order_qty: int = 20
    initial_inventory: int = 80
    suez_lead_weeks: int = 3
    suez_disrupted_lead_weeks: int = 8
    cape_lead_weeks: int = 5
    cape_congested_extra_weeks: int = 1

    # --- costs ---
    suez_unit_cost: float = 4.0
    cape_unit_cost: float = 6.0
    holding_cost: float = 1.0           # per unit per week
    stockout_cost: float = 20.0         # per unserved unit
    probe_cost: float = 30.0
