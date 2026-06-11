"""Single regression net for the supply-chain POMDP world.

Pins the properties the research depends on: seed-determinism, action
exogeneity, no hidden-state leakage, the crash-week fingerprint
ambiguity, transit-week voyage causality, in-transit holding,
bookkeeping, the API boundary, and clairvoyant DP == engine replay.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.world import World, WorldConfig
from src.world.emission import observe_counts, probe_result
from src.world.engine import HIDDEN_KEYS
from src.world.logistics import Books, resolve_week
from src.world.oracle import arrival_week, hidden_trajectory, oracle_plan
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


def counts(**kw):
    return tuple(observe_counts(HiddenState(**kw), CFG).values())


def sail(weekly_hidden, routes=None):
    """Drive Books through resolve_week with a scripted hidden sequence.
    Returns (books, first_shipment, weekly_costs)."""
    books = Books(inventory=CFG.initial_inventory)
    first = None
    costs = []
    for week, h in enumerate(weekly_hidden, start=1):
        route = routes[week - 1] if routes else "suez"
        _, c = resolve_week(books, route, h, week, CFG)
        if first is None:
            first = next(s for s in books.pipeline if s.dispatched_week == 1)
        costs.append(c)
    return books, first, costs


CALM = HiddenState()
SHORT = HiddenState("disruption", 0, "short")
LONG = HiddenState("disruption", 0, "long")
RECOV = HiddenState("recovery")


def test_same_seed_same_trace():
    assert run_episode(7).trace == run_episode(7).trace


def test_actions_do_not_affect_hidden_trajectory():
    a = run_episode(11)
    b = run_episode(11, routes=("cape", "suez"), probe=True)
    assert [r["hidden"] for r in a.trace] == [r["hidden"] for r in b.trace]


def test_no_hidden_leak_in_observations():
    for rec in run_episode(3).trace:
        assert not (HIDDEN_KEYS & rec["obs"].keys())


def test_crash_week_three_way_ambiguity():
    """The trap: false alarm, short onset, and long onset are identical."""
    fa = counts(event_state="false_alarm")
    short0 = counts(event_state="disruption", event_age=0, disruption_type="short")
    long0 = counts(event_state="disruption", event_age=0, disruption_type="long")
    assert fa == short0 == long0 == (28, 25, 66)


def test_fingerprints_separate_one_week_later():
    assert counts(event_state="disruption", event_age=1, disruption_type="short") == (0, 0, 72)
    assert counts(event_state="disruption", event_age=1, disruption_type="long") == (14, 10, 96)
    assert counts() == (70, 70, 60)
    assert counts(event_state="recovery") == (56, 56, 69)


def test_baseline_and_cape_local_fingerprints():
    assert counts(event_state="watch") == (63, 63, 60)
    assert counts(cape_local_congestion=True) == (70, 70, 81)
    crash_k = counts(event_state="false_alarm", cape_local_congestion=True)
    assert crash_k == (28, 25, 87)  # K shifts cape only; ambiguity survives


def test_probe_reveals_type_and_costs():
    assert probe_result(HiddenState()) == "all_clear"
    assert probe_result(HiddenState(event_state="watch")) == "elevated_risk"
    assert probe_result(HiddenState(event_state="false_alarm")) == "false_alarm"
    assert probe_result(SHORT) == "blockage_short_term"
    assert probe_result(LONG) == "crisis_long_term"
    assert probe_result(RECOV) == "recovering"
    world = World()
    world.reset(0)
    obs, _, _, _ = world.step({"route": "suez", "probe": True})
    assert obs["cost_breakdown"]["probe"] == CFG.probe_cost
    assert obs["probe_result"] is not None


def test_suez_clean_passage():
    _, s, _ = sail([CALM] * 5)
    assert (s.arrives_week, s.status) == (4, "at_sea")


def test_suez_dispatch_during_disruption_is_unaffected_if_canal_clears():
    _, s, _ = sail([LONG, RECOV, CALM, CALM, CALM])
    assert s.arrives_week == 4  # v0 punished the dispatch week; v1 must not


def test_suez_recovery_backlog_at_transit():
    _, s, _ = sail([CALM, CALM, RECOV, CALM, CALM])
    assert s.arrives_week == 5


def test_suez_queued_then_released():
    _, s, _ = sail([CALM, CALM, LONG, CALM, CALM, CALM])
    assert (s.arrives_week, s.status) == (5, "at_sea")


def test_suez_queued_then_diverted():
    _, s, _ = sail([CALM, CALM, LONG, HiddenState("disruption", 1, "long"), CALM, CALM, CALM])
    assert (s.arrives_week, s.status) == (7, "diverted_via_cape")


def test_cape_congestion_at_rounding_week():
    _, clean, _ = sail([CALM] * 6, routes=["cape"] * 6)
    assert clean.arrives_week == 5
    _, k, _ = sail([CALM, CALM, HiddenState(cape_local_congestion=True), CALM, CALM, CALM],
                   routes=["cape"] * 6)
    assert k.arrives_week == 6
    _, crisis, _ = sail([CALM, CALM, HiddenState("disruption", 1, "long"), CALM, CALM, CALM],
                        routes=["cape"] * 6)
    assert crisis.arrives_week == 6
    _, blockage, _ = sail([CALM, CALM, HiddenState("disruption", 1, "short"), CALM, CALM, CALM],
                          routes=["cape"] * 6)
    assert blockage.arrives_week == 5  # short blockage never congests the Cape


def test_in_transit_holding_charged():
    _, _, costs = sail([CALM] * 4)
    assert [c["in_transit"] for c in costs] == [20, 40, 60, 60]


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
        in_transit = sum(s["qty"] for s in obs["pipeline"])
        assert obs["cost_breakdown"]["in_transit"] == CFG.holding_cost * in_transit
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


def test_oracle_arrivals_match_engine():
    for seed in (1, 7, 12):
        traj = hidden_trajectory(seed, CFG)
        for route in ("suez", "cape"):
            world = World()
            world.reset(seed)
            while not world.done:
                world.step({"route": route, "probe": False})
            landed = {}
            for rec in world.trace[1:]:
                for s in rec["obs"]["pipeline"]:
                    landed[s["dispatched_week"]] = s["eta"]
                for d in list(landed):
                    a = arrival_week(route, d, traj, CFG)
                    if a is not None and a <= rec["week"]:
                        assert a == landed[d]


def test_oracle_dp_matches_engine_replay():
    for seed in (1, 2, 7, 12, 17):
        cost, routes = oracle_plan(seed, CFG)
        world = World()
        world.reset(seed)
        for r in routes:
            world.step({"route": r, "probe": False})
        assert world.done
        assert abs(world.total_cost - cost) < 1e-6


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
