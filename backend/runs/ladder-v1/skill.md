> **STALE** — superseded by the `bench.py` pipeline; current numbers: `skill_scores.csv` (canonical) and `report.md` (generated). Kept for lab-notebook narrative.

# ladder-v1 skill scores (updated 2026-07-07: oracle = 20-rep mean)

skill = (basestock − llm) / (basestock − oracle); 1.0 = oracle-level, 0 = no better than base-stock, negative = worse than base-stock.

Oracle reference is the MEAN of 20 independent oracle replications (k≈200 particles,
20 distinct MC streams) per seed — a single oracle run is a stochastic policy whose
total swings ~10% between random streams, so the old k=50 single-draw references
(sweep/results.csv cost_oracle) were noisy. Standard error of the means: 0.3–1.6%.
skill > 1 is possible: the fair oracle is belief-optimal within its candidate menu,
not globally optimal, and LLMs beat its mean on seeds 143/99.

| tier | seed | basestock | oracle (±se) | sonnet-5 cost | sonnet skill | gpt-5.4 cost | gpt skill |
|------|------|-----------|--------------|---------------|--------------|--------------|-----------|
| EASY | 157  | 5442 | 3880 ±16  | 3767  | 1.07 | 4346 | 0.70 |
| EASY | 25   | 6100 | 4826 ±43  | 5192  | 0.71 | 5198 | 0.71 |
| EASY | 112  | 5185 | 4159 ±13  | 4080  | 1.08 | 4857 | 0.32 |
| MED  | 1    | 9101 | 6932 ±102 | 8539  | 0.26 | 8970 | 0.06 |
| MED  | 143  | 9254 | 7671 ±121 | 6949  | 1.46 | 6674 | 1.63 |
| MED  | 172  | 7865 | 6041 ±92  | 6746  | 0.61 | 8645 | −0.43 |
| HARD | 21   | 6488 | 3956 ±48  | 5613  | 0.35 | 4433 | 0.81 |
| HARD | 170  | 10795 | 8660 ±110 | 10376 | 0.20 | 9202 | 0.75 |
| HARD | 99   | 9638 | 8354 ±76  | 8523  | 0.87 | 7994 | 1.28 |

Tier means: sonnet-5 EASY 0.95 / MED 0.78 / HARD 0.47; gpt-5.4 EASY 0.58 / MED 0.42 / HARD 0.95.
(143 inflates MED for both; on the port-trap seeds 1/172/170/21 the old story holds.)

## deepseek-v4-pro (added 2026-07-07, same FAITHFUL arm)

| group | seed | cost | skill |
|-------|------|------|-------|
| ISOLATED | 157 | 6335 | −0.57 |
| ISOLATED | 25 | 7950 | −1.45 |
| ISOLATED | 112 | 4633 | 0.54 |
| PERSISTENT | 1 | 9673 | −0.26 |
| PERSISTENT | 172 | 10147 | −1.25 |
| PERSISTENT | 170 | 13515 | −1.27 |
| COMPOUND | 21 | 6111 | 0.15 |
| COMPOUND | 143 | 7840 | 0.89 |
| COMPOUND | 99 | 7265 | 1.85 |

Group means: ISOLATED −0.50 / PERSISTENT −0.93 / COMPOUND 0.96. Below base-stock on
5/9 seeds. CAUTION: seed 99 skill 1.85 (beat the oracle mean on the hardest seed
while failing easy ones) — read that trace before citing it; likely a conservative
big-buffer policy that happens to fit 99's relentless stress profile.

Oracle replication data: scratch sweep 2026-07-07; regenerate with
`run_oracle(seed, k)` for k in 191..210 and average (k seeds the MC stream).

## 20-seed expansion: oracle refs for the 11 new seeds (20-rep means, 2026-07-07)

| seed | group | oracle mean | se |
|------|-------|-------------|-----|
| 60  | ISOLATED    | 5093.5 | 33.1 |
| 24  | ISOLATED    | 3950.5 | 11.4 |
| 86  | ISOLATED    | 4364.9 | 13.5 |
| 95  | PERSISTENT | 7632.5 | 41.6 |
| 29  | PERSISTENT | 6686.1 | 64.6 |
| 58  | PERSISTENT | 7776.9 | 60.2 |
| 108 | PERSISTENT | 9031.5 | 90.8 |
| 44  | COMPOUND  | 7521.5 | 101.2 |
| 94  | COMPOUND  | 6170.6 | 50.6 |
| 154 | COMPOUND  | 5574.7 | 25.4 |
| 85  | COMPOUND  | 5996.5 | 12.4 |

basestock refs for these seeds: sweep/results.csv. LLM scores pending
(deepseek running; sonnet/gpt blocked on key raise).

## deepseek-v4-pro, 11 new seeds (2026-07-07 evening; all validated 26wk + EPISODE DONE)

| group | seed | cost | skill |
|-------|------|------|-------|
| ISOLATED | 60 | 6425 | 0.33 |
| ISOLATED | 24 | 4704 | 0.37 |
| ISOLATED | 86 | 6357 | −1.76 |
| PERSISTENT | 95 | 12429 | −1.61 |
| PERSISTENT | 29 | 8241 | 0.08 |
| PERSISTENT | 58 | 13636 | −2.82 |
| PERSISTENT | 108 | 10094 | −0.21 |
| COMPOUND | 44 | 8666 | 0.30 |
| COMPOUND | 94 | 6072 | 1.06 |
| COMPOUND | 154 | 6710 | 0.32 |
| COMPOUND | 85 | 6903 | 0.44 |

deepseek 20-seed group means: ISOLATED −0.42 / PERSISTENT −1.05 / COMPOUND 0.72 (script-computed 2026-07-08; an earlier hand-summed −0.76 for PERSISTENT was wrong).
(seed 58 first attempt died at wk13 and was rerun; lesson -> validate every
trace for 26 weeks + EPISODE DONE before scoring.)

## sonnet-5, 11 new seeds (2026-07-07 late; all validated 26wk + EPISODE DONE)

| group | seed | cost | skill |
|-------|------|------|-------|
| ISOLATED | 60 | 6543 | 0.27 |
| ISOLATED | 24 | 4755 | 0.33 |
| ISOLATED | 86 | 5382 | −0.41 |
| PERSISTENT | 95 | 8150 | 0.72 |
| PERSISTENT | 29 | 8099 | 0.17 |
| PERSISTENT | 58 | 8647 | 0.43 |
| PERSISTENT | 108 | 8643 | 1.44 |
| COMPOUND | 44 | 9287 | −0.07 |
| COMPOUND | 94 | 6182 | 0.99 |
| COMPOUND | 154 | 6763 | 0.29 |
| COMPOUND | 85 | 7332 | 0.17 |

IMPORTANT 20-seed finding: sonnet's combined group means flatten to ~ISOLATED 0.51 /
PERSISTENT 0.55 / COMPOUND 0.58 — the 9-seed "monotone decline with stress" was a
small-sample artifact (original 3 ISOLATED seeds flattered it). Per-seed variance
dominates group means. The robust story is the belief-level one (detection lag ~0,
knowing-doing rate high on trap seeds), not a difficulty gradient in skill.

## gpt-5.4, 11 new seeds (2026-07-07 late; all validated 26wk + EPISODE DONE)

| group | seed | cost | skill |
|-------|------|------|-------|
| ISOLATED | 60 | 5031 | 1.03 |
| ISOLATED | 24 | 5069 | 0.07 |
| ISOLATED | 86 | 5074 | 0.02 |
| PERSISTENT | 95 | 7104 | 1.29 |
| PERSISTENT | 29 | 7620 | 0.45 |
| PERSISTENT | 58 | 8231 | 0.70 |
| PERSISTENT | 108 | 8663 | 1.42 |
| COMPOUND | 44 | 8543 | 0.38 |
| COMPOUND | 94 | 7621 | 0.14 |
| COMPOUND | 154 | 6016 | 0.73 |
| COMPOUND | 85 | 6550 | 0.66 |

New-11 group means: ISOLATED 0.37 / PERSISTENT 0.96 / COMPOUND 0.48. Note gpt's
new-set PERSISTENT strength vs its −0.43 on seed 172 — per-seed variance
dominates for flagships; report per-seed distributions, not just group means.

## BENCHMARK RUN STATUS: all 60 runs complete (3 models x 20 seeds), 2026-07-07.

## n=50 update (2026-07-09, script-computed)

CANONICAL FILE: `skill_scores.csv` (this dir) — all 120 (model,seed) cells,
generated by script from traces + sweep/results.csv + 20-rep oracle CSVs.
The hand-maintained tables above cover the original 20 seeds only and one
median there was wrong (deepseek ISOLATED med is −0.12, not 0.33). Read the
CSV, not the tables, for any paper number.

Seed 11 is UNSCOREABLE for skill: its 20-rep oracle mean (6806.1) is WORSE
than basestock (6587.7) — negative headroom, denominator sign flips. It was
selected on the old noisy single-run oracle value. Excluded from all skill
means; still valid for detection/knowing-doing (no oracle involved).
Thin headroom (<700), kept but flagged: seeds 36 (584), 160 (583), 164 (488).

Group means (mean / median, neg = seeds below basestock floor):

| model | n | ISOLATED | PERSISTENT | COMPOUND | ALL | neg |
|---|---|---|---|---|---|---|
| sonnet-5 | 49 | +0.54 / +0.71 (n=11) | +0.70 / +0.61 (n=15) | +0.33 / +0.35 (n=23) | +0.49 / +0.45 | 9 |
| gpt-5.4 | 49 | +0.21 / +0.07 (n=11) | +0.55 / +0.61 (n=15) | +0.86 / +0.73 (n=23) | +0.62 / +0.65 | 8 |
| deepseek-v4-pro | 20 | −0.42 / −0.12 (n=6) | −1.05 / −1.25 (n=7) | +0.72 / +0.44 (n=7) | −0.24 / +0.12 | 9 |

deepseek unchanged (n=20 core; dropped from expansion, provider instability).
