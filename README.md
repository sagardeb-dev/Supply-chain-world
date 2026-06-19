# supply-chain-pomdp

A factored partially-observable supply-chain benchmark with an **exact causal
oracle** as its anchor. You run a procurement desk on the Asia–Europe shipping
lane for 26 weeks: keep ~20 units/week flowing, decide how to route and who to
source from, and pay for intel only when it is worth it. Two hidden generators
drive the world — a shipping-lane disruption chain and a supplier-reliability
chain — and the benchmark measures how much of the optimal (oracle) value an
agent captures, and where its reasoning breaks.

A FastAPI backend serves both the world API and a static Three.js frontend on
the same origin. No Node build step.

---

## What makes it a benchmark, not a toy

- **Factored POMDP, exact oracle.** Two independent latent chains (lane
  disruption + spot-supplier reliability) couple to the agent *only through
  cost*. That keeps the belief factorized, so the optimal policy is computed by
  an **exact finite-horizon belief-MDP expectimax** (no approximation). The
  oracle value is the score everything is measured against. Adding a factor is
  +1 marginal, not a rewrite.
- **Noiseless emissions, real ambiguity.** Observations are deterministic
  functions of hidden state with a deliberate 1-week ambiguity band (e.g. a
  transit-count crash that could be a false alarm, a grounding, or a war).
  The agent's job is inference under that ambiguity, not denoising.
- **Calibrated to the real world.** Voyage lengths, divert penalties, crisis
  transit counts, unit costs, supplier-bankruptcy hazards — every magnitude
  traces to a cited real anchor (2021 Suez obstruction, 2023–2026 Red Sea
  crisis, UNCTAD/IMF PortWatch, supplier-failure statistics). See
  `backend/V1_CHANGE_LOG.md`.

## The two hidden factors

1. **Lane disruption** — a semi-Markov chain over calm / watch / disruption
   (short grounding vs long war) / recovery. Drives transit counts on Suez,
   Bab-el-Mandeb, and the Cape. You route via Suez (~3 wk, cheaper) or around
   the Cape (~4 wk, dearer), and may buy a $30 briefing to disambiguate.
2. **Supplier reliability** — a semi-Markov chain over reliable / wobbling /
   degraded / **defunct** for the spot supplier, surfaced as an OTIF
   scorecard. A degraded supplier can ship short — or die for good.

## Suppliers, contracts, and emergence

Three suppliers — **Incumbent** (qualified: reliable, dearer, evergreen
contract), **Spot** (cheaper, drifts, can ship short or collapse), **Backup**
(mid-tier, 1-week onboarding). Sourcing is per-*contract*, not per-order: you
sign a contract (with negotiable term length and clauses), and you can only
source a supplier you hold a live contract with.

The interesting mechanics are not hand-coded scenarios — they **emerge** from
three authored primitives:

| Lever | What is authored | What emerges |
|---|---|---|
| Generative primitive | a per-week hazard a degraded supplier goes `defunct` | unscheduled supplier collapses, no scripted week |
| Standing rule | a *condition*: a contract is "open" iff expired **or** its supplier is not alive | when a sourced supplier dies, its contract auto-opens and a renewal prompt fires — nothing references the collapse primitive |
| Cost gradient | a weekly overhead for carrying ≥2 live contracts | dual-sourcing-under-volatility appears as the agent's optimal hedge |

The discipline that makes this work: **never write a rule against a date or a
named scenario — only against a condition, a probability, or a cost.**

---

## Quick start

From the repo root:

    cd backend
    uv sync
    uv run uvicorn src.api.app:app --host 0.0.0.0 --port 9000

Open <http://localhost:9000>. The backend serves the frontend on the same
origin — there is no separate frontend server.

In the UI you can **play** the desk yourself or **watch an LLM agent** play.
Toggle **research mode** to reveal the hidden tape (x-ray) live; it is off for
benchmark runs.

## Development

Reload mode:

    cd backend
    uv run uvicorn src.api.app:app --reload --host 0.0.0.0 --port 9000

Regression suite (single file, fast subset):

    cd backend
    uv run pytest test_world.py -q

The two slow oracle tests run the full ~122 s exact solve; include them for the
oracle gate, deselect them for fast iteration:

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
      src/world/      world engine, factored kernels, emissions, contracts
      src/world/causal_oracle.py   exact belief-MDP expectimax (the anchor)
      src/agent/      LLM agent harness (deepagents, OpenRouter, SSE)
      src/api/        FastAPI app (serves the world API + the frontend)
      test_world.py   the single regression file (engine, oracle, API pins)
      V1_CHANGE_LOG.md   every design decision, with real-world evidence
      claude-mds/     architecture, dependency graph, sequence-of-* design docs
    frontend/         static JS/CSS/Three.js UI served by FastAPI

## Where to read next

- `backend/V1_CHANGE_LOG.md` — design decisions and calibration evidence.
- `backend/claude-mds/architecture.md` — the two-factor framing.
- `backend/claude-mds/sequence-of-ideas/003-factored-world-and-per-factor-oracles.md`
  — why the factored oracle stays exact.
- `backend/claude-mds/sequence-of-changes/004-supplier-roster-contracts.md`
  — the supplier roster, contracts, and the three levers.
