# `api/` — the FastAPI app

Serves three things on one origin: the world as an HTTP API, agent episodes as a
server-sent-event (SSE) stream, and the static `frontend/`. No separate frontend
server and no Node build step — the static mount is added last so the API routes
win.

`app.py` is the whole app. Run it from the repo root README's instructions
(`uvicorn src.api.app:app`).

## Routes

**Play the world yourself (one episode = one server-side `World`):**

| Method · Path | Purpose |
|---|---|
| `POST /episodes` | Create an episode (seed, config), return the week-0 observation. |
| `POST /episodes/{id}/step` | Apply an action, advance one week, return the new observation + cost. |
| `POST /episodes/{id}/briefing` | Buy the paid lane briefing (within-week, no advance). |
| `GET /episodes/{id}/trace` | The full per-week trace so far. |
| `GET /episodes/{id}/xray` | The hidden tape — **research mode only**, off for benchmark runs. |
| `GET /benchmark/{seed}` | The oracle / benchmark summary for a seed. |

**Watch an LLM agent play:**

| Method · Path | Purpose |
|---|---|
| `POST /agent/runs` | Start an agent run (model, seed, world). |
| `GET /agent/runs/{id}/stream` | SSE stream of the agent's reasoning, tool calls, and world replies as they happen. |
| `POST /agent/runs/{id}/advance` | Step a step-gated run forward (human-approval mode). |
| `GET /agent/runs/{id}/log` | The recorded run log. |

The `xray` route is the one place hidden state is exposed; it is gated to
research mode so a benchmark run can never read it.
