# Measuring the Knowing-Doing Gap in LLM Agents with a Fair Bayesian Oracle

*Workshop paper draft — v0 skeleton 2026-07-07. Numbers marked [PENDING] land when
deepseek runs + belief grader finish (see backend/runs/TRACKER.md).*

## Abstract
[Write last. One paragraph: LLM agents run a 26-week inventory POMDP with six hidden
failure factors; scored between a base-stock floor and a Bayes-filter oracle that sees
identical observations; models detect hidden failures but their policies collapse when
failures compound — the knowing-doing gap, made a cost-weighted number.]

## 1. Introduction
- Long-horizon agent benchmarks show degradation (Vending-Bench, RetailBench) and
  games/tool-use show the knowing-doing gap (Broken Links 2605.00226, 2605.14038,
  2511.13240, 2504.16078) — but qualitatively or vs privileged oracles.
- Contribution: a factored-POMDP benchmark where the Bayes-optimal *fair* baseline is
  computable on the same observations, so the gap between "perfect reasoning" and the
  LLM is measurable per-seed; a controlled compound-stress difficulty axis; 3 metrics
  that separate seeing from acting.

## 2. The benchmark
- Task: weekly replenishment for an electronics importer, 26 weeks, order qty + route
  + optional levers (freight lock, air, inspect, audit/switch supplier). Cost = holding
  + stockout + fees; lower better.
- World: six hidden factor state-machines (demand, supplier, freight, port, quality,
  canal disruption); agent sees only symptoms. FAITHFUL prompt: rules only, no playbook.
- Seeds (9, frozen), grouped by true tape stress profile:
  ISOLATED 157/25/112, PERSISTENT 1/172/170, COMPOUND 21/143/99.
  [Insert seed dossier table — timelines already computed.]

## 3. Baselines and metrics
- Floor: base-stock policy. Fair oracle: per-factor particle filters + candidate
  rollout, same observations; reference = mean of 20 replications (single runs swing
  ~10%; se 0.3–1.6%). Oracle is fair not optimal — skill > 1 possible, observed 2/9 seeds.
- skill = (basestock − llm)/(basestock − oracle).
- detection lag: weeks from true episode start to factor first named in rationale.
- knowing-doing rate: fraction of correctly-diagnosed stress weeks that still stocked out.

## 4. Results
- Skill table (sonnet-5, gpt-5.4 done; deepseek-v4-pro [PENDING]):
  sonnet 0.95/0.78/0.47 by group; gpt 0.58/0.42/0.95 with −0.43 on 172.
  deepseek seed 157 first point: −0.29 on the EASIEST seed [PENDING full row].
- Detection lag + knowing-doing tables [PENDING grader].
- Case study: seed 1 — both models diagnosed the 8-week port congestion within ~1-2
  weeks, froze sea orders, leaned on capped air, missed the concurrent demand lift,
  4 (sonnet) / 3 (gpt) consecutive zero-inventory weeks. Right belief, wrong action.

## 5. Related work
[Positioning already written — see memory related-work-hypotheses.md 2026-07-07 update:
adopt knowing-doing vocabulary; differentiator = fair (non-privileged) computable oracle
+ compound-stress axis; AIM-Bench = biases; Who&When ≠ our attribution.]

## 6. Limitations & future work
- Stated belief only (rationale window; internal belief may precede — Broken Links).
- Oracle fair-not-optimal; no clairvoyant ceiling.
- One arm (FAITHFUL); COACHED and forced-belief-JSON arms = future work.
- 9 seeds, 3 models, single SKU.
