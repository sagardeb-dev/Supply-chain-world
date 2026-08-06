# WORKSHOP REVISION PHASE — declared 2026-07-28

The paper has entered its third phase. Read this before any paper work in
this phase; FREEZE #2 facts and standing rules in `CLAUDE.md` still bind.

## Timeline (how we got here — newest last)

- **2026-07-08..10** — drafting phase: paper.tex written, math map, §2 v3,
  Pass B to n=50, paper-check run #1.
- **2026-07-15** — FREEZE #2 declared (4 models × 50 seeds canonical,
  results.md regenerated); full story-v2 sweep executed; paper-check run #2
  (6 blockers fixed same day); name **STOCKTAKE** + final title decided;
  arXiv package built (2-author tarball at repo root, ASCII abstract
  prepared); venue scan pointed at NeurIPS workshop announcements.
- **~2026-07-23** — arXiv v1 submission in progress user-side (exact posted
  status UNVERIFIED in-session — confirm with user before claiming "posted").
  A simulated external review of STOCKTAKE received and triaged
  (`REVIEW-EXTERNAL-2026-07-23.md`). Learned-dynamics oracle built +
  validated (`LEARNED-ORACLE.md`, `backend/fit_oracle.py`). check.sh +
  cite_check both green post-everything.
- **2026-07-28** — TARGET VENUE SETTLED (below). Ground-truth calibration
  arrived: the user's OTHER paper (ACDB, active causal discovery, NeurIPS
  2026 Evals&Datasets #3531) got real reviews, meta leaning REJECT. Lessons
  absorbed into the priority list below. OpenRouter credit checked: ~$1,025
  remaining. THIS phase declared.

## Target venue (settled 2026-07-28)

**Workshop on Evaluation of Interactive Agents @ NeurIPS 2026**
(eval-interactive-agents-workshop.github.io) — first edition; Dec 12 or 13,
Atlanta. **Deadline Aug 29 AoE, notification Sep 29.** 9pp full / 4pp short,
EXCLUDING references+appendix (main text currently ~10pp → trim ~1pp).
NeurIPS 2026 LaTeX (already our style). Non-archival; explicitly welcomes
dual submission. OpenReview link "coming soon" — anonymity policy unknown
until it opens; NeurIPS allows arXiv preprints during review.
Backup/parallel: SEA @ NeurIPS (same notification date). Organizers:
Georgia Tech / Columbia / Princeton / TTIC / MSR / Google DeepMind.

Fit levers (from their CFP, leaned on 2026-07-28 discussion): grader design
incl. calibration (our 3-layer stack), trajectory-level eval of intermediate
states (belief scoring), latent-state-preserving environment, reliability
across repeated trials (our current gap), fair-oracle-as-calibrated-reference.
Do NOT chase: user simulation (we have none), causal framing (1 sentence max).

## Priority list for the revision (order matters; set 2026-07-28)

Calibrated against the ACDB rejection: (a) UQ absence "directly weakens
credibility", (b) the WHY/mechanism analysis must be IN the submission not
the rebuttal, (c) benchmark-internal jargon undefined at first use kills
readability, (d) proprietary-API-only panels draw reproducibility complaints.

1. **Uncertainty quantification** — FREE, offline, on existing CSVs. Paired
   bootstrap CIs (models share identical 49 scoreable seeds → paired design)
   + Wilcoxon signed-rank on headline contrasts. Expect: above/below-floor
   tier split survives; within-tier orderings (gpt-vs-sonnet 0.13, grok-vs-
   deepseek 0.10) may not → claims become "two tiers" where needed. Also
   report CI width = the benchmark's resolution at n=50 (spec-sheet framing).
2. **Cost decomposition** — FREE, trace-side. Excess cost on diagnosed weeks
   split into stockout vs premium-lever spend (air/lock/inspect/dual) vs
   holding, per model. Upgrades the over-response story from trace-reading
   to measurement (fixes the standing TRACE-INSIGHTS L106 scoping caveat).
3. **Repeats ablation** — ~$150-250. 3 extra runs × 4 models × 10 stratified
   seeds (2 ISO / 3 PERS / 5 COMP, include exhibit seeds, never seed 11).
   Canonical numbers stay frozen; repeats feed a NEW variance table only.
   Check first: bench.py output-dir separation so ladder-v1 is never touched.
4. **Learned-oracle paragraph** — experiment DONE (LEARNED-ORACLE.md);
   writing only. Frame as grader/reference calibration, not a new arm.
5. **Prose calibration pass** — abstract/intro readable with ZERO internal
   vocabulary (fair oracle, skill score, KDR, symptom-blind floor, group
   names all defined at first use); metric definitions in main text;
   self-contained captions; one explicit "what this enables that RetailBench/
   AIM-Bench cannot" sentence in §2. Plus the ~1pp trim to 9pp.
6. **Optional (~$50): one open-weights model row** through the same
   OpenRouter harness — answers the reproducibility complaint.

Ablation arms discussed but NOT greenlit (user: "discussion for now"):
belief-injection (oracle posterior in prompt), COACHED (--coached exists).
Design notes live in chat 2026-07-28; belief-injection = one plain-English
posterior line per week, nothing else changed.

## New related-work candidates for §2 (all API-verified 2026-07-23..28)

Must-consider: Agent-BRACE 2605.11436 (closest method neighbor — they BUILD
belief/policy decoupling, we MEASURE it; cite in revision), ABBEL 2512.20111
(belief bottlenecks in language), risk-knowledge gap 2508.13465 (Maddison
group, knowing-doing in safety). Context: SupChain-Bench 2602.07342 (SOP/
tool orchestration, clearly distinct), Pinductor 2605.13740 (LLM-prior POMDP
learning — contrast for learned oracle), BetaZero 2306.00249 + POMCPOW
1709.06196 (bridge-baseline vocabulary), EcoGym 2602.09514.
**Never cite:** "VEROIC" (does not exist — reviewer garble of 2604.27536);
InfoSeeker 2604.02971 exists but is a web-search agent (mischaracterized by
the simulated review); anything Zenodo/junk-journal tier. Everything enters
through cite_check.py.

## Standing constraints (unchanged)

Frozen arXiv v1 is untouchable; all revision numbers are ADDITIVE (new
tables/paragraphs), never edits to frozen claims. No auto-commit. Sonnet for
subagents. Numbers only from runs files. check.sh + paper-check before any
share. Exa search available (`EXA_API_KEY` in backend/.env,
category="research paper").
