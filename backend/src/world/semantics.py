"""Agent-facing text and label layer, in two parallel vocabularies.
"real" carries genuine referents (Suez, Red Sea, groundings, attacks) -
the domain-knowledge channel under test in the semantics ablation.
"anon" is structurally identical with referents stripped.

Rules (V1_CHANGE_LOG 2026-06-11(b)):
R1 - bulletins are a pure function of HiddenState.regime, so the shared
     "crash" regime makes false_alarm and week-0 of either disruption
     type byte-identical, mirroring the count ambiguity exactly.
R2 - no duration or probability language anywhere: the duration prior
     IS the domain knowledge being measured.
R3 - both modes carry identical information (same revelation timing).
"""

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

ROUTE_DISPLAY = {
    "real": {"suez": "suez", "cape": "cape"},
    "anon": {"suez": "route_1", "cape": "route_2"},
}
ROUTE_PARSE = {mode: {v: k for k, v in m.items()}
               for mode, m in ROUTE_DISPLAY.items()}

COUNT_KEYS = {
    "real": {"suez_count": "suez_count", "bab_count": "bab_count",
             "cape_count": "cape_count"},
    "anon": {"suez_count": "waterway1_count", "bab_count": "strait_count",
             "cape_count": "waterway2_count"},
}

STATUS_DISPLAY = {
    "real": {"at_sea": "at_sea", "queued_at_suez": "queued_at_suez",
             "diverted_via_cape": "diverted_via_cape"},
    "anon": {"at_sea": "at_sea", "queued_at_suez": "queued_at_waterway1",
             "diverted_via_cape": "diverted_via_waterway2"},
}

# Supplier id + scorecard-band labels (factor 2). Same real/anon ablation
# boundary as the routes: identical information, referents stripped in anon.
SUPPLIER_DISPLAY = {
    "real": {"qualified": "qualified", "spot": "spot", "backup": "backup"},
    "anon": {"qualified": "source_a", "spot": "source_b", "backup": "source_c"},
}
SUPPLIER_PARSE = {mode: {v: k for k, v in d.items()}
                  for mode, d in SUPPLIER_DISPLAY.items()}
SUPPLIER_BAND_DISPLAY = {
    "real": {"ontime": "ontime", "slipping": "slipping", "failing": "failing"},
    "anon": {"ontime": "band_0", "slipping": "band_1", "failing": "band_2"},
}
