"""The freight module's data table: visible BAND -> the MEAN cost multiplier
on the route base rate. realized_mult is a NOISY draw around this (a fluctuating
spot rate), so the rate regime must be filtered. Scalar knobs (transition probs,
noise sd) live on the global WorldConfig.

Band collapse = the GRI-week ambiguity (mirrors disruption "crash"): tightening
and spike ONSET share `jump`; they separate next week into `high` (tightening
plateaus) vs `peak` (spike climbs)."""

FREIGHT_MEANS = {
    "low":  0.7,   # slack / overcapacity
    "mid":  1.0,   # normal (spot ~ contract)
    "jump": 1.8,   # tightening & spike ONSET — shared (the GRI ambiguity)
    "high": 1.8,   # tightening sustained (plateau)
    "peak": 4.0,   # spike sustained (Red-Sea / pandemic scale)
}
