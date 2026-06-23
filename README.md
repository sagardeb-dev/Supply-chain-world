# supply-chain-pomdp

A partially-observable supply-chain decision problem with an exactly-computable
optimum. You run a procurement desk on the Asia–Europe shipping lane for 26
weeks: order stock, choose a shipping route and a supplier, and decide when
paid intelligence is worth buying. Hidden processes — a shipping-lane
disruption chain and a supplier-reliability chain — evolve underneath and leak
only indirect signals. The benchmark scores how close an agent's total cost
comes to the optimal policy's, and where its inference breaks down.

A FastAPI backend serves both the world API and a static Three.js frontend on
the same origin. No Node build step.

## Why it exists

Most agent benchmarks can only rank policies against each other or against a
human baseline — the *optimum is unknown*, so "how far from best-possible was
this?" has no answer. This world is built so that answer is computable.

The hidden factors are independent in their dynamics and their signals, and
couple to the agent only through cost. Under those conditions the optimal
partially-observed policy is an exact finite-horizon dynamic program over the
agent's belief — no sampling, no function approximation. So an agent's score
has an absolute meaning (dollars above the best achievable under the same
uncertainty), and the gap decomposes cleanly:

- **regret vs the causal oracle** — pure skill deficit. The oracle saw exactly
  the same observations; anything extra the agent paid is its own inference
  error.
- **causal − clairvoyant** — the *luck premium* of the seed: what an agent who
  could see the future would have saved over the best non-clairvoyant policy.
  This is the irreducible part, charged to the draw, not the player.

## How a week works

Each week you choose an order quantity (`0`, `20`, or `40` units), and if you
order, a route and a supplier. You may also manage supplier contracts, and you
may pay $30 for a briefing that disambiguates the lane state before you commit.
Then the week resolves: latent factors advance, ships sail and the ones that
reach a chokepoint that week are routed or delayed, arrivals stock inventory,
demand (≈20 units/week) is served, and costs total up. You then see the new
observation — never the hidden state — and decide again.

Routing is a real trade-off. Suez is ~3 weeks and cheaper; the Cape is ~4 weeks
and dearer. A Suez ship that meets the canal during a closure waits a week and
then diverts around the Cape, billed at the Cape rate — so ordering into Suez
during a known crisis is not a free reroute.

## The hidden factors

The default world has two latent factors. Both are semi-Markov regimes
(state plus age) whose observations are *noiseless* functions of the regime,
with a deliberate one-week onset ambiguity — the agent's job is inference under
that ambiguity, not denoising.

1. **Lane disruption** — calm / watch / disruption (a short grounding or a long
   war) / recovery / false alarm. Drives the transit counts you observe on
   Suez, Bab-el-Mandeb, and the Cape, plus a trade-press bulletin. The crash
   week is genuinely ambiguous: a count collapse could be a false alarm, a
   grounding, or a war, and only resolves over subsequent weeks.
2. **Supplier reliability** — a per-supplier OTIF chain (reliable / wobbling /
   degraded / defunct) for the spot supplier, surfaced as a scorecard. A
   degraded supplier can ship short, or fail for good.

A larger six-factor world (`RICH`) adds demand, freight-rate, port-congestion,
and quality factors, these with *noisy* emissions (a quality regime, for
instance, never fully reveals itself from a single AQL sample — it must be
filtered over weeks). The default two-factor world is kept byte-identical to
its original arithmetic, which is what keeps the oracle's pinned value stable;
the rich factors are additive and inert when absent. See
`backend/src/world/README.md`.

## Suppliers and contracts

Three suppliers: an incumbent (reliable, dearer, evergreen contract), a spot
supplier (cheaper, drifts, can ship short or collapse), and a mid-tier backup
with a one-week onboarding lag. Sourcing is per-contract, not per-order — you
hold a contract (with a negotiable term length and clauses) and can only source
a supplier you currently have a live contract with.

The contract behaviour is written against conditions, not scripted events. A
contract is "open" *iff* it has expired or its supplier is no longer alive; a
weekly overhead is charged for carrying two or more live contracts. From those
two rules, a sourced supplier's collapse auto-opens its contract and prompts a
renewal, and dual-sourcing emerges as the hedge under volatility — without any
code referencing a specific week or a named scenario.

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
origin — there is no separate frontend server.

In the UI you can play the desk yourself or watch an LLM agent play. Toggle
research mode to reveal the hidden tape (x-ray) live; it is off for benchmark
runs.

## Development

Reload mode:

    cd backend
    uv run uvicorn src.api.app:app --reload --host 0.0.0.0 --port 9000

Regression suite (single file, fast subset):

    cd backend
    uv run pytest test_world.py -q

Two tests run the full exact solve (~122 s). Include them for the oracle gate;
deselect them for fast iteration:

    uv run pytest test_world.py -q -k "not causal_oracle_within_bounds and not benchmark_endpoint"

Oracle / benchmark summary:

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
      src/world/             the factored-POMDP world
        engine.py            World: the reset()/step() orchestrator
        registry.py          composes modules into the default and RICH worlds
        config.py            global scalar knobs
        modules/             Tier 1 — the latent factors, each a sealed box
        substrate/           Tier 2 — module-agnostic ships/inventory/logistics
        couplings.py         Tier 3 — the only code that reads two factors (in cost)
        oracle/              clairvoyant + exact causal oracle (the anchors)
      src/agent/             LLM agent harness (deepagents, OpenRouter, SSE)
      src/api/               FastAPI app (serves the world API + the frontend)
      test_world.py          the single regression file (engine, oracle, API pins)
      V1_CHANGE_LOG.md       design decisions, each with its real-world anchor
      claude-mds/            architecture and design notes
    frontend/                static JS/CSS/Three.js UI served by FastAPI

## Where to read next

- `backend/src/world/README.md` — the world's three-tier design and the factored
  structure that keeps the oracle exact.
- `backend/src/world/oracle/README.md` — the clairvoyant and causal oracles, and
  what regret against each one measures.
- `backend/src/world/modules/README.md` — the six latent factors and how a module
  stays a sealed box.
- `backend/V1_CHANGE_LOG.md` — design decisions and calibration evidence.
