"""All world numbers in one place. 1 tick = 1 week, Asia-Europe lane.
Every calibrated number traces to a real-world statistic pinned in
V1_CHANGE_LOG.md (2026-06-11 entry)."""

from dataclasses import dataclass

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
    # --- masked-distress task: the spot supplier's OTIF scorecard LAGS its true
    # reliability (a gameable contractual metric); the timely truth lives in two
    # noisy "books" channels (realized_fill + realized_lead_slip) and
    # request_audit() buys a sharpened read of the CURRENT hidden regime. The
    # skill measured: does the agent mine its own delivery history instead of
    # trusting the green scorecard. The agent harness turns this ON; the flag
    # only stays False here so the legacy single-shot supplier tests still run.
    sup_mask_otif: bool = False
    audit_cost: float = 25.0              # paid supplier audit; tune vs runs (VOI knob)
    sup_lead_slip_sd: float = 2.5         # noise sd of the realized-lead-slip sensor
    sup_fill_sd: float = 0.12             # noise sd of the realized-fill draw (so a
                                          # single partial fill no longer IDs the regime)
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

    # --- demand semi-Markov kernel (latent module #3, RICH worlds only) ---
    # Unused unless the demand module is in the registry, so adding these does
    # not touch the default 2-factor world. Grounded in demand sensing / CPFR /
    # bullwhip: promo is a fixed-length calendar spike, seasonal a sustained
    # lift, decline a sticky downshift.
    demand_promo_onset: float = 0.03       # normal -> promo_spike
    demand_seasonal_onset: float = 0.015   # normal -> seasonal_lift
    demand_decline_onset: float = 0.005    # normal -> structural_decline
    demand_promo_max: int = 4              # promo runs a fixed ~4 wks then ends
    demand_seasonal_persist: float = 0.85  # seasonal lift sticks week to week
    demand_seasonal_max: int = 8           # seasonal caps at ~8 wks
    demand_decline_persist: float = 0.97   # structural decline is sticky
    # realized POS is a noisy draw around the regime mean (so the regime must be
    # FILTERED over weeks, not read in one); the forward forecast is a second,
    # noisier read of the same mean (demand sensing). ~Poisson spread at mean 20.
    demand_noise_sd: float = 4.0           # sd of the realized weekly POS
    demand_forecast_sd: float = 6.0        # sd of the forward forecast (noisier)

    # --- freight-rate semi-Markov kernel (latent module #4, RICH worlds only) ---
    # Unused unless the freight module is in the registry. Grounded in FBX/SCFI
    # spot dynamics: tightening via carrier discipline/GRIs, spike via shocks.
    fr_tighten_onset: float = 0.06         # normal -> tightening
    fr_slack_onset: float = 0.04           # normal -> slack
    fr_spike_onset: float = 0.18           # tightening -> spike (shock escalation)
    fr_tighten_recover: float = 0.25       # tightening -> normal (GRI fades)
    fr_tighten_max: int = 6                # tightening caps at ~6 wks
    fr_spike_persist: float = 0.80         # spike decays (mean ~5 wks)
    fr_spike_max: int = 6                  # spike caps at ~6 wks
    fr_slack_persist: float = 0.93         # slack is sticky (overcapacity lingers)
    fr_noise_sd: float = 0.15              # sd of the realized rate multiplier
    fr_outlook_sd: float = 0.25            # sd of the forward outlook (noisier)

    # --- port/customs semi-Markov kernel (latent module #5, RICH worlds only) ---
    # Unused unless the port module is in the registry. Destination-stage dwell:
    # congestion backlogs run weeks; customs holds are short (~1 wk).
    port_build_onset: float = 0.06         # clear -> building
    port_customs_onset: float = 0.04       # clear -> customs_hold
    port_congest_onset: float = 0.30       # building -> congested
    port_build_clear: float = 0.30         # building -> clear
    port_congest_persist: float = 0.85     # congestion is sticky (~5 wks)
    port_congest_max: int = 8              # congestion caps at ~8 wks
    port_customs_persist: float = 0.20     # customs hold is short (~1 wk)
    port_wait_noise_sd: float = 2.0        # sd of the realized berth-wait days
    port_outlook_sd: float = 3.0           # sd of the forward outlook (noisier)
    port_demurrage_rate: float = 2.0       # demurrage cost per held unit per week

    # --- supplier-quality semi-Markov kernel (latent module #6, RICH worlds only) ---
    # Unused unless the quality module is in the registry. Process drift is
    # gradual-then-sudden: the drifting->out hazard rises with age (tool wear).
    q_drift_onset: float = 0.04            # in_control -> drifting
    q_out_base: float = 0.05               # drifting -> out_of_control base hazard
    q_out_age_slope: float = 0.04          # ...rising per week in drift (tool wear)
    q_drift_recover: float = 0.20          # drifting -> in_control (caught early)
    q_out_recover: float = 0.25            # out_of_control -> in_control (intervention)
    quality_rework_cost: float = 15.0      # rework/scrap cost per defective unit
    # The realized batch defect FRACTION is a NOISY draw around the regime mean
    # (a finite-batch sample, not the exact process rate), so the defective count
    # the agent sees is a noisy estimate of the hidden regime -- it cannot read
    # the regime off the arrived/rework delta. Gamma multiplier, mean 1.0,
    # CV = 1/sqrt(shape); shape 2.0 -> CV ~0.71 (adjacent regimes overlap).
    q_defect_shape: float = 2.0

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
    order_max: int = 100  # free order-qty cap; ~5 weeks of mean demand, generous
                          # enough not to bind a sane base-stock. Calibration knob.
    initial_inventory: int = 80
    suez_unit_cost: float = 4.0
    cape_unit_cost: float = 6.0           # ~1.5x Suez operating cost
    holding_cost: float = 1.0             # per unit per week, on-hand AND in-transit
    stockout_cost: float = 20.0           # scarcity premium (crisis rates 3-5x)
    briefing_cost: float = 30.0           # paid analyst assessment, bought pre-decision
