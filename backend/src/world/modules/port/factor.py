"""The destination-port latent factor: a hidden congestion/customs state + its
kernel.

The fifth latent module, on the disruption template: a semi-Markov regime
(clear/building/congested/customs_hold) whose visible band sets the MEAN berth
wait; the realized wait is a NOISY draw. Distinct from the disruption module
(which delays the mid-voyage Suez leg) -- this is the DESTINATION stage, after
the ocean leg. NEVER reads another module (Becker Def. 2).

Grounded in 2021-24 berth queues, demurrage/detention, CBP exam holds: a desk
infers the hidden port state from a noisy berth-wait reading; a single slow week
reads the same whether congestion is building or a customs hold landed."""

import random
from dataclasses import dataclass, asdict

from ...config import WorldConfig
from .config import PORT_WAIT

PORT_REGIMES = ("clear", "building", "congested", "customs_hold")


def port_band(regime: str, regime_age: int) -> str:
    """Visible band (keys PORT_WAIT). congested & customs_hold ONSET (age 0)
    share `slow`; at age>=1 a persisting hold/backlog reads `congested`."""
    if regime == "clear":
        return "clear"
    if regime == "building":
        return "building"
    if regime_age == 0:
        return "slow"               # the shared onset ambiguity
    return "congested"


@dataclass(frozen=True)
class PortState:
    regime: str = "clear"
    regime_age: int = 0
    berth_wait: int = 1     # noisy realized berth-wait days (the observable)
    wait_outlook: int = 1   # noisy FORWARD wait outlook (port advisories)

    @property
    def band(self) -> str:
        return port_band(self.regime, self.regime_age)

    @property
    def mean(self) -> int:
        return PORT_WAIT[self.band]

    @property
    def blocked(self) -> bool:
        """Arrivals are held this week (congestion backlog or a customs hold)."""
        return self.regime in ("congested", "customs_hold")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["band"] = self.band
        return d


def step_port(p: PortState, rng: random.Random, cfg: WorldConfig) -> PortState:
    """Advance the port regime, then draw this week's noisy berth wait + forward
    outlook. Sibling of step_hidden, same rng. Reads ONLY PortState. rng order:
    transition, berth_wait, outlook."""
    s, age = p.regime, p.regime_age
    if s == "clear":
        r = rng.random()
        if r < cfg.port_build_onset:
            nxt = "building"
        elif r < cfg.port_build_onset + cfg.port_customs_onset:
            nxt = "customs_hold"
        else:
            nxt = "clear"
    elif s == "building":
        r = rng.random()
        if r < cfg.port_congest_onset:
            nxt = "congested"
        elif r < cfg.port_congest_onset + cfg.port_build_clear:
            nxt = "clear"
        else:
            nxt = "building"
    elif s == "congested":
        over = (age + 1 >= cfg.port_congest_max
                or rng.random() > cfg.port_congest_persist)
        nxt = "clear" if over else "congested"
    else:  # customs_hold: short (mostly a 1-week event)
        nxt = "customs_hold" if rng.random() < cfg.port_customs_persist else "clear"

    new_age = 0 if nxt != s else age + 1
    mean = PORT_WAIT[port_band(nxt, new_age)]
    berth = max(0, round(rng.gauss(mean, cfg.port_wait_noise_sd)))
    outlook = max(0, round(rng.gauss(mean, cfg.port_outlook_sd)))
    return PortState(regime=nxt, regime_age=new_age,
                     berth_wait=berth, wait_outlook=outlook)
