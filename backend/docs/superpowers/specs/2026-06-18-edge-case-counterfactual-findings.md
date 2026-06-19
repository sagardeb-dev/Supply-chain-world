# Edge-case & counterfactual red-team — findings

Method: 9 parallel finders (one per code area) applied code-edge-case lenses +
the 4 world-counterfactual lenses; **every** finding was then adversarially
verified against the source (refute-by-default). 67 raised → **24 confirmed**
(2 high, 8 medium, 14 low), 43 rejected/downgraded. Run `wf_a40bd927-cd5`.

The default 2-factor world and the golden pin (`4251.96…`) are **not** touched by
any confirmed finding — every leak/realism issue is RICH-world-only or a
design-observation about the default world, not a correctness regression.

---

## Root cause #1 — the agent-visible `cost_breakdown` (+ `arrived`) is a deterministic readout of the hidden RICH regimes (12/24 findings)

`engine._build_obs` copies the full `costs` dict into `obs["cost_breakdown"]`,
and `obs["arrived"]` plus the `pipeline` qtys are visible. Every RICH effect that
touches cost is therefore **invertible**, defeating the "emit a noisy signal, the
agent must filter the regime" design those modules are built on:

| Channel | Leak | Severity |
|---|---|---|
| `arrived` vs gross | `defective = round(gross·defect_fraction)`; at gross=40 the three quality regimes map to **0 / 1 / 2** defects → regime read off **exactly** | **HIGH** |
| `cost_breakdown["rework"]` | `rework = 15.0·defective` → `defective = rework/15` → regime, a second exact channel | **HIGH/MED** |
| `cost_breakdown["demurrage"]` | present ⇔ `port_blocked` (congested/customs_hold); `arrived==0` confirms it → binary port state exact | MED |
| `cost_breakdown["shipping"]` | `shipping = shipped·(base·freight_mult ± econ)` → `freight_mult` exact (≈ same info as `freight_index`, mildest) | LOW |
| **key-set itself** | `demurrage`/`rework` keys are added *conditionally* → mere presence/absence is a categorical exact readout, independent of the numbers | LOW |
| spot dispatch | `shipped = round(qty·frac)`, frac 0.5 (wobbling) vs 0.0 (degraded) → collapses the one deliberate supplier "slipping" ambiguity in a single order | LOW |

**Why it matters now:** the bracket anchor (next phase) assumes these states are
*not* directly observable (it's the non-collapsing belief that motivates a
bracket over an exact DP). This side channel collapses quality/port/supplier
beliefs to point masses, so the RICH POMDP is far closer to an MDP than intended.

**Common fix:** break the deterministic regime→observable link. Either (a) make
the effect stochastic — `defective ~ Binomial(gross, defect_fraction)` consuming
the module's rng in registry order — so `arrived`/`rework` no longer invert; and
(b) surface a *fixed* cost-key set (init demurrage/rework to 0.0 unconditionally)
and fold regime-deterministic lines into a noised aggregate rather than itemizing
them per effect.

## Root cause #2 — the paid analyst briefing is vestigial under optimal play (default world)

At the crash week the support is `{false_alarm, short, long}`; **one week later**
those diverge into fully distinct noiseless count rows (`calm (70,70,60)` vs
`blockage (0,0,72)` vs `crisis (14,10,96)`). So the disruption *type* — the only
thing the briefing reveals — is free by waiting a week. The optimal causal oracle
**never buys a briefing** across 30 seeds. Not a bug (golden still valid), but the
one information-purchase lever in the POMDP doesn't bite unless the agent is
forced to commit an irreversible order *in* the crash week (lower buffer / higher
demand-to-lead-time, or a perishability/expiry pressure).

## Theme #3 — "forward" channels aren't forward (mislabeled)

`demand.forecast`, `freight.outlook`, `port.wait_outlook` are each a second noisy
`_draw(mean, …)` around the **current-week** regime mean — a redundant present
read (which does add filtering information), **not** a leading indicator of next
week's transition. The CPFR/GRI/port-advisory framing in the docstrings oversells
them. Fix: relabel, or draw them around a one-step lookahead so they genuinely
lead. Quality has no forward channel at all for its age-dependent hazard.

## Theme #4 — realism warts (RICH, low)

- **structural_decline** is memoryless (97%/wk persist, no age-depth) and snaps
  fully back to base in one week — "structural" is a misnomer for a sticky
  transient; add a hysteretic/aged `recovering` band.
- **freight multiplier is global** across both lanes/suppliers — real spot rates
  are lane-specific; hold a per-lane realized draw.
- **quality is global**, not attached to the sourced supplier (so dual-source /
  switch can't change it).
- **supplier degraded→reliable skips `wobbling`** — a distressed supplier can read
  "on-time" the very next week with no slip warning; route recovery through the
  intermediate state.

## Theme #5 — action-space gaps (the agent can observe but not respond)

No lever responds to quality (`out_of_control` "recovers only on (implicit)
intervention" — but no intervene/audit/reject action exists), to port (no
expedite/priority-berth/reroute), or to freight beyond route choice (no
contract-vs-spot forward lock). The agent is a passive filter on four of six
modules.

## Theme #6 — robustness edges (low)

- `freight._draw` uses a one-sided `max(0.1, …)` clamp that silently masks a
  misconfigured `sd` instead of asserting validity.
- The `watch` branch thresholds sum to 0.85 (0.15 implied "stay") — correct, but
  the cumulative-threshold pattern is fragile to config edits; add a
  `WorldConfig.__post_init__` sum-assert (it guards both `factor.py`'s residual
  `else` and `causal.py`'s `1-pd-fa-calm` residual).
- Orders dispatched within transit-time of the horizon are paid for but never
  arrive, with no terminal/salvage credit → late orders strictly dominated (a
  truncation artifact, present identically in engine + both oracles).

---

### Verification discipline
43 of 67 raised findings were rejected or downgraded on adversarial review —
e.g. "demand_forecast is a useless strictly-dominated duplicate" was refuted (a
second independent noisy read *does* add filtering information; the real issue is
only the misleading label). The confirmed set above is what survived.
