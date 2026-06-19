"""Tier 2 — voyage presentation maps (the real/anon ablation for routes
and shipment status). Identical information in both modes; referents
stripped in anon. Module-specific vocabularies (disruption bulletins,
supplier scorecard labels) live in their own modules' text.py."""

ROUTE_DISPLAY = {
    "real": {"suez": "suez", "cape": "cape"},
    "anon": {"suez": "route_1", "cape": "route_2"},
}
ROUTE_PARSE = {mode: {v: k for k, v in m.items()}
               for mode, m in ROUTE_DISPLAY.items()}

STATUS_DISPLAY = {
    "real": {"at_sea": "at_sea", "queued_at_suez": "queued_at_suez",
             "diverted_via_cape": "diverted_via_cape"},
    "anon": {"at_sea": "at_sea", "queued_at_suez": "queued_at_waterway1",
             "diverted_via_cape": "diverted_via_waterway2"},
}
