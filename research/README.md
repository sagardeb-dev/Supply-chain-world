# Measuring the knowing-doing gap in LLM agents

This project asks a narrow question about LLM agents in sequential decision
problems: when an agent correctly identifies a hidden problem, does its policy
respond correctly? We find that it often does not, and we built the instrument
that turns that observation into a number.

## The task

An LLM plays the weekly replenishment manager for an electronics importer over
a 26-week episode. Each week it reads a business dashboard (inventory, orders
in transit, realized demand, freight quotes, port wait times, quality reports),
writes a short rationale, and commits an order — quantity, shipping route, and
optionally a mitigation lever such as locking a freight rate, expediting by
air, inspecting a batch, or switching supplier. Costs accrue for holding stock,
missing demand, and using levers. The episode score is total cost.

The environment is a partially observable Markov decision process with six
hidden factors — demand regime, supplier health, freight market, port
congestion, quality drift, and canal disruption — each a hidden state machine
that emits noisy symptoms. The agent never observes a factor's state directly.
Episodes are generated from seeds; the event tape is independent of the
agent's actions, so any two policies on the same seed face identical worlds.

Twenty frozen seeds form the benchmark, selected from a 200-seed pool by their
true stress profile and split into three groups: ISOLATED (six seeds, one
short-lived shock at a time), PERSISTENT (seven seeds, a multi-week port
blockage overlapping a demand rise — the configuration where the intuitive
response, freezing orders, is the wrong one), and COMPOUND (seven seeds,
multi-factor pileups).

## The measurement

Every run is scored between two reference policies on the same seed:

- **Floor:** a base-stock policy that ignores all signals.
- **Fair oracle:** per-factor Bayesian particle filters plus forward rollouts
  over a candidate action menu. It reads the byte-identical observation
  dictionary that is serialized into the LLM's prompt, and its randomness is
  independent of the world's. It knows the environment's generative parameters
  (transition probabilities, regime means), which the LLM receives only as a
  qualitative description; we report it as Bayes-optimal given the true model,
  a fair upper reference rather than a ceiling. Its reference value per seed
  is the mean of 20 independent replications (standard error 0.3–1.6%).

Three metrics per run:

1. **Skill** — the fraction of the floor-to-oracle cost gap the agent closed.
2. **Detection lag** — weeks from the true onset of a factor episode to the
   factor first appearing in the agent's stated rationale (graded by a small
   LLM against the fixed factor vocabulary; labels audited against traces).
3. **Knowing-doing rate** — among weeks where the stated rationale correctly
   named a currently stressed factor, the fraction that still ended in a
   stockout.

"Knowing" here means stated belief in the rationale text. That is a lower
bound on internal knowledge, and we treat it as such.

## What we found

Across sonnet-5, gpt-5.4, and deepseek-v4-pro (60 episodes), detection is
nearly uniform: 85–92% of the 114 hidden-factor episodes are named within
about a week of onset, by every model. Costs are not uniform: deepseek scores
below the no-signal floor on 9 of 20 seeds, and every model's knowing-doing
rate roughly doubles on PERSISTENT seeds (0.41–0.49) relative to ISOLATED seeds.
The gap between seeing a problem and acting on it, not the seeing, is what
separates models — and it widens exactly where the world punishes the
intuitive response. Trace excerpts in `case-studies.md` show the mechanism:
one model freezes orders while narrating the blockage that will starve it;
another buys its way into fees against a two-week disruption it had itself
called short.

## Files

- `draft.md`, `paper.tex` — the paper (workshop preprint, non-archival target).
- `results.md` — final tables, with provenance for every number.
- `case-studies.md` — verified trace excerpts and per-seed event timelines.
- `WRITING.md` — prose rules for this directory.
- `CLAUDE.md` — ground rules for AI-assisted work here, including the
  verify-against-traces requirement.

Code, traces, references: `../backend` (world engine under `src/world/`, agent
harness under `src/agent/`, all runs and scored references under
`runs/ladder-v1/`, working log in `runs/TRACKER.md`).

## Reproducing

From `../backend`: a run is
`uv run python -m src.agent.play_agent --seed N --model <slug> --rich --exp ladder-v1`;
oracle references are the mean of `run_oracle(seed, k)` for k in 191..210
(`oracle_policy.py`); belief grading is `uv run python runs/grade_beliefs.py`
(incremental, resumable). The world is procedurally generated from seeds, so
no episode can appear in any model's training data; seeds are published.

## Status and roadmap

Complete: 60 runs, three-tier references, belief grading, fairness audit of
the oracle. Pending: human audit of a grader-label sample; the deepseek
seed-99 trace. Planned next: repeat runs to quantify provider nondeterminism,
prompt-arm ablations (coached playbook, forced belief statement), a
clairvoyant ceiling, warm-start episodes, and a 50-seed extension.
