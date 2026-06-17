"""HTTP boundary for the world engine. Session-keyed episodes so a
frontend or agent harness can drive reset/briefing/step; the hidden
trace is only served after the episode ends (live via /xray for
research_mode episodes only). Route names are translated
to/from the episode's semantics vocabulary here (R4) - the engine only
ever sees canonical names."""

import threading
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.world import World, WorldConfig
from src.world.causal_oracle import CausalOracle, causal_play
from src.world.oracle import oracle_plan
from src.world.semantics import ROUTE_PARSE
from report_oracle import fixed_policy_cost, base_stock_cost

app = FastAPI(title="supply-chain-pomdp")
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


class ActionRequest(BaseModel):
    qty: Literal[0, 20, 40]
    route: str | None = None  # vocabulary depends on episode semantics


class StepResponse(BaseModel):
    obs: dict
    cost: float
    done: bool


class BriefingResponse(BaseModel):
    briefing: str
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
    return BriefingResponse(briefing=world.request_briefing(),
                            cost=world.cfg.briefing_cost)


@app.post("/episodes/{episode_id}/step", response_model=StepResponse)
def step_episode(episode_id: str, action: ActionRequest) -> StepResponse:
    world = _get(episode_id)
    if world.done:
        raise HTTPException(status.HTTP_409_CONFLICT, "episode is done")
    route = None
    if action.qty:
        route = ROUTE_PARSE[world.cfg.semantics].get(action.route or "")
        if route is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"unknown route {action.route!r} for this episode")
    obs, cost, done, _info = world.step({"qty": action.qty, "route": route})
    return StepResponse(obs=obs, cost=cost, done=done)


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


# Serve the Three.js frontend (if present) from the same origin. Mounted
# last so the API routes above take precedence.
_FRONTEND = Path(__file__).resolve().parents[3] / "frontend"
if _FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND, html=True), name="frontend")
