# STATS-GUIDELINES.md — how claims get made (grounded 2026-07-28)

Companion to WRITING.md. WRITING.md governs prose; this governs which
sentences are *allowed to exist*. Written after the UQ pass showed some of
our v1 claims were stronger than the data (below-floor, within-tier
ordering, half the COMPOUND exception). All sources below verified via Exa
2026-07-28 — real papers, safe to cite.

## The core discipline

1. **Exploratory → confirmatory, in that order, and label which mode you're
   in.** Staring at tables and noticing patterns is exploratory — it
   generates candidate claims, never claims. A claim is a pattern that
   survived a test designed to kill it. Writing exploratory observations in
   confirmatory language is the failure mode (ours, and the field's).
2. **Comparison-verb rule.** Any sentence with beats / worse / best / below /
   faster / flat is an inference about the world → needs a CI and a test
   BEFORE the sentence is written. Counts and means of your own sample
   ("−0.23 on our 49 seeds", "22 of 49 below floor") are descriptive facts →
   need only accuracy. Check every results sentence against this split.
3. **Stats gate before prose.** Error bars are computed when the results
   table is first built, not retrofitted after the story is written. We
   retrofitted; it cost us three softened claims. Never again: no results
   prose until uq-style output exists for the numbers it cites.
4. **"Flat" / "same" needs its own test.** Similar means don't prove
   sameness (our detection 84–88% claim). Absence of a significant
   difference ≠ evidence of equivalence — say "we found no significant
   difference" or run an equivalence test; never "identical".
5. **Correct for multiple comparisons whenever a family of claims is made**
   (we use Holm). A ranking of k models implies k(k−1)/2 pairwise claims;
   evalci's reanalysis found 3 of 8 adjacent MMLU leaderboard gaps dissolve
   after exactly this correction — the same thing that happened to our
   within-tier orderings.
6. **Report the benchmark's resolution**, not just its scores: the typical
   CI half-width on a pairwise contrast (ours: 0.31 skill units at n=50).
   A gap smaller than the resolution is not a finding, it's a coin flip.
7. **Negative/null results are stated as what they are**: "statistically
   indistinguishable from the floor" is a supported, publishable claim;
   "below the floor" (when the CI straddles 0) is not.

## The literature (what each canon says, one line each)

- **Dror et al. 2018, "Hitchhiker's Guide to Testing Statistical
  Significance in NLP" (ACL P18-1128)** — the field ignores or misuses
  significance testing; gives a test-selection protocol. Nonparametric
  (Wilcoxon) when score distributions are non-normal — our case.
- **Miller 2024, "Adding Error Bars to Evals" (arXiv 2411.00640,
  Anthropic)** — evals ARE experiments; treat questions (for us: seeds) as
  drawn from a super-population; use paired differences between models to
  kill item-difficulty variance; plan sample sizes with power analysis.
  Closest thing to an official "how to report LLM evals" doc.
- **Agarwal et al. 2021, "Deep RL at the Edge of the Statistical Precipice"
  (NeurIPS 2021, arXiv 2108.13264)** — point estimates from few runs
  routinely reverse under proper interval estimates; report bootstrap CIs
  over runs, interquartile means, performance profiles. The RL twin of our
  situation (costly episodes → few runs → wide CIs).
- **Colas et al. 2018, "How Many Random Seeds?" (arXiv 1806.08295)** —
  power analysis: given the effect you want to detect and the variance you
  observed, N follows. Use to answer "would more seeds rescue the
  within-tier ordering?" (our answer: ~4–6× — not worth it).
- **Dehghani et al. 2021, "The Benchmark Lottery" (arXiv 2107.07002)** —
  rankings are fragile to task/seed selection, not just noise. Our
  stress-profile axis is the mitigation: report per-group, not just ALL.
- **Alzahrani et al. 2024, "When Benchmarks are Targets" (arXiv
  2402.01781)** — leaderboard ranks flip under minute format perturbations;
  never over-read adjacent ranks. Supports "tiers, not neighbors" framing.
- **Blackwell et al. 2024, "Towards Reproducible LLM Evaluation" (arXiv
  2410.03492)** — LLMs are stochastic even at temperature 0 with fixed
  seed; repeats quantify run-to-run variance. The citation for our repeats
  ablation's motivation.
- **evalci (arXiv 2607.04429)** — per-item results table → CI + paired
  test + multiplicity correction in one call; validated against
  independent references. Same machinery as our uq.py (we keep our own —
  paired-by-seed with a custom skill metric — but it's the sanity
  cross-check option and a citable precedent).

## How this maps onto STOCKTAKE right now

DONE (uq.py, 2026-07-28): paired bootstrap + Wilcoxon + Holm on skill
scores → two-tier claim confirmed; below-floor softened to fail-to-beat;
COMPOUND exception attributed to the GPT side only; resolution 0.31; oracle
noise negligible (0.02 vs 0.6–1.2 seed spread).

BELIEF-SIDE, TESTED 2026-07-28 (uq.py section 2, seed-cluster bootstrap,
sanity-gated against frozen confound/KDR/detection tables — exact match):
- "Detection is flat 84–88%" — SUPPORTED as no-significant-difference (no
  pairwise gap survives Holm; smallest adj. p=0.05, sonnet-vs-deepseek).
  Phrase as "no detectable difference", never "identical".
- "KDR peaks on PERSISTENT for all four models" — SUPPORTED at full
  strength (Holm p ≤ 0.024 for all four).
- "Diagnosed weeks stock out MORE than undiagnosed" — SUPPORTED for all
  four models (Holm p ≤ 0.008); confound table is solid.
- "Below-floor models have SHORTEST detection lags" — DISSOLVED (all Holm
  p = 1.0). Soften everywhere to "detect no slower". Results §5 sentence
  "the two models below the floor have the shortest detection lags" is the
  overclaim to fix in the prose pass.

COST DECOMPOSITION, TESTED 2026-07-30 (analysis/cost_decomp.py; engine
replay verified against all 5,200 logged weekly totals; contrasts
PRE-REGISTERED before results were seen — first use of the discipline):
- "All models escalate levers on diagnosed weeks" — SUPPORTED (all four
  Holm p < 1e-4; +$42..87/wk vs calm).
- "Sonnet out-airs gpt on diagnosed weeks" — SUPPORTED (+$31 [13,50],
  Holm p < 1e-4).
- "gpt's diagnosed-week cost is more stockout-shaped than sonnet's" —
  REFUTED IN REVERSE (share difference −0.03 [−0.06,−0.004], p=0.026;
  disclosed as a failed pre-registration in §5).
- Below-floor over-response is ordering+holding-shaped, NOT lever-shaped
  (grok/deepseek levers $81/$67 vs procurement $87/$98 + holding
  $120/$133) — descriptive composition facts; cross-model lever
  comparisons NOT tested (CIs overlap gpt) — never add a comparison verb
  there without a new test.

DEFECT LEDGER: research/DEFECTS.md (started 2026-07-30) — every measurement
defect gets a row with a concrete fix + status the day it is found;
disclosure without a fix is not a status. D2a/D2b (week-26 unknowable
rows + 17 undetectable episodes) FIXED same day: detection is now 89–94%
of 266 detectable episodes (was 84–88% of 283), confound significant for
ALL FOUR again (gpt 0.24 → 0.022) with undiag pools 124/137/170/95.
grade_beliefs.py hardened: engine-truth stockouts mandatory where replay
exists, grader API failure now raises instead of returning [].

AIR-STOCKOUT CORRECTION 2026-07-30 (adversarial audit of grade_beliefs.py):
the trace-derived stockout flag miscounted 343 air-saved weeks as stockouts
(100% air-linked, zero misses the other way; verified vs engine replay).
Regraded from cost_weeks.csv engine truth (backups *.pre-airfix). Verdict
changes: KDR-persistent-peak now significant for gpt (.018) + deepseek
(.028) ONLY (sonnet/grok .23); confound significant for 3 of 4 (gpt .24);
"KDR rank-inverts with skill" DEAD (gpt lowest, sonnet highest — both top
tier); "below-floor models have lowest diagnosed-week stockout rates" DEAD
(gpt lowest). All KDRs roughly halve (persistent 0.18–0.26). Paper §4
footnote disclosure + Tables 3/4 + abstract/intro sweep done same day.
Extra disclosures added to §6: precision 0.29–0.35 (recall-only detection),
~1/3 of false alarms are sub-threshold real activity, any-overlap partial
diagnoses 55–70% of multi-stress diagnosed weeks, never-detected mostly
right-censored (26–34 of 33–46 start wk≥24; week 26 has no rationale).

LEARNED ORACLE, TESTED 2026-07-30 (learned_refs.py + learned_vs_true.py,
50 seeds x 20 reps replacing the 4-seed/single-run validation the
adversarial pass rejected): learned − true = +$71 [−$20,+$186]/seed,
p=0.47; skill shifts +0.04..0.10, all CIs straddle 0; degradation point
estimates concentrate on quality-stressed/COMPOUND seeds as predicted,
not significant. Claim is SCOPED to transition dynamics (emissions/
topology/cost mechanics stay known). Seed 12 goes negative-headroom under
the learned scale.

ORACLE-SIDE COST DECOMPOSITION — PRE-REGISTERED 2026-07-30, BEFORE ANY
ORACLE WEEKLY DATA EXISTS (analysis/oracle_cost_weeks.py + oracle_decomp.py).
Design: replay the fair oracle under the exact oracle_refs protocol (20 reps,
k=191..210, deterministic per (seed,k)), collect the engine's own per-week
cost_breakdown, average buckets over reps per (seed,week), then compare each
model's spend on ITS OWN diagnosed (seed,week) cells against the oracle's
spend on those same cells. Sanity gate: per-seed rep-mean of weekly totals
must reproduce oracle_refs.csv means (|diff| <= 0.05). Caveat disclosed up
front: week-t inventory reflects each policy's earlier decisions, so this is
"what a competent policy's books look like on the same tape weeks", not a
per-week counterfactual of a single decision.
- F3 (per model, Holm-4): holding_total $/wk on model-m's DIAG weeks,
  model minus oracle. Prediction: positive for grok + deepseek (the
  over-ordering/over-holding story becomes EXCESS, not just composition).
- F4 (per model, Holm-4): procurement $/wk on m's DIAG weeks, model minus
  oracle. Prediction: positive for grok + deepseek.
- F5 (single test): air $/wk on sonnet's DIAG weeks, sonnet minus oracle.
  Prediction: positive (the "air over-doser" claim gets its reference).
Everything else (oracle bucket table by class, per-lever means) is
descriptive. RESULTS (2026-07-30, all gates passed):
- F3 CONFIRMED for grok +$25.5 [18.0,33.5] and deepseek +$37.6 [25.9,49.7]
  (both Holm <1e-4). Sonnet came out NEGATIVE −$10.2 [−13.9,−6.4] (Holm
  <1e-4) — unpredicted sign, disclose as such. gpt n.s. (+3.2, Holm 0.27).
- F4 CONFIRMED for grok +$19.6 [8.2,31.2] (Holm .0012) and deepseek +$29.7
  [14.5,46.8] (<1e-4). gpt/sonnet n.s. (Holm 0.46 both).
- F5 CONFIRMED: sonnet air +$65.4 [49.5,83.1] (<1e-4).
- Descriptive keeper: oracle lever spend on diagnosed-stress weeks is
  $55–60/wk (nonzero!) — escalation is what a competent policy does; the
  models' defect is magnitude (sonnet levers 126 vs oracle 55) and mix.
- Never write untested cross-bucket comparisons from the descriptive table
  (e.g. CALM holding vs oracle was NOT pre-registered — descriptive only).

KDR DURATION CONFOUND — PRE-REGISTERED 2026-07-31, BEFORE ANY KDR-vs-
DURATION NUMBER EXISTS (analysis/kdr_duration.py; trigger: ladder audit
D12 — PERSISTENT tapes have far longer port blockages, mean 6.3 wk vs
0.7/3.1, so "KDR peaks on PERSISTENT" may be a duration effect, not a
profile-category effect). Data: per-seed KDR = share of diagnosed stressed
weeks (week<26, D2a rule) that stocked out, from beliefs.csv engine-truth
stockouts; duration = port_block_longest from sweep/results.csv; seeds
with zero diagnosed stressed weeks are NaN. Seed-cluster bootstrap,
N_BOOT=10_000, BOOT_SEED=20260728.
- F6 (per model, Holm-4): Spearman rank correlation across seeds between
  per-seed KDR and port_block_longest. Prediction: positive for all four
  (the duration story).
- F7 (per model, Holm-4): partial association of PERSISTENT membership
  with per-seed KDR after rank-residualizing both on port_block_longest.
  Prediction: no detectable partial association (CI straddles 0) — i.e.
  duration absorbs the group effect. NOTE: a straddling CI is reported as
  "no detectable partial effect", never as proof of zero (rule 4).
Interpretation rules fixed now: if F6 positive and F7 null -> paper
reframes the peak as "peaks on persistent stress, consistent with
blockage duration driving the rate"; if F7 positive -> categorical
framing stands with the test behind it; anything else -> report as-is,
exploratory label. RESULTS (2026-07-31, all 50 seeds have defined KDR
for every model):
- F6 CONFIRMED for 3 of 4: sonnet +0.443 [+0.163,+0.681] (Holm .0054),
  grok +0.358 [+0.099,+0.585] (.015), deepseek +0.618 [+0.397,+0.777]
  (<1e-4); gpt positive but n.s. (+0.244 [-0.046,+0.502], Holm .092).
- F7 NULL as predicted after Holm for all four (partial assoc, Holm >=
  0.086 all); gpt is the borderline (+0.333, raw p .022, Holm .086) —
  disclose, don't claim.
- Descriptive: KDR by duration tercile is monotone increasing for all
  four models (e.g. deepseek 0.061/0.085/0.290 short/mid/long).
- Per the interpretation rule fixed above: paper phrases the peak as
  "peaks on persistent stress, consistent with blockage duration
  driving the rate", not as a categorical profile effect.

Repeats ablation (priority #3) upgrades all of this from "uncertainty over
seeds" to "uncertainty over seeds AND runs" (Blackwell/Agarwal framing).

## Rules of thumb for future experiments

- Decide the headline contrasts BEFORE running (pre-registration lite: a
  list in the phase md). Everything else is labeled exploratory.
- Paired designs whenever possible: same seeds for every arm. Pairing is
  free variance reduction (Miller §; our tier CIs would be ~2× wider
  unpaired).
- One primary metric per claim; the rest are supporting.
- When a claim dies, the softened version is usually MORE damning — hunt
  for it ("can't beat a symptom-blind rule" > "below the floor").
