"""Shared ground-truth replay: which factors are truly stressed each week.

One canonical copy of the stress definition used by sweep/run_sweep.py's
_tape_features and runs/grade_beliefs.py (both predate this module and keep
their own copies for ladder-v1 provenance; new code imports from here).
Replays the seed's tape passively (empty actions) and reads hidden state via
filters.py's own reader so roster/nested-key handling matches the oracle.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FACTORS = ["disruption", "freight", "port", "quality", "supplier", "demand"]


def stressed_set(rec) -> set:
    import filters as filt_mod
    out = set()
    for f in FACTORS:
        t = filt_mod._true_regime(rec, f)
        if ((f == "disruption" and t == "disruption")
                or (f == "freight" and t == "spike")
                or (f == "port" and t in ("congested", "customs_hold"))
                or (f == "quality" and t == "out_of_control")
                or (f == "supplier" and t in ("degraded", "defunct"))
                or (f == "demand" and t != "normal")):
            out.add(f)
    return out


def true_stress_by_week(seed: int) -> dict[int, set]:
    """{week: set of stressed factors} for weeks 0..26, RICH masked world
    (the benchmark configuration)."""
    from src.world.engine import World
    from src.world.config import WorldConfig
    from src.world.registry import RICH
    w = World(WorldConfig(sup_mask_otif=True), registry=RICH)
    w.reset(seed)
    while not w.done:
        w.step({})
    return {rec["week"]: stressed_set(rec) for rec in w.trace}
