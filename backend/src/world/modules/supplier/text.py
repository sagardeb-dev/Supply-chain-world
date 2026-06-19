"""The supplier module's display vocabulary (real/anon ablation, identical
information). Supplier ids and scorecard-band labels: same ablation boundary
as the routes -- referents stripped in anon, revelation timing unchanged."""

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
