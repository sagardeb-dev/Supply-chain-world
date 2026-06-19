"""Port/customs module — a hidden semi-Markov destination-port state (clear/
building/congested/customs_hold) visible as a NOISY berth-wait reading + a NOISY
forward outlook, with a 1-week onset ambiguity (congestion vs customs hold). Its
EFFECT holds arrivals + charges demurrage when blocked. The fifth latent factor;
rich worlds only. Distinct from disruption (mid-voyage) -- this is the
destination dwell stage.

drives=("",): a singleton module-state."""

from .config import PORT_WAIT
from .emission import effect, emit, view
from .factor import (PORT_REGIMES, PortState, port_band, step_port)

DRIVES = ("",)

__all__ = [
    "PortState", "step_port", "port_band", "PORT_REGIMES",
    "effect", "emit", "view", "PORT_WAIT", "DRIVES",
]
