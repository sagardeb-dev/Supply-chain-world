"""The supplier module's data tables: the OTIF scorecard bands and the
per-supplier roster profile. The tunable scalar knobs (sup_*, the unit
economics, contract knobs) live on the global WorldConfig dataclass so the
oracle and logistics read them unchanged; the roster/band tables that are
this module's alone live here."""

# OTIF scorecard bands: noiseless readout of SupplierState.regime (factor 2).
# "slipping" is SHARED by wobbling AND degraded-onset -- the supplier analogue
# of the disruption "crash" ambiguity. (otif_pct, lead_days_quoted)
SUPPLIER_SCORECARD = {
    "ontime":   (98, 14),
    "slipping": (82, 18),
    "failing":  (55, 28),
    "defunct":  (None, None),   # dead supplier: OTIF '-' on the scorecard
}

# Masked-distress task (cfg.sup_mask_otif). The OTIF scorecard LAGS the true
# regime by ~one severity step -- it is a gameable contractual metric that still
# reads healthy while the supplier is actually wobbling/degrading; only deep
# failure shows. (apparent_band, otif_pct, lead_days). The agent must catch the
# decline EARLIER, from the noisy books channels, not from this table.
SUPPLIER_SCORECARD_MASKED = {
    "ontime":   ("ontime",   98, 14),
    "slipping": ("ontime",   96, 15),   # masked: a slip still reads on-time
    "failing":  ("slipping", 86, 19),   # only now surfaces, as a mild "slip"
    "defunct":  ("defunct", None, None),
}

# Mean of the realized-lead-slip sensor (days) per TRUE reliability state, the
# noisy books channel #2 (cfg.sup_lead_slip_sd is the spread). Adjacent regimes
# overlap at the default sd, so one reading never identifies the state -- it must
# be filtered over weeks. Keyed by rel_state (drawn in step_supplier).
SUPPLIER_LEAD_SLIP = {
    "reliable": 0.0,
    "wobbling": 3.0,
    "degraded": 7.0,
    "defunct":  0.0,   # dead: no shipments, sensor irrelevant
}

# Mean realized FILL fraction per TRUE reliability state, the noisy books channel
# #1 (cfg.sup_fill_sd is the spread). Overlapping at the default sd, so a single
# partial fill no longer identifies the regime -- a healthy supplier can have an
# unlucky week and a wobble a good one. Legacy ships the deterministic lookup in
# SupplierState.fulfilled_fraction instead (fill_draw stays None). Drawn in
# step_supplier; defunct ships nothing.
SUPPLIER_FILL_MEAN = {
    "reliable": 0.95,
    "wobbling": 0.60,
    "degraded": 0.15,
    "defunct":  0.0,
}


# Per-supplier display profile (factor-2 roster). Self-contained: each entry
# declares everything the scorecard row needs, so _supplier_row has no
# instance-name branch and adding supplier #4 is one entry ("Nth costs the
# same as 2nd").
#   kernel       -- per-supplier reliability-kernel personality (Phase 2). None
#                   => fall back to the global cfg.sup_* fields (spot's legacy
#                   behaviour AND the calibration surface for the drifting-spot
#                   tasks). A dict => this supplier's own transition params. WHO
#                   actually drifts in a given world is DRIVES(cfg), not this
#                   table: with sup_all_drift off only spot drifts; with it on
#                   all three do, each reading its own kernel here.
#   otif/lead    -- frozen-display constants shown when this supplier is NOT
#                   drifting in this world (None for one whose row is always a
#                   live regime read, i.e. spot).
#   onboard_weeks-- weeks before this supplier's FIRST order can ship.
#   econ         -- unit economics vs the route base cost. "attr" names the
#                   WorldConfig field holding the magnitude (cfg stays the
#                   single source of truth -- the cost arithmetic in
#                   logistics/oracle reads the SAME fields). "sign" is the
#                   direction of unit_delta; "key" is the extra display key
#                   (unit_discount / unit_premium), or None for just a delta.
# ponytail: the per-supplier kernel magnitudes below are calibration knobs --
# grounded starting personalities (spot cheap/volatile, backup mid, qualified
# premium/steady), swept later by the benchmark tuning workstream, not final.
SUPPLIERS = {
    "qualified": {"kernel": {"onset": 0.03, "wobble_to_degraded": 0.30,
                             "wobble_to_reliable": 0.55, "degraded_persist": 0.50,
                             "max_degraded": 2, "defunct_from_degraded": 0.0},
                  "otif": 99, "lead": 14, "onboard_weeks": 0,
                  "econ": {"attr": "qualified_premium", "sign": 1,
                           "key": "unit_premium"}},
    "spot":      {"kernel": None, "otif": None, "lead": None, "onboard_weeks": 0,
                  "econ": {"attr": "spot_unit_discount", "sign": -1,
                           "key": "unit_discount"}},
    "backup":    {"kernel": {"onset": 0.06, "wobble_to_degraded": 0.40,
                             "wobble_to_reliable": 0.40, "degraded_persist": 0.60,
                             "max_degraded": 3, "defunct_from_degraded": 0.03},
                  "otif": 95, "lead": 16, "onboard_weeks": 1,
                  "econ": {"attr": "backup_unit_delta", "sign": 1, "key": None}},
}
