# FINAL-PLAN.md — locked plan to submission (written 2026-08-05)

Target: **Evaluation of Interactive Agents @ NeurIPS 2026** (verified 2026-08-05:
deadline **Aug 29 AoE**, ≤9pp excluding refs+appendix, NeurIPS 2026 style,
**double-blind**, OpenReview live, non-archival, dual-submission OK).
Backup (same deadline, verified): "Who Verifies the Agents?" @ NeurIPS 2026.

**FREEZE RULE:** this list is the contract. Nothing gets ADDED without
dropping something of equal effort. New attack ideas after today go to a
"post-submission" list, not here. Status marks: [ ] open · [x] done ·
[USER] needs the author · [PAID] needs spend approval.

Sources: five web-grounded adversarial audits 2026-08-05 (venue, novelty,
method, stats, construct validity — full reports in PROJECT-LOG refs) +
the standing queue (DEFECTS.md, WORKSHOP-REVISION.md).

---

## Phase 0 — TODAY, unblocks everything else

- [ ] [USER] **The D13 commit.** `.gitignore` is already fixed; commit all
  ledgers (RESULTS-LOG, DEFECTS, STATS-GUIDELINES, PROJECT-LOG, TRACKER,
  runs/*.md), `backend/analysis/`, `fit_oracle.py`, `learned_trans.json`,
  modified sources, CSVs, paper.tex/pdf, `.claude/workflows`.
  *Now doubly critical:* the stats audit showed every "pre-registered"
  claim in the paper is unverifiable until these files have git history.
  Commit regularly from now on — the timestamps ARE the pre-registration.
- [ ] Claude: rerun `bench.py report` after the commit so manifest.json
  records the true code hash (repro audit: current hash is false).

## Phase 1 — free fixes (wording, citations, local analyses). Target: Aug 8–12

Prose/citation fixes (NET WORDS MUST NOT GROW — every added sentence is
paid for from the standing cut menu; page budget after this phase: ≤9.0pp):

- [ ] M1 **Rename the oracle honestly.** Replace "Bayes-optimal given the
  true model" everywhere with "certainty-equivalent rollout over a
  restricted candidate menu, computed with the true generative
  parameters"; cite Bertsekas (ADP→MPC survey) + Bozkurt et al.
  2602.02814. Resolves the internal contradiction with "fair reference
  rather than an optimum" and makes skill>1 easier to explain.
- [ ] M2a **Surface the missing-levers fact** next to the reference-policy
  paragraph: the oracle's menu excludes briefing/audit; ceiling is a
  lower bound of the full-menu rollout, most on canal-ambiguous tapes.
- [ ] M4 Cite Agarwal 2108.13264 at the normalization/uncertainty
  paragraph; re-derive the $700 headroom cutoff from oracle per-seed SEs
  (one-line recomputation) or disclose it as a round-number choice.
- [ ] M5 Scope sentence: learned-oracle test addresses only the
  true-parameters asymmetry, not menu restriction/information actions.
- [ ] N1 Cite+differentiate **MerchantBench 2607.28956** (same task shape,
  outcomes-only, no fair oracle, no belief grading) in §2 + appendix table.
- [ ] N2 Cite+differentiate **Belief at Risk 2606.15473** (their filter
  audits the LLM's own outputs; ours never sees them).
- [ ] N3 One clause acknowledging the knowing-doing naming pattern is
  spreading (KTD-Fin 2605.28359, KAPRO 2606.20661); contribution = the
  fair-reference measurement, not the name.
- [ ] C1 **Faithfulness paragraph** (deepest construct fix): cite Turpin
  2305.04388, Anthropic 2505.05410, 2511.13240, 2601.07972; reframe
  "lower bound" — stated-belief/action coupling runs both ways; lean on
  Table 5's diagnosed-week escalation (Holm <1e-4) as the empirical
  evidence the two aren't decoupled here; keep "co-occurrence ≠ cause".
- [ ] C2a Report second-grader agreement **stratified by generator model**
  (re-slice of existing audit data); put the 43% exact-set figure beside
  the 89% metric-relevant figure in the main text; one sentence on audit
  staleness (20-seed core only).
- [ ] C3 One-sentence disclosure: seed curation filters on headroom, which
  inflates the skill spread relative to an unfiltered seed distribution.
- [ ] C4 Narrow the contamination sentence: specific tapes can't be in
  training data; no claim about genre-level familiarity.
- [ ] C5a Limitations sentence + POSIX 2410.02185 citation: the two-tier
  ranking is untested against prompt paraphrase; single spare prompt is
  the high-sensitivity regime.
- [ ] C6 One sentence: "diagnose/know" = the grader's textual-detection
  label (Appendix B); no internal-representation claim.
- [ ] S2a Cite Blackwell 2410.03492 in the single-run disclosure.
- [ ] S6 Name the five Holm families explicitly as fixed-by-design.
- [ ] V3 One sentence: "interactive" here = sustained agent-environment
  interaction, not human-in-the-loop.
- [ ] V4 Short LLM-assistance disclosure sentence (no rule requires it;
  costs nothing; strictest-venue practice).

Local analyses (no API cost, all on existing data):

- [ ] S3 **Resolvability ratio q** (Kotawala 2605.30315) for the reported
  contrasts from existing bootstrap draws; expect cross-tier q≫1,
  within-tier q<1 — strengthens "tiers, not neighbors"; cite.
- [ ] S4 **F7 robustness**: conditional-permutation test (Berrett et al.
  1807.05405) or proper partial-Spearman beside the rank-residual
  version; footnote if it agrees (pre-register expectation: agrees).
- [ ] S5 **BCa vs percentile** intervals on uq/oracle_decomp/kdr_duration;
  one sentence if they agree within rounding.
- [ ] M3 **Floor lead-time robustness**: recompute the base-stock floor
  with the stochastic-lead-time safety-stock formula (σ_L from engine
  replay), report how C_base and mean skill move. Metric definition
  stays frozen — this is a robustness number + disclosure, not a
  redefinition. (Highest-yield single analysis in the plan: it tests
  the denominator of the headline metric.)
- [ ] M2b **Oracle full-menu check**: add briefing/audit to
  `build_candidates()`, rerun the 20-rep reference on the canal-stressed
  seeds, report the delta. Local compute, ~half-day. Turns attack M2
  into a robustness result.
- [ ] Page budget: land ≤9.0pp using the standing cut menu (trace
  narrative→appendix ~0.25pp, §5 CI-repeat trims ~0.15pp, §2 causal
  paragraph ~0.15pp, uncertainty wording ~0.1pp, abstract ~0.05pp),
  offsetting Phase-1 additions.

## Phase 2 — paid / decision items. [USER] decides by ~Aug 15

- [ ] [PAID ~$3–5] **D6 re-grade, non-OpenAI grader** (e.g. a Gemini or
  Grok grader): closes the silent-failure bound AND the same-family
  judge bias (construct attack C2) in one shot. Recommended: YES.
- [ ] [PAID ~$150–250] **Repeats ablation** (3 reps, Blackwell design):
  the only reviewer demand that needs new model runs; upgrades every
  claim from seeds-only to seeds+runs uncertainty. Recommended: YES if
  budget allows; the disclosure is honest either way.
- [ ] [PAID ~$15–30] C5b optional: paraphrased-FAITHFUL rerun on 5–10
  seeds × 2 below-floor models — tests the two-tier ranking against
  prompt wording. Recommended: yes if repeats are approved (same
  pipeline), else skip and keep the disclosure.
- [ ] [USER] arXiv v2 decision (frozen v1 carries pre-correction Tables
  3/4 + the old "Bayes-optimal" framing after M1). Recommend v2 shortly
  after submission.
- [ ] Skip (post-submission list): open-weights/SLM row ($50), uncurated
  seed-sample robustness (needs new runs), belief-elicitation arm (D8),
  human baseline.

## Phase 3 — submission week (Aug 22–29)

- [ ] Bib swap: every \todocite → verified \citep (verify each on arXiv:
  title/authors/venue), including all Phase-1 additions.
- [ ] Gemini stray row cleanup (or keep + one manifest note).
- [ ] Run the **paper-check workflow** (7-verifier chain-of-evidence gate)
  on the near-final draft; fix blockers; rerun until clean.
- [ ] WRITING.md pre-submission checklist (page limit, anonymization, every
  number traced, greplist, limitations, fairness sentence, Fig 1
  standalone, disclosure).
- [ ] Anonymized copy: drop `[preprint]` style option; grep for author
  names/links; verify PDF shows no identity.
- [ ] Final: check.sh + fresh build + submit on OpenReview
  (NeurIPS.cc/2026/Workshop/IAEval) ≥24h before the AoE deadline.

---

## What we are NOT doing (decided 2026-08-05, don't relitigate)

- No metric redefinition (floor formula, skill score, detection rule) —
  frozen; robustness checks + disclosure only.
- No seed reclassification (D10 fixed by wording; labels reproduced by
  classify_seeds.py).
- No new prompt arms, domains, SKUs, or models before submission.
- No chasing further attack surfaces: five web audits + three repo audits
  are the evidence base; the paper's job now is to absorb them.
