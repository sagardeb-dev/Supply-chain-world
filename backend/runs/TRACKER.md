# Benchmark final-pass tracker (started 2026-07-07, paper draft due Fri 2026-07-10)

Working log so no session loses the thread. FAITHFUL arm only. Update in place.

**AIR-STOCKOUT CORRECTION 2026-07-30 (belief side only):** grade_beliefs.py's
trace-derived stockout flag (`inv + arrived < demand`) omits air-expedited
arrivals — 343 air-saved weeks miscounted as stockouts (100% air-linked,
verified vs engine replay in cost_weeks.csv). beliefs.csv stockout column
regraded from engine truth; belief_metrics.csv / report.md / results.md
regenerated (backups *.pre-airfix). Detection + lag byte-identical; all KDRs
roughly halve; persistent-peak now significant 2/4, confound 3/4 (uq.md).
Skill-side files untouched. Full details: research/results.md Table-3 block
+ research/STATS-GUIDELINES.md.
SAME DAY, D2 FIXES: week-26 stress rows (no rationale exists) excluded from
diag/undiag pools everywhere; 17 onset-week-26 episodes excluded from the
detection denominator (undetectable by construction; new n_undetectable
column in belief_metrics.csv). Detection is now 89–94% of 266 detectable
episodes; confound significant for all four models again (uq.md). KDR
unchanged. Full defect ledger: research/DEFECTS.md.

**NUMBERS FROZEN 2026-07-09:** belief grading complete + independently verified (126 cells);
research/results.md regenerated at n=50 (Tables 1-4 incl. new severity-confound check) via
`runs/results_tables.py`; report.md/manifest.json regenerated; deepseek belief metrics filtered
to core-20 (6 pre-rationale traces had no rationale text — excluded). Paper session may transcribe.

**CORRECTION + UNFREEZE IN FLIGHT 2026-07-10:** the "6 pre-rationale traces" claim above was
wrong about the FILES — the traces on disk for deepseek seeds 53/119/135/160/178/189 (and
72/74/82/91) are valid 2026-07-08 re-runs WITH all 26 rationales, on the same commit (7112e72)
as the core-20. What was pre-rationale was the stale beliefs.csv rows: the grader graded the
OLD overwritten files and its resume skipped the re-runs. Fixed: those 156 stale rows deleted
(backup beliefs.csv.bak), deepseek flipped to full-50 in bench_config.py. NOW RUNNING (detached):
grok seeds 178/187/189/194/198 + deepseek's 20 missing seeds, then re-grade (10 deepseek seeds
need grading: the 6 above + 72/74/82/91 + the 20 new... i.e. 30 total) → score → report →
results.md regen → freeze #2. Numbers in results.md are the n=50/3-model freeze until then.

**FREEZE #2 DECLARED 2026-07-15:** the 2026-07-10 correction pipeline completed 2026-07-11
(report.md/manifest.json/skill_scores.csv/belief_metrics.csv regenerated at four models x 50
seeds, commit 932ce7a; gemini dropped after 1-seed smoke, binding). research/results.md
regenerated 2026-07-15 via runs/results_tables.py — Tables 1-4 four-model, episode-pooled
convention settled as canonical (per-seed means agree within 0.03). Trace audit
(research/TRACE-INSIGHTS-2026-07-10.md, adversarially verified) bound into results.md as
interpretation constraints: KDR is one channel (under-response) of a two-faced gap; the old
gpt/sonnet rank-swap claim is dead (real shape 3-vs-1, sonnet the COMPOUND outlier).
Paper session may transcribe. Paper itself NOT yet rewritten — awaiting author go signal.

## Decisions (frozen)
- **Seeds: 20, frozen 2026-07-07.** Groups by stress profile (not EASY/MED/HARD):
  - ISOLATED (isolated shocks, 6): 157, 25, 112, 60, 24, 86
  - PERSISTENT (long port congestion x demand regime, 7): 1, 172, 170, 95, 29, 58, 108
  - COMPOUND (3-factor pileups, 7): 21, 143, 99, 44, 94, 154, 85
- **Models (3):** anthropic/claude-sonnet-5, openai/gpt-5.4 (traces done), deepseek/deepseek-v4-pro (running).
- **Oracle refs:** 20-rep means, in runs/ladder-v1/skill.md (2026-07-07). basestock from sweep/results.csv.
- **Metrics:** (1) skill score; (2) detection lag = first week factor named in rationale minus episode start, per stress episode; (3) knowing-doing rate = fraction of stress-weeks where the agent named the true active factor yet still incurred stockout cost that week (tape-checkable, no oracle needed).
- **Framing:** measuring the "knowing-doing gap" (adopt lit vocabulary), fair Bayes-filter oracle on identical observations = differentiator vs RetailBench (privileged oracle). No clairvoyant ceiling; oracle framed as fair baseline, skill>1 possible.
- **Dropped for paper (= the 3 later ablation arms + extras):** (1) COACHED playbook arm, (2) STRUCTURED-BELIEF arm (forced weekly belief JSON), (3) QUANTITATIVE-DISCLOSURE arm; plus clairvoyant ceiling, multi-SKU, warm-start rollout history, 50-seed expansion (deepseek full grid + flagship stratified subset).

## Status
- [x] Oracle k-instability fixed (20-rep means, se 0.3-1.6%) -> skill.md rewritten
- [x] Seed dossier (true regime timelines) -> in conversation + skill.md context
- [x] Related-work survey -> memory: related-work-hypotheses.md
- [x] Manifest re-badged to ISOLATED/PERSISTENT/COMPOUND
- [x] deepseek-v4-pro 9 runs DONE 2026-07-07, all 26wk, traces in ladder-v1
- [ ] Belief grader built + tested (subagent) -> runs/grade_beliefs.py, outputs runs/ladder-v1/beliefs.csv + metrics
- [x] deepseek skill scores in skill.md (ISOLATED -0.50, PERSISTENT -0.93, COMPOUND 0.96; seed 99 outlier 1.85 needs trace read)
- [ ] Detection-lag + knowing-doing tables computed for all 3 models
- [ ] Paper draft (Wed-Fri)

## Notes
- Launch cmd: uv run python -m src.agent.play_agent --seed N --model deepseek/deepseek-v4-pro --rich --exp ladder-v1
- Grader model: cheap (haiku/gpt-mini class) via same OpenRouter key; grader sees ONLY the rationale text + factor vocabulary, outputs JSON factors-named per week.
- Ground truth for grading: replay tape via filters._true_regime (see sweep/run_sweep.py pattern).
- User commits himself. Leave everything uncommitted.

## 20-seed expansion (2026-07-07, evening)
- 11 new seeds picked from sweep pool by group + headroom>800: ISOLATED 60/24/86, PERSISTENT 95/29/58/108, COMPOUND 44/94/154/85.
- [ ] oracle 20-rep means for new 11 (running, scratchpad/oracle-reps-new11.txt) -> merge into skill.md
- [x] deepseek runs on new 11 DONE (58 died wk13 once, rerun clean; all 20 deepseek traces valid; skill.md updated)
- [x] sonnet-5 + gpt-5.4 runs on new 11 DONE (all 22 clean; ~$14 total thanks to caching); ALL 60 BENCHMARK RUNS COMPLETE
- [ ] grader over all new traces (deepseek 20 + flagship 11x2) after runs land
- Original 9 seeds unchanged; existing traces stay valid.

## Break-the-paper audit (2026-07-07 night)
- [x] skill denominators all positive (min gap $723, seed 86 — footnote)
- [x] deepseek traces free of harness/parse errors (scores are real decisions)
- [x] oracle fairness audit: FAIR-WITH-CAVEATS — no state/RNG leak, obs byte-identical to LLM prompt; disclose filters use true model params (framing in research/CLAUDE.md)
- [x] grader agreement: haiku-4.5 on 100 wks — 43% exact, 89% on label∩truth (metric-relevant); grader_agreement.csv
- [x] 30-row stratified manual read done by Fable (HIT 10/10, MISS 9/10, calm ~50% over-labeled but metric-excluded)
- Disclosed not fixed: single run per (model,seed) cell — limitations sentence; optional $5 repeat-spread check.

## Session close 2026-07-08 (grader final + deliverables)
- [x] grader v3: incremental+resume+detached; 1560 weeks graded; PARSER BUG found+fixed (rationale was attached to week+1; labels shifted to same-week alignment, no regrade needed)
- [x] label audit round 2: previous failure cases fixed; residual = borderline over-labels on calm weeks (metrics unaffected)
- [x] pooled metrics computed; skill.md deepseek PERSISTENT mean corrected (−1.05, was hand-summed −0.76)
- [x] research/results.md written (3 tables + provenance + open items)
- [x] research/README.md written (WRITING.md-compliant, greplist clean)
- Remaining for user: human spot-check of grader labels; read deepseek seed-99 trace before citing it; commit everything.

## Post-preprint roadmap (priority order, decided 2026-07-08)
1. Learned-model oracle: estimate world params from held-out TRAINING seeds
   (never the benchmark 20 — same-seed passes would memorize the tape and
   become clairvoyant), then run the filter-oracle with learned params.
   Gives ladder: learned-model <= true-model oracle <= clairvoyant. Answers
   the fairness caveat; strongest archival addition.
2. Repeat runs (3x on contrast cells) to quantify provider nondeterminism.
3. 50-seed extension (~$60-70 all models at observed run costs).
4. Ablation arms: COACHED, STRUCTURED-BELIEF, QUANTITATIVE-DISCLOSURE.
5. Clairvoyant ceiling; warm-start episodes; other trap mechanisms in pool.
6. Package as a real benchmark (user, 2026-07-09): DONE 2026-07-09. `backend/bench.py`
   (run|oracle|score|grade|report|all) + `bench_config.py` (single source for GROUPS/CORE20/MODELS)
   + `test_bench.py` (7 tests). Verified: regenerated skill_scores.csv BYTE-IDENTICAL to the
   scratchpad score_all.py output; oracle seed-157 refs reproduced bit-for-bit (run_oracle is
   deterministic per (seed,k), reps = k in range(191,211)). Scratchpad one-offs retired
   (score_all.py, oracle_refs_30.py, launch_*.sh, grade_new.sh); their oracle-reps files merged
   into runs/ladder-v1/oracle_refs.csv (50 seeds). .gitignore now tracks runs/ pipeline code +
   TRACKER + ladder-v1 CSVs/manifest/report (traces still ignored — user decision whether to ship).
   manifest.json is now GENERATED by `bench.py report`; runs/ladder-v1/report.md is the
   script-computed numbers table. Known limits: grade_beliefs.py hardcodes ladder-v1;
   trace-cost regex pinned by a real-trace test.
7. Solver-decomposition half-version (~1 day): replay traces for exact weekly inv/pipeline ->
   policy head at agent's state -> per-week prescribed vs actual order on diagnosed weeks.

## 50-seed expansion (launched 2026-07-08, overnight)
- 30 new seeds (headroom>=500, relaxed PERSISTENT threshold port>=4 & dem>=4):
  ISOLATED +6: 160 91 178 11 189 36 | PERSISTENT +8: 198 135 194 119 169 145 53 74 | COMPOUND +16: 72 82 90 9 148 168 163 0 14 187 100 33 12 75 164 39
  -> 50 total: 12 ISOLATED / 15 PERSISTENT / 23 COMPOUND
- [x] 60 flagship runs DONE 2026-07-09 14:25, all 60 valid (26wk+EPISODE DONE), zero failures
- [x] oracle 20-rep refs for the 30 DONE -> merged into runs/ladder-v1/skill_scores.csv
- [x] skill recomputed for ALL cells, script-only: runs/ladder-v1/skill_scores.csv is CANONICAL
  (found: old deepseek ISOLATED median wrong in results.md, −0.12 not 0.33; hand-summing strikes again)
- SEED 11 UNSCOREABLE for skill: 20-rep oracle mean > basestock (negative headroom −218; selected on
  stale single-run oracle value). Excluded from skill means (n=49 flagships); kept for belief metrics.
  Thin headroom flagged: 36 (584), 160 (583), 164 (488).
- n=49 group means: sonnet ALL +0.49 (COMPOUND +0.33, 7 neg); gpt ALL +0.62 (COMPOUND +0.86, ISOLATED
  +0.21); story shift vs n=20: sonnet's COMPOUND edge shrank, gpt's grew; ISOLATED noisier (thin headroom).
- [x] deepseek seed-99 trace READ (2026-07-09): 1.85 skill is NOT reproducible skill. Got mauled in the
  early compound crisis like everyone (cum $5024 by wk11, 6 straight air-expedites, stockouts wks 7-10),
  then its habitual passivity fit the seed's calm cheap-freight middle, and it STOPPED ordering wk22+ so
  the late blockage (wks 24-26) found it with no exposed pipeline. References are expensive on this seed
  (bs 9638, oracle 8354) because policies that keep serving pay crisis logistics. Verdict: end-of-horizon
  abandonment + reference-cost quirk, not insight. Cite with this caveat or exclude from prose.
- Trace-read finding (seeds 39/168/94, both flagships, full read): models run different STANDING POLICIES.
  gpt = forward-buy/batch when freight cheap, coast through spikes, hard endgame stop (wins on persistent
  freight/blockage regimes -> new-16 COMPOUND +0.88 vs sonnet +0.22; loses when shocks pierce coast windows,
  e.g. seed 94: 9 air-expedites, 0.14). sonnet = JIT drip 15-30/wk + hedging instruments (locks, Cape,
  briefings), never banks cheap stock, buys INTO expensive regimes (seed 39: bad freight lock at top,
  7 airs, -0.15; seed 168: drip into permanent wk8+ blockage, -0.01). Within-model across-seed spread
  (~3 skill units) >> between-model same-seed gap: policy x seed-regime fit dominates model quality.
- [ ] grading new 60 traces (detached, scratchpad/grade_new.log; resume-aware) -> then pooled belief metrics
- [ ] after grading: KDR confound check (above), regenerate research/results.md (n noted per cell)
- [x] CITATION check (2026-07-09, arXiv API direct): 2605.00226 VERIFIED REAL = "Why Do LLMs Struggle in
  Strategic Play? Broken Links Between Observations, Beliefs, and Actions" (a websearch subagent had
  flagged it unverifiable — API lookup beats websearch for ID checks). Also verified real: AIM-Bench
  2508.11416, RetailBench 2606.15862, Vending-Bench 2502.15840, knowing-doing origin = "LLMs are Greedy
  Agents" 2504.16078 (bandit; correct rationale 87% but greedy action ~64% — cite as term origin).
- [x] Lit survey DONE (2026-07-09, workflow wf_8dcffa48-60a) -> research/related-work-survey.md.
  225 candidates / 14 deep-read; verdict: NO paper combines (long-horizon hidden-regime inventory task
  + information-matched Bayes-filter oracle + belief-vs-action gap). Closest per axis: RetailBench
  (hidden state, but PRIVILEGED oracle, own words), 1206.6283 (Bayes-filter inventory POMDP, pre-LLM),
  2606.00476 (uses "knowing-doing gap" literally, but poker CoT-faithfulness). Watch: Agent-BRACE
  2605.11436 (belief/action decoupling, TextWorld) and BayesBench 2606.30850 (belief trajectories,
  no actions) are the nearest neighbors to our belief metrics.
  !! TWO RetailBench arXiv IDs exist: 2603.16453 (Strategy Stability; deep-read, "privileged oracle"
  quotes from here) and 2606.15862 (coherent decision making; the one previously in TRACKER). Verify
  which version each quote/claim comes from before citing in paper.tex.
- Paper plan for seed ambiguity (decided 2026-07-09): (1) inclusion rule stated as metric property —
  skill undefined when 20-rep oracle headroom <= 0 (excludes seed 11; kept for belief metrics);
  (2) report headroom distribution + flag thin seeds (36/160/164); (3) robustness check on ALL 50 seeds
  via denominator-free metric: % cost vs basestock; (4) medians alongside means (robust to thin
  denominators); (5) disclose PERSISTENT oversampling vs pool prevalence.
- Policy-style finding: to harden from anecdote -> evidence, compute per-model order-behavior stats over
  all 50 seeds from traces (no API cost): order frequency, mean order size, corr(order qty, freight
  index), air-expedite count, endgame order stop week. Backs "batch-vs-drip" claim quantitatively.
  Variance framing: cite reliability-science precedent (2603.29231, ICC 2512.06710) — within-model
  across-seed spread as first-class finding, not apology.
- Solver-decomposition metric (user idea 2026-07-09, from previous paper): solver(true belief) vs
  solver(agent's belief) vs agent action. Policy head exists (oracle_policy.build_candidates+simulate
  takes any belief + inv/pipeline). BLOCKED for existing runs: agent belief only exists as prose;
  grader labels are categorical, not a posterior. (a) Full version = STRUCTURED-BELIEF arm with
  belief-JSON schema matching filter state space — post-preprint, new runs, note elicitation may
  itself change behavior. (b) Half version, computable NOW from existing traces (CPU only): tape is
  action-independent so filter belief stream is fixed -> run policy head at agent's actual
  inv/pipeline each week = per-week prescribed action; deviation on correctly-diagnosed weeks =
  action-level KDR (upgrades "knew and stocked out" to "knew, prescription was 65, ordered 20").
  For Friday paper: cite (a) in future work only.
- [ ] KDR confound check (strengthens Table 3, no new API calls): compare stockout rate on diagnosed vs UNdiagnosed stress weeks within each group. If diagnosed ~ undiagnosed, that's the cleaner knowing-doing statement; if diagnosed << undiagnosed, current KDR overstates the gap (PERSISTENT peak may just be base-rate hardness). Data: beliefs.csv (labels) + traces (stockout weeks).
- Budget: ~$60 expected vs $71 key remaining; launcher resumes cleanly after top-up if short.
- NOTE for results: new seeds relax headroom to >=500 (was 800) — check thin denominators (<700) before including in skill means.
- 2026-07-08 late: deepseek DROPPED from 30-seed expansion (provider flaky, ~40% mid-episode deaths; user call) -> deepseek stays n=20 core, flagships n=50; partial deepseek traces deleted; sweep relaunched sonnet+gpt only.
