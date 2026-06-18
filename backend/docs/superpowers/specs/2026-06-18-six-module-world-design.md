# Six-Module World — Design Spec (Goals 2 & 3)

**Branch:** continue on `feat/world-library-refactor` (goal 1 done) — do NOT spawn
new branches unless the work diverges hard.
**Date:** 2026-06-18
**Depends on:** goal 1 (the by-module library). Each new module is a sealed-box
`modules/<name>/` package + one `REGISTRY` entry — the library makes this cheap.

## Goal

A fully-functional factored-POMDP world with **6 coupled latent modules**, each a
**semi-Markov** hidden factor on the disruption template (the gold standard),
grounded in real supply-chain data, each leaking a **noiseless-or-low-noise weekly
signal** with a deliberate 1-week ambiguity so a smart agent can *resolve* the
uncertainty. Interesting for a human to read; intuitive for the agent.

Core research principle (unchanged): **can an agent make good decisions under
uncertainty when the world leaks partial data to clarify hidden state?** More
modules = more coupled uncertainty to reason about.

## The 6 modules (2 exist, 4 new)

Each: hidden semi-Markov state (state + age), a noiseless/low-noise visible
channel, a deliberate 1-week ambiguity, and couplings ONLY through cost/reward
(Becker TI-Dec-MDP Theorem 1 — transitions/observations stay independent so the
joint belief factors into a product of per-module marginals).

### ① disruption — EXISTS (the template)
Event HMM (calm→watch→{disruption(short|long)|false_alarm}→recovery), mid-voyage
Suez/Red Sea chokepoint. Visible: transit counts + bulletin. Ambiguity: "crash"
week shared by false_alarm + week-0 of either disruption type.

### ② supplier reliability — EXISTS
Per-supplier reliability chain (reliable→wobbling→degraded→defunct); fulfilled
fraction at dispatch. Visible: OTIF scorecard. Ambiguity: "slipping" band.

### ③ demand — NEW  [grounded: demand sensing, CPFR, bullwhip]  ← FINALIZED
Scaled to the existing world's base demand (20/wk), mirroring the disruption
template exactly (a visible BAND that collapses two hidden causes for one week).
- **Hidden states (semi-Markov, regime + regime_age):** `normal` / `promo_spike`
  (age-capped ~4 wks → normal) / `seasonal_lift` (persist 0.85, cap ~8 wks) /
  `structural_decline` (persist 0.97, sticky).
- **Visible BAND → units** (the noiseless POS observable = realized demand units):
  `base`=20, `surge`=26, `promo`=26, `seasonal`=30, `depressed`=14.
  Band property: normal→base; decline→depressed; **age 0 of promo OR seasonal →
  `surge` (THE shared reading)**; age≥1 → `promo`(26) vs `seasonal`(30).
- **Ambiguity (mirrors disruption "crash"):** onset week both promo & seasonal emit
  `surge`=26 — indistinguishable; week 2 separates (promo stays 26 / may end →20;
  seasonal rises to 30). The decision it forces: reorder hard (sustained seasonal)
  vs ride it out (transient promo)?
- **Coupling (cost only):** `resolve_week` uses demand_units (not `cfg.weekly_demand`)
  for `served`/`shortfall` — drives the core stockout/holding loop. A surge colliding
  with an active disruption ⇒ amplified stockout (bullwhip). Quality escape × surge =
  worst effective shortfall.
- **Knobs (WorldConfig, unused until demand is in a registry):** demand_promo_onset
  =0.03, demand_seasonal_onset=0.015, demand_decline_onset=0.005, demand_promo_max=4,
  demand_seasonal_persist=0.85, demand_seasonal_max=8, demand_decline_persist=0.97.
- **Inert-by-absence:** the default registry does NOT include demand, so the pinned
  2-factor world is unchanged; demand appears only in the RICH registry. Its rng
  draws come AFTER disruption+supplier ⇒ the disruption golden is unperturbed.

### ④ freight rate — NEW  [grounded: FBX/Drewry WCI/SCFI, GRI, blank sailings]
- **States:** `slack` (0.7×, persist 0.93, months) / `normal` (1.0×, 0.90) /
  `tightening` (1.6×, 0.80 age-rising) / `spike` (3.5-6×, 0.85 wk1-4 → 0.55 wk5+).
- **Visible (noiseless):** weekly spot index print (a number; level + slope).
- **Ambiguity:** a **GRI-announcement week** prints the elevated rate whether it
  *sticks* (tightening) or *collapses* next week (back to normal) — GRIs routinely
  "run out of steam." Identical that week, separate the next.
- **Coupling (cost):** scales the shipping unit cost per route (`base × multiplier`).
  Interacts with route choice and with disruption diversions (absorbed capacity can
  tip the regime toward spike).
- **Numbers:** ~$1.6k floor / ~$8-10k crisis-peak per FEU → multipliers above.

### ④ freight — FINALIZED design (noisy + forward from the start)
- **Hidden states (semi-Markov):** `slack` / `normal` / `tightening` / `spike`.
- **Band → mean multiplier:** low 0.7, mid 1.0, **jump 1.8** (tightening & spike
  ONSET share it — the GRI-week ambiguity), high 1.8 (tightening sustained), peak
  4.0 (spike sustained). realized_mult = noisy draw around the band mean.
- **Visible:** `freight_index` = round(realized_mult×100) (a noisy spot-index print).
  **Forward channel:** `freight_outlook` (noisier second read — carrier guidance/GRI).
- **Ambiguity:** tightening-onset vs spike-onset both read `jump`; next week separates
  (plateau at high vs climb to peak).
- **Coupling (cost only):** scales the route base cost in resolve_week
  (`base_eff = base_route × freight_mult`), via the EFFECT interface below.

**Freight counterfactual pass (DONE):** noisy from the start (not too
deterministic ✓), realistic spot dynamics ✓, forward outlook channel ✓.
**Gap → backlog:** no contract-vs-spot freight HEDGE — a real desk locks ~70% on
contract rates against the spot regime; that's an action-space lever the agent
lacks (analogous to supplier contracts). Also: one regime scales both lanes
equally (lane-specific dynamics is a refinement). Revisit at agent-run time.

### Effect interface (extracted when freight = the 2nd substrate-effect module)
`Module.effect(state, cfg) -> dict` of named substrate contributions; the engine
merges all modules' effects each week and passes the dict to `resolve_week`, which
reads them with defaults: `effects.get("demand", cfg.weekly_demand)`,
`effects.get("freight_mult", 1.0)`, later `port_delay`/`usable_frac`. demand is
migrated onto this (was an explicit `demand=` param). disruption/supplier stay as
explicit `h`/`sup` params (no churn). Named fns, not lambdas (picklable).

### ⑤ port / customs — NEW  [grounded: berth queues, demurrage/detention, CBP exams]
- DESTINATION-port stage (distinct from disruption's mid-voyage chokepoint —
  delay accrues AFTER the ocean leg, no double-count).
- **States:** `clear` (+0 wk, persist 0.90) / `building` (+1, 0.60) / `congested`
  (+2..+4, 0.85, weeks-long) / `customs_hold` (+1, persist 0.15, ~1-wk sojourn).
- **Visible (low-noise):** berth-wait days + a binary hold-notice flag
  (clear 0-2d, building 3-6d, congested 14+d).
- **Ambiguity:** week-1 a slow arrival reads identically for `congested` (long berth
  wait) vs a fresh `customs_hold`; week-2 they separate (hold clears & lands, or wait
  persists).
- **Coupling (cost+lead):** adds extra arrival-week delay ⇒ demurrage/holding;
  stacks after the disruption voyage delay.
- **Numbers:** demurrage ~$2-2.7k/container/day; congested ~$14-19k/wk; CBP exam
  prior ~0.035/shipment; free time 4-7 days.

### ⑤ port/customs — FINALIZED implementation design
- **Hidden states (semi-Markov):** `clear` / `building` / `congested` / `customs_hold`.
- **Band → mean berth-wait days:** clear 1, building 4, **slow 14** (congested &
  customs_hold ONSET share it — the ambiguity), congested 16. berth_wait = noisy draw.
- **Visible:** `berth_wait` (noisy) + forward `wait_outlook`. Ambiguity: a `slow`
  week is congestion-starting OR a customs hold; next week separates (congestion
  persists vs hold clears).
- **EFFECT (lead-time + cost, NOT a point cost):** `{"port_blocked": regime in
  (congested, customs_hold), "demurrage_rate": cfg.port_demurrage_rate}`. In
  resolve_week, when port_blocked, ships DUE this week are held +1 wk
  (`s.arrives_week = week+1`, re-checked weekly so the hold lasts the congestion
  duration) and demurrage = rate × held_qty. This is the one module that mutates
  arrival timing — guarded by port_blocked so the DEFAULT world (no port) runs the
  original arrival logic byte-identically. `demurrage` cost key added ONLY when >0
  (keeps default cost_breakdown identical). Port is RICH-only ⇒ no oracle-mirror
  obligation (resolve_rel is default-world-only).
- **Distinct from disruption:** disruption = mid-voyage Suez delay; port =
  destination-stage dwell. No double-count.

**Port counterfactual pass (DONE):** realistic congestion/demurrage/customs ✓,
noisy berth-wait + forward outlook ✓, regime hidden ✓. **Gap → backlog:** no
expedite / priority-berthing / alternate-port lever (action-space expansion a
real desk has). Customs holds currently delay ALL arrivals that week (simplified;
real holds flag a subset).

### ⑥ quality — NEW  [grounded: SPC, AQL ISO 2859, PPM, cost of poor quality]
- Process-quality of what's delivered (defects), orthogonal to OTIF (on-time).
- **States:** `in_control` (50-100 PPM, persist 0.97) / `drifting` (1-2.5%, 0.85
  age-rising exit) / `out_of_control` (4-8%, 0.90 absent intervention). "Gradual
  then sudden" via age-rising drift→out hazard.
- **Visible (LOW-NOISE, the one noisy channel):** a coarse 3-band AQL readout
  ACCEPT / MARGINAL / REJECT (vs AQL 1.0/2.5). Coarse banding keeps belief tractable.
- **Ambiguity:** a single MARGINAL reading is shared by late-`in_control` noise vs
  early-`drifting`; next sample separates them.
- **Coupling (cost):** defective fraction doesn't count toward usable inventory
  (effective shortfall) + rework/scrap charge (COPQ ~3-5× unit). Worst during a
  demand spike.
- **TRACTABILITY NOTE:** this is the only genuinely *noisy* emission ⇒ belief does
  not collapse to a singleton ⇒ it is the factor that forces the anchor bracket
  (below). Option to coarsen its emission toward near-deterministic to stay
  exact-friendly is open.

### ⑥ quality — FINALIZED design (the NOISY-emission factor)
- **Hidden states (semi-Markov):** `in_control` / `drifting` (age-rising hazard to
  out — "gradual then sudden") / `out_of_control`.
- **Observable = NOISY DISCRETE sample:** a coarse AQL band `accept`/`marginal`/
  `reject` drawn per week from per-regime probabilities (in_control mostly accept
  but occasionally marginal; drifting straddles; out mostly reject). This is the
  one emission that does NOT collapse to a singleton — the ambiguity is inherent
  (a `marginal` is shared by late-in_control vs early-drifting), so no deterministic
  band-collapse is needed. **This factor is why the full RICH world needs the
  bracket anchor, not an exact DP.**
- **EFFECT (cost):** `defect_fraction` (per regime: ~0.001/0.02/0.06) of ARRIVING
  units are defective ⇒ don't enter usable inventory (effective shortfall) + a
  rework charge. Applied in resolve_week's landing branch; default world has no
  quality ⇒ fraction 0 ⇒ byte-identical. Emerges: a quality escape during a demand
  spike = worst (the demand×quality coupling, via inventory, no transition edge).
- **Forward lever (backlog):** a paid supplier audit (VoI probe) — not in v1.

## Coupling web (all through cost — belief stays factored)

```
demand ──(stockout/holding)── inventory ──(usable units)── quality
   \                                                         /
    (bullwhip when spike×disruption)            (escape×spike = worst)
       \                                          /
        disruption ──(diversion)── freight ──(unit cost × regime)
            \                                   
             (voyage delay) ── port/customs ──(+lead, demurrage)
        supplier ──(fulfilled fraction at dispatch; crisis_backorder×disruption)
```
No transition edges between modules — only reward reads. Every new two-factor read
goes in `couplings.py` (the one auditable tier-3 home).

## Anchor strategy (the "oracle isn't the bottleneck" steer)

Do NOT cripple module richness to keep the exact factored DP tractable. Bracket the
optimum instead. Concrete recipe (grounded — Brown–Smith–Sun 2010 OR; DESPOT
JAIR 2017; Becker TI-Dec-MDP 2004):

- **Lower bound (on optimal cost):** seeded **clairvoyant shortest-path DP** over
  the seed-fixed full latent trajectory (penalty = 0) for v1 — this already exists
  for the disruption factor (`oracle/clairvoyant.py`), generalize it to all factors.
  v2: tighten with an **information-relaxation martingale penalty** (a value-function
  difference for revealing factor-k's next draw, built from a cheap QMDP value).
  Weak duality ⇒ any penalty keeps it a valid lower bound.
- **Upper bound (on optimal cost):** a feasible non-anticipating policy. Primary =
  **DESPOT** (Somani/Ye/Hsu/Lee): sample K fixed *seeded* scenarios (reproducible),
  sparse O(|A|^D·K) tree, regularized objective → near-optimal policy whose
  Monte-Carlo cost is a sound upper bound. Pure-Python-friendly (generative model,
  no |S| enumeration). ~500 scenarios, horizon 26.
- **Bracket & report:** `clairvoyant_low ≤ info_relax_low ≤ OPTIMAL ≤ DESPOT_upper`.
  Benchmark the agent against the bracket: `agent_cost − upper` = skill deficit;
  `upper − info_relax_low` = anchor uncertainty (bracket width). Fixed seeds + CIs.
- **Keep 5 noiseless factors exact:** with transition + observation independence the
  joint belief stays `b(s)=∏ₖ bₖ(sₖ)` (closed under Bayes update — Becker), each
  marginal collapsing to singletons/≤3-atom windows ⇒ existing factored expectimax
  unchanged. **Isolate the one noisy factor (quality):** handle only its marginal
  approximately — QMDP on that marginal, or **coarsen its 3-band emission toward
  near-deterministic** (bin the sample outcome) to restore tiny support.

## Counterfactual review — REQUIRED per module (not optional)

Every module gets a red-team pass BEFORE it's "done" — structural tests passing
is not enough. Four lenses:
1. **Does it really happen like this?** Check the mechanic against reality; flag
   anything inverted or over-clean.
2. **What other info would the agent need?** Real desks get FORWARD signals
   (forecasts, calendars, indices), not just backward realized observations.
3. **State / action space expansion?** Are the agent's levers/observations rich
   enough for the decision the module creates?
4. **Too deterministic?** If the hidden state is identifiable from ~1 clean
   observation, the uncertainty is thin and the DP is trivial. Real factors carry
   irreducible noise you never fully filter. (This is also where the
   "oracle isn't the bottleneck" steer bites: prefer realistic NOISE, lean on the
   bracket anchor; keep the DEFAULT 2-factor world noiseless+exact-anchored.)

### Demand — review findings & resolution
**v1 flaws (found by the red-team pass):** too deterministic (flat per-regime POS
⇒ ~1-week regime ID ⇒ trivial DP); mis-framed realism (flat POS; seasonality as
hidden is backwards); missing forward info; coarse action grid.

**v2 (DONE, commit pending):**
- ✅ **Noise:** `realized` POS = `gauss(band_mean, demand_noise_sd=4)` clamped ≥0
  ⇒ the regime must be FILTERED over several noisy weeks, not read in one. Default
  2-factor world stays noiseless+exact (demand is RICH-only); RICH is bracket-anchored.
- ✅ **Forward channel:** `demand_forecast` = a second, noisier read
  (`demand_forecast_sd=6`) of the underlying mean — the "demand sensing" signal the
  agent weighs against backward POS. Both are per-week draws stored on DemandState
  (precedent: HiddenState.cape_local_congestion).
- **v3 backlog:** make the forecast genuinely FORWARD/typed so it helps the
  promo-vs-seasonal *persistence* call (currently a same-mean nowcast — tightens the
  level estimate but doesn't directly disambiguate persistence). Reconsider framing
  seasonality as a known calendar. Revisit the {0,20,40} action grid (a 60 option /
  expedite / safety-stock-target) at calibration / agent-run time.

## Implementation note — PREREQUISITE before any new module

The engine currently stores exactly two factors by name: `self.hidden`
(disruption singleton) + `self.suppliers` (roster), and the `drives=("",)`
convention maps a singleton module to `self.hidden`. That only works for ONE
singleton — a 3rd singleton factor (demand/freight/port/quality) would collide on
`self.hidden`. So **step 0 is generalizing engine state** + parameterizing the
World by its registry, so "new worlds = new registries":

- `World(cfg=None, registry=None)` → `self.registry = registry or REGISTRY`; loop
  `self.registry` in `_advance_modules`/`_build_obs`. Default registry = the
  current 2-factor tuple ⇒ golden byte-identical.
- Generic per-module state: `self.module_states[m.id]` = one state for a singleton
  module, a `{sid: state}` dict for a roster module. Keep `self.hidden` /
  `self.suppliers` as thin aliases/properties into it so existing engine code and
  the trace are untouched (low churn, preserves the golden).
- New singleton modules append to a NEW registry (`SIX`/`rich`), NOT the default —
  so the pinned 2-factor world stays exactly as-is, and the rich world is a
  separate preset. New modules' rng draws come AFTER disruption+supplier ⇒ their
  trajectories (and the disruption-only golden) are unperturbed.
- The substrate (`resolve_week`) generalizes via OPTIONAL, default-inert params
  (`demand=None`→`cfg.weekly_demand`, `freight=None`→1.0×, `port=None`→no delay,
  `quality=None`→fraction 1.0). Default world passes None ⇒ identical; the rich
  world threads each active module's cost-relevant output. Each new two-factor read
  still goes in `couplings.py`.

This is the library payoff: a World is parameterized by (config, registry). Verify
with the golden pin (default registry) + a smoke test that a custom registry runs.

## Implementation plan (incremental — one module per slice, tests + golden re-pin)

Each new module slice:
1. `modules/<name>/` package (factor + emission + text + config), sealed-box.
2. One `REGISTRY` entry (extends the rng draw order — re-pin determinism).
3. Wire its observed slice into `_build_obs` (automatic via emit/view).
4. Its cost coupling(s) into `couplings.py` + `substrate/logistics.py`.
5. Tests: kernel distribution, emission byte-pin, ambiguity-window, coupling, leak
   guard, determinism. Re-pin any affected golden.
6. Update `claude-mds/architecture.md` + this spec.

Order: ③ demand → ④ freight → ⑤ port → ⑥ quality (simplest/most-decoupled first;
quality last because it's the noisy one driving the anchor rework).

Then: build the bracket anchor; run the LLM agent (OpenRouter, $30 budget) on the
6-factor world and measure regret vs the bracket.

## Out of scope
- Frontend (cannot inspect it this session).
- Reworking the existing single-factor exact oracle into a 6-factor exact DP
  (replaced by the bracket).
