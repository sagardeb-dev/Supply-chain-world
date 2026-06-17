"""Run state, persistence, and the astream->SSE bridge for one agent
episode. The agent owns the 26-week loop; this module only carries its
state, snapshots the World for resume, and translates LangGraph stream
events into SSE lines. No fallback logic: every failure becomes an
`error` SSE event and the run stops.

Resume rests on two persisted halves keyed by the same run_id: the agent's
message history (deepagents' AsyncSqliteSaver, owned by the API layer) and
the World object (pickled here). Both restore to the same week because the
World snapshot is written inside the place_order tool_result boundary, the
same point the agent checkpoints.
"""

import json
import pickle
from pathlib import Path

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langgraph.types import Command

from src.world import World, WorldConfig

RUNS_DIR = Path("runs")

KICKOFF = ("Begin. You are at week 0. Read the situation with get_week, then "
           "run the full 26-week episode, placing exactly one order each week "
           "until the episode reports done.")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class AgentRun:
    """Holds one episode's World + bookkeeping. The recorder doubles as a
    JSONL log on disk so a run can be inspected after the fact."""

    def __init__(self, run_id: str, seed: int, model_slug: str, mode: str,
                 semantics: str = "real"):
        self.run_id = run_id
        self.seed = seed
        self.model_slug = model_slug
        self.mode = mode
        self.semantics = semantics
        self.world = World(WorldConfig(semantics=semantics))
        self.world.reset(seed)
        self.recorder: list[dict] = []
        self.active = False  # guards against a double stream on reconnect
        RUNS_DIR.mkdir(exist_ok=True)
        self.log_path = RUNS_DIR / f"{run_id}.log"

    def record(self, week, kind: str, payload: dict) -> None:
        event = {"week": week, "kind": kind, "payload": payload}
        self.recorder.append(event)
        with self.log_path.open("a") as f:
            f.write(json.dumps(event) + "\n")

    # --- persistence (the World half of resume) ---

    def _pkl_path(self) -> Path:
        return RUNS_DIR / f"{self.run_id}.world.pkl"

    def save(self) -> None:
        """Snapshot everything needed to rebuild this run's World. Called at
        the place_order boundary so it stays aligned with the agent's own
        checkpoint."""
        blob = {"world": self.world, "run_id": self.run_id, "seed": self.seed,
                "model_slug": self.model_slug, "mode": self.mode,
                "semantics": self.semantics, "recorder": self.recorder}
        with self._pkl_path().open("wb") as f:
            pickle.dump(blob, f)

    @classmethod
    def load(cls, run_id: str) -> "AgentRun":
        with (RUNS_DIR / f"{run_id}.world.pkl").open("rb") as f:
            blob = pickle.load(f)
        run = cls.__new__(cls)
        run.run_id = blob["run_id"]
        run.seed = blob["seed"]
        run.model_slug = blob["model_slug"]
        run.mode = blob["mode"]
        run.semantics = blob["semantics"]
        run.world = blob["world"]
        run.recorder = blob["recorder"]
        run.active = False
        run.log_path = RUNS_DIR / f"{run_id}.log"
        return run


async def stream(run: AgentRun, build_agent_fn, kickoff):
    """Async generator of SSE lines. `build_agent_fn` is a zero-arg callable
    that constructs the agent -- called INSIDE the try so a build failure
    (missing key, bad model slug) surfaces as a visible `error` event rather
    than an opaque 500. `kickoff` is the user message on a fresh run, None to
    resume from the last checkpoint, or a Command(resume=...) to release a
    step-gate. Demuxes ["updates","messages"] into thought / tool_call /
    tool_result / interrupt / done / error. Persists the World after each step."""
    config = {"configurable": {"thread_id": run.run_id}}
    if kickoff is None:
        agent_input = None
    elif isinstance(kickoff, Command):
        agent_input = kickoff
    else:
        agent_input = {"messages": [{"role": "user", "content": kickoff}]}

    run.active = True
    try:
        agent = build_agent_fn()  # inside try: build errors become `error` events
        async for mode, payload in agent.astream(
                agent_input, config, stream_mode=["updates", "messages"]):
            if mode == "messages":
                chunk, _meta = payload
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    yield _sse("thought", {"text": chunk.content})
            elif mode == "updates":
                for node, delta in payload.items():
                    if node == "__interrupt__":
                        yield _sse("interrupt", _interrupt_payload(delta))
                        continue
                    if not isinstance(delta, dict):
                        continue
                    for m in delta.get("messages", []):
                        if isinstance(m, AIMessage) and m.tool_calls:
                            for tc in m.tool_calls:
                                yield _sse("tool_call",
                                           {"id": tc.get("id"), "name": tc["name"],
                                            "args": tc["args"]})
                        elif isinstance(m, ToolMessage):
                            payload = {"name": getattr(m, "name", None),
                                       "content": str(m.content)}
                            if m.name == "place_order":
                                run.save()
                                # the place_order tool just appended
                                # {qty,route,cost,done,obs} to recorder
                                last = run.recorder[-1] if run.recorder else None
                                if last and last.get("kind") == "place_order":
                                    p = last["payload"]
                                    payload.update({"obs": p["obs"],
                                                    "cost": p["cost"],
                                                    "done": p["done"],
                                                    "week": last.get("week")})
                            yield _sse("tool_result", payload)
        run.save()
        yield _sse("done", {"run_id": run.run_id,
                            "total_cost": run.world.total_cost,
                            "seed": run.seed})
    except Exception as exc:  # no fallback: surface and stop
        yield _sse("error", {"message": repr(exc)})
    finally:
        run.active = False


def _interrupt_payload(delta) -> dict:
    """Pull the proposed action(s) out of an interrupt update so the
    frontend can show what the agent wants to do before the human approves."""
    try:
        items = delta if isinstance(delta, (list, tuple)) else [delta]
        proposals = []
        for it in items:
            val = getattr(it, "value", it)
            reqs = val.get("action_requests", []) if isinstance(val, dict) else []
            for a in reqs:
                proposals.append({"name": a.get("name"), "args": a.get("args")})
        return {"proposals": proposals}
    except Exception:
        return {"proposals": [], "raw": str(delta)}
