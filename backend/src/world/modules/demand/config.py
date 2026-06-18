"""The demand module's data table: the visible BAND -> realized weekly units.
Scaled to the world's base demand (20/wk). The scalar transition knobs
(demand_*_onset, *_persist, *_max) live on the global WorldConfig.

The band collapse is the deliberate 1-week ambiguity (mirrors the disruption
"crash"): promo and seasonal ONSET both read `surge`; they separate the next
week into `promo` (transient, same level) vs `seasonal` (sustained, higher)."""

DEMAND_LEVELS = {
    "base":      20,   # normal
    "surge":     26,   # promo & seasonal ONSET — the shared ambiguity reading
    "promo":     26,   # promo after onset (transient; may end -> base)
    "seasonal":  30,   # seasonal after onset (sustained; separates from promo)
    "depressed": 14,   # structural decline (sticky)
}
