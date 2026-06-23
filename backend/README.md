# backend

The Python backend: the POMDP world, the LLM-agent harness that plays it, and a
FastAPI app that serves both the world API and the static frontend. Run and
setup instructions live in the [repo root README](../README.md); this file maps
the three subsystems and how they fit together.

```
src/
  world/   the factored-POMDP simulator + the optimal-policy oracles
  agent/   the LLM agent harness (drives a World through the OpenRouter API)
  api/     FastAPI app: world HTTP API + SSE stream + static frontend
test_world.py   the single regression file (engine, oracle pins, API)
report_oracle.py  prints the oracle / benchmark summary
V1_CHANGE_LOG.md  every calibrated magnitude and its real-world source
```

## `src/world/` — the simulator

A weekly supply-chain decision problem expressed as a **factored POMDP**:
independent hidden factors that couple to the agent only through cost, which is
what keeps the optimal policy an exactly-solvable dynamic program. `World.reset`
/ `World.step` is the whole interface. A `World` is `(config, registry)` — the
default registry is the two-factor world the oracle is pinned to; `RICH` is the
six-factor world. See [`src/world/README.md`](src/world/README.md) and the
binding invariants in [`src/world/AGENTS.md`](src/world/AGENTS.md).

## `src/agent/` — the harness

Wraps a `World` in the three tools an LLM agent calls (`place_order`,
`buy_briefing`, `lock_freight`), builds a `deepagents` agent on an OpenRouter
model, and runs an episode while recording every decision. `play_agent.py` is the
headless entry point used to produce the traces in [`../run/`](../run). See
[`src/agent/README.md`](src/agent/README.md).

## `src/api/` — the server

A FastAPI app that exposes the world over HTTP, streams agent episodes over SSE,
and serves the static `frontend/` from the same origin (no Node build step). See
[`src/api/README.md`](src/api/README.md).

## Tests

One regression file. The default world is held **byte-identical** by two pins —
`CausalOracle().value() == 4251.96…` and the `resolve_rel`↔`resolve_week` mirror
test — so any change that perturbs the two-factor dynamics or cost arithmetic
fails the suite. Two tests run the full exact solve (~2 min); deselect them for
fast iteration (see the root README).
