"""The supplier latent factor: hidden reliability state + kernel.

A SECOND, fully separate latent factor from the disruption chain: its own
states, its own visible band, its own kernel. It NEVER reads HiddenState --
that isolation is the point (Becker Def. 2: transition independence keeps
the joint belief factored). One latent module per task, debuggable alone."""

import random
from dataclasses import dataclass, asdict

from ...config import WorldConfig
from .config import SUPPLIER_FILL_MEAN, SUPPLIER_LEAD_SLIP

SUPPLIER_STATES = ("reliable", "wobbling", "degraded", "defunct")


@dataclass(frozen=True)
class SupplierState:
    """The spot supplier's reliability factor -- the second latent module.
    Independent of HiddenState; its own kernel advances it.

    Visible band (regime) collapses two states into one for exactly one week,
    mirroring the disruption "crash" ambiguity: a fresh "wobbling" and the
    onset week of "degraded" both read "slipping" on the scorecard, then
    separate the following week (degraded ages into "failing")."""

    rel_state: str = "reliable"
    rel_age: int = 0  # weeks the supplier has been in degraded
    lead_slip: float = 0.0  # masked task: this week's NOISY realized-lead-slip
                            # sensor (days). 0 unless cfg.sup_mask_otif drew it.
    fill_draw: float | None = None  # masked task: this week's NOISY realized fill
                            # fraction. None => legacy deterministic lookup.

    @property
    def regime(self) -> str:
        """Scorecard-band key. wobbling and degraded-onset share "slipping";
        defunct (the dead supplier, Lever 1) is its own absorbing band."""
        if self.rel_state == "reliable":
            return "ontime"
        if self.rel_state == "wobbling":
            return "slipping"
        if self.rel_state == "defunct":
            return "defunct"
        # degraded
        return "slipping" if self.rel_age == 0 else "failing"

    @property
    def fulfilled_fraction(self) -> float:
        """Share of a spot order this supplier actually ships this week. Masked
        task: a NOISY per-week draw (fill_draw, set by the kernel) so a single
        partial fill no longer identifies the regime -- it must be filtered.
        Legacy: the deterministic lookup (fill_draw is None), byte-identical."""
        if self.fill_draw is not None:
            return self.fill_draw
        return {"reliable": 1.0, "wobbling": 0.5,
                "degraded": 0.0, "defunct": 0.0}[self.rel_state]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["regime"] = self.regime
        return d


def step_supplier(sup: SupplierState, rng: random.Random,
                  cfg: WorldConfig) -> SupplierState:
    """Advance the spot supplier's reliability factor. Sibling of step_hidden,
    same rng (exogeneity: actions never consume it). Reads ONLY SupplierState
    -- never the disruption state -- so the two latent modules are transition
    independent (Becker Def. 2) and debuggable in isolation.

    Runs UNCONDITIONALLY every week (the supplier drifts whether or not you
    source from it), which is what makes the scorecard a free side-channel."""
    s, age = sup.rel_state, sup.rel_age
    if s == "reliable":
        nxt = "wobbling" if rng.random() < cfg.sup_onset_prob else "reliable"
    elif s == "wobbling":
        r = rng.random()
        if r < cfg.sup_wobble_to_degraded:
            nxt = "degraded"
        elif r < cfg.sup_wobble_to_degraded + cfg.sup_wobble_to_reliable:
            nxt = "reliable"
        else:
            nxt = "wobbling"
    elif s == "defunct":
        # Lever 1: absorbing. A dead supplier stays dead for the episode.
        return sup
    else:  # degraded
        # First check the death hazard (degraded is the only entry to defunct);
        # then the recover-or-persist branch as before.
        if rng.random() < cfg.sup_defunct_from_degraded:
            nxt = "defunct"
        else:
            over = (age + 1 >= cfg.sup_max_degraded
                    or rng.random() > cfg.sup_degraded_persist)
            nxt = "reliable" if over else "degraded"
    # masked task ONLY: draw this week's noisy lead-slip sensor. Gated on the
    # flag so the default world draws no extra rng -> trajectory + golden tests
    # byte-identical. Drawn last (after the transition) to keep rng order stable.
    slip, fill = sup.lead_slip, sup.fill_draw
    if cfg.sup_mask_otif:
        slip = round(max(0.0, rng.gauss(SUPPLIER_LEAD_SLIP[nxt],
                                        cfg.sup_lead_slip_sd)), 1)
        fill = round(min(1.0, max(0.0, rng.gauss(SUPPLIER_FILL_MEAN[nxt],
                                                 cfg.sup_fill_sd))), 2)
    return SupplierState(rel_state=nxt, rel_age=0 if nxt != s else age + 1,
                         lead_slip=slip, fill_draw=fill)
