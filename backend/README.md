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
report_oracle.py  prints the base-stock / fixed-policy benchmark summary (the floor)
filters.py        exact per-factor HMM forward filters (RICH latent modules)
oracle_policy.py  Bayes-filter fair oracle: rolling-horizon policy over filters.py's posteriors (the mid-tier baseline)
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

Wraps a `World` in the tools an LLM agent calls. `place_order` and
`buy_briefing` are always bound; `buy_audit`, `lock_freight`, `expedite_air`,
`inspect_batch`, and `order_component` are bound only when the world's
registry/product actually has the module they act on (registry/product-gated
tools — see [`src/agent/README.md`](src/agent/README.md)). Builds a
`deepagents` agent on an OpenRouter model, and runs an episode while recording
every decision. `play_agent.py` is the headless entry point used to produce
the traces in `runs/`.

## `src/api/` — the server

A FastAPI app that exposes the world over HTTP, streams agent episodes over SSE,
and serves the static `frontend/` from the same origin (no Node build step). See
[`src/api/README.md`](src/api/README.md).

## Tests

One regression file (`test_world.py`) — ~126 fast tests in a few seconds. It
pins the factored dynamics and cost arithmetic, the registry draw order, and the
base-stock / fixed-policy baselines that the `/benchmark` endpoint serves.

## Reproducing the benchmark — `bench.py`

The whole evaluation pipeline is one CLI (config in `bench_config.py`:
seed groups, model list, oracle rep count). Every step skips work already on
disk, so each command is safe to re-run.

```bash
uv run python bench.py run      # fill missing (model, seed) traces (LLM calls, sequential)
uv run python bench.py oracle   # 20-rep Bayes-oracle refs -> runs/<exp>/oracle_refs.csv (CPU, deterministic)
uv run python bench.py score    # skill = (basestock-llm)/(basestock-oracle) -> skill_scores.csv
uv run python bench.py grade    # belief grading (pass-through to runs/grade_beliefs.py)
uv run python bench.py report   # runs/<exp>/report.md + regenerated manifest.json
```

`basestock` costs come from `sweep/results.csv` (regenerate with
`uv run python -m sweep.run_sweep`). `runs/<exp>/oracle_refs.csv` is committed
so scoring works without recomputing the oracle; `run_oracle` is deterministic
per (seed, k), so any row can be verified by rerunning
`bench.py oracle --seeds N --out /tmp/check.csv` and diffing.
