"""The freight-rate latent factor: a hidden ocean-rate regime + its kernel.

The fourth latent module, on the disruption template: a semi-Markov regime
(slack/normal/tightening/spike) whose visible band sets the MEAN cost
multiplier; the realized multiplier is a NOISY draw (a fluctuating spot rate),
so the agent filters the regime from a noisy index print + a noisier forward
outlook. NEVER reads another module (Becker Def. 2).

Grounded in FBX/Drewry/SCFI spot indices, GRIs, blank sailings: a desk infers
hidden capacity-tightness from published prints; a GRI-announcement week reads
elevated whether the hike sticks (tightening) or collapses back (normal)."""

import random
from dataclasses import dataclass, asdict

from ...config import WorldConfig
from .config import FREIGHT_MEANS

FREIGHT_REGIMES = ("slack", "normal", "tightening", "spike")


def freight_band(regime: str, regime_age: int) -> str:
    """Visible band (keys FREIGHT_MEANS). tightening & spike ONSET (age 0) share
    `jump`; at age>=1 they separate into `high` (plateau) vs `peak` (climb)."""
    if regime == "slack":
        return "low"
    if regime == "normal":
        return "mid"
    if regime_age == 0:
        return "jump"                       # the shared GRI-onset ambiguity
    return "high" if regime == "tightening" else "peak"


@dataclass(frozen=True)
class FreightState:
    regime: str = "normal"
    regime_age: int = 0
    realized_mult: float = 1.0   # noisy realized cost multiplier (what you pay)
    outlook: float = 1.0         # noisy FORWARD rate outlook (carrier guidance/GRI)

    @property
    def band(self) -> str:
        return freight_band(self.regime, self.regime_age)

    @property
    def mean(self) -> float:
        return FREIGHT_MEANS[self.band]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["band"] = self.band
        return d


def _draw(mean: float, sd: float, rng: random.Random) -> float:
    """A positive multiplier draw around `mean` (Gaussian, clamped)."""
    return max(0.1, round(rng.gauss(mean, sd), 4))


def step_freight(f: FreightState, rng: random.Random,
                 cfg: WorldConfig) -> FreightState:
    """Advance the rate regime, then draw this week's noisy realized multiplier
    + forward outlook. Sibling of step_hidden, same rng (exogeneity). Reads ONLY
    FreightState. rng draw order: transition, realized, outlook."""
    s, age = f.regime, f.regime_age
    if s == "slack":
        nxt = "slack" if rng.random() < cfg.fr_slack_persist else "normal"
    elif s == "normal":
        r = rng.random()
        if r < cfg.fr_tighten_onset:
            nxt = "tightening"
        elif r < cfg.fr_tighten_onset + cfg.fr_slack_onset:
            nxt = "slack"
        else:
            nxt = "normal"
    elif s == "tightening":
        r = rng.random()
        if r < cfg.fr_spike_onset:
            nxt = "spike"
        elif (r < cfg.fr_spike_onset + cfg.fr_tighten_recover
              or age + 1 >= cfg.fr_tighten_max):
            nxt = "normal"
        else:
            nxt = "tightening"
    else:  # spike: decays back toward normal, age-capped
        over = age + 1 >= cfg.fr_spike_max or rng.random() > cfg.fr_spike_persist
        nxt = "normal" if over else "spike"

    new_age = 0 if nxt != s else age + 1
    mean = FREIGHT_MEANS[freight_band(nxt, new_age)]
    realized = _draw(mean, cfg.fr_noise_sd, rng)
    outlook = _draw(mean, cfg.fr_outlook_sd, rng)
    return FreightState(regime=nxt, regime_age=new_age,
                        realized_mult=realized, outlook=outlook)
