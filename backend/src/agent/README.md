# `agent/` — the LLM agent harness

Drives a `World` through an LLM. `make_tools` (`tools.py`) exposes a
**registry/product-gated** tool set — which tools exist depends on which
modules and product the world was built with, not a fixed list — builds a
[`deepagents`](https://github.com/langchain-ai/deepagents) agent on an OpenRouter
model, runs a full 26-week episode, and records every decision. This is what
produces the benchmark traces in `../../runs/`.

## Files

| File | Role |
|---|---|
| `prompt.py` | `SYSTEM_PROMPT`: the desk briefing — the levers, the six observation channels, the cost model, the lane structure, and the loop contract. Every number matches `world/config.py`; nothing leaks hidden state. |
| `tools.py` | `make_tools(run)` → the LangChain tools the model calls, closed over one run. |
| `service.py` | `svc_observation` / `svc_briefing` / `svc_audit` / `svc_lock` / `svc_expedite` / `svc_inspect` / `svc_order_component` / `svc_step`: a thin layer between the tools and `World`. Validates input and returns plain dicts; bad input raises (no fallback). |
| `factory.py` | `build_model` (OpenRouter `ChatOpenAI`, `temperature=0`, streaming) and `build_agent` (a deep agent with the prompt + tools). |
| `runner.py` | `AgentRun`: holds the `World` and the event recorder; `kickoff_message` builds the week-0 user turn. |
| `play_agent.py` | Headless entry point: streams an agent (or a fixed policy) through an episode and prints the aligned trace with the hidden tape. |

## The tools are registry/product-gated

`place_order` and `buy_briefing` are always bound. Every other tool is bound
only when the world it is closed over actually has the module (or product
shape) that tool acts on — `make_tools` checks `run.world.registry` and
`run.world.cfg.product` and assembles the list accordingly:

- **`place_order` — the only week-advancing tool, always present.** It calls
  `svc_step` → `World.step`, which advances every latent factor one week and
  resolves the voyage. Exactly one call per week. Its first argument,
  `rationale`, is **required**: the world will not advance without the model
  writing out its reasoning for that week. (Reasoning models otherwise return a
  silent tool call — the required field forces visible, comparable per-week
  reasoning regardless of provider.) `qty` is a free integer `0..cfg.order_max`
  (100) — there is no fixed menu.
- **`buy_briefing` — always present.** Pays to disambiguate the current lane
  state before committing; a within-week action, does not advance time.
- **`buy_audit` — bound only when `cfg.sup_mask_otif` is set** (the
  masked-supplier sub-challenge, where the OTIF scorecard lags and needs a paid
  probe). In the default noiseless scorecard, an audit is moot.
- **`lock_freight` — bound only when the world's registry has a `freight`
  module** (RICH). Forward-buys the freight rate for N weeks.
- **`expedite_air` — bound only when the registry has a `port` module** (RICH).
  Air-freights units in to sidestep port congestion/holds.
- **`inspect_batch` — bound only when the registry has a `quality` module**
  (RICH). Pays for a quality read on an incoming batch.
- **`order_component` — bound only when the product has more than one
  component** (a BOM/assembly product, e.g. `earbuds`). A single-component
  world orders entirely through `place_order`'s `qty` and never sees this tool.

New agent levers follow this pattern — added as within-week tools gated on the
module/product that motivates them, never as new `place_order` arguments (see
[`../world/AGENTS.md`](../world/AGENTS.md)).

## How a run flows

```
play_agent → AgentRun(seed, model, registry)        # builds the World
           → build_agent(model, make_tools(run))     # deep agent on OpenRouter
           → stream(kickoff_message(world))           # week-0 report as user turn
loop: model reads the report → optionally buys a briefing / locks freight
      → calls place_order(rationale, …) → svc_step → World.step
      → new observation returned to the model → repeat until the episode is done
```

The model sees only observations — never the hidden state. `play_agent` prints
the hidden tape beneath each week for *inspection*, but it is not in the model's
context.

## Running

`--model` is required (an OpenRouter slug) unless `--policy` is given; needs
`OPENROUTER_API_KEY` in `backend/.env`.

```
cd backend
uv run python -m src.agent.play_agent --seed 8 --model openai/gpt-5.1 --rich
uv run python -m src.agent.play_agent --seed 8 --policy basestock --rich   # no LLM
```

Traces are saved to
`runs/<experiment>/<model-slug>/seed<N>[-earbuds][-rich][-coached].chat.txt`
(`--exp` names the experiment folder, default `adhoc`), with a `manifest.json`
per experiment. See [`../../runs/ladder-v1/`](../../runs/ladder-v1) for a
completed sweep (9 seeds x 2 models) and its skill table.
