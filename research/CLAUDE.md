# research/ — workshop paper for the supply-chain POMDP benchmark

Paper draft lives here (`draft.md`, later `paper.tex`). Code and data live in
`../backend`. Deadline: draft by Fri 2026-07-10.

## What the paper claims
LLM agents run a 26-week inventory-replenishment POMDP with six hidden failure
factors (demand, supplier, freight, port, quality, canal disruption). They are
scored between a base-stock floor and a **fair Bayes-filter oracle** — a particle-
filter policy that sees the *same observations* as the LLM (not privileged).
Finding: models detect hidden failures fine; their **policies collapse when
failures compound** — the "knowing-doing gap" (use that term; it's established
in the literature, don't rebrand it). Novelty = the measurement, not the gap:
a computable fair oracle + a controlled compound-stress seed axis.

## Ground truth for all numbers
- Skill scores + oracle references (20-rep means): `../backend/runs/ladder-v1/skill.md`
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
- Related-work positioning is settled: see memory file
  `related-work-hypotheses.md` (2026-07-07 update) — nearest neighbor is
  "Broken Links" (arXiv 2605.00226); RetailBench's oracle is privileged, ours
  isn't; AIM-Bench is about decision biases, no hidden regimes.

## Style
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
files (including case-studies.md and this file), open the actual trace under
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
