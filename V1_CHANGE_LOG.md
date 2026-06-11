# V1 Change Log

Design decisions for the supply-chain POMDP world. Each entry records what
changed, why, and the evidence. Code follows this file, never the reverse.

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
