# frontend

A static Three.js UI for the world, served by the FastAPI backend from the same
origin. No package manager and no build step: the one runtime dependency,
`three`, is loaded from a CDN via an import map in `index.html`. Open the backend
(`http://localhost:9000`) and this is what it serves.

What it does: play the desk yourself or watch an LLM agent play, with a 3D view
of the lane and shipments. A research-mode toggle reveals the hidden tape (x-ray)
live by calling the backend's `xray` route — off for benchmark runs.

## Files

| File | Role |
|---|---|
| `index.html` | Page shell + the `three` import map. |
| `js/main.js` | Entry point; wires the modules together. |
| `js/api.js` | Calls the backend routes (episodes, agent runs, SSE). |
| `js/store.js` | Client-side run/episode state. |
| `js/scene.js` | The Three.js scene — lane, ports, shipments. |
| `js/ui.js` | Controls, panels, the situation report. |
| `js/agent.js` | Subscribes to the agent SSE stream and renders it. |
| `css/style.css` | Styles. |

Everything talks to the backend over the routes documented in
[`../backend/src/api/README.md`](../backend/src/api/README.md).
