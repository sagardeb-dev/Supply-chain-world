"""HTTP boundary for the world engine. Session-keyed episodes so a
frontend or agent harness can drive reset/briefing/step; the hidden
trace is only served after the episode ends (live via /xray for
research_mode episodes only). Route names are translated
to/from the episode's semantics vocabulary here (R4) - the engine only
ever sees canonical names."""

import threading
from pathlib import Path

from dotenv import load_dotenv

# load backend/.env so OPENROUTER_API_KEY (read in agent/factory.py) is present
# before any agent code runs. Searches cwd upward; uvicorn runs from backend/.
load_dotenv()
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.world import World, WorldConfig
from src.world.oracle import CausalOracle, causal_play
from src.world.oracle import oracle_plan
from src.world.substrate.semantics import ROUTE_PARSE
from src.world.modules.supplier import SUPPLIER_PARSE
from src.agent.service import svc_audit, svc_briefing, svc_step
from report_oracle import fixed_policy_cost, base_stock_cost

from contextlib import asynccontextmanager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

_RUNS_DIR = Path("runs")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Persistent agent checkpointer for the app lifetime. Entered once here
    (the saver is an async context manager) and shared on app.state so every
    agent run resumes across process restarts."""
    _RUNS_DIR.mkdir(exist_ok=True)
    cm = AsyncSqliteSaver.from_conn_string(str(_RUNS_DIR / "agent_ckpt.sqlite"))
    app.state.saver = await cm.__aenter__()
    try:
        yield
    finally:
        await cm.__aexit__(None, None, None)


app = FastAPI(title="supply-chain-pomdp", lifespan=lifespan)


# No-build frontend: tell browsers to always revalidate static assets so a
# JS/CSS/HTML edit lands on the next load instead of being masked by a stale
# module cache. etag/last-modified still make unchanged files a cheap 304.
# ponytail: blanket no-cache is fine here -- this server is the dev/demo host,
# not a CDN; switch to hashed filenames if it ever needs real cache lifetimes.
@app.middleware("http")
async def _no_cache_static(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-cache"
    return response
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
episodes: dict[str, World] = {}
research_ids: set[str] = set()


class ResetRequest(BaseModel):
    seed: int
    semantics: Literal["real", "anon"] = "real"
    research_mode: bool = False


class ResetResponse(BaseModel):
    episode_id: str
    obs: dict


class ContractAction(BaseModel):
    action: str            # sign|switch|renew|lapse
    supplier: str          # canonical or anon supplier id
    terms: str | None = None  # negotiation menu key: short|long|strict|lenient


class ActionRequest(BaseModel):
    qty: Literal[0, 20, 40]
    route: str | None = None  # vocabulary depends on episode semantics
    supplier: str | None = None  # qualified|spot|backup (or anon source_*)
    contract: ContractAction | None = None  # sign/renew/switch/lapse a contract


class StepResponse(BaseModel):
    obs: dict
    cost: float
    done: bool


class BriefingResponse(BaseModel):
    briefing: str
    cost: float


class AuditResponse(BaseModel):
    audit: str
    cost: float


def _get(episode_id: str) -> World:
    world = episodes.get(episode_id)
    if world is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown episode")
    return world


@app.post("/episodes", response_model=ResetResponse,
          status_code=status.HTTP_201_CREATED)
def create_episode(req: ResetRequest) -> ResetResponse:
    world = World(WorldConfig(semantics=req.semantics))
    obs = world.reset(req.seed)
    episode_id = uuid4().hex
    episodes[episode_id] = world
    if req.research_mode:
        research_ids.add(episode_id)
    return ResetResponse(episode_id=episode_id, obs=obs)


@app.post("/episodes/{episode_id}/briefing", response_model=BriefingResponse)
def buy_briefing(episode_id: str) -> BriefingResponse:
    world = _get(episode_id)
    if world.done:
        raise HTTPException(status.HTTP_409_CONFLICT, "episode is done")
    r = svc_briefing(world)
    return BriefingResponse(briefing=r["briefing"], cost=r["cost"])


@app.post("/episodes/{episode_id}/audit", response_model=AuditResponse)
def buy_audit(episode_id: str) -> AuditResponse:
    world = _get(episode_id)
    if world.done:
        raise HTTPException(status.HTTP_409_CONFLICT, "episode is done")
    r = svc_audit(world)
    return AuditResponse(audit=r["audit"], cost=r["cost"])


@app.post("/episodes/{episode_id}/step", response_model=StepResponse)
def step_episode(episode_id: str, action: ActionRequest) -> StepResponse:
    world = _get(episode_id)
    if world.done:
        raise HTTPException(status.HTTP_409_CONFLICT, "episode is done")
    route = supplier = None
    if action.qty:
        route = ROUTE_PARSE[world.cfg.semantics].get(action.route or "")
        if route is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"unknown route {action.route!r} for this episode")
        supplier = SUPPLIER_PARSE[world.cfg.semantics].get(action.supplier or "")
        if supplier is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"unknown supplier {action.supplier!r} for this episode")
    contract = None
    if action.contract is not None:
        csup = SUPPLIER_PARSE[world.cfg.semantics].get(action.contract.supplier)
        if csup is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"unknown contract supplier {action.contract.supplier!r}")
        contract = {"action": action.contract.action, "supplier": csup,
                    "terms": action.contract.terms}
    r = svc_step(world, action.qty, route, supplier, contract)
    return StepResponse(obs=r["obs"], cost=r["cost"], done=r["done"])


@app.get("/episodes/{episode_id}/trace")
def episode_trace(episode_id: str) -> dict:
    world = _get(episode_id)
    if not world.done:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "trace available only after the episode ends")
    return {"total_cost": world.total_cost, "trace": world.trace}


@app.get("/episodes/{episode_id}/xray")
def episode_xray(episode_id: str) -> dict:
    world = _get(episode_id)
    if episode_id not in research_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "xray requires a research_mode episode")
    return {"weeks": [{"week": rec["week"], **rec["hidden"]}
                      for rec in world.trace]}


_bench = {"status": "unsolved", "oracle": None, "per_seed": {},
          "lock": threading.Lock(), "error": None}


def _solve_oracle() -> None:
    try:
        oracle = CausalOracle(WorldConfig())
        oracle.value()  # forces the exact solve (~122 s, once per process)
        _bench["oracle"] = oracle
        _bench["status"] = "ready"
    except Exception as exc:  # surfaced as a 500 by the endpoint
        _bench["error"] = repr(exc)
        _bench["status"] = "error"


@app.get("/benchmark/{seed}")
def benchmark(seed: int) -> JSONResponse:
    if not (0 <= seed <= 1_000_000_000):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "seed out of range")
    with _bench["lock"]:
        if _bench["status"] == "unsolved":
            _bench["status"] = "solving"
            threading.Thread(target=_solve_oracle, daemon=True).start()
    if _bench["status"] == "solving":
        return JSONResponse(status_code=202, content={"status": "solving"})
    if _bench["status"] == "error":
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"oracle solve failed: {_bench['error']}")
    if seed not in _bench["per_seed"]:
        cfg = WorldConfig()
        clairvoyant, _plan = oracle_plan(seed, cfg)
        causal, rows = causal_play(seed, cfg, _bench["oracle"])
        suez20 = fixed_policy_cost(seed, "suez", cfg)
        cape20 = fixed_policy_cost(seed, "cape", cfg)
        basestock = base_stock_cost(seed, cfg)
        _bench["per_seed"][seed] = {
            "status": "ready", "seed": seed,
            "clairvoyant": clairvoyant, "causal": causal,
            "suez20": suez20, "cape20": cape20, "basestock": basestock,
            "naive_min": min(suez20, cape20, basestock),
            "luck_premium": causal - clairvoyant, "plan": rows,
        }
    return JSONResponse(content=_bench["per_seed"][seed])


# ----------------------------------------------------------------------
# Agent harness: run/stream/advance/log. One deepagents session plays a
# whole 26-week episode; its reasoning, tool calls, and results stream out
# over SSE. Two modes (autonomous / step_gated) and true resume by run_id
# (the agent's messages live in the sqlite checkpointer entered at lifespan;
# the World is pickled by the runner under the same id). Registered BEFORE
# the static mount so these routes win.
# ----------------------------------------------------------------------

from fastapi.responses import StreamingResponse
from langgraph.types import Command

from src.agent.runner import AgentRun, stream as agent_stream, kickoff_message
from src.agent.factory import build_agent
from src.agent.prompt import build_system_prompt
from src.agent.tools import make_tools

agent_runs: dict[str, AgentRun] = {}


class AgentRunRequest(BaseModel):
    seed: int
    model: str
    mode: Literal["autonomous", "step_gated"] = "autonomous"
    semantics: Literal["real", "anon"] = "real"


def _build_agent_for(run: AgentRun):
    tools = make_tools(run)
    return build_agent(run.model_slug, run.mode, tools, app.state.saver,
                       build_system_prompt(run.world))


@app.post("/agent/runs", status_code=status.HTTP_201_CREATED)
def create_agent_run(req: AgentRunRequest) -> dict:
    run_id = uuid4().hex
    run = AgentRun(run_id, req.seed, req.model, req.mode, req.semantics)
    agent_runs[run_id] = run
    return {"run_id": run_id, "seed": req.seed, "model": req.model,
            "mode": req.mode, "semantics": req.semantics}


@app.get("/agent/runs/{run_id}/stream")
def stream_agent_run(run_id: str) -> StreamingResponse:
    run = agent_runs.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    if run.active:
        raise HTTPException(status.HTTP_409_CONFLICT, "run already streaming")
    # First connect kicks off the episode; a reconnect after a drop resumes
    # from the last checkpoint (kickoff=None). The agent is built INSIDE the
    # stream so a build failure (missing key) becomes an error event, not a 500.
    kickoff = kickoff_message(run.world) if not run.recorder else None
    return StreamingResponse(
        agent_stream(run, lambda: _build_agent_for(run), kickoff),
        media_type="text/event-stream")


@app.post("/agent/runs/{run_id}/advance")
def advance_agent_run(run_id: str) -> StreamingResponse:
    run = agent_runs.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    if run.mode != "step_gated":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "advance only applies to step_gated runs")
    cmd = Command(resume={"decisions": [{"type": "approve"}]})
    return StreamingResponse(
        agent_stream(run, lambda: _build_agent_for(run), cmd),
        media_type="text/event-stream")


@app.get("/agent/runs/{run_id}/log")
def agent_run_log(run_id: str) -> dict:
    run = agent_runs.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    return {"run_id": run_id, "seed": run.seed, "model": run.model_slug,
            "mode": run.mode, "events": run.recorder}


# Serve the Three.js frontend (if present) from the same origin. Mounted
# last so the API routes above take precedence.
_FRONTEND = Path(__file__).resolve().parents[3] / "frontend"
if _FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND, html=True), name="frontend")
