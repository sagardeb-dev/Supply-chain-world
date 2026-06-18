"""Tier 2 — substrate: the route/status display vocabulary, in two parallel
semantics ("real" carries genuine referents; "anon" strips them, identical
information). The disruption bulletins/briefings/count-keys live with the
disruption module; the supplier id/band labels live with the supplier module.
What remains here is the substrate's own observed vocabulary: routes and
shipment statuses.
"""

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
