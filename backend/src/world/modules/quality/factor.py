"""The supplier-quality latent factor: a hidden process-quality state + its
kernel.

The sixth latent module. Distinct from the others: its observation is a NOISY
DISCRETE AQL sample (accept/marginal/reject), so the belief does not collapse to
a singleton -- this is the factor that makes the full RICH world need the bracket
anchor rather than an exact DP. Semi-Markov with a "gradual then sudden" drift:
the drifting -> out_of_control hazard rises with age (tool wear accumulates).
NEVER reads another module (Becker Def. 2).

Grounded in SPC / AQL ISO 2859 / PPM / cost of poor quality."""

import random
from dataclasses import dataclass, asdict

from ...config import WorldConfig
from .config import AQL_BANDS, QUALITY_BAND_PROBS, QUALITY_DEFECT

QUALITY_REGIMES = ("in_control", "drifting", "out_of_control")


def _sample_band(regime: str, rng: random.Random) -> str:
    """Draw the week's AQL inspection band from the regime's probabilities."""
    r, cum = rng.random(), 0.0
    for band, p in zip(AQL_BANDS, QUALITY_BAND_PROBS[regime]):
        cum += p
        if r < cum:
            return band
    return "reject"


@dataclass(frozen=True)
class QualityState:
    regime: str = "in_control"
    regime_age: int = 0
    sample_band: str = "accept"   # this week's noisy AQL inspection result
    realized_defect: float = 0.0  # this week's NOISY batch defect fraction (a
                                  # finite-batch sample around the regime mean)

    def to_dict(self) -> dict:
        return asdict(self)


def step_quality(q: QualityState, rng: random.Random,
                 cfg: WorldConfig) -> QualityState:
    """Advance the process-quality regime, then draw this week's noisy AQL
    sample. Sibling of step_hidden, same rng. Reads ONLY QualityState. The
    drifting->out hazard rises with age (gradual-then-sudden tool wear). rng
    order: transition, AQL sample, defect-fraction realization."""
    s, age = q.regime, q.regime_age
    if s == "in_control":
        nxt = "drifting" if rng.random() < cfg.q_drift_onset else "in_control"
    elif s == "drifting":
        r = rng.random()
        hazard = min(1.0, cfg.q_out_base + cfg.q_out_age_slope * age)
        if r < hazard:
            nxt = "out_of_control"
        elif r < hazard + cfg.q_drift_recover:
            nxt = "in_control"
        else:
            nxt = "drifting"
    else:  # out_of_control: recovers only on (implicit) intervention
        nxt = "in_control" if rng.random() < cfg.q_out_recover else "out_of_control"

    new_age = 0 if nxt != s else age + 1
    # the realized batch defect fraction is a NOISY finite-batch sample around the
    # regime's true rate (Gamma multiplier, mean 1), so round(gross*frac) is a
    # noisy count -- the agent cannot read the regime off arrived/rework exactly.
    realized = QUALITY_DEFECT[nxt] * rng.gammavariate(
        cfg.q_defect_shape, 1.0 / cfg.q_defect_shape)
    return QualityState(regime=nxt, regime_age=new_age,
                        sample_band=_sample_band(nxt, rng),
                        realized_defect=round(realized, 5))
