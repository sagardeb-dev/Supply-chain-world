# `oracle/` — the anchors

The oracles sit **above** the engine — they *drive* `World` instances, never live
inside one. They define the cost scale against which an agent's play is measured.
Both today are single-factor (the `disruption` world); the supplier marginal is
deferred.

| File | Oracle | What it is |
|------|--------|------------|
| `clairvoyant.py` | clairvoyant | DP on the **seed-fixed** trajectory — the luck-*inclusive* per-seed **lower bound**. |
| `causal.py` | causal-aware | Exact expectimax on the belief-MDP — the **benchmark anchor**, the optimal *non-clairvoyant* policy. |

Reading: regret against the causal oracle is pure **skill deficit**;
`causal − clairvoyant` per seed is the **luck premium** of that seed.

## Clairvoyant — the per-seed lower bound

Because the hidden trajectory is a function of the **seed alone** (actions never
consume the rng), the oracle replays the seed once with a no-op playthrough to
learn the *entire* future, then solves exactly for the cost-minimizing
`(qty, route)` sequence. It never buys briefings — it already knows every regime.

- `hidden_trajectory(seed, cfg)` — one no-op playthrough recovers `h_1..h_H`.
- `arrival_week(route, dispatch, traj, cfg)` — deterministic arrival under
  transit-week causality; the exact mirror of `substrate.books._advance`.
- `optimal_plan_for(trajectory, cfg)` — DP over `(week, inventory, pending)`;
  returns `(min_cost, plan)`. In-transit holding is charged up-front at dispatch,
  which sums to the same total the engine charges weekly.
- `oracle_cost(seed)` / `oracle_plan(seed)` — the public surface.

## Causal — the benchmark anchor

Solves the belief-MDP exactly by finite-horizon expectimax over the agent's
information state, using the **true kernel but no knowledge of the future**.

Two facts make this tractable:

1. **Finitely-supported beliefs.** Observations are *noiseless* functions of the
   regime, so reachable beliefs are singletons everywhere except the crash week,
   where the support is `{false_alarm, short-onset, long-onset}` — and sub-beliefs
   of that as in-flight ships leak more. The belief update groups chance branches
   by the **full agent-visible outcome** (regime, pipeline state, arrived qty).
2. **A canonical relative pipeline.** Once a ship's chokepoint has resolved, only
   `(weeks-until-arrival, qty)` matter; queued ships merge into one qty pool. The
   encoding is value-preserving and pinned against the real `Books` machinery.

Public surface:

- `CausalOracle(cfg)` — build once per config (the memo is policy-wide, not
  per-seed). `.value()` is the expected total cost of the optimal causal policy
  from reset; `.decide(week, belief, inventory, pipe)` returns `(brief?, qty,
  route)`, the optimal action at an info state — including whether buying the
  paid briefing has positive value of information.
- `causal_play(seed, cfg)` / `causal_cost(seed, cfg)` — run the oracle on the
  **live engine**, deciding from observations only. Every step cross-checks the
  engine's outcome against the DP branch (cost, inventory, pipeline must match) —
  this is the live guard that the DP mirror and the real physics agree.

## The golden pin

`CausalOracle().value() == 4251.9607875333395` is pinned as a test. It is the
silent-corruption guard for the default world: any change that perturbs the
two-factor dynamics or the cost arithmetic moves this number and fails the suite.

## `resolve_rel` ↔ `resolve_week`

`causal.py:resolve_rel` is the **pinned mirror** of
`substrate/logistics.py:resolve_week` — the same weekly physics on the DP's
relative encoding. They are deliberately not deduped (a shared abstraction would
de-optimize the DP). Held in lockstep by `test_resolve_rel_mirrors_resolve_week`
+ the `causal_play` cross-check. Change one, change the other.
