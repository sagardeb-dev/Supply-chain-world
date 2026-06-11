"""HTTP boundary for the world engine. Session-keyed episodes so a
frontend or agent harness can drive reset/briefing/step; the hidden
trace is only served after the episode ends. Route names are translated
to/from the episode's semantics vocabulary here (R4) - the engine only
ever sees canonical names."""

from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from src.world import World, WorldConfig
from src.world.semantics import ROUTE_PARSE

app = FastAPI(title="supply-chain-pomdp")
episodes: dict[str, World] = {}


class ResetRequest(BaseModel):
    seed: int
    semantics: Literal["real", "anon"] = "real"


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
