"""The oracles: anchors that sit ABOVE the engine (they drive World
instances), never inside it.

  clairvoyant -- DP on the seed-fixed trajectory; the luck-INCLUSIVE
                 per-seed lower bound.
  causal      -- exact expectimax on the belief-MDP; THE benchmark anchor
                 (optimal NON-clairvoyant policy). Single-factor today
                 (disruption); the supplier marginal is deferred.

Both public surfaces are re-exported here so importers use
`from src.world.oracle import ...` regardless of which file a name lives in.
"""

from .causal import (CausalOracle, EMPTY_PIPE, canonical, causal_cost,
                     causal_play, regime_of, resolve_rel, transition_dist)
from .clairvoyant import (arrival_week, hidden_trajectory, optimal_plan_for,
                          oracle_cost, oracle_plan)

__all__ = [
    "CausalOracle", "EMPTY_PIPE", "canonical", "causal_cost", "causal_play",
    "regime_of", "resolve_rel", "transition_dist",
    "arrival_week", "hidden_trajectory", "optimal_plan_for", "oracle_cost",
    "oracle_plan",
]
