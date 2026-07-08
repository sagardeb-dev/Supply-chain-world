# MATH.md — exact mechanics of the benchmark (compiled from code, 2026-07-08)

Everything below was read directly out of the backend source by three code-mapping
passes. File:line references point at `/data/supply-chain-pomdp/backend/`.
This is the ground truth for any mechanics sentence in paper.tex.

## 1. One week, in order

Each `place_order(...)` call advances the world one week (engine.py:310-466):

1. **Hidden factors step first** (engine.py:288-308). Six independent chains
   advance using the episode's seeded RNG. No kernel ever sees the agent's
   action or the books — that is why the tape is action-independent.
2. **Arrivals land.** Shipments whose ETA is this week arrive; if the port is
   blocked, arrivals are pushed one week and demurrage accrues.
3. **Quality bites.** Each landed batch loses `round(qty * defect_fraction)`
   units to defects; defective units cost rework.
4. **Demand is served** from on-hand stock; shortfall = lost sales.
5. **Costs are summed** into `total_cost`.

## 2. The weekly cost function (logistics.py:169-186, engine.py:426-441)

| component | formula | constants |
|---|---|---|
| shipping | shipped_units × unit_price | unit_price = route_base × freight_mult + supplier delta; suez $4.0, cape $6.0 per unit |
| supplier delta | qualified +1.0, spot −1.5, backup +0.3 | supplier/config.py:87-111 |
| holding | $1.0 × on-hand units | config.py:179 |
| in-transit | $1.0 × units on the water | logistics.py:173 |
| stockout | $20.0 × unmet demand units | config.py:180 |
| demurrage | $2.0 × qty held at a blocked port | config.py:120 |
| rework | $15.0 × defective units landed | config.py:137 |
| diversion surcharge | $2.0 × qty (Suez ship forced around the Cape) | books.py:107 |
| crisis back-order | $60.0 × supplier shortfall units, only during canal watch/crash/blockage/crisis | couplings.py:16-24 |
| air expedite | $15.0/unit, cap 20/week | config.py:126-127 |
| briefing / audit / inspect | flat $30 / $25 / $40 per call | config.py:181,52,156 |
| dual-source overhead | $4.0/week while ≥2 contracts live | config.py:69 |

Key ratios: air ($15) sits between sea ($4–6) and stockout ($20); holding is
1/20th of stockout, so the critical ratio p/(p+h) = 20/21 ≈ 0.95.

## 3. The six hidden factors (each an independent semi-Markov chain)

Stress regimes (what counts as "stressed" for episodes, grade_beliefs.py:132-143)
are marked *.

| factor | states | key transitions | observation (noise) |
|---|---|---|---|
| demand | normal, promo_spike*, seasonal_lift*, structural_decline* | onset .03/.015/.005; promo fixed 4wk; seasonal persist .85 cap 8; decline persist .97 | pos_units, forecast (Gauss sd 4 / 6); means 20/26/30/14 |
| supplier (spot drifts) | reliable, wobbling, degraded*, defunct* | onset .10; wobble→degraded .45; degraded→defunct .06; degraded recovers ≤4wk | scorecard band reads ONE step better than truth (masked); lead-slip Gauss sd 2.5; fill Gauss sd .12 |
| freight | slack, normal, tightening, spike* | tighten onset .06; tighten→spike .18; spike persist .80 cap 6 | freight_index/outlook = 100×mult, Gauss sd .15/.25; means .7/1.0/1.8/4.0 |
| port | clear, building, congested*, customs_hold* | build onset .06; build→congested .30; congested persist .85 cap 8; customs ~1wk | berth_wait/outlook Gauss sd 2/3; means 1/4/14/16 days |
| quality | in_control, drifting, out_of_control* | drift onset .04; hazard .05+.04×age (gradual-then-sudden); out recovers .25 | aql_result band (accept/marginal/reject), discrete probs per regime |
| canal ("disruption") | calm, watch, disruption*, recovery, false_alarm | calm→watch .08; watch→disruption .50 (70% short ≤2wk, else long persist .92) | exact Suez/Bab/Cape transit counts per regime — noiseless but "crash" is deliberately ambiguous between false alarm and real onset |

Physics: a blocked canal queues Suez ships at the chokepoint (week+2), then
diverts them (+3 weeks, Cape rate + $2/unit surcharge). Port congestion holds
arrivals (+1 week each week, demurrage). Suez lead 3wk, Cape 4wk.

## 4. The agent's levers (tools.py)

place_order(qty ≤ 100, route suez/cape, supplier, optional contract action) —
commits the week. Before committing it may stack: lock_freight(weeks) (freezes
today's rate, no fee), expedite_air(qty ≤ 20, $15/unit, lands next week,
bypasses port), inspect_batch ($40, scales down defects on this week's batch),
buy_briefing ($30, reveals exact canal state), buy_audit ($25, reveals exact
supplier state). Contract terms menu: short/long/strict/lenient with price
multipliers .97/1.06/1.03/.95. Malformed calls are rejected without advancing
the week.

## 5. Base-stock floor (report_oracle.py:35-63)

Order-up-to-S, symptom-blind: S = round(μ·L + z·σ·√L) with μ = 20 (weekly
demand), σ = 4, L = lead+review = 4, z = Φ⁻¹(20/21) ≈ 1.668 → orders
max(0, S − inventory position) every week, always Suez, always qualified.
Never locks, flies, inspects, or reads a single symptom.

## 6. The oracle (filters.py + oracle_policy.py)

**Not particle filters.** Each factor gets an EXACT discrete Bayes filter
(HMM forward algorithm): predict with the true transition table, correct by
multiplying the likelihood of this week's observation, normalize
(filters.py:48-92). State spaces are small enumerations of (regime, age), so
the posterior is exact — no particles, no resampling.

Decision layer = receding-horizon Monte Carlo (oracle_policy.py):
1. Sample K futures (K≈200 for the reference runs) of all six factors from the
   filters' posteriors, rolled forward with the true transition tables.
2. Enumerate a small candidate grid for THIS week: qty ∈ {0, order-up-to 4wk,
   6wk of expected demand}; route; supplier; lock_freight only if
   P(tightening∪spike) > .3; air only if port-risk > .3; inspect only if
   quality-risk > .5 and a batch lands next week.
3. Score each candidate on all K futures with a surrogate simulator (this
   week = candidate, future weeks = base-stock continuation); pick the
   cheapest mean. Same K futures reused across candidates (common random
   numbers).
4. Execute through the identical World API the LLM's tools wrap.

Fairness guarantees: `engine.py:521` asserts no hidden key ever enters an
observation; oracle and LLM both read `world.trace[-1]["obs"]`
(service.py:5-8, oracle_policy.py:362) — the byte-identical dict. Disclosed
asymmetry: the filters use the TRUE transition probabilities and regime means
(imported from world config, never re-fit); the LLM gets only the qualitative
prose description. The oracle never buys briefings or audits (it doesn't need
them; the LLM can). Oracle reference = mean of 20 independent replications per
seed (single runs swing ~10%); SE 0.3–1.6%.

## 7. Skill score

skill = (C_base − C_agent) / (C_base − C_oracle). Worked example, seed 1:
base-stock $9,101, oracle mean $6,932 ± 102, Sonnet $8,539 →
skill = (9101−8539)/(9101−6932) = 0.26.

## 8. Belief metrics (grade_beliefs.py)

- Grader: gpt-5-mini, temp 0, low reasoning effort; sees ONLY the rationale
  text + the fixed 6-name vocabulary; strict-JSON output; labels a factor only
  if the text claims it is a problem THIS week (ruled-out mentions,
  precautions don't count). Same-week alignment: the rationale written after
  seeing week W's dashboard is credited to week W.
- Episode: maximal consecutive run of weeks a factor's true regime is stressed
  (starred regimes in §3). 114 episodes across the 20 tapes.
- Detection lag: first week ≥ episode start where the grader says the factor
  was named, minus start. Mean lag is over DETECTED episodes only;
  never-detected episodes are counted separately (n_never_detected). Naming a
  factor before onset never counts. (Known quirk: the forward scan has no
  upper bound at the episode's end, so a missed episode can in principle be
  credited from a later window of the same factor.)
- Knowing-doing rate: over weeks where named ∩ truly-stressed ≠ ∅,
  the fraction where available (prev inventory + arrivals) < realized demand,
  i.e. a same-week stockout. Causal caveat: the stockout may stem from orders
  weeks earlier.
- Audits: 30-row stratified manual read (hit-class 10/10 correct; 9/10 misses
  genuine, 1 ambiguous in the pessimistic direction; calm-week over-labels
  ~50% but excluded by construction). Second grader (haiku-4.5, same prompt,
  100 weeks): exact-label agreement 43%, agreement on the metric-relevant
  quantity (label ∩ true stress) 89%.

## 9. Corrections this file forced in paper.tex

- "particle filters (k≈200 particles)" → exact discrete Bayes filters;
  k≈200 is the number of Monte Carlo rollouts per decision, not particles.
  (skill.md's own header says "k≈200 particles" — that shorthand is wrong.)
- Figure 1 oracle box relabeled "Bayes filters + rollout".
