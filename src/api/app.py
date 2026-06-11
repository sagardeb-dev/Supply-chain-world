"""HTTP boundary for the world engine. Session-keyed episodes so a
frontend can drive reset/step; the hidden trace is only served after
the episode ends."""

from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from src.world import World

app = FastAPI(title="supply-chain-pomdp")
episodes: dict[str, World] = {}


class ResetRequest(BaseModel):
    seed: int


class ResetResponse(BaseModel):
    episode_id: str
    obs: dict


class ActionRequest(BaseModel):
    route: Literal["suez", "cape"]
    probe: bool = False


class StepResponse(BaseModel):
    obs: dict
    cost: float
    done: bool


def _get(episode_id: str) -> World:
    world = episodes.get(episode_id)
    if world is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown episode")
    return world


@app.post("/episodes", response_model=ResetResponse, status_code=status.HTTP_201_CREATED)
def create_episode(req: ResetRequest) -> ResetResponse:
    world = World()
    obs = world.reset(req.seed)
    episode_id = uuid4().hex
    episodes[episode_id] = world
    return ResetResponse(episode_id=episode_id, obs=obs)


@app.post("/episodes/{episode_id}/step", response_model=StepResponse)
def step_episode(episode_id: str, action: ActionRequest) -> StepResponse:
    world = _get(episode_id)
    if world.done:
        raise HTTPException(status.HTTP_409_CONFLICT, "episode is done")
    obs, cost, done, _info = world.step({"route": action.route, "probe": action.probe})
    return StepResponse(obs=obs, cost=cost, done=done)


@app.get("/episodes/{episode_id}/trace")
def episode_trace(episode_id: str) -> dict:
    world = _get(episode_id)
    if not world.done:
        raise HTTPException(status.HTTP_409_CONFLICT, "trace available only after the episode ends")
    return {"total_cost": world.total_cost, "trace": world.trace}
