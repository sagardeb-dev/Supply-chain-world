"""reset()/step() orchestrator. The only module that knows the sequence:
evolve hidden -> resolve logistics -> emit observation."""

import random

from .config import WorldConfig
from .emission import observe_counts, probe_result
from .logistics import Books, resolve_week
from .state import HiddenState
from .transition import step_hidden

HIDDEN_KEYS = {"event_state", "event_age", "suez_regime", "bab_regime",
               "cape_congestion", "signal_reliability", "seasonal_dip",
               "cape_local_congestion"}


class World:
    def __init__(self, cfg: WorldConfig | None = None):
        self.cfg = cfg or WorldConfig()

    def reset(self, seed: int) -> dict:
        self.rng = random.Random(seed)
        self.week = 0
        self.hidden = HiddenState()
        self.books = Books(inventory=self.cfg.initial_inventory)
        self.done = False
        self.total_cost = 0.0
        self.trace = []
        obs = self._build_obs(arrived=0, costs={}, probe=None)
        self.trace.append({"week": 0, "hidden": self.hidden.to_dict(),
                           "action": None, "obs": obs, "cost": 0.0})
        return obs

    def step(self, action: dict):
        """action = {"route": "suez"|"cape", "probe": bool}"""
        if self.done:
            raise RuntimeError("episode is done; call reset()")
        route = action["route"]
        if route not in ("suez", "cape"):
            raise ValueError(f"unknown route {route!r}")

        self.week += 1
        self.hidden = step_hidden(self.hidden, self.rng, self.cfg)
        arrived, costs = resolve_week(self.books, route, self.hidden, self.week, self.cfg)

        probe = None
        if action.get("probe"):
            probe = probe_result(self.hidden)
            costs["probe"] = self.cfg.probe_cost

        cost = float(sum(costs.values()))
        self.total_cost += cost
        self.done = self.week >= self.cfg.horizon_weeks

        obs = self._build_obs(arrived=arrived, costs=costs, probe=probe)
        info = {"hidden": self.hidden.to_dict()}  # for replay/oracle, never the agent
        self.trace.append({"week": self.week, "hidden": info["hidden"],
                           "action": dict(action), "obs": obs, "cost": cost})
        return obs, cost, self.done, info

    def _build_obs(self, arrived: int, costs: dict, probe) -> dict:
        obs = {
            "week": self.week,
            **observe_counts(self.hidden, self.cfg),
            "inventory": self.books.inventory,
            "arrived": arrived,
            "pipeline": [s.to_dict() for s in self.books.pipeline],
            "cost_breakdown": dict(costs),
            "probe_result": probe,
        }
        assert not (HIDDEN_KEYS & obs.keys()), "hidden state leaked into observation"
        return obs
