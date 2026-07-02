# backend

The Python backend: the POMDP world, the LLM-agent harness that plays it, and a
FastAPI app that serves both the world API and the static frontend. Run and
setup instructions live in the [repo root README](../README.md); this file maps
the three subsystems and how they fit together.

```
src/
  world/   the factored-POMDP simulator + classical-policy baselines
  agent/   the LLM agent harness (drives a World through the OpenRouter API)
  api/     FastAPI app: world HTTP API + SSE stream + static frontend
test_world.py   the single regression file (engine, world, agent, API)
report_oracle.py  prints the base-stock / fixed-policy benchmark summary
V1_CHANGE_LOG.md  every calibrated magnitude and its real-world source
```

## `src/world/` — the simulator

A weekly supply-chain decision problem expressed as a **factored POMDP**:
independent hidden factors that couple to the agent only through cost, which
keeps the factors independent so adding a factor or SKU is a config change.
`World.reset` / `World.step` is the whole interface. A `World` is
`(config, registry)` — bare `World()` is the legacy two-factor `REGISTRY`, the
**scored** inventory-management task is the three-factor `CORE`
(disruption + supplier + demand), and `RICH` is the full six-factor world. See
[`src/world/README.md`](src/world/README.md) and the
binding invariants in [`src/world/AGENTS.md`](src/world/AGENTS.md).

## `src/agent/` — the harness

Wraps a `World` in the tools an LLM agent calls (`place_order`, `buy_briefing`,
and `lock_freight` in freight-enabled worlds), builds a `deepagents` agent on an OpenRouter
model, and runs an episode while recording every decision. `play_agent.py` is the
headless entry point used to produce the traces in [`../run/`](../run). See
[`src/agent/README.md`](src/agent/README.md).

## `src/api/` — the server

A FastAPI app that exposes the world over HTTP, streams agent episodes over SSE,
and serves the static `frontend/` from the same origin (no Node build step). See
[`src/api/README.md`](src/api/README.md).

## Tests

One regression file (`test_world.py`) — ~126 fast tests in a few seconds. It
pins the factored dynamics and cost arithmetic, the registry draw order, and the
base-stock / fixed-policy baselines that the `/benchmark` endpoint serves.
