"""Tier 3 — couplings: the ONLY code allowed to read two factors at once.

A coupling lives in the REWARD, never in a kernel or an emission. That is the
provably-exact regime (Becker TI-Dec-MDP, JAIR 2004, Theorem 1): the factors'
transitions and observations stay independent (so the joint belief stays a
product of marginals), while the cost couples them. Keeping every such term in
this one auditable file is what makes the "solve V1 and V2 separately and ADD
them" trap (Thm 1's JV term => V_global != V1 + V2) impossible to commit by
accident: there is exactly one place a cost reads both factors.
"""

# regimes during which a spot shortfall is a crisis back-order, not a shrug.
_CRISIS_REGIMES = ("watch", "crash", "blockage", "crisis")


def crisis_backorder(shortfall_units: int, h, cfg) -> float:
    """The Becker JV coupling: a spot shortfall is cheap in calm weeks but
    punishing when a disruption is brewing -- the lost units must be
    back-ordered at the crisis spot rate. Reads BOTH factors (the disruption
    regime via `h` and the supplier-derived `shortfall_units`) but returns a
    pure cost, so the belief stays factored."""
    if shortfall_units and h.regime in _CRISIS_REGIMES:
        return cfg.crisis_backorder_kappa * shortfall_units
    return 0.0
