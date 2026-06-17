# V1 Change Log

Design decisions for the supply-chain POMDP world. Each entry records what
changed, why, and the evidence. Code follows this file, never the reverse.

## 2026-06-17 — Supplier roster, contracts, and the three emergence levers

### Problem

The world had one supplier choice (qualified vs spot) and no relationship
structure. The manager's ask: model real supplier relationships — multiple
suppliers, contracts with terms and timers, the ability to negotiate, and
events like a supplier going under. The deeper ask: can these mechanics
*emerge* from authored primitives, so adding realistic detail does not mean
hand-coding every scenario? The answer is a recipe (below) and three levers.

### The module recipe (one entity = one module)

Every entity is built from fixed slots, so adding one is additive and the
exact oracle survives:

- **state** — its own dataclass, reads no other module.
- **kernel** — `step(state, rng, cfg)`: one tick, own state + shared rng only.
- **emission** — noiseless, own observation keys.
- **actions** — finite verbs + a validator.
- **cost** — the ONLY slot allowed to read more than one module's state.

Two laws keep the exact oracle alive: (1) couple only through cost, so beliefs
factorize and the oracle is exact factored expectimax — adding a supplier is
+1 marginal; (2) one tick = bounded work, so "negotiation" is menu selection,
never a multi-round dialogue.

### The three levers (emergence without per-scenario code)

The discipline: **never write a rule against a date or a named scenario —
only against a condition, a probability, or a cost.**

1. **Generative primitive** — a low-probability kernel transition. Here:
   `sup_defunct_from_degraded = 0.06`/week, a chronically degraded spot
   supplier dies for good (absorbing `defunct`). This produces unscheduled
   collapse events without anyone scripting "week N, supplier dies".
2. **Standing rule** — a CONDITION, never a date. A contract is *open*
   (needs attention) iff `expired OR supplier-not-alive`. Nothing references
   the defunct primitive; yet when a sourced supplier dies, its contract
   auto-opens and the renewal prompt fires. Proven by
   `test_defunct_spot_auto_opens_its_contract_no_script`.
3. **Cost gradient** — `dual_source_overhead = 4.0`/week for carrying ≥2 live
   time-boxed contracts. We author only the cost; the *strategy* of hedging
   under volatility emerges as the agent's optimal response.

### Decisions

1. **Roster of three** (`SUPPLIERS` registry): `qualified` (frozen incumbent,
   OTIF 99, lead 14d, +$1.0/u, evergreen contract), `spot` (drifts via the
   reliability kernel, −$1.5/u, can ship short or die), `backup` (frozen
   mid-tier, OTIF 95, lead 16d, +$0.3/u, 1-week onboarding before its first
   shipment). Only spot carries hidden latent state — the oracle's one
   supplier chain.
2. **Per-contract sourcing, not per-order.** You sign a contract with a
   supplier; sourcing is gated to suppliers with a live contract. No fallback:
   sourcing an uncontracted supplier raises (`ValueError`), it does not
   silently substitute.
3. **Evergreen incumbent.** The qualified contract has `end_week = None` and
   never expires — avoids the dominance trap only via the `qualified_premium`
   knob (the incumbent is reliable but dearer, so the cheaper-but-riskier spot
   stays a real choice).
4. **Negotiation = menu** (`TERM_MENU`: short/long/strict/lenient), each a
   bounded set of (weeks, unit multiplier, OTIF floor, break-fee multiplier).
   `contract_weeks = 8` → ~3 renewal events per 26-week horizon;
   `contract_otif_floor = 85`; `contract_break_fee = 10.0` (irreversibility
   teeth on early exit).
5. **Hard gap.** When an exclusive spot supplier dies, you are stuck — you
   cannot even source it (its contract is now open) and backup needs
   onboarding. The punishment is the absence of an escape hatch; it falls out
   of R2 (defunct → ships 0) × R4 (the mask), not from coded logic.

### Frontend (R8)

- 3-row defunct-aware scorecard (OTIF/lead/unit-delta, severity band, DEFUNCT
  marker, ◆ contracted / ← sourced / onboard marks).
- Contract HUD: contract chips (supplier, ends-week or evergreen, unit price)
  plus an auto-renewal banner that surfaces `contract_open` — the emergence,
  visible, fired by the world's standing rule, not a scripted week.
- **Auto-sign UX**: the supplier deck chooses who fulfils this week's order;
  sourcing a supplier with no open contract auto-signs one in the same step.
  The act of sourcing IS contracting — no separate sign screen, and it removes
  the dead-end where selecting an uncontracted supplier hard-failed.

### Oracle gate (R7)

The exact belief-MDP expectimax solver still solves (~122 s once per process)
and the engine-vs-DP cross-check still passes against the fully rebuilt engine:
contracts are observed and deterministic (not belief), so coupling stays
cost-only and the factorization holds. Shipped decision: the oracle remains
qualified-only-valid for v1 (it sources the incumbent); the fully factored
supplier-marginal oracle is deferred as a scoped follow-up. The anchor — the
benchmark's entire value — survives.

### Verification

- `test_world.py`: 80 fast tests pass (2 slow oracle tests deselected for
  speed; run them for the gate). Key pins: the defunct kernel hazard
  distribution, the no-script auto-open emergence, the per-contract source
  mask (raises on uncontracted), the dual-source overhead cost, the hard gap.
- Live page driven via Playwright: 3-supplier scorecard + contract HUD render;
  sourcing spot auto-signs and the second contract chip appears (Week 0 → 1,
  no 500).

### Calibration evidence (supplier reliability + bankruptcy)

| World number | Real anchor |
|---|---|
| sup_defunct_from_degraded 0.06/wk | ~16% tech-sector bankruptcy; ~14.5% of disruptions are supplier failures — a few %/wk from a distressed (degraded) supplier gives a realistic 'distressed → dead' tail |
| qualified OTIF 99 vs spot drift | tier-1 qualified vendors run high, audited OTIF; spot/marketplace sources slip |
| backup 1-wk onboard | new-supplier qualification/onboarding lead before first PO ships |
| contract 8 wks | quarter-ish purchase-agreement terms → ~3 renewals/horizon |
| break fee 10.0 | early-termination clauses are standard teeth on supply contracts |

## 2026-06-17 — LLM agent harness (deepagents, OpenRouter, SSE, resume)

### Problem

The world has a clean Gym-shaped surface (reset / step / request_briefing)
but no agent and no way to watch one play. A prior attempt produced a
turn-by-turn agent — re-invoked fresh once per week, no memory across
weeks, 26 cold questionnaires instead of one continuous planner. That is
the "quiz not a job" mistake reincarnated in the agent. We need to (a)
see an LLM play live, and (b) measure the one missing number: how much of
the causal-oracle skill gap a real LLM captures, and where its reasoning
fails. That number gates the "scale the factors" decision (which
difficulty axis is actually too easy) — building a second latent module
before we have it would be blind.

### Decisions

1. **The agent owns the loop.** One deepagents session runs the whole
   26-week episode. We hand it its tools once plus a system prompt
   describing the desk, and let the tool-calling loop run until the
   episode reports done. There is NO `for week in range(26)` wrapping the
   agent; the week counter lives inside World. This is the entire point
   of the rebuild.

2. **Tools mirror the three real world actions, 1:1.** get_week
   (the current observation), buy_briefing (the paid analyst line),
   place_order (qty in {0,20,40} x route in {suez,cape}, advances a
   week). No invented actions, no "assessment report" — the world has
   exactly these three. The briefing tool is exposed even though the
   oracle never buys it (the chokepoint leaks make the info effectively
   free): an agent that buys it is over-spending, and that over-spend is
   a measurement, not a bug to fix here.

3. **Tools are thin wrappers over the same in-process World methods the
   HTTP handlers call.** A new svc_* service layer (svc_observation /
   svc_briefing / svc_step) is the single path both the HTTP API and the
   agent tools go through — no self-HTTP, no duplicated world logic, same
   gates. The agent never receives the step() info dict (hidden state);
   get_week output is asserted to share no key with HIDDEN_KEYS.

4. **No fallback logic, anywhere.** A missing OPENROUTER_API_KEY, a
   place_order with qty>0 and no route, or a model error each RAISE and
   surface as a visible SSE `error` event. No silent default route, no
   retry-with-simpler-prompt, no default order. The run either works or
   stops loud.

5. **OpenRouter is the sole provider; the key stays server-side.** The
   model is langchain_openai.ChatOpenAI pointed at
   https://openrouter.ai/api/v1, key read from os.environ
   (exported in the VM shell before uvicorn — never committed, never sent
   to the browser). Any OpenRouter slug can be typed at run time; the
   frontend default starts cheap to validate plumbing before a flagship
   run spends credit.

6. **Two run modes via interrupt_on.** Autonomous = the agent plays all
   26 weeks straight through. Step-gated = create_deep_agent(...,
   interrupt_on={"place_order": True}) pauses before each order; the
   human clicks Advance and the run resumes via
   Command(resume={"decisions":[{"type":"approve"}]}). One config line is
   the only difference.

7. **True mid-run resume by run_id.** deepagents' AsyncSqliteSaver
   persists the agent's message history across process restarts; we
   separately pickle the World object (verified picklable and
   rng-faithful across pickle) keyed by the same run_id, snapshotting it
   inside place_order so the agent checkpoint and the world snapshot never
   diverge by more than one idempotent step. On resume: load the World,
   rebuild the agent against the same checkpointer + thread_id, continue.

8. **Reasoning streams live over SSE.** agent.astream(input, config,
   stream_mode=["updates","messages"]) demuxes into SSE events: `thought`
   (reasoning tokens from messages), `tool_call` and `tool_result`
   (structured, from updates), `interrupt` (step-gate pause), `done`,
   `error`. A vanilla-JS EventSource panel renders them; the existing
   oracle scoreboard fills in at `done`. The 3D scene reacting to the
   stream is deferred — the text panel is the diagnostic.

### Scope

New code lives in backend/src/agent/ (service, tools, factory, prompt,
runner) plus four endpoints and a sqlite lifespan in src/api/app.py, plus
a frontend agent panel. The engine (src/world/*) is UNTOUCHED. New deps
go in a uv `agent` dependency group. Tests extend test_world.py with a
MOCKED model — no test makes a live LLM call.


### Sign-off (verified 2026-06-17)

Built across commits add5edb..(this). Backend tests: 42/42 (38 prior +
service_parity, tools_gating, resume_roundtrip, agent_sse_mock; the agent
tests use a mocked model, no live LLM). Run persistence verified live:
per-run JSONL log + pickled World snapshots + the deepagents sqlite
checkpointer all populated by a real episode.

Frontend verified live with Playwright. Two bugs found and fixed there:
the start modal (z 50) covered the always-on agent panel and ate its
clicks (panel raised to z 60); and the agent was built synchronously in
the endpoint, so a missing key raised an opaque 500 instead of a visible
error (stream() now takes a build thunk and constructs the agent inside
its try, so missing-key / bad-slug surface as a readable `error` event --
confirmed live before the key was supplied).

First real agent-vs-oracle datapoint (seed 3, model openai/gpt-oss-120b:nitro,
autonomous): the agent played all 26 weeks and the scoreboard rendered
clairvoyant $3200 = causal oracle $3200 (luck premium 0 on this seed),
best fixed policy $3560, agent $4540. The agent's regret vs the oracle is
$1340 and it underperformed the naive base-stock policy by ~$1000: it
settled into a rigid 20-via-Suez-every-week policy, ignored the Red Sea
disruption bulletin it saw from week 4, never front-loaded (qty 40), and
never switched to Cape. So the very signal the world is built around went
unused. This reframes "too easy": the agent is not beating the existing
task, let alone finding it trivial -- the gap to scale toward is the
agent's, not the oracle's. The next factor decision should be gated on a
sweep across seeds and a stronger model, not assumed.

Open / deferred: model dropdown (text input for now), edit/reject in the
step-gate (approve-only), 3D scene reacting to the stream (text panel is
the diagnostic), a multi-seed agent sweep.

## 2026-06-12 — Research surface: read-only API + explainer UI

### Problem

The frontend is a faithful play client but says nothing about what the
project IS: no statement that the disruption regime is the single hidden
semi-Markov factor (regime, age), no visual distinction between the one
RNG draw per week (transition.step_hidden) and the pure-function
everything-else, no oracle, no regret. A visitor concludes "shipping
game", not "exact-oracle POMDP benchmark". Separately, the agent door
must stay open: agents will play the same HTTP API, so any UI that
reveals hidden state live must be impossible to reach from a benchmark
episode — unreachable, not merely unshown.

### Decisions

1. **The research surface is read-only.** No engine change. New API
   endpoints serve only what world.trace and the oracle machinery
   already compute. The world dynamics, observation channels, and action
   space are untouched.
2. **X-ray access is gated at episode creation.** ResetRequest gains
   research_mode: bool = False. GET /episodes/{id}/xray returns the
   hidden trajectory SO FAR (week, event_state, age, disruption_type,
   regime) and responds 403 for non-research episodes. Rationale: the
   gate is a property of the episode, set before the first observation,
   so an agent harness physically cannot peek mid-episode. The
   post-episode /trace reveal stays available to all episodes (existing
   behavior, an analysis-side artifact).
3. **GET /benchmark/{seed}** returns the anchor set for a seed:
   clairvoyant, causal, suez20, cape20, basestock, naive_min, the luck
   premium (causal - clairvoyant), and the causal oracle's weekly plan
   rows (week, briefed, qty, route, belief_support, cost). The causal
   oracle solves lazily in a background thread on first request (~122 s,
   once per process) and is cached; while solving the endpoint returns
   202 {status: "solving"}. NOTE: this endpoint reveals seed-level
   structure (disruption weeks via the plan), so an agent harness must
   not expose it to agents; creation-time gating of /benchmark is
   deferred until the harness exists.
4. **Every UI element maps 1:1 to an engine object** (the anti-slop
   rule). The start-modal diagram's nodes are the actual modules —
   hidden chain (the ONLY stochastic call, seeded), emission (pure
   function, crash week 3-cause ambiguous by R1), actions (exogenous),
   logistics (pure function). The X-ray rail renders (regime, age) per
   week — age made visible because duration-in-state is what carries
   the temporal information. The end-of-episode scoreboard renders the
   paper's regret decomposition: agent - causal = skill deficit,
   causal - clairvoyant = luck premium. The oracle ghost strip renders
   causal_play's weekly plan. No element without a referent.

Deferred: live belief strip (needs the belief tracker extracted from
causal_play), agent trace-replay viewer, /benchmark gating.

Verification results (2026-06-12 sign-off):
- 38/38 tests pass (162 s incl. the one oracle solve). Two new pins:
  test_xray_gating_and_content (normal episode -> /xray 403; research
  episode -> 200, tape grows per step, week-0 is calm; anon research
  episode still serves canonical hidden keys), test_benchmark_endpoint
  (causal >= clairvoyant, naive_min = min of the three baselines,
  luck_premium = causal - clairvoyant, 26 plan rows, seed -1 -> 422;
  the 122 s solve bypassed by injecting the module-scoped causal
  fixture as the cached oracle).
- Live end-to-end via Playwright against the running server:
  * security boundary CONFIRMED live, not just in test: a non-research
    episode's GET /xray returns 403; a research episode returns the
    seed-3 hidden tape calm(age 0->3) -> watch(0) -> crash(0, short) ->
    blockage(1, short). The age increments visibly inside calm — the
    semi-Markov clock the rail is meant to teach.
  * GET /benchmark/3 served the cached anchor set: clairvoyant 3300,
    causal 3880, suez20 5000, cape20 6040, basestock 4280,
    naive_min 4280, luck_premium 580, 26 plan rows — identical to the
    report_oracle sweep, and the plan bought 0 briefings.
  * Three screenshots captured: the start-modal world-structure diagram
    (HIDDEN node amber = the only stochastic factor), the live X-ray
    rail mid-disruption, and the end-modal regret scoreboard (four bars
    clairvoyant < causal < you < naive, decomposition
    skill $240 + luck $580, ghost strip with the zero-briefing caption).
- Commits on dev: d1eb042 (docs), f9401a8 (api), 6f4b91c (tests),
  61defcb (diagram), 597135d (rail), 4e5b0aa (scoreboard). main
  untouched.


## 2026-06-11 (c) — Causal-aware oracle: the benchmark anchor

### Problem

The clairvoyant oracle is luck-INCLUSIVE: it reads the realized future, so
regret against it mixes "the agent played worse than it could have" with
"the agent could not have known". The benchmark anchor must be the optimal
NON-clairvoyant policy: the best achievable expected cost given exactly the
agent's information (counts, bulletin, books, optional paid briefing) and
the true kernel — no future knowledge.

### Decisions

1. **Formal class & solver.** The world is a finite-horizon MOMDP
   (Ong/Png/Hsu/Lee 2010: books observed, event core hidden) whose hidden
   factor is an exogenous semi-Markov mode process (HM-MDP, Choi & Yeung)
   with deterministic observations (DetPOMDP, Bonet 2009). Reachable
   beliefs are finitely supported — at most {false_alarm, short-onset,
   long-onset} at a crash week — so the exact solver is finite-horizon
   expectimax / DP on the belief-MDP (Ross et al., JAIR 2008). No
   point-based (SARSOP/PBVI) or Monte-Carlo (POMCP/DESPOT) machinery is
   needed; the oracle is exact, not approximate.
2. **Module `src/world/causal_oracle.py`**: exact transition distribution
   mirroring transition.step_hidden (agreement pinned by a Monte-Carlo
   test), a pure-tuple mirror of logistics.resolve_week (agreement pinned
   by a randomized scenario test), memoized expectimax over
   (week, belief, inventory, pipeline), and a policy runner that plays the
   live engine FROM OBSERVATIONS ONLY (regime inverted from the noiseless
   suez count; briefing text parsed back to a type; per-step cost asserted
   against the DP branch).
3. **Observation grouping uses the full agent-visible outcome** — regime
   AND pipeline statuses/arrivals AND arrived qty — not counts alone. Ship
   state leaks information by design and the belief update must honor it:
   a Suez ship queued at the chokepoint on the crash week excludes
   false_alarm ("our ship did not sail through"); a Cape ETA slip at the
   rounding point reveals a long crisis. These leaks are realistic and
   intended; the causal oracle exploits them optimally.
4. **Briefing as a controlled-sensing action** (ACNO-style, Krale et al.
   2023): considered only when the belief is non-degenerate (zero VOI
   otherwise), bought iff expected savings >= 30, decided inside the DP —
   no special-casing or hand-set threshold.
5. **Tractability prune (policy-space restriction, never a semantics
   change):** qty > 0 is disallowed when inventory position (on hand + on
   water) already covers all remaining demand; such an order can only add
   shipping/holding cost, so the prune is dominance-safe.
6. **cape_local is integrated out at the resolve step** — it is iid,
   observed when it matters, and never persists; it branches the chance
   node only when a Cape ship sits at its congestion point that week.
7. **Structural predictions to check at sign-off** (from the OR
   literature: Song-Zipkin belief-dependent base-stock; Tomlin 2006
   contingent rerouting): the causal oracle should (a) run a base-stock-
   like qty rule modulated by the belief, (b) reroute via Cape on
   revealed long crises, ride out short blockages, (c) buy the briefing
   only at crash weeks, if at all.

### Verification results

- 36/36 tests. Three new pins: exact kernel distribution vs the
  transition.step_hidden sampler (Monte-Carlo, 10 cores x 20k draws);
  the relative pipeline encoding vs the real Books machinery on 60
  randomized 26-week scenarios; causal >= clairvoyant on seeds 1-8 with
  belief support <= 3 (the runner additionally cross-checks every step:
  unique observation-group match, cost and inventory agreement with the
  live engine).
- Exact solve: ~122s once per config (~1.3M V / 1.6M Q memo entries);
  per-seed playback is instantaneous — the policy is solved once, not
  per seed. The first (absolute-tuple) encoding did NOT terminate; the
  relative encoding (e0, e1, queued_qty, arrivals<=3wk) is what makes
  the exact solve tractable, and is value-preserving by construction.
- Ex-ante expected cost 3839.8. Sweep seeds 1-20: causal mean 4087.
  Luck premium (causal - clairvoyant) in [0, 1120], mean 572 — and
  exactly 0 on the quiet seeds (4, 14, 19), as it must be.
- Gap (naive_min - causal) in [320, 1100], mean 505; the causal oracle
  beats every naive baseline on 20/20 seeds. The anchor is strictly
  harder than naive_min and strictly fairer than clairvoyance. Regret
  decomposition now available per seed:
  agent - causal = skill deficit; causal - clairvoyant = luck premium.
- Structural predictions (decision 7) confirmed: belief-dependent
  base-stock shape; ordering pauses exactly on crash weeks (never
  dispatch into a possibly blocked canal) with immediate resumption;
  short blockages ridden out via Suez, no Cape switch — consistent with
  the short-dominated crash posterior (0.50 short / 0.21 long / 0.29
  false alarm, narrowing to {short, long} when a queued ship excludes
  the false alarm).
- EMPIRICAL FINDING — the optimal policy buys ZERO briefings on all 20
  seeds. The chokepoint status leak does most of the briefing's job for
  free, and the residual VOI never reaches the 30 price. Consequence
  for the benchmark: briefing purchases by agents are measurable
  OVERSPEND, not skill. If the briefing lever should do real work,
  either price it below the crash-week VOI or weaken the status leak;
  recorded as an open design question, not changed here.

## 2026-06-11 (b) — V2 task surface: the real planner job

### Problem

The v1 mechanics are causally correct but the task surface is not a real
job. Order qty is forced at 20/wk (the planner number-one lever — quantity
and timing — is missing, so holding/stockout costs do no decision work).
The probe is paid omniscience with backwards timing: it rides on the step,
so its result describes the NEXT week and arrives with the commitment it
should have informed. And the semantic channel (news) — the one the
research claim is about — is absent: counts are numbers in both ablation
arms, so there is almost nothing semantic to ablate.

### Decisions

1. **Persona**: import replenishment planner, one SKU, Shanghai->Rotterdam,
   weekly cadence, 26 weeks. Judged on landed cost + holding + service.
2. **Action space**: qty in {0, 20, 40} x route in {suez, cape} (route only
   when qty > 0). Demand stays deterministic 20/wk (isolates supply side).
3. **Two-stage week**: obs -> optional paid analyst briefing (30, describes
   the CURRENT week hidden state incl. disruption type) -> order. The probe
   rider is deleted. Same value of information (type one week early at the
   crash week), sane timing and semantics.
4. **News bulletin observation channel**: deterministic template on
   HiddenState.regime. Crash week byte-identical across false_alarm /
   short-onset / long-onset (R1). No duration or probability language in
   any text, either mode (R2) — otherwise reading comprehension would
   substitute for the domain knowledge under test.
5. **Semantics ablation switch**: cfg.semantics in {real, anon}. Identical
   information in both modes (R3); anonymization applied only at the
   presentation boundary — engine internals stay canonical (R4); the
   post-episode trace reveal stays canonical (analysis-side artifact).
6. **Balance**: the quiet-seed gap-0 property dies by design (the oracle
   burns the initial 80 buffer by ordering 0 early). New naive anchor set:
   always-suez-20, always-cape-20, base-stock-suez (order-up-to 80 =
   demand x (suez lead + 1)). Gates re-derived post-sweep; numbers
   recorded below after verification.

7. **Diversion surcharge** (found during sign-off): the first sweep's
   oracle ordered Suez throughout long crises because a diverted voyage
   was billed at the Suez rate for what is physically a Cape transit
   (200 vs 220 to book Cape outright) - the route lever went dead
   exactly when it should matter most. Fix: the Cape price differential
   ((cape - suez) x qty) is billed at the diversion week, mirroring
   carriers' documented diversion surcharges. The DP charges it
   up-front at dispatch (same accounting as in-transit holding);
   replay equality re-verified.

Deferred: causal-aware oracle (next build), demand noise, freight-rate
spikes, air expedite, agent harness.

### Verification results

- test_world.py: 33/33 passing (incl. crash-bulletin identity R1, banned
  duration vocabulary R2, anon leak scan, real/anon numeric identity R3,
  diversion surcharge, DP == engine replay).
- Sweep (seeds 1-20, commit 68297b0): gap = naive_min - oracle with
  naive_min over {suez20, cape20, basestock-80}: min 360, max 1840,
  mean 1077; 20/20 discriminative. Quiet seeds (14, 19) floor at 360 =
  pure inventory-policy skill (basestock holds excess buffer a
  clairvoyant does not need); disruption seeds gap 1100-1840. suez20 is
  strictly worse than basestock on quiet seeds, so the qty lever does
  real decision work.
- Oracle plans (seeds 6, 12) post-surcharge: front-load 40 before onset,
  Cape during long crises, switch back to Suez (queue-and-wait) when the
  reopening is imminent - the documented 2024 importer playbook.
- DP runtime ~1.5 s/seed on the (qty, route) lattice; no inventory cap
  needed.
- NOTE vs v1: the quiet-seed gap-0 property is retired by design; the
  oracle-vs-naive gap now includes inventory-policy skill (floor ~360)
  on top of disruption response.

## 2026-06-11 — Transit-week causality rebuild

### Problem

The v0 engine evaluated lead time against the hidden state **at the dispatch
week** and locked the arrival immediately. A ship ordered during a disruption
was punished even though it would not reach the canal for ~2 weeks; a ship
dispatched in calm sailed through a later disruption unscathed. Combined with
noiseless counts that uniquely fingerprinted every regime, the optimal policy
was a reactive lookup table: no forecasting, no use of the transition model,
probe strictly dominated, and quiet-seed oracle gaps were a holding-cost
arbitrage (in-transit goods were free to hold). See memory:
noiseless-world-identifiability-findings.

### Decisions

1. **Chokepoint state applies at the transit week, not the dispatch week.**
   Suez voyage = 2 weeks to the canal + 1 week canal-to-destination (the canal
   sits ~day 20 of a ~28-day Shanghai-Rotterdam run). The canal state on the
   week the ship is AT the canal decides: open -> through (arrive t+3);
   recovery -> backlog queue (+1, arrive t+4); disruption -> ship queues. A
   queued ship waits at most 1 week: if the canal clears it proceeds (t+4),
   if not the carrier diverts it around the Cape (+3 weeks, arrive t+6) —
   the observed Ever Given / Red Sea carrier behavior.
2. **Disruptions have a hidden type drawn at onset**: `short` (physical
   blockage, Ever Given class: 6 days blocked + ~5 days backlog ≈ 1-2 weekly
   ticks; P=0.7) or `long` (security crisis, Red Sea class: 12+ months,
   weekly persist 0.92 ≈ mean 12.5 weeks, horizon-bounded; P=0.3). Duration
   forecasting — the actuarial bet — is now the core skill under test, and
   the type prior is exactly where LLM domain knowledge should pay.
3. **Crash-week ambiguity is deliberate and exact.** First week of
   false_alarm, short disruption, and long disruption all emit the identical
   fingerprint (suez 28 / bab 25 / cape 66). One week later counts separate:
   blockage (0/0/72: canal shut), crisis (14/10/96: transits -75/-90%, Cape
   +60%), false alarm (reverts). false_alarm is reachable only from `watch`
   (same as disruption), so sequence history cannot break the ambiguity.
4. **Probe = paid intelligence briefing (30).** Returns the ground-truth
   regime descriptor including disruption type (blockage_short_term vs
   crisis_long_term) at the crash week — i.e. it buys one week of earlier
   knowledge. Its value is now genuine and quantifiable by the oracle gap
   with/without probing, fixing v0's strict dominance.
5. **Holding cost applies to in-transit goods** (capital cost at the same
   1/unit/week). Kills the delay-arrivals arbitrage; Cape's longer voyage now
   carries its true capital cost.
6. **Cape congestion** (+1 week) applies at the ship's week-2 rounding point
   if either the iid local-congestion coin (K, p=0.08) or a long crisis
   (diverted-traffic surge: Cape volumes +60-74% during the Red Sea crisis)
   is active that week.
7. **Anchor**: the clairvoyant oracle (replay + exact DP) remains the
   luck-inclusive lower bound. The benchmark anchor will be a causal-aware
   oracle (knows current state + true kernel, plays optimal expected value);
   its per-seed regret vs the clairvoyant is the irreducible luck band, and
   agent skill = mean regret vs the causal-aware oracle over seeds. Built
   next, after this rebuild is reviewed.
8. **Deferred, recorded**: anonymization switch for the semantics ablation
   (label map at the obs/action boundary); agent harness as a separate
   package with a Policy protocol (multi-agent later — World stays a pure
   single-decision-stream engine; concurrency lives above it); noise knob.

### Calibration evidence (1 tick = 1 week, Asia-Europe lane)

| World number | Real anchor |
|---|---|
| suez voyage 3 wks | Shanghai-Rotterdam via Suez ~28 days |
| cape voyage 4 wks | via Cape ~40 days (+10-14 days) |
| divert penalty +3 wks | mid-voyage U-turn ≈ Cape total from Red Sea approach |
| short type: 1-2 wks | Ever Given: 6 days blocked, backlog cleared ~5 days later |
| long type: persist 0.92/wk | Red Sea crisis: Dec 2023 into 2026, transits still -60% |
| crisis counts 14/10/96 | Suez container transits -75/-90%; Cape tonnage +60-74% |
| blockage counts 0/0/72 | canal physically closed; 369-422 ships queued |
| cape unit 6 vs suez 4 | ~1.5x operating cost for +10 days fuel/charter |
| stockout 20/unit (5x suez) | Asia-Europe spot rates 3-5x during the crisis |

Sources: Wikipedia 2021 Suez obstruction; supplychaindive Ever Given
timeline; NPR backlog clearing; UNCTAD osginf2024d2; IMF blog Mar 2024
(PortWatch); J.P. Morgan Red Sea research; porteconomicsmanagement
Shanghai-Rotterdam routing; GEP / Flexport rate and rerouting reports;
Logfret 2026 Suez traffic update.

### Verification gates

- Single test file `test_world.py` pins: fingerprint table incl. the exact
  three-way crash ambiguity, probe-type mapping, every voyage branch
  (through/recovery-queue/queue-release/divert, cape +1 paths), in-transit
  holding conservation, exogeneity, determinism, no-leak, API contract,
  and clairvoyant DP == engine replay.
- `report_oracle.py` sweep over seeds 1-20 must replay every DP plan on the
  live engine to the exact cost.
