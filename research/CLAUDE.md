# research/ — workshop paper for the supply-chain POMDP benchmark

The paper is `paper.tex`. Code and data live in
`../backend`. PHASE (2026-07-28): workshop revision — read `WORKSHOP-REVISION.md`
first (target: Eval of Interactive Agents @ NeurIPS 2026, deadline Aug 29 AoE).
arXiv v1 (frozen) preceded it; frozen claims are untouchable, revision is additive.

## What the paper claims
LLM agents run a 26-week inventory-replenishment POMDP with six hidden failure
factors (demand, supplier, freight, port, quality, canal disruption). They are
scored between a base-stock floor and a **fair Bayes-filter oracle** — exact
per-factor HMM forward filters (NOT a particle filter; verified against
filters.py 2026-07-09) driving a rollout policy that sees the *same
observations* as the LLM (not privileged).
Finding (FOUR models n=50, FREEZE #2 2026-07-15): detection is flat 84–88%
across a skill spread of +0.62 (gpt-5.4) to −0.23 (deepseek-v4-pro); two of
four models (deepseek, grok-4.5) end BELOW the symptom-blind base-stock
floor while naming factors slightly FASTER. The **knowing-doing rate peaks
on PERSISTENT stress for all four models**, but overall KDR RANK-INVERTS
with skill — the gap has **two faces**: under-response (stockout despite
diagnosis = KDR) and over-response (premium-lever overspend/hoarding,
invisible to a stockout-based rate; how grok/deepseek buy low KDR). Present
KDR as one channel, always beside the severity confound (Table 4). Group
shape is **3-vs-1**: gpt/deepseek/grok comparatively best on COMPOUND,
sonnet the exception (worst there). DEAD claims — never reintroduce: the
gpt/sonnet rank-swap ("Sonnet the reverse"), "sonnet best on ISOLATED",
anything on the TRACE-INSIGHTS §5 refuted list, and ALL core-20 deepseek
numbers. "Knowing-doing gap" is the established term; don't rebrand it.
Novelty = the measurement, not the gap: a computable fair oracle + a
controlled stress-profile seed axis.

## Ground truth for all numbers
- **`RESULTS-LOG.md` first**: the temporal ledger of every result — which
  file is canonical for which claim, and which older numbers are SUPERSEDED.
  Every new experiment/correction/regeneration gets an entry the day it
  lands; a paper number may only be transcribed from the source its
  claim-map row names.
- Skill scores + oracle references: `../backend/runs/ladder-v1/skill_scores.csv`
  and `oracle_refs.csv`; script-built tables in `../backend/runs/ladder-v1/report.md`
  (`bench.py report`). `skill.md` is the stale n=20-era narrative — do not use.
- `research/results.md` is canonical only when the freeze-signal line in the
  memory file `paper-workstream-status.md` says so (it goes stale each time a
  new model's rows land, then is regenerated and re-frozen).
- Run inventory, seed groups, decisions log: `../backend/runs/TRACKER.md`
- Experiment manifest: `../backend/runs/ladder-v1/manifest.json`
- Belief metrics (detection lag, knowing-doing rate): `../backend/runs/ladder-v1/belief_metrics.csv` (grader output)
- Never recompute or invent numbers — read them from these files. If a number
  is missing, mark [PENDING], don't estimate.

## Key facts writers get wrong
- skill = (basestock − llm) / (basestock − oracle). skill > 1 is legitimate
  (oracle is fair, not optimal) — happened on seeds 143 and 99.
- Seed groups are ISOLATED / PERSISTENT / COMPOUND (stress profiles), not
  easy/medium/hard.
- Only the FAITHFUL prompt arm is in the paper (rules only, no playbook).
  COACHED and belief-JSON arms are future work.
- Detection is measured from the agent's per-week `rationale` text — this is
  *stated* belief, a lower bound on knowing; say so in limitations.
- Oracle reference = mean of 20 replications; single oracle runs swing ~10%.
- Related-work positioning IS settled (§2 v3, 2026-07-09): funnel shape,
  4-row descriptive comparison table, every claim verified by agents reading
  the actual papers (survey file `archive/related-work-survey.md` is leads-only and
  contains known errors — see memory file). Remaining related-work task is
  the bib swap: replace red \todocite placeholders with verified \citep.

## Style
- **Read `STATS-GUIDELINES.md` before writing any results claim** — stats gate
  before prose; comparison verbs need a CI + test first (uq.py output).
- **Read `WRITING.md` before drafting or editing any paper prose** — craft rules,
  benchmark-paper rejection map, AI-writing hard rules (citation/number
  verification, slop greplist, disclosure), pre-submission checklist.
- Plain English; the author vibecodes — define terms on first use.
- No auto-commit; the user commits himself.
- Build: `tectonic paper.tex` (installed at ~/.local/bin).
- After any paper/figure change: run `./check.sh` (free deterministic gate),
  rebuild, and send the PDF to the user (SendUserFile) so they can preview it.
- Before sharing/submitting a draft: run the `paper-check` workflow
  (.claude/workflows/paper-check.js) — 5 sonnet verifiers (numbers, trace
  quotes, citations, story-consistency, prose). Evolve that script as the
  paper grows.

## Verify against traces, not just mds
Before quoting or citing any trace excerpt, number, or claim from these md
files (including archived mds and this file), open the actual trace under
`../backend/runs/ladder-v1/<model>/seedN-rich.chat.txt` and confirm it — grep
for the quoted text, recount the weeks, recompute the cost from the `cum $`
lines. The mds are summaries written mid-work and can drift or contain
transcription errors; the traces are ground truth. Same for metrics: spot-check
a few rows of beliefs.csv / belief_metrics.csv against the raw trace before
putting them in a table.

## Oracle fairness (audited 2026-07-07, adversarial read-only pass)
Verdict FAIR-WITH-CAVEATS. Safe to claim: oracle never reads hidden state
(engine.py asserts hidden keys out of obs), never shares randomness with the
world, rolls out from filter beliefs, and reads the byte-identical obs dict
that is JSON-pasted into the LLM prompt (service.py svc_observation).
MUST DISCLOSE: the oracle's filters use the true generative-model parameters
(transition probs, regime means — e.g. FREIGHT_MEANS, DEMAND_MEANS, onset/
persist probs in filters.py); the LLM sees only a qualitative world
description. Frame as "Bayes-optimal given the true generative model" —
knows-the-physics, not peeks-at-state.
UPDATE 2026-07-23: the knows-the-physics caveat now has an empirical answer —
the learned-dynamics oracle (`LEARNED-ORACLE.md`, backend/fit_oracle.py)
refits all transition probabilities from 200 passive observation tapes and
matches the true oracle's cost within MC noise. Cite that file, not memory,
for the numbers.
