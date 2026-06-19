"""The demand latent factor: a hidden demand regime + its kernel.

The third latent module (after disruption + supplier), on the same template:
a semi-Markov chain (regime + age) whose VISIBLE band sets the MEAN of weekly
demand. The realized POS is a NOISY draw around that mean, so the agent cannot
read the regime from one observation -- it must FILTER several noisy weeks (the
realistic uncertainty; v1's flat level was too deterministic). It NEVER reads
another module's state (Becker Def. 2 -- transition independence keeps the joint
belief factored).

Grounded in demand sensing / CPFR / bullwhip: an import desk cannot directly see
whether elevated, noisy sell-through is a transient PROMO or a sustained SEASONAL
lift; it gets a noisy POS reading AND a noisy forward forecast and must weigh
them over time."""

import random
from dataclasses import dataclass, asdict

from ...config import WorldConfig
from .config import DEMAND_MEANS

DEMAND_REGIMES = ("normal", "promo_spike", "seasonal_lift", "structural_decline")


def demand_band(regime: str, regime_age: int) -> str:
    """Visible band (keys DEMAND_MEANS). promo and seasonal ONSET (age 0) share
    `surge`; at age>=1 they separate into `promo` (transient) vs `seasonal`."""
    if regime == "normal":
        return "base"
    if regime == "structural_decline":
        return "depressed"
    if regime_age == 0:
        return "surge"          # the shared onset-ambiguity mean
    return "promo" if regime == "promo_spike" else "seasonal"


@dataclass(frozen=True)
class DemandState:
    regime: str = "normal"
    regime_age: int = 0      # weeks in the current regime (the hidden state)
    # this week's draws (per-week, like HiddenState.cape_local_congestion):
    realized: int = 20       # noisy realized POS = what sold / what's consumed
    forecast: int = 20       # noisy FORWARD demand-sensing read of the mean

    @property
    def band(self) -> str:
        return demand_band(self.regime, self.regime_age)

    @property
    def mean(self) -> int:
        return DEMAND_MEANS[self.band]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["band"] = self.band
        return d


def _draw(mean: int, sd: float, rng: random.Random) -> int:
    """A non-negative integer demand draw around `mean` (Gaussian, clamped).
    Deterministic given the seeded rng -> the world stays reproducible."""
    return max(0, round(rng.gauss(mean, sd)))


def step_demand(d: DemandState, rng: random.Random,
                cfg: WorldConfig) -> DemandState:
    """Advance the demand regime, then draw this week's noisy POS + forward
    forecast. Sibling of step_hidden, same rng (exogeneity). Reads ONLY
    DemandState. Promo is a fixed-length calendar event (deterministic exit at
    the age cap); seasonal persists with a hazard + cap; decline is sticky.

    rng draw order (load-bearing): transition, then realized, then forecast."""
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
        nxt = "normal" if age + 1 >= cfg.demand_promo_max else "promo_spike"
    elif s == "seasonal_lift":
        over = (age + 1 >= cfg.demand_seasonal_max
                or rng.random() > cfg.demand_seasonal_persist)
        nxt = "normal" if over else "seasonal_lift"
    else:  # structural_decline: sticky
        nxt = ("structural_decline"
               if rng.random() < cfg.demand_decline_persist else "normal")

    new_age = 0 if nxt != s else age + 1
    mean = DEMAND_MEANS[demand_band(nxt, new_age)]
    realized = _draw(mean, cfg.demand_noise_sd, rng)
    forecast = _draw(mean, cfg.demand_forecast_sd, rng)
    return DemandState(regime=nxt, regime_age=new_age,
                       realized=realized, forecast=forecast)
