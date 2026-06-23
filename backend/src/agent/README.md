# `agent/` — the LLM agent harness

Drives a `World` through an LLM. It exposes the world as three tools, builds a
[`deepagents`](https://github.com/langchain-ai/deepagents) agent on an OpenRouter
model, runs a full 26-week episode, and records every decision. This is what
produced the traces in [`../../../run/`](../../../run).

## Files

| File | Role |
|---|---|
| `prompt.py` | `SYSTEM_PROMPT`: the desk briefing — the levers, the six observation channels, the cost model, the lane structure, and the loop contract. Every number matches `world/config.py`; nothing leaks hidden state. |
| `tools.py` | `make_tools(run)` → the LangChain tools the model calls, closed over one run. |
| `service.py` | `svc_step` / `svc_briefing` / `svc_lock`: a thin layer between the tools and `World`. Validates input and returns plain dicts; bad input raises (no fallback). |
| `factory.py` | `build_model` (OpenRouter `ChatOpenAI`, `temperature=0`, streaming) and `build_agent` (a deep agent with the prompt + tools). |
| `runner.py` | `AgentRun`: holds the `World` and the event recorder; `kickoff_message` builds the week-0 user turn. |
| `play_agent.py` | Headless entry point: streams an agent (or a fixed policy) through an episode and prints the aligned trace with the hidden tape. |

## The two tool tiers

The tools split by whether they advance time:

- **`place_order` — the only week-advancing tool.** It calls `svc_step` →
  `World.step`, which advances every latent factor one week and resolves the
  voyage. Exactly one call per week. Its first argument, `rationale`, is
  **required**: the world will not advance without the model writing out its
  reasoning for that week. (Reasoning models otherwise return a silent tool call
  — the required field forces visible, comparable per-week reasoning regardless
  of provider.)
- **`buy_briefing` and `lock_freight` — within-week actions.** They act on the
  current week without advancing it (pay for intel; forward-buy the freight
  rate). `lock_freight` is bound only in worlds that have a freight market.

New agent levers follow this pattern — added as within-week tools, never as new
`place_order` arguments (see [`../world/AGENTS.md`](../world/AGENTS.md)).

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

Traces are saved to `runs/seed<N>-<model>.chat.txt`.
