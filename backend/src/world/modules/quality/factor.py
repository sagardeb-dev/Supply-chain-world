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
    sid: str = ""  # Phase 3: which roster member this is ("" = the legacy
                   # global process). Appended LAST (defaulted) so the existing
                   # positional ctor calls stay valid, and a bare QualityState()
                   # keeps legacy (cfg-driven) behaviour byte-identical.

    def to_dict(self) -> dict:
        return asdict(self)


def _resolve_kernel(sid: str, cfg: WorldConfig) -> dict:
    """Resolve this state's quality-kernel params: sid=="" -> the global
    cfg.q_* fields exactly as today (byte-identity for the legacy singleton);
    else this supplier's own "quality" personality dict from the SUPPLIERS
    profile (Phase 3, mirrors supplier.step_supplier's kernel resolution).
    Deferred import: the quality factor may read the supplier module's TABLE
    for this dict only -- it never reads supplier STATE, so factored
    independence (Becker Def. 2) still holds."""
    if sid == "":
        return {"drift_onset": cfg.q_drift_onset, "out_base": cfg.q_out_base,
                "out_age_slope": cfg.q_out_age_slope,
                "drift_recover": cfg.q_drift_recover,
                "out_recover": cfg.q_out_recover}
    from ..supplier.config import SUPPLIERS
    return SUPPLIERS[sid]["quality"]


def step_quality(q: QualityState, rng: random.Random,
                 cfg: WorldConfig) -> QualityState:
    """Advance the process-quality regime, then draw this week's noisy AQL
    sample. Sibling of step_hidden, same rng. Reads ONLY QualityState (+ its
    OWN resolved kernel params -- never another module/supplier STATE). The
    drifting->out hazard rises with age (gradual-then-sudden tool wear). rng
    order: transition, AQL sample, defect-fraction realization."""
    k = _resolve_kernel(q.sid, cfg)
    s, age = q.regime, q.regime_age
    if s == "in_control":
        nxt = "drifting" if rng.random() < k["drift_onset"] else "in_control"
    elif s == "drifting":
        r = rng.random()
        hazard = min(1.0, k["out_base"] + k["out_age_slope"] * age)
        if r < hazard:
            nxt = "out_of_control"
        elif r < hazard + k["drift_recover"]:
            nxt = "in_control"
        else:
            nxt = "drifting"
    else:  # out_of_control: recovers only on (implicit) intervention
        nxt = "in_control" if rng.random() < k["out_recover"] else "out_of_control"

    new_age = 0 if nxt != s else age + 1
    # the realized batch defect fraction is a NOISY finite-batch sample around the
    # regime's true rate (Gamma multiplier, mean 1), so round(gross*frac) is a
    # noisy count -- the agent cannot read the regime off arrived/rework exactly.
    # QUALITY_DEFECT/shape stay SHARED across suppliers (regime -> fraction is
    # the same physics; personalities differ in how often they're in bad regimes).
    realized = QUALITY_DEFECT[nxt] * rng.gammavariate(
        cfg.q_defect_shape, 1.0 / cfg.q_defect_shape)
    return QualityState(regime=nxt, regime_age=new_age,
                        sample_band=_sample_band(nxt, rng),
                        realized_defect=round(realized, 5), sid=q.sid)
