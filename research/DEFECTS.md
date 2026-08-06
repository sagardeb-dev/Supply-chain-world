# DEFECTS.md — belief-grading / metric defect ledger (started 2026-07-30)

Standing rule: every defect found in the measurement pipeline gets a row
here the day it is found, with a concrete fix, its status, and the numbers
it moved. Disclosure without a fix is not a status. Adversarial audits
append; nothing is deleted. Companion to STATS-GUIDELINES.md (which
governs claims; this governs the instruments behind them).

Status vocabulary: FIXED (canonical numbers corrected, source patched) /
GUARDED (source patched so it cannot recur; historical data unaffected) /
MEASURED (quantified, reported as metric or robustness number) /
OPEN (fix designed, not yet executed — reason stated).

## D1 — air-stockout flag  [FIXED 2026-07-30]

The grader derived stockout from the trace's printed `inv + arrived <
demand`; air-expedited units land outside `arrived`. 343 air-saved weeks
across the 4 models flagged as stockouts (100% air-linked; zero errors the
other way; sonnet worst at 111). Every KDR roughly halved; "KDR
rank-inverts with skill" and "below-floor models have lowest diagnosed
stockout rates" died; persistent-peak significance narrowed to
gpt/deepseek.
**Fix:** beliefs.csv stockout regraded from cost_weeks.csv engine truth
(checksum-verified replay); grade_beliefs.py now reads engine truth and
REFUSES the trace fallback for replayed models; full chain regenerated
(belief_metrics, report.md, results.md, uq, paper Tables 3/4 + §4
disclosure footnote). Backups: *.pre-airfix.

## D2a — week-26 rows in belief denominators  [FIXED 2026-07-30]

The final week has no rationale (the run ends before another decision), so
its 38 stressed rows per model are unknowable — yet they sat in the
UNDIAG pool of the confound and the cost-decomposition class split.
**Fix:** week 26 excluded from the diag/undiag pools in grade_beliefs.py,
results_tables.py, uq.py, cost_decomp.py (CALM keeps its truth-only wk26
rows; DIAG counts unchanged — no wk26 week can be diagnosed). Effect:
undiag pools 162/175/208/133 → 124/137/170/95; confound gap WIDENS and is
significant for all four models again (gpt Holm p 0.24 → 0.022).

## D2b — undetectable episodes counted as missed  [FIXED 2026-07-30]

17 of 283 stress episodes have onset in week 26 — no rationale can ever
name them. They were counted as never-detected, deflating detection for
every model equally.
**Fix:** excluded from the detection denominator at the grader
(n_undetectable column added to belief_metrics.csv). Detection: 84–88% of
283 → 89–94% of 266 detectable (sonnet 94.0, gpt 93.2, grok 92.5,
deepseek 89.1). "No pairwise difference survives Holm" unchanged
(smallest adj. p = 0.052). fig2 regenerated. Remaining censoring (onset
24–25, 1–2 rationale weeks) stays disclosed, not excluded — detection
there is possible, just hard, and equally so for every model.

## D3 — detection is recall-only  [MEASURED 2026-07-30]

A model that names every factor every week scores 100% detection.
**Fix:** precision now a reported metric beside detection: strict
precision (vs at-threshold stress) gpt 0.34, sonnet 0.35, grok 0.29,
deepseek 0.30; naming volume 1.33–1.74 factors/week (grok highest AND
tersest — scattershot, not verbosity). In paper §6 with numbers.
Follow-up (OPEN): a precision-controlled detection variant (e.g. credit
capped by per-week naming budget) needs a design pass before it can be a
headline metric.

## D4 — binary stress threshold miscredits early warnings  [MEASURED 2026-07-30]

~1/3 of "false alarms" name sub-threshold-but-real activity
(freight:tightening 314, supplier:wobbling 282, disruption:watch 274,
quality:drifting 252, port:building 140 namings) — including conditions
the world's own paid audit reports in those words ("slipping").
**Fix:** lenient precision (brewing regimes not counted against) reported
beside strict: gpt 0.41, sonnet 0.43, grok 0.36, deepseek 0.37. In paper
§6. Follow-up (OPEN): a three-state truth (calm/brewing/stressed) for the
detection metric itself is a v2 metric change — needs its own
calibration pass, do not bolt on silently.

## D5 — any-overlap rule counts partial diagnoses  [MEASURED 2026-07-30]

On multi-stress weeks, naming ONE stressed factor counts the week as
diagnosed (55–70% of diagnosed multi-stress weeks named only a subset), so
COMPOUND KDR partly blames "knew but stocked out" where the agent half-knew.
**Fix:** full-coverage KDR (named ⊇ stressed) computed as robustness:
persistent peak holds for gpt (0.14 vs 0.09 all-weeks) and deepseek (0.23
vs 0.16), weakens for sonnet/grok — convergent with the significance
pattern (only gpt/deepseek survive Holm). Disclosed in §6; ledger keeps
the numbers.

## D6 — grader API failure returned [] silently  [GUARDED 2026-07-30]

A grader that failed 4 retries returned an empty factor list,
indistinguishable from "named nothing" — biasing detection down by an
unlogged amount.
**Fix (source):** grade_rationale now raises after exhausted retries
(resume makes rerun cheap); a failure can no longer be recorded as data.
**Historical data:** cannot be reconstructed from logs. Bounding option:
re-grade all 5,200 weeks with the same grader (~$3–5 of gpt-5-mini) and
diff — also yields a grader-stability number. AWAITING GO (paid).

## D7 — unbounded detection window  [MEASURED 2026-07-30]

A factor named long after its episode ended still counts as detecting it
(2.0–2.8% of detections land after episode end; disclosed in appendix).
**Fix:** bounded-window robustness computed (window = episode span + 1
grace week): detection 88.0–91.4% vs 89.1–94.0% unbounded — conclusions
unchanged. Ledger keeps the variant; switching the headline definition is
not warranted by a ≤2.6pp delta.

## D8 — stated belief is style-dependent  [OPEN — needs a new arm]

Terse models under-state what they track (grok: 41-word median rationale
vs 82–87), so cross-model detection comparisons ride on disclosure style,
partially mitigated by D3's precision reporting (scattershot visible).
**Fix design:** a belief-elicitation arm (structured belief JSON each
week, graded against the same truth) — already on the parked ablations
list; paid + prompt-arm change, needs greenlight. Until then the paper's
"lower bound" framing stands.

## D9 — single cheap grader  [MEASURED (pre-existing audit)]

gpt-5-mini, temp 0, one pass. Second-grader agreement 89% on the
metric-relevant component (disclosed in §6); residual disagreement sits on
calm-week over-labels which cannot enter KDR by construction. D6's paid
re-grade would add a same-grader stability number for free.

## D10 — COMPOUND definition contradicts the tapes  [FIXED 2026-07-31]

paper.tex:425 defines COMPOUND as "pileups of three or more concurrent"
factor episodes. Seed 143 (COMPOUND, and one of the two named skill>1
seeds) never exceeds max_overlap=2 (sweep/results.csv); meanwhile 5 of 15
PERSISTENT seeds meet the 3+ bar (58 and 108 hit 4-way overlap). The
stated definition is not what separates the groups — duration
(port_block_longest: PERSISTENT mean 6.3 wk vs COMPOUND 3.1 vs ISOLATED
0.7) is. Verifiable from the paper's own appendix table, no code needed.
**Fix:** rewrite the group definitions in §3 to describe what actually
distinguishes the tapes (ISOLATED = short, single-factor windows;
PERSISTENT = one long-duration blockage dominating; COMPOUND = multiple
overlapping/back-to-back episodes) instead of a numeric concurrency bar
the tapes violate. Do NOT reclassify seeds (would silently regenerate
every per-group number).
**Done 2026-07-31:** paper Sec. 3 bullets rewritten to the true separators
(ISOLATED = max one factor stressed at once; PERSISTENT = port blockage
>= 4 wk alongside >= 4 demand-stress weeks; COMPOUND = everything else,
2+ concurrent, no dominating blockage). No seeds reclassified.

## D11 — no reproducible classifier behind GROUPS; iterative curation  [FIXED 2026-07-31]

The GROUPS dict in bench_config.py is hand-typed; no committed script
produces it (sweep/analyze.py computes a different EASY/MEDIUM/HARD
taxonomy, never used). TRACKER.md shows three curation rounds with
shifting thresholds (headroom>800 → headroom>=500, "relaxed PERSISTENT
threshold port>=4 & dem>=4"), and the 2026-07-08 expansion happened after
interim per-group skill patterns were visible. paper.tex:430-431's
"membership is fixed by the tape alone ... an independent variable"
overstates this.
**Fix:** (a) write backend/analysis/classify_seeds.py that reproduces the
50 labels from tape features alone and commit it as the post-hoc
formalization; report its agreement with the hand labels; (b) soften the
paper sentence to disclose curated-in-rounds selection ("seeds were
curated iteratively for stress coverage and headroom; labels formalized
post hoc by the committed classifier"). Both cheap; awaiting go.
**Done 2026-07-31:** analysis/classify_seeds.py reproduces ALL 50 labels
(rule: max_overlap<=1 -> ISOLATED; port_block_longest>=T and
stress_demand>=T -> PERSISTENT with T=7 core-20 round / T=4 expansion;
else COMPOUND). Paper Sec. 3 now discloses the three-round curation and
the threshold relaxation, and the "independent variable" sentence is
replaced by the classifier claim.

## D12 — KDR-peaks-on-PERSISTENT untested against duration confound  [MEASURED 2026-07-31]

PERSISTENT differs from the other groups in raw severity, not just shape:
longest single blockage 6.3 wk (vs 0.7/3.1), total stressed weeks ~22 (tied
with COMPOUND, 3x ISOLATED), highest median headroom ($1609). Table 4 tests
the within-group severity confound only; nothing tests whether "peaks on
PERSISTENT" survives controlling for duration — the paper's own prose
(§5, "when a disruption lasts many weeks...") already reads it as a
duration story.
**Fix:** pre-register + run a per-seed test: KDR (or diagnosed-stockout
count) vs port_block_longest / total-stressed-weeks across seeds (rank
correlation or regression, seed-cluster bootstrap), then either report
"the peak is explained by duration" as the finding or keep the categorical
framing with the test behind it. Local compute only, no API cost.
**Done 2026-07-31:** pre-registered F6/F7 (STATS-GUIDELINES) run via
analysis/kdr_duration.py. F6: KDR rises with blockage duration, Spearman
+0.36..+0.62 Holm<=.015 for sonnet/grok/deepseek (gpt +0.24 n.s.). F7:
PERSISTENT membership adds NO detectable association once duration is
controlled (Holm>=.086 all four; gpt borderline, raw p=.022). Paper Sec. 5
now attributes the peak to duration, not the profile label.

## D13 — provenance layer outside version control  [OPEN — user commit required]

.gitignore line 9 (`*.md`, only READMEs excepted) keeps 79 of 88 markdown
files out of git — including RESULTS-LOG.md, DEFECTS.md (this file),
STATS-GUIDELINES.md, and every runs/ladder-v1 report. Additionally: all of
backend/analysis/ (uq.py, cost_decomp.py, oracle_decomp.py, learned_*),
fit_oracle.py, learned_trans.json, and the derived CSVs behind Table 5 /
§5 / §6 are untracked; the D1/D2 fixes to grade_beliefs.py /
results_tables.py / oracle_policy.py are uncommitted; manifest.json claims
"commit b8f260f" (2026-07-16) for data generated 2026-07-30; HEAD's
paper.tex still carries the dead 84–88%/283 numbers. A clone of HEAD today
reproduces the pre-correction paper with no record of why it's wrong.
**Fix:** scope the .gitignore rule (allow research/*.md and
backend/runs/**/*.md), then one commit of: docs + analysis/ + fixed
sources + regenerated CSVs + paper.tex/pdf; rerun `bench.py report` after
committing so manifest.json records the true hash. Author commits himself.

## D14 — no LLM model-snapshot pinning  [OPEN — forward-only]

Neither the 4 benchmark models nor the grader resolve to dated snapshots;
traces and manifest.json record only the OpenRouter alias (e.g.
x-ai/grok-4.5, openai/gpt-5-mini). If an alias moves, reruns and the D6
re-grade cannot prove same-model. The 200 existing traces cannot be
retrofitted.
**Fix:** log the API response's resolved model id into every future trace
header and into manifest.json (small patch to the runner + grader);
disclose alias-level pinning as a limitation for the existing runs.

## D15 — undisclosed deepagents scaffolding in the harness  [OPEN — found 2026-08-06]

The harness builds agents with `deepagents.create_deep_agent` (v0.6.10,
`src/agent/factory.py`), which silently adds built-in tools (`write_todos`,
`ls/read_file/write_file/edit_file/glob/grep`, `execute`, `task` subagents)
and appends the SDK's own scaffolding prompt AFTER our system prompt. The
paper says all models ran "under the rules-only prompt of Section 3" — as
written, false: every model also saw deepagents' planning-scaffold prompt
and tool menu. Trace audit (all 200 episodes): file/execute/subagent tools
were never used by any model, but `write_todos` uptake is heavily
differential — sonnet 38/50 seeds (82 calls), gpt 13/50 (27), deepseek
2/50 (3), grok 0/50. Uptake ordering matches the headline skill ranking,
and deepagents' default target model is claude-sonnet — a same-family
harness-tuning objection analogous to C2. Descriptive check: sonnet skill
0.516 on todo seeds vs 0.424 without (confounded by seed difficulty, not
causal).
**Fix (decision pending):** (a) minimum — disclose the scaffold + per-model
uptake stats and correct the "rules-only prompt" sentence; (b) pilot a
clean-harness rerun (built-ins excluded via HarnessProfile or plain
create_agent; world tools only, prompt exactly as the paper describes) on
a few seeds × 2 models (sonnet max-uptake, grok zero-uptake) to measure
the delta; (c) if the delta moves skill materially, full clean rerun
becomes the canonical result and the deepagents runs become a scaffolding
ablation. Pairs naturally with the D14 snapshot-pinning fix and the
Blackwell repeats ablation (same spend event).

## Verification trail

Every fix above was verified by: engine-replay checksums (5,200/5,200
weekly totals), byte-identical detection/lag under D1 (which never read
the flag), DIAG counts and all cost_decomp pre-registered contrasts
byte-identical under D2a, and uq.py sanity gates updated to the corrected
tables and passing. Alignment of rationale→week was probe-tested: 99.1%
of 1,255 quoted-inventory checks match (11 misses are agent arithmetic,
not parser offset).
