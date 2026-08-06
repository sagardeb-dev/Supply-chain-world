# RESULTS-LOG.md — temporal ledger of every result (started 2026-07-30)

We are experimenting rapidly and results supersede each other within days.
This file is the single place that records, IN TIME ORDER, why each result
exists, what produced it, where its canonical numbers live, and whether it
is still current. Rules:

1. **Every new experiment, correction, or regeneration gets an entry the day
   it lands** — trigger, method, canonical file, headline, status.
2. **Statuses:** CANONICAL (paper may cite it), SUPERSEDED-BY → entry N
   (paper must NOT cite it; kept for provenance), PENDING (data or analysis
   still running — nothing citable yet).
3. **When a file is regenerated, the old entry is marked SUPERSEDED the same
   commit of work** — never silently overwritten. Backups keep the old bytes
   (e.g. `*.pre-airfix`).
4. Before any paper number sweep, check the table below: a claim may only be
   transcribed from the file this table names.

Companion docs (this ledger indexes them, never duplicates their content):
TRACKER.md (run inventory), DEFECTS.md (defect fixes), STATS-GUIDELINES.md
(which tests back which sentences), WORKSHOP-REVISION.md (phase plan).

## Current claim → canonical source map (as of 2026-07-30)

| Paper claim | Canonical source | Last regenerated |
|---|---|---|
| Skill scores, two-tier split, resolution 0.31 | `backend/runs/ladder-v1/skill_scores.csv` + `uq.md` §1 | frozen 2026-07-15 (skill) / uq rerun 2026-07-30 |
| Oracle references (per-seed, 20-rep) | `backend/runs/ladder-v1/oracle_refs.csv` | frozen 2026-07-15 |
| Detection %, lags, episode counts (266 detectable) | `backend/runs/ladder-v1/belief_metrics.csv` + `report.md` | 2026-07-30 (entry 7) |
| KDR by group, severity confound (Table 3/4) | `backend/runs/ladder-v1/report.md` + `uq.md` §2 | 2026-07-30 (entry 7) |
| All CIs / p-values / Holm on the above | `backend/runs/ladder-v1/uq.md` | 2026-07-30 (entry 7) |
| Cost decomposition (Table 5) | `backend/runs/ladder-v1/cost_decomp.csv` / `.md` | 2026-07-30 (entry 4, D2a-patched entry 7) |
| Learned-oracle robustness (§6) | `oracle_refs_learned.csv` + STATS-GUIDELINES "LEARNED ORACLE, TESTED 2026-07-30" block | 2026-07-30 (entry 5) |
| Grader edge-case numbers (precision, censoring, full-coverage KDR) | `research/DEFECTS.md` D3/D4/D5/D7/D9 | 2026-07-30 (entry 6–7) |
| Oracle-side cost reference (planned Table 5 column / prose) | `backend/runs/ladder-v1/oracle_decomp.csv` / `.md` | PENDING (entry 8) |

## The ledger (oldest first)

### 1 — 2026-07-15 · FREEZE #2: 4 models × 50 seeds, skill scores
**Trigger:** expansion from the 20-seed core to the full 50-seed ladder.
**Did:** full runs for gpt-5.4 / sonnet-5 / grok-4.5 / deepseek-v4-pro;
`bench.py score|report`; results.md regenerated and frozen.
**Canonical:** `skill_scores.csv`, `oracle_refs.csv`, `report.md` skill tables.
**Headline:** skill spread +0.62 (gpt) to −0.23 (deepseek); seed 11 excluded
(negative headroom) → n=49.
**Status:** CANONICAL for skill/cost totals. Its belief-side numbers
(detection 84–88% of 283, original KDR/confound tables) are
SUPERSEDED-BY → 6, 7.

### 2 — ~2026-07-23 · arXiv v1 + learned-dynamics oracle built
**Trigger:** preprint freeze; simulated external review; "oracle knows the
physics" criticism needed an empirical answer.
**Did:** arXiv package frozen (v1 status user-side); `fit_oracle.py`
Baum-Welch on 200 passive tapes, validated on 4 seeds/single runs
(`LEARNED-ORACLE.md`).
**Status:** arXiv v1 FROZEN — but it carries pre-correction Tables 3/4
(entries 6–7); v2 is the user's call. The 4-seed learned-oracle validation
is SUPERSEDED-BY → 5 (adversarial pass rejected it as too thin).

### 3 — 2026-07-28 · UQ pass (uq.py) + stats discipline
**Trigger:** ACDB rejection lesson — no error bars weakens credibility.
**Did:** seed-cluster paired bootstrap + Wilcoxon + Holm over skill and
belief claims; STATS-GUIDELINES.md written; WORKSHOP-REVISION phase declared.
**Headline:** two-tier split survives; within-tier orderings dissolve;
"below floor" softened to "fail to beat the floor"; resolution 0.31.
**Status:** skill-side verdicts CANONICAL. Belief-side verdicts from this
date SUPERSEDED-BY → 6, 7 (uq.md was rerun after the corrections).

### 4 — 2026-07-30 · Cost decomposition (revision priority #2)
**Trigger:** over-response story rested on trace-reading; reviewer would ask
"where does the money actually go?"
**Did:** `analysis/cost_decomp.py` replays all 200 episodes through the
engine; 5,200 weekly totals byte-verified vs trace banners; FIRST
pre-registered contrast set (F1/F2).
**Canonical:** `cost_weeks.csv`, `cost_decomp.csv`/`.md`; paper Table 5.
**Headline:** all four escalate levers +$42–87/wk on diagnosed weeks
(Holm p<1e-4); sonnet out-airs gpt +$31; gpt-stockout-share pre-registration
FAILED in reverse (disclosed); below-floor over-response is
ordering+holding-shaped, not lever-shaped.
**Status:** CANONICAL (classify() D2a-patched in entry 7; DIAG rows verified
byte-identical after the patch).

### 5 — 2026-07-30 · Learned oracle at full protocol (50 seeds × 20 reps)
**Trigger:** adversarial pre-write pass predicted reviewers would reject the
4-seed validation (entry 2).
**Did:** `analysis/learned_refs.py` (k=191..210 protocol with learned
transitions) + `analysis/learned_vs_true.py` paired analysis.
**Canonical:** `oracle_refs_learned.csv`; summary block in STATS-GUIDELINES;
§6 paragraph.
**Headline:** learned − true = +$71 [−20, +186]/seed, p=0.47; skill shifts
+0.04..0.10, CIs straddle 0; claim scoped to transition dynamics; seed 12
flips negative-headroom under the learned scale.
**Status:** CANONICAL. Supersedes entry 2's validation.

### 6 — 2026-07-30 · D1 air-stockout correction (adversarial grader audit)
**Trigger:** user asked for an adversarial attack on the knowing-doing
implementation; audit found grade_beliefs derived stockouts from printed
`prev_inv + arrived < demand`, which misses air-expedited units.
**Did:** 343 air-saved weeks (100% air-linked, 0 reverse errors) regraded
from engine-truth `cost_weeks.csv`; backups `*.pre-airfix`; source now
refuses trace-derived stockouts where replay exists (D6 guard).
**Canonical:** regenerated `beliefs.csv`; disclosure footnote in paper §4;
DEFECTS.md D1.
**Headline:** all KDRs roughly halve; "KDR rank-inverts with skill" DEAD;
"below-floor models have lowest diagnosed-week stockout rates" DEAD.
**Status:** CANONICAL as a correction event. Its interim tables (confound
3-of-4, detection of 283) lasted hours and are SUPERSEDED-BY → 7.

### 7 — 2026-07-30 · D2a/D2b week-26 fixes → current belief-side numbers
**Trigger:** user: defects must get concrete fixes and a persistent ledger
(DEFECTS.md created). Week 26 has no rationale → stressed wk-26 rows are
unknowable (D2a) and 17 episodes with onset week 26 are undetectable by
construction (D2b).
**Did:** patched grade_beliefs.py / results_tables.py / uq.py /
cost_decomp.py / fig2.py; regenerated belief_metrics.csv, report.md,
uq.csv/uq.md, fig2.pdf; full paper sweep.
**Canonical:** everything belief-side as of this entry — detection
94.0/93.2/92.5/89.1% (sonnet/gpt/grok/dpsk) of 266 detectable; lags
0.32–0.42 ("no slower", all Holm 1.0); KDR persistent peak 0.18–0.26
significant for gpt (.018) + deepseek (.028) only; confound diag/undiag
significant for ALL FOUR (Holm ≤ 0.022), undiag pools 124/137/170/95.
**Status:** CANONICAL — the numbers in the paper today.

### 8 — 2026-07-30 · Oracle-side cost decomposition — PENDING
**Trigger:** my adversarial self-review: Table 5 shows composition, not
excess; "DeepSeek holds $133/wk on diagnosed weeks" needs "vs what the
oracle's books look like on those same weeks".
**Did so far:** contrasts F3/F4/F5 PRE-REGISTERED in STATS-GUIDELINES
(predictions: holding+procurement excess positive for grok/deepseek; sonnet
air excess positive) BEFORE any data existed; `run_oracle(week_rows=...)`
hook; `analysis/oracle_cost_weeks.py` generating 50 seeds × 20 reps in the
background (gates: weekly components sum to episode total; rep-means must
reproduce oracle_refs.csv within $0.05); `analysis/oracle_decomp.py` ready.
**Canonical:** `oracle_cost_weeks.csv` (26,000 rows), `oracle_decomp.csv`/`.md`.
**Result (landed same day, all gates passed — rep-means reproduce
oracle_refs.csv):** F3 holding excess CONFIRMED for grok +$25/wk and
deepseek +$38/wk (Holm <1e-4); sonnet NEGATIVE −$10 (unpredicted sign,
significant); gpt n.s. F4 procurement excess CONFIRMED grok +$20 (Holm
.0012), deepseek +$30 (<1e-4); gpt/sonnet n.s. F5 sonnet air excess
+$65/wk [49,83] CONFIRMED. Descriptive: the oracle itself spends $55–60/wk
on levers on diagnosed-stress weeks — escalation is correct behavior;
models fail on dosage/instrument mix.
**Status:** CANONICAL — the oracle reference column for Table 5 / §5.

### 9 — 2026-07-31 · Ladder-audit fixes (D10/D11) + KDR duration test (D12)
**Trigger:** triple adversarial audit (ladder/slop/repro) found seed 143
violates the paper's "3+ concurrent" COMPOUND definition, GROUPS has no
generating script, and the PERSISTENT KDR peak was untested against the
duration confound (PERSISTENT mean port block 6.3 wk vs 0.7/3.1).
**Did:** paper §3 group definitions rewritten to the true separators (no
seeds reclassified); `analysis/classify_seeds.py` reproduces all 50 labels
(max_overlap≤1 → ISOLATED; port_block≥T & demand≥T → PERSISTENT, T=7
core-20 round / T=4 expansion; else COMPOUND); curation-in-rounds +
threshold relaxation now disclosed in §3. F6/F7 pre-registered in
STATS-GUIDELINES BEFORE data, then run via `analysis/kdr_duration.py`.
**Canonical:** classify_seeds.py (self-checking), kdr_duration.py stdout
values recorded in STATS-GUIDELINES "KDR DURATION CONFOUND" block.
**Headline:** F6 — per-seed KDR rises with longest port blockage
(Spearman +0.44 sonnet / +0.36 grok / +0.62 deepseek, Holm ≤ .015; gpt
+0.24 n.s.). F7 — PERSISTENT membership adds no detectable association
once duration is controlled (Holm ≥ .086 all four; gpt borderline raw
p=.022). Paper §5 now says the peak is duration-driven, not a
profile-category effect.
**Status:** CANONICAL — the KDR-peak framing in the paper today.
