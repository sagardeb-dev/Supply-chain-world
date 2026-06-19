"""The demand module's data table: the visible BAND -> the MEAN of weekly
demand. The realized weekly POS is a NOISY draw around this mean (see factor),
so the hidden regime must be filtered over several weeks, not read in one --
that is the realistic uncertainty (a flat, noiseless level was a v1 mistake).
Scaled to the world's base demand (20/wk). Scalar knobs (transition probs,
noise sd) live on the global WorldConfig.

The band collapse is the deliberate onset ambiguity (mirrors disruption
"crash"): promo and seasonal ONSET share the `surge` mean; they separate the
next week into `promo` (transient, same mean) vs `seasonal` (sustained, higher).
"""

DEMAND_MEANS = {
    "base":      20,   # normal
    "surge":     26,   # promo & seasonal ONSET — shared mean (onset ambiguity)
    "promo":     26,   # promo after onset (transient; may end -> base)
    "seasonal":  30,   # seasonal after onset (sustained; separates from promo)
    "depressed": 14,   # structural decline (sticky)
}
