# `run/` — recorded agent episodes

Full traces of LLM agents playing the six-factor (`RICH`) world, for two seeds
(8 and 19) across the capable GPT-5 tier (`gpt-5`, `gpt-5.1`, `gpt-5.2`,
`gpt-5.4`). Each file is one complete 26-week episode: the agent's per-week
reasoning, the order it placed, the cost, and — for inspection only — the hidden
state underneath. These are reference artifacts for reading how a model actually
reasons through the task and where it loses money.

```
run/
  seed8/   gpt-5.txt  gpt-5.1.txt  gpt-5.2.txt  gpt-5.4.txt
  seed19/  gpt-5.txt  gpt-5.1.txt  gpt-5.2.txt  gpt-5.4.txt
```

Regenerate any of them:

```
cd backend
uv run python -m src.agent.play_agent --seed 8 --model openai/gpt-5.1 --rich
```

## The task

You run a procurement desk on the Asia–Europe shipping lane for 26 weeks. The
only objective is to **minimize total cost over the whole horizon** — not any
single week. You start with 80 units on hand and demand runs ~20 units/week,
served from inventory; unmet demand is a stockout at $20/unit (the heaviest
cost). Each week you read a situation report and make exactly one decision, which
advances the world.

Six independent hidden processes evolve underneath and leak only indirect
signals. You never see their state — you infer it from noisy weekly readings:

| factor | what it does | what you see |
|---|---|---|
| **disruption** | the Suez/Red Sea corridor can close (a short grounding or a long war), delaying or diverting ships | transit counts (Suez/Bab/Cape) + a trade-press bulletin |
| **supplier** | the cheap *spot* supplier's reliability drifts; it can ship short or fail for good | an OTIF scorecard per supplier |
| **demand** | underlying demand drifts (promo spikes, seasonal lifts, structural decline) | noisy units-sold + a forward forecast |
| **freight** | the spot shipping rate drifts slack→normal→tightening→spike | a freight index (~100 normal) + outlook |
| **port** | the destination port can congest or place a customs hold, holding arrivals a week | berth-wait days + outlook |
| **quality** | the supplier's process can drift out of control, making a fraction of arrivals defective | a noisy accept/marginal/reject AQL reading |

The disruption and supplier signals are **noiseless** (the count pattern is an
exact lookup on the regime, with one deliberate one-week onset ambiguity: a real
disruption and a false alarm look identical for exactly one week, and only
resolve the week after). The demand/freight/port/quality signals are **noisy** —
no single reading identifies the regime, so they must be filtered over weeks.

## The levers

One week-advancing tool and two within-week actions:

- **`place_order(rationale, qty, route, supplier, …)`** — the only tool that
  advances the week. `qty ∈ {0, 20, 40}`; if you order you pick a `route`
  (`suez`, ~3 wk and cheaper, but exposed to the corridor; `cape`, ~4 wk and
  dearer, but reliable) and a `supplier` you hold a live contract with. The same
  call can sign/switch/renew/lapse a contract. **`rationale` is required every
  week** — the world will not advance without the model writing out its reasoning
  (this is what the `REASON` lines in the traces are).
- **`buy_briefing()`** — pay $30 to disambiguate the current lane state before
  committing. Optional.
- **`lock_freight(weeks)`** — forward-buy the freight rate, fixing the multiplier
  for N weeks regardless of the spot index. A bet: it caps a spike but you forgo
  a drop, and an unused week still burns the window.

Routing is a real trade-off, not a free reroute: a Suez ship that meets the canal
during a closure waits a week and *then* diverts around the Cape, billed at the
Cape rate. Ordering into Suez during a known crisis pays the penalty.

## How to read a trace

```
WEEK 0  inv 80  Suez 70/70/60  arrived 0  pipe [-]  demand 20/20  freight 100  port 1d  qual accept
        hidden: lane=calm spot=reliable dem=normal frt=normal prt=clear qly=in_control

REASON Week 0: demand stable ~20, lane and freight normal, 80 units is ~4 weeks
       of cover. Order 20 via Suez to track demand without overbuilding …
  >> place_order(qty=20, route=suez, supplier=qualified)
WORLD  week 1  cost $180  cum $180
       inv 80  Suez 70/70/60  arrived 0  pipe [20@4s]  demand 19/20  freight 105 …
       hidden: lane=calm spot=reliable dem=normal frt=normal prt=clear qly=in_control
```

- The first line of each block is **what the agent saw** (the observation) plus
  its order and the week's cost.
- `REASON` is the agent's required per-week rationale; `>>` is the tool call.
- The **`hidden:` line is the x-ray** — the true latent state, printed here for
  inspection. The agent never sees it; it must infer it from the line above.
- `pipe [20@4s]` = 20 units arriving week 4 via Suez. A `Q` means queued at the
  canal, `D` means diverted to the Cape.

## Scores

Total cost over 26 weeks (lower is better), six-factor world, `temperature=0`,
post the required-`rationale` change. Same seed = same hidden tape across all
models, so columns are directly comparable.

| model | seed 8 | seed 19 |
|---|---|---|
| `gpt-5` | **$6,779** | **$6,676** |
| `gpt-5.1` | $7,505 | $8,225 |
| `gpt-5.2` | $8,446 | $7,882 |
| `gpt-5.4` | $7,645 | $8,937 |

What these runs show, read honestly:

- **The score does not track capability.** The base `gpt-5` is the cheapest on
  *both* seeds, and the more capable `gpt-5.1/5.2/5.4` are all worse — capability
  anti-correlates with cost here. The benchmark separates *can-play* from *can't*
  (a model that violates the contract rules or runs lean into the stockout cluster
  does much worse), but among capable models it is not measuring skill.
- **Requiring a written rationale every week raised costs.** These post-fix runs
  are all dearer than the same models scored before `rationale` was mandatory
  (e.g. `gpt-5.1` on seed 8: $6,261 → $7,505). Forcing per-week articulation seems
  to nudge the stronger models into *more* active management — contract churn,
  route fiddling — that costs money. That is itself a finding about the task: more
  deliberation is not rewarded, so the prompt and the world, not the model, are
  the binding constraints.
- **Most of the controllable cost is one decision.** A counterfactual sweep shows
  the large, foresight-knowing optimum comes mostly from carrying more buffer in
  the calm weeks *before* a disruption is visible — a bet against an unseen
  hazard. That decision is the real "under uncertainty" content of the episode,
  and the rest is largely arithmetic on near-observable state.

See `../backend/src/world/README.md` for the world's design and
`../backend/src/agent/README.md` for the harness that produced these traces.
