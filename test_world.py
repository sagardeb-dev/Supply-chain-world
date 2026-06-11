"""Single regression net for the noiseless supply-chain POMDP world.

Pins the properties the research depends on: seed-determinism, action
exogeneity, no hidden-state leakage, the trap arithmetic, logistics
bookkeeping, and the API boundary.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.world import World, WorldConfig
from src.world.emission import observe_counts, probe_result
from src.world.engine import HIDDEN_KEYS
from src.world.logistics import lead_time
from src.world.state import HiddenState

CFG = WorldConfig()


def run_episode(seed, routes=("suez",), probe=False):
    world = World()
    world.reset(seed)
    i = 0
    while not world.done:
        world.step({"route": routes[i % len(routes)], "probe": probe})
        i += 1
    return world


def test_same_seed_same_trace():
    assert run_episode(7).trace == run_episode(7).trace


def test_actions_do_not_affect_hidden_trajectory():
    a = run_episode(11)
    b = run_episode(11, routes=("cape", "suez"), probe=True)
    assert [r["hidden"] for r in a.trace] == [r["hidden"] for r in b.trace]


def test_no_hidden_leak_in_observations():
    for rec in run_episode(3).trace:
        assert not (HIDDEN_KEYS & rec["obs"].keys())


def test_trap_arithmetic():
    counts = {
        name: observe_counts(h, CFG)
        for name, h in [
            ("calm", HiddenState()),
            ("watch", HiddenState(event_state="watch")),
            ("disruption", HiddenState(event_state="disruption")),
            ("false_alarm", HiddenState(event_state="false_alarm")),
            ("cape_local", HiddenState(cape_local_congestion=True)),
        ]
    }
    assert counts["calm"] == {"suez_count": 70, "bab_count": 70, "cape_count": 60}
    assert counts["watch"]["suez_count"] == 63
    assert counts["disruption"]["suez_count"] == 38
    assert counts["false_alarm"]["suez_count"] == 35
    # the trap: on Suez alone, a false alarm looks WORSE than a real disruption
    assert counts["false_alarm"]["suez_count"] < counts["disruption"]["suez_count"]
    # only Cape separates them
    assert counts["disruption"]["cape_count"] == 81
    assert counts["false_alarm"]["cape_count"] == 60
    # reverse trap: local Cape congestion mimics the disruption signature on Cape only
    assert counts["cape_local"]["cape_count"] == 81
    assert counts["cape_local"]["suez_count"] == 70


def test_probe_results_and_cost():
    assert probe_result(HiddenState(event_state="watch")) == "likely_disruption"
    assert probe_result(HiddenState(event_state="disruption")) == "likely_disruption"
    assert probe_result(HiddenState(event_state="false_alarm")) == "likely_false_alarm"
    assert probe_result(HiddenState()) == "all_clear"
    world = World()
    world.reset(0)
    obs, _, _, _ = world.step({"route": "suez", "probe": True})
    assert obs["cost_breakdown"]["probe"] == CFG.probe_cost
    assert obs["probe_result"] is not None


def test_lead_times():
    assert lead_time("suez", HiddenState(), CFG) == 3
    assert lead_time("suez", HiddenState(event_state="disruption"), CFG) == 8
    assert lead_time("cape", HiddenState(), CFG) == 5
    assert lead_time("cape", HiddenState(event_state="disruption"), CFG) == 6
    assert lead_time("cape", HiddenState(cape_local_congestion=True), CFG) == 6


def test_books_conservation_and_stockout_billing():
    world = World()
    world.reset(5)
    inv = CFG.initial_inventory
    while not world.done:
        obs, _, _, _ = world.step({"route": "suez", "probe": False})
        served = min(inv + obs["arrived"], CFG.weekly_demand)
        assert obs["inventory"] == inv + obs["arrived"] - served
        shortfall = CFG.weekly_demand - served
        assert obs["cost_breakdown"]["stockout"] == CFG.stockout_cost * shortfall
        inv = obs["inventory"]


def test_termination():
    world = run_episode(1)
    assert world.week == CFG.horizon_weeks
    with pytest.raises(RuntimeError):
        world.step({"route": "suez", "probe": False})


def test_trace_completeness():
    world = run_episode(2)
    assert len(world.trace) == CFG.horizon_weeks + 1
    for rec in world.trace:
        assert {"week", "hidden", "action", "obs", "cost"} <= rec.keys()


def test_api_episode_lifecycle():
    client = TestClient(app)
    r = client.post("/episodes", json={"seed": 9})
    assert r.status_code == 201
    episode_id = r.json()["episode_id"]

    assert client.get(f"/episodes/{episode_id}/trace").status_code == 409

    done = False
    while not done:
        r = client.post(f"/episodes/{episode_id}/step", json={"route": "suez"})
        assert r.status_code == 200
        done = r.json()["done"]

    assert client.post(f"/episodes/{episode_id}/step", json={"route": "suez"}).status_code == 409

    r = client.get(f"/episodes/{episode_id}/trace")
    assert r.status_code == 200
    body = r.json()
    assert len(body["trace"]) == CFG.horizon_weeks + 1
    assert "event_state" in body["trace"][0]["hidden"]

    assert client.post("/episodes/nope/step", json={"route": "suez"}).status_code == 404
