# supply-chain-pomdp

A partially-observable inventory-management benchmark. You run the procurement
desk for an electronics importer on the Asia–Europe shipping lane for 26 weeks:
each week decide how much stock to order, which route and supplier to use, and
whether to buy paid intelligence. Several latent processes — lane disruption,
supplier reliability, demand, and (in the full world) freight rates, port
congestion, and inbound quality — evolve underneath and leak only noisy or
indirect signals. An agent is scored on total cost over the episode.

A FastAPI backend serves the world API and a static Three.js frontend from the
same origin. No Node build step.

## The decision problem

Each week:

1. Optionally buy a $30 briefing that resolves the current lane state before you
   commit.
2. Choose an order quantity — a free integer from `0` to `order_max` (100) — and,
   if ordering, a route and a supplier.
3. Optionally adjust supplier contracts (sign / switch / renew / lapse).

The week then resolves: latent factors advance, ships sail and any that reach a
chokepoint that week are routed or delayed, arrivals stock inventory, demand
(~20 units/week) is served from on-hand stock, and costs total up. You observe
the result — never the hidden state — and decide again. Unmet demand is lost;
there is no backorder.

## Routing

Suez is ~3 weeks at $4/unit; the Cape is ~4 weeks at $6/unit. A Suez ship that
reaches the canal during a closure waits a week, then diverts around the Cape and
is billed the Cape differential at the diversion week — ordering into Suez during
a known disruption is not a free reroute.

## Latent factors

The scored task (the `CORE` registry) has three factors:

- **Lane disruption** — a semi-Markov regime (calm / watch / disruption / recovery
  / false alarm) driving the Suez, Bab-el-Mandeb, and Cape transit counts and a
  trade-press bulletin. The onset week is deliberately ambiguous: a count collapse
  can be a false alarm, a short grounding, or a long war, and only resolves over
  later weeks. Emissions are noiseless functions of the regime.
- **Supplier reliability** — a per-supplier OTIF chain (reliable / wobbling /
  degraded / defunct), surfaced as a scorecard. Only the spot supplier drifts; it
  can ship short or fail outright.
- **Demand** — a regime over the weekly order rate (base / surge / promo /
  seasonal / depressed).

Bare `World()` is the legacy two-factor world (disruption + supplier only). The
full `RICH` registry adds freight-rate, port-congestion, and quality factors,
all with *noisy* emissions — a quality regime, for instance, never fully reveals
itself from a single AQL sample and must be filtered over weeks. Factors are
appended to the registry and are inert when absent. See
`backend/src/world/README.md`.

## Suppliers and contracts

Three suppliers: an incumbent (`qualified` — reliable, dearer, evergreen
contract), a spot supplier (cheaper, drifts, can ship short or collapse), and a
mid-tier backup with a one-week onboarding lag. Sourcing is per-contract, not
per-order: you hold a contract (with a term length and clauses) and can only
source a supplier you currently hold a live contract with.

Contract behaviour is written against conditions, not scripted events. A contract
is "open" iff it has expired or its supplier is no longer alive; a weekly overhead
is charged for carrying two or more live contracts. From those two rules a sourced
supplier's collapse auto-opens its contract and prompts a renewal, and
dual-sourcing emerges as a hedge under volatility — without any code referencing
a specific week or named scenario.

## Cost model

| term | rate |
|---|---|
| shipping | $4/unit Suez, $6/unit Cape |
| holding | $1/unit/week (on-hand and in-transit) |
| stockout | $20/unit of unmet demand (lost sales) |
| briefing | $30 per analyst read |
| supplier audit | $25 (masked-supplier task only) |
| dual-sourcing | weekly overhead for holding ≥2 live contracts |

The $1-vs-$20 holding-to-stockout ratio implies a newsvendor critical ratio of
20/21 ≈ 0.95 — a target service level around 95%.

## Scoring

An agent's score is total cost over the 26-week episode (lower is better),
reported with its fill rate (served / demanded). `report_oracle.py` computes
per-seed reference baselines:

- **suez20 / cape20** — order 20 units every week via a single fixed route.
- **base-stock** — an order-up-to-`S` policy with `S` set from the newsvendor
  critical ratio (~95% service).
- **naive_min** — the minimum of the three.

## Calibration

Magnitudes trace to cited real-world anchors rather than being chosen for feel:
voyage lengths, divert penalties, crisis transit counts, unit costs, and
supplier-failure hazards are pinned to the 2021 Suez obstruction, the 2023–2026
Red Sea crisis, UNCTAD/IMF PortWatch data, and published supplier-bankruptcy
statistics. Each magnitude and its source is recorded in
`backend/V1_CHANGE_LOG.md`.

## Quick start

From the repo root:

    cd backend
    uv sync
    uv run uvicorn src.api.app:app --host 0.0.0.0 --port 9000

Open <http://localhost:9000>. The backend serves the frontend from the same
origin; there is no separate frontend server. In the UI you can play the desk
yourself or watch an LLM agent play. Research mode reveals the hidden tape
(x-ray) live; it is off for benchmark runs.

## Development

Reload mode:

    cd backend
    uv run uvicorn src.api.app:app --reload --host 0.0.0.0 --port 9000

Regression suite (single file, ~126 tests, a few seconds):

    cd backend
    uv run pytest test_world.py -q

Baseline summary (per-seed suez20 / cape20 / base-stock cost + fill / naive_min):

    cd backend
    uv run python report_oracle.py

## Prerequisites

- Python 3.12+
- uv
- A browser

## Frontend dependencies

There is no frontend package manager. The frontend's only external runtime
dependency, `three`, is loaded from a CDN via an import map in
`frontend/index.html`. uv manages the Python side only.

## Repository layout

    backend/
      src/world/             the factored-POMDP world (pure stdlib, no I/O)
        engine.py            World: the reset()/step() orchestrator
        registry.py          composes modules into REGISTRY / CORE / RICH
        config.py            global scalar knobs
        couplings.py         the only code that reads two factors (in cost)
        modules/             Tier 1 — the six latent factors, each a sealed box
        substrate/           Tier 2 — module-agnostic ships / inventory / logistics
      report_oracle.py       per-seed baseline policies (fixed-route + base-stock)
      src/agent/             LLM agent harness (deepagents, OpenRouter, SSE)
      src/api/               FastAPI app (world API + agent runs + static frontend)
      test_world.py          the single regression file (engine, world, agent, API)
      V1_CHANGE_LOG.md       design decisions, each with its real-world anchor
      claude-mds/            architecture and dependency notes
    frontend/                static JS/CSS/Three.js UI served by FastAPI
