"""The demand latent factor: a hidden demand regime + its kernel.

The third latent module (after disruption + supplier), on the same template:
a semi-Markov chain (regime + age) whose VISIBLE band collapses two hidden
causes for exactly one week. It NEVER reads another module's state (Becker
Def. 2 — transition independence keeps the joint belief factored).

Grounded in demand sensing / CPFR / bullwhip: an import desk cannot directly
see whether elevated sell-through is a transient PROMO or a sustained SEASONAL
lift until it watches one more week."""

import random
from dataclasses import dataclass, asdict

from ...config import WorldConfig

DEMAND_REGIMES = ("normal", "promo_spike", "seasonal_lift", "structural_decline")


@dataclass(frozen=True)
class DemandState:
    regime: str = "normal"
    regime_age: int = 0  # weeks in the current regime

    @property
    def band(self) -> str:
        """Visible demand band (keys DEMAND_LEVELS). promo and seasonal ONSET
        (age 0) share `surge` -- indistinguishable for one week; at age>=1 they
        separate into `promo` (transient) vs `seasonal` (sustained, higher)."""
        if self.regime == "normal":
            return "base"
        if self.regime == "structural_decline":
            return "depressed"
        if self.regime_age == 0:
            return "surge"          # the shared ambiguity reading
        return "promo" if self.regime == "promo_spike" else "seasonal"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["band"] = self.band
        return d


def step_demand(d: DemandState, rng: random.Random,
                cfg: WorldConfig) -> DemandState:
    """Advance the demand regime. Sibling of step_hidden, same rng
    (exogeneity). Reads ONLY DemandState. Promo is a fixed-length calendar
    event (deterministic exit at the age cap, like a short disruption);
    seasonal persists with a hazard and a cap; decline is sticky."""
    s, age = d.regime, d.regime_age
    if s == "normal":
        r = rng.random()
        if r < cfg.demand_promo_onset:
            nxt = "promo_spike"
        elif r < cfg.demand_promo_onset + cfg.demand_seasonal_onset:
            nxt = "seasonal_lift"
        elif r < (cfg.demand_promo_onset + cfg.demand_seasonal_onset
                  + cfg.demand_decline_onset):
            nxt = "structural_decline"
        else:
            nxt = "normal"
    elif s == "promo_spike":
        # transient, fixed-length: deterministic exit at the cap
        nxt = "normal" if age + 1 >= cfg.demand_promo_max else "promo_spike"
    elif s == "seasonal_lift":
        over = (age + 1 >= cfg.demand_seasonal_max
                or rng.random() > cfg.demand_seasonal_persist)
        nxt = "normal" if over else "seasonal_lift"
    else:  # structural_decline: sticky
        nxt = ("structural_decline"
               if rng.random() < cfg.demand_decline_persist else "normal")
    return DemandState(regime=nxt, regime_age=0 if nxt != s else age + 1)
