# 1. Introduction (working draft v3, 2026-07-07 — findings slot filled from final results)

*¶6 numbers are from `results.md` (script-computed, 60 episodes). Citations are
placeholders in [brackets].*

---

**¶1 — Context.** LLM agents are increasingly evaluated on long-horizon decision
tasks — running a vending machine for months [Vending-Bench, 2502.15840], managing
a retail store [RetailBench, 2606.15862], operating supply chains [AIM-Bench,
2508.11416; InvAgent, 2407.11384]. These tasks share a structure: the world has
hidden state (a demand shift, a failing supplier) that the agent can only infer
from noisy symptoms, and profit depends on acting on those inferences week after
week. Benchmarks in this genre consistently report that agent performance degrades
over long horizons. What they largely cannot report is *why*.

**¶2 — Problem.** When an agent loses money on such a task, there are two distinct
failure modes. It may have failed to *infer* the hidden state — never realized
demand had shifted. Or it may have inferred correctly and failed to *act* — stated
the right diagnosis in its reasoning and still placed the wrong order. The second
failure mode is documented across strategic games, tool use, and agentic tasks
under the name of the **knowing-doing gap** [Broken Links, 2605.00226; 2605.14038;
2511.13240; 2504.16078]: models' stated beliefs are often correct while their
actions lag or contradict them. Distinguishing these two modes matters practically
— they call for entirely different fixes (better inference scaffolding vs. better
policy elicitation) — but requires knowing what a correct inference *was worth*.

**¶3 — Gap.** Existing evidence for the knowing-doing gap is either qualitative —
manual trace inspection and post-hoc labeling [2605.00226] — or quantified against
a reference policy that sees privileged information: RetailBench's oracle, for
instance, is computed with access to ground truth the agent never observes
[2606.15862]. A privileged oracle conflates the two failure modes by construction:
the shortfall it measures bundles "didn't know" and "knew but didn't act" into one
number. To attribute cost to the knowing-doing gap specifically, the reference
policy must be denied exactly the same information the agent is denied.

**¶4 — Approach.** We build a benchmark where that fair reference is computable.
The task is a 26-week inventory-replenishment POMDP (a partially observable Markov
decision process: the world has hidden state the agent sees only through noisy
observations): each week the agent orders stock, picks shipping routes, and may
pull operational levers (freight-rate locks, air expedite, batch inspection,
supplier audit/switch), paying holding, stockout, and fee costs. Six hidden factor
processes — demand, supplier reliability, freight rates, port congestion, batch
quality, and a canal disruption — evolve on a pre-generated tape; the agent sees
only symptoms. Because the world is a factored POMDP with a fixed tape, an
explicit Bayesian policy is feasible: per-factor particle filters feeding a
rollout policy over the same action menu, receiving **exactly the observation
stream the LLM receives** — fair, not privileged, and not optimal (an LLM can
legitimately beat it). One asymmetry remains and we state it up front: the
oracle's filters use the environment's true generative parameters (transition
probabilities, regime means), where the LLM gets only a qualitative world
description — it knows the physics, never the hidden state, so we report it as
"Bayes-optimal given the true model." Anchoring the other end with a symptom-blind base-stock
heuristic yields a **skill score** (0 = no better than ignoring the symptoms,
1 = matches the fair Bayesian). Alongside it, two belief-side metrics measured
from the agent's per-week stated rationale — *detection lag* (how quickly the true
factor is first named) and *knowing-doing rate* (how often correctly-diagnosed
stress weeks still incur stockouts) — separate seeing from acting. Finally, the
twenty evaluation seeds (selected from a 200-seed pool by their true stress
profile) are grouped into ISOLATED (isolated short shocks), PERSISTENT (a long port
blockage overlapping a demand rise — the configuration where the intuitive
response, freezing orders, is the wrong one), and COMPOUND (multi-factor
pileups) — making the interaction of hidden failures a controlled variable
rather than an accident of sampling.

**¶5 — Contributions.**
1. A six-factor supply-chain POMDP benchmark with a **fair, computable
   Bayes-filter oracle** — a particle-filter policy conditioned on the identical
   observation stream as the agent (reference = mean of 20 replications per seed).
   Fairness is what makes agent shortfall attributable to acting rather than
   confounded with knowing.
2. A **controlled compound-stress axis** (single-shock / persistent-bottleneck / compound
   seeds) that varies whether hidden failures overlap, holding the world fixed.
3. **Three metrics separating inference from action** — skill score, detection
   lag, knowing-doing rate — evaluated over 60 episodes: three models (Claude
   Sonnet 5, GPT-5.4, DeepSeek-V4-Pro) on twenty seeds, under a rules-only
   prompt with no strategy playbook.

**¶6 — Findings.** Detection is nearly uniform and fast: every model names
85–92% of the 114 hidden-factor episodes in its rationale, typically within a
week of onset. What separates models — and stress profiles — is what happens
after the diagnosis. The two flagship models close 55–64% of the
floor-to-oracle gap overall, while DeepSeek-V4-Pro lands *below the
symptom-blind floor on 9 of 20 seeds*, with detection as good as the others'.
And for every model the knowing-doing rate concentrates on the PERSISTENT seeds:
41–49% of correctly-diagnosed stress weeks there still end with an empty shelf,
versus 6–30% on single-shock seeds. The traces show two distinct mechanisms
behind the same gap: one model freezes (it stops ordering while narrating the
very blockage that will starve it), another flails (it stacks freight locks,
air expedites, and double orders against a disruption it had itself called
short-lived). The gap between seeing a problem and acting on it, not the
seeing, is what this benchmark measures — and it widens precisely where the
world punishes the intuitive response.

---

## Notes for revision (not paper text)

- IMPORTANT framing shift vs draft.md: the 20-seed data killed the "skill
  degrades monotonically with compounding" story (sonnet group means are flat
  0.51/0.55/0.58 — the 9-seed gradient was a small-sample artifact, see
  skill.md). The robust finding is belief-level: uniform detection + the
  knowing-doing rate doubling on PERSISTENT. ¶6 and contribution 2's selling
  point are written to that story; draft.md §4 and the title's emphasis should
  follow suit, and nothing in the paper should claim a skill-vs-stress gradient.
- The seed-1 vignette (now representative — Exhibit A in case-studies.md) can
  return to ¶1/¶2 as an opening hook; verify quotes against the trace first
  per CLAUDE.md.
- Open caveats to carry into limitations, not to block the intro: deepseek
  seed-99 trace unread (don't cite that cell); human spot-check of grader
  labels pending; single run per (model, seed) cell.
- Citation keys are placeholders; swap to real \cite in paper.tex and
  click-verify every one (WRITING.md D1).
