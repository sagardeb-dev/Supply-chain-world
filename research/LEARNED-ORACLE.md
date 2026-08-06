# Learned-dynamics oracle (v1) — built + validated 2026-07-23

Answers the "your oracle is privileged" objection: keep the exact same
filters and MPC, but make the oracle LEARN the world's probabilities from
watching, instead of reading them out of `WorldConfig`.

Code: `backend/fit_oracle.py` (fitter) + `--params` flag on
`backend/oracle_policy.py`. Uncommitted. `backend/learned_trans.json` is a
generated artifact (regenerate any time).

## Framing (the words the literature uses)

- **System identification**: known model family (state spaces, arc topology,
  sensor model), unknown parameters (every transition probability).
- **Baum-Welch / EM for HMMs**: the fitting algorithm (Rabiner 1989 tutorial;
  modern guarantees: Yang, Balakrishnan & Wainwright 2015, arXiv 1512.08269).
  Our (regime, age) states are hidden semi-Markov territory (Yu 2010 survey).
- **Certainty-equivalent MPC**: plan as if the fitted parameters were true
  (Åström & Wittenmark; "Certainty-Equivalence MPC" IEEE TAC 2026).
- **Sample-complexity curve**: oracle skill vs number of training episodes.
- LLM-flavored alternative to contrast against: Pinductor (arXiv 2605.13740)
  learns POMDP models with language-model priors instead of EM.

## Algorithm

1. **Training data** — 200 passive episodes (seeds 5000+, disjoint from all
   benchmark seeds), no actions taken, record ONLY the observation stream
   (freight index, berth wait, AQL band, POS units, canal counts, supplier
   scorecard). Never the hidden tape. No LLM calls; data is free.
2. **Baum-Welch per factor** — start every transition table at uniform over
   the existing arcs; repeat until the likelihood plateaus:
   - E-step: forward-backward over every training episode -> expected count
     of each hidden transition given current parameter guesses;
   - M-step: transition prob = expected count / row total (+ eps=1e-3
     smoothing). Converged in 3-27 iterations per factor.
   Sensor model held known, so states stay identified with regime labels
   (no label switching in v1).
3. **Certainty-equivalent control** — swap learned tables into the built
   filters and run the UNCHANGED MPC oracle. One seam makes it a 10-line
   change: filtering and lookahead sampling both read `filt.trans`, so
   overriding that one attribute converts the whole oracle.

## Commands

```bash
cd backend
uv run python fit_oracle.py --fit 200 --out learned_trans.json
uv run python fit_oracle.py --compare learned_trans.json   # param-error table
uv run python oracle_policy.py --seeds 7,8,19,64 --params learned_trans.json
```

## Results (2026-07-23)

Control cost, true vs learned dynamics (N=200 fit), same seeds/config:

| seed | true oracle | learned oracle | floor (bstock) |
|-----:|------------:|---------------:|---------------:|
|    7 |      11,074 |         11,018 |         10,774 |
|    8 |       6,047 |          6,255 |          6,417 |
|   19 |       5,137 |          5,216 |          6,004 |
|   64 |       6,470 |          6,446 |          6,841 |

Learned == true within Monte-Carlo noise on all four seeds.

## Results v2 (2026-07-30, all 50 benchmark seeds, full 20-rep protocol)

The 4-seed table above is superseded. `analysis/learned_refs.py` reran the
exact bench.py reference protocol (20 deterministic reps, k=191..210) with
the learned tables on all 50 benchmark seeds -> `runs/ladder-v1/
oracle_refs_learned.csv`; `analysis/learned_vs_true.py` does the paired
analysis (paired bootstrap 10k draws seed 20260728 + Wilcoxon):

- Cost: learned − true = +$71 [−$20, +$186] per seed (+1.2% of mean
  reference cost), Wilcoxon p = 0.47 — no detectable difference; CI caps
  degradation at ~3%.
- Stratified where failure was predicted (badly-fit quality deep-age arcs):
  quality-stressed seeds +135 [−18, +381], COMPOUND +141 [−47, +378] —
  point estimates worst exactly there, neither significant.
- Skill-scale shift (rescoring the 4 models, jointly scoreable seeds):
  +0.04..+0.10, every CI straddles 0, all inside the 0.31 resolution;
  two-tier structure unchanged. Seed 12 flips to negative headroom under
  the learned scale (excluded by the metric's own rule, like seed 11).

**Headline (scoped): the reference's strength survives replacing the known
TRANSITION dynamics with 200 watched episodes. Emissions, topology, and
cost mechanics stay known — say so wherever this is cited.**

Paper: §6 paragraph added 2026-07-30 (after the fairness-asymmetry
disclosure), with Rabiner 1989 cite (DOI-verified).

Parameter recovery scales with data (demand mean|err| 0.46 @ N=20 -> 0.08
@ N=200; port 0.09 -> 0.05). One honest identifiability gap: quality's deep
drifting-age hazards stay badly estimated (AQL emissions carry no age
signal; deep ages rarely visited). CE control is robust to it — reportable
finding, not a bug.

## Still privileged in v1 / v2 ideas

- Emission parameters (Gaussian means/sds, band tables) and the surrogate's
  cost mechanics are still read from config. Learning them too is v2 —
  label-switching then becomes real (fixable: the MPC only needs per-state
  learned means, labels never matter).
- Sweep N for the full sample-complexity curve, run the learned oracle on
  all 50 benchmark seeds, and report skill-scale shift vs the true oracle.
