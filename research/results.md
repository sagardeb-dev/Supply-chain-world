# Final benchmark results (2026-07-08)

All numbers below are script-computed from the files named in each section.
Provenance: 60 episodes (3 models x 20 seeds), FAITHFUL prompt arm, traces in
`backend/runs/ladder-v1/<model>/seedN-rich.chat.txt`, all validated (26 weeks +
EPISODE DONE). Belief labels: grader v2 prompt with same-week alignment
(`backend/runs/grade_beliefs.py`, gpt-5-mini, temperature 0); per-week labels in
`beliefs.csv`, per-seed metrics in `belief_metrics.csv`, both under
`backend/runs/ladder-v1/`. Seed groups and oracle references:
`backend/runs/ladder-v1/skill.md` and `manifest.json`. Naming: the backend files
use the older group labels SINGLE / PORT-TRAP — same groups as ISOLATED /
PERSISTENT here (COMPOUND unchanged).

## Table 1 — skill score, 20 seeds

skill = (basestock − llm) / (basestock − oracle). 0 = base-stock floor,
1 = fair-oracle mean. n = seeds per group; neg = seeds scored below the floor.

| model | ISOLATED (n=6) | PERSISTENT (n=7) | COMPOUND (n=7) | all 20 | neg seeds |
|---|---|---|---|---|---|
| sonnet-5 | 0.51 (med 0.71) | 0.55 (med 0.43) | 0.58 (med 0.35) | 0.55 | 2 |
| gpt-5.4 | 0.48 (med 0.70) | 0.61 (med 0.70) | 0.80 (med 0.73) | 0.64 | 1 |
| deepseek-v4-pro | −0.42 (med 0.33) | −1.05 (med −1.25) | 0.72 (med 0.44) | −0.24 | 9 |

Per-seed values: skill.md. Notes: single run per (model, seed) cell; skill > 1
occurs (5 cells) and is legitimate — the oracle is fair, not optimal. The
deepseek COMPOUND mean is inflated by seed 99 (1.85), unverified by trace
reading; its COMPOUND median is 0.44.

## Table 2 — detection (pooled over all stress episodes)

Episode = maximal run of consecutive weeks one factor is truly stressed
(114 episodes per model across the 20 seeds). Lag in weeks from episode start
to the factor first appearing in the agent's stated rationale.

| model | episodes missed | mean lag (detected) |
|---|---|---|
| sonnet-5 | 10 / 114 | 0.35 |
| gpt-5.4 | 9 / 114 | 0.30 |
| deepseek-v4-pro | 17 / 114 | 0.24 |

All three models detect ~85–92% of hidden-factor episodes, typically within
the first week. Detection separates the models far less than cost does.

## Table 3 — knowing-doing rate (pooled)

Among weeks where the agent's rationale correctly named at least one truly
stressed factor: fraction that still ended in a stockout.

| model | ISOLATED | PERSISTENT | COMPOUND | all |
|---|---|---|---|---|
| sonnet-5 | 0.30 | 0.49 | 0.27 | 0.37 |
| gpt-5.4 | 0.06 | 0.41 | 0.29 | 0.31 |
| deepseek-v4-pro | 0.14 | 0.49 | 0.34 | 0.37 |

For every model the rate is highest on PERSISTENT seeds: correct diagnosis
coexists with an empty shelf in 41–49% of correctly-diagnosed weeks there,
versus 6–30% on ISOLATED seeds. Caveat: a stockout in week W may be caused by an
order decision several weeks earlier; the rate measures whether correct
diagnosis prevented empty shelves, not week-level fault.

## Grader-label validation (done 2026-07-08)

Two independent checks; second-grader data in
`backend/runs/ladder-v1/grader_agreement.csv`:

1. Stratified 30-row manual read (10 metric-relevant hits, 10 misses, 10
   calm-week labels) against raw trace rationales: all 10 hit-class
   intersections correct; 9/10 misses genuinely the model's (1 ambiguous,
   direction pessimistic for detection); calm-week labels ~50% over-labeled,
   a class the metrics exclude by construction.
2. Independent second grader (claude-haiku-4.5, identical prompt, 100 sampled
   weeks): exact-label agreement 43% — the task is ambiguous on borderline
   benign mentions — but agreement on the metric-relevant quantity
   (label ∩ true stress) is 89%.

Conclusion: the reported detection and knowing-doing numbers rest on the
label component where graders and manual reading agree; the noisy component
does not enter any table.

## Known open items

- Seed-99 deepseek trace unread; do not cite that cell without reading it.
- Single run per cell; provider nondeterminism unquantified.
