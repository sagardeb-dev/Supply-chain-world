"""Single regression net for the supply-chain POMDP world.

Pins the properties the research depends on: seed-determinism, action
exogeneity, no hidden-state leakage, the crash-week fingerprint
ambiguity (counts AND bulletin), transit-week voyage causality,
in-transit holding, variable order quantity, the two-stage week
(pre-decision briefing), the semantics ablation (real/anon), the API
boundary, and clairvoyant DP == engine replay.
"""

import random

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.world import World, WorldConfig
from src.world.emission import analyst_briefing, news_bulletin, observe_counts
from src.world.engine import HIDDEN_KEYS
from src.world.logistics import Books, resolve_week
from src.world.oracle import arrival_week, hidden_trajectory, oracle_plan
from src.world.semantics import BULLETINS
from src.world.state import HiddenState
from src.world.causal_oracle import (EMPTY_PIPE, CausalOracle, canonical,
                                     causal_play, resolve_rel,
                                     transition_dist)
from src.world.transition import step_hidden


CFG = WorldConfig()


def run_episode(seed, routes=("suez",), qty=20):
    world = World()
    world.reset(seed)
    i = 0
    while not world.done:
        if qty:
            world.step({"qty": qty, "route": routes[i % len(routes)]})
        else:
            world.step({"qty": 0})
        i += 1
    return world


def counts(**kw):
    return tuple(observe_counts(HiddenState(**kw), CFG).values())


def sail(weekly_hidden, orders=None):
    """Drive Books through resolve_week with a scripted hidden sequence.
    orders = [(qty, route)] per week, default (20, "suez").
    Returns (books, first_week1_shipment_or_None, weekly_costs)."""
    books = Books(inventory=CFG.initial_inventory)
    first = None
    costs = []
    for week, h in enumerate(weekly_hidden, start=1):
        qty, route = orders[week - 1] if orders else (20, "suez")
        _, c = resolve_week(books, qty, route, h, week, CFG)
        if first is None:
            first = next((s for s in books.pipeline if s.dispatched_week == 1), None)
        costs.append(c)
    return books, first, costs


CALM = HiddenState()
SHORT = HiddenState("disruption", 0, "short")
LONG = HiddenState("disruption", 0, "long")
RECOV = HiddenState("recovery")


def test_same_seed_same_trace():
    assert run_episode(7).trace == run_episode(7).trace


def test_actions_do_not_affect_hidden_trajectory():
    a = run_episode(11, qty=0)
    b = run_episode(11, routes=("cape", "suez"), qty=40)
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


def test_bulletin_crash_week_identical_across_causes():
    crash_states = [
        HiddenState("false_alarm", 0, None, False),
        HiddenState("disruption", 0, "short", False),
        HiddenState("disruption", 0, "long", False),
    ]
    for mode in ("real", "anon"):
        mcfg = WorldConfig(semantics=mode)
        texts = {news_bulletin(h, mcfg) for h in crash_states}
        assert len(texts) == 1, f"crash bulletin must be identical in {mode}"


def test_bulletin_separates_types_after_onset():
    short = news_bulletin(HiddenState("disruption", 1, "short", False), CFG)
    long_ = news_bulletin(HiddenState("disruption", 1, "long", False), CFG)
    crash = news_bulletin(HiddenState("disruption", 0, "short", False), CFG)
    assert short != long_ and short != crash and long_ != crash


def test_briefing_reveals_type_at_crash_week():
    fa = analyst_briefing(HiddenState("false_alarm", 0, None, False), CFG)
    sh = analyst_briefing(HiddenState("disruption", 0, "short", False), CFG)
    lo = analyst_briefing(HiddenState("disruption", 0, "long", False), CFG)
    assert len({fa, sh, lo}) == 3  # briefing breaks the three-way ambiguity


def test_no_duration_language_in_any_text():
    # R2: duration words would let reading comprehension substitute for
    # domain knowledge. Spot-banned vocabulary across every template.
    banned = ("week", "month", "day", "year", "soon", "brief ", "extended",
              "short", "long", "prolonged", "temporar", "indefinite",
              "likely", "probab", "%")
    from src.world.semantics import BRIEFINGS
    for table in (BULLETINS, BRIEFINGS):
        for mode in table:
            for key, text in table[mode].items():
                low = text.lower()
                for w in banned:
                    assert w not in low, f"{mode}/{key} leaks duration-ish word {w!r}"


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
    cape6 = [(20, "cape")] * 6
    _, clean, _ = sail([CALM] * 6, orders=cape6)
    assert clean.arrives_week == 5
    _, k, _ = sail([CALM, CALM, HiddenState(cape_local_congestion=True), CALM, CALM, CALM],
                   orders=cape6)
    assert k.arrives_week == 6
    _, crisis, _ = sail([CALM, CALM, HiddenState("disruption", 1, "long"), CALM, CALM, CALM],
                        orders=cape6)
    assert crisis.arrives_week == 6
    _, blockage, _ = sail([CALM, CALM, HiddenState("disruption", 1, "short"), CALM, CALM, CALM],
                          orders=cape6)
    assert blockage.arrives_week == 5  # short blockage never congests the Cape


def test_diversion_surcharge_billed_at_cape_rate():
    # A diverted voyage is a Cape voyage: the carrier bills the price
    # differential at the diversion week. Without this, ordering Suez
    # into a known crisis would dominate booking Cape outright.
    hidden = [CALM, CALM, LONG, HiddenState("disruption", 1, "long"),
              CALM, CALM, CALM]
    _, s, costs = sail(hidden, orders=[(20, "suez")] + [(0, None)] * 6)
    assert s.status == "diverted_via_cape"
    assert costs[3]["surcharge"] == (CFG.cape_unit_cost - CFG.suez_unit_cost) * 20
    assert all(c["surcharge"] == 0 for i, c in enumerate(costs) if i != 3)


def test_in_transit_holding_charged():
    _, _, costs = sail([CALM] * 4)
    assert [c["in_transit"] for c in costs] == [20, 40, 60, 60]


def test_qty_zero_dispatches_nothing():
    books, first, costs = sail([CALM] * 4, orders=[(0, None)] * 4)
    assert first is None and books.pipeline == []
    assert all(c["shipping"] == 0 and c["in_transit"] == 0 for c in costs)
    assert books.inventory == CFG.initial_inventory - 4 * CFG.weekly_demand


def test_qty_forty_ships_forty():
    books, first, costs = sail([CALM] * 5, orders=[(40, "suez")] + [(0, None)] * 4)
    assert costs[0]["shipping"] == 40 * CFG.suez_unit_cost
    assert costs[0]["in_transit"] == 40 * CFG.holding_cost
    assert first.qty == 40 and first.arrives_week == 4
    assert costs[3]["in_transit"] == 0  # the 40 landed at week 4


def test_books_conservation_and_stockout_billing():
    world = World()
    world.reset(5)
    inv = CFG.initial_inventory
    while not world.done:
        obs, _, _, _ = world.step({"qty": 20, "route": "suez"})
        served = min(inv + obs["arrived"], CFG.weekly_demand)
        assert obs["inventory"] == inv + obs["arrived"] - served
        shortfall = CFG.weekly_demand - served
        assert obs["cost_breakdown"]["stockout"] == CFG.stockout_cost * shortfall
        in_transit = sum(s["qty"] for s in obs["pipeline"])
        assert obs["cost_breakdown"]["in_transit"] == CFG.holding_cost * in_transit
        inv = obs["inventory"]


def test_briefing_describes_current_week_and_charges_once():
    world = World()
    world.reset(7)
    # force a known CURRENT hidden state (pre-transition - R5)
    world.hidden = HiddenState("disruption", 0, "long", False)
    b1 = world.request_briefing()
    b2 = world.request_briefing()
    assert "security-crisis" in b1  # current state, type revealed
    assert b1 == b2
    obs, _, _, _ = world.step({"qty": 20, "route": "cape"})
    assert obs["cost_breakdown"]["briefing"] == CFG.briefing_cost  # charged once
    obs2, _, _, _ = world.step({"qty": 20, "route": "cape"})
    assert "briefing" not in obs2["cost_breakdown"]  # flag cleared


def test_step_validation():
    world = World()
    world.reset(1)
    with pytest.raises(ValueError):
        world.step({"qty": 30, "route": "suez"})
    with pytest.raises(ValueError):
        world.step({"qty": 20})  # qty > 0 needs a route
    world.step({"qty": 0})       # no route needed


def test_bulletin_present_and_matches_regime():
    world = World()
    obs = world.reset(1)
    assert obs["bulletin"] == BULLETINS["real"]["calm"]
    while not world.done:
        obs, _, _, info = world.step({"qty": 20, "route": "suez"})
        assert obs["bulletin"] == BULLETINS["real"][info["hidden"]["regime"]]


FORBIDDEN_REAL_TOKENS = ("suez", "cape", "red sea", "bab", "houthi",
                         "ever given", "grounded", "salvage", "good hope")


def test_anon_mode_strips_real_entities():
    acfg = WorldConfig(semantics="anon")
    world = World(acfg)
    world.reset(3)
    blob = [str(world.trace[0]["obs"])]
    while not world.done:
        blob.append(world.request_briefing())
        obs, *_ = world.step({"qty": 20, "route": "suez"})
        blob.append(str(obs))
    # guarantee full template coverage regardless of the seed's story
    for h in (CALM, HiddenState("watch"), SHORT, LONG,
              HiddenState("disruption", 1, "short"),
              HiddenState("disruption", 1, "long"),
              RECOV, HiddenState("false_alarm")):
        blob.append(news_bulletin(h, acfg))
        blob.append(analyst_briefing(h, acfg))
    text = " ".join(blob).lower()
    for tok in FORBIDDEN_REAL_TOKENS:
        assert tok not in text, f"anon mode leaks {tok!r}"


def test_anon_and_real_numbers_identical():
    # R3: same seed, same actions -> identical numeric trajectory
    wr = World(WorldConfig())
    wa = World(WorldConfig(semantics="anon"))
    wr.reset(3)
    wa.reset(3)
    while not wr.done:
        or_, cr, *_ = wr.step({"qty": 20, "route": "suez"})
        oa_, ca, *_ = wa.step({"qty": 20, "route": "suez"})
        assert cr == ca
        assert or_["inventory"] == oa_["inventory"]
        assert or_["suez_count"] == oa_["waterway1_count"]
        assert or_["cape_count"] == oa_["waterway2_count"]


def test_termination():
    world = run_episode(1)
    assert world.week == CFG.horizon_weeks
    with pytest.raises(RuntimeError):
        world.step({"qty": 20, "route": "suez"})


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
                world.step({"qty": 20, "route": route})
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
        cost, plan = oracle_plan(seed, CFG)
        world = World()
        world.reset(seed)
        for qty, route in plan:
            world.step({"qty": qty, "route": route} if qty else {"qty": 0})
        assert world.done
        assert abs(world.total_cost - cost) < 1e-6, f"seed {seed}"


def test_oracle_uses_quantity_lever():
    # With the 80-unit starting buffer and a 3-week lead, ordering 20
    # every single week cannot be optimal - the oracle must burn buffer.
    _, plan = oracle_plan(1, CFG)
    assert any(q != 20 for q, _ in plan)


def test_api_episode_lifecycle():
    client = TestClient(app)
    r = client.post("/episodes", json={"seed": 9})
    assert r.status_code == 201
    episode_id = r.json()["episode_id"]

    assert client.get(f"/episodes/{episode_id}/trace").status_code == 409

    done = False
    while not done:
        r = client.post(f"/episodes/{episode_id}/step",
                        json={"qty": 20, "route": "suez"})
        assert r.status_code == 200
        done = r.json()["done"]

    assert client.post(f"/episodes/{episode_id}/step",
                       json={"qty": 20, "route": "suez"}).status_code == 409

    r = client.get(f"/episodes/{episode_id}/trace")
    assert r.status_code == 200
    body = r.json()
    assert len(body["trace"]) == CFG.horizon_weeks + 1
    assert "event_state" in body["trace"][0]["hidden"]

    assert client.post("/episodes/nope/step",
                       json={"qty": 20, "route": "suez"}).status_code == 404


def test_api_briefing_and_anon_episode():
    client = TestClient(app)
    r = client.post("/episodes", json={"seed": 3, "semantics": "anon"})
    assert r.status_code == 201
    eid = r.json()["episode_id"]
    obs = r.json()["obs"]
    assert "waterway1_count" in obs and "suez_count" not in obs

    b = client.post(f"/episodes/{eid}/briefing")
    assert b.status_code == 200 and b.json()["cost"] == CFG.briefing_cost

    # canonical name must be rejected in anon mode; anon name accepted
    bad = client.post(f"/episodes/{eid}/step", json={"qty": 20, "route": "suez"})
    assert bad.status_code == 422
    ok = client.post(f"/episodes/{eid}/step", json={"qty": 20, "route": "route_1"})
    assert ok.status_code == 200
    assert ok.json()["obs"]["cost_breakdown"]["briefing"] == CFG.briefing_cost


# --- causal-aware oracle (the benchmark anchor) --------------------------


@pytest.fixture(scope="module")
def causal():
    return CausalOracle(CFG)


def test_transition_dist_matches_sampler():
    """The DP's exact kernel must agree with transition.step_hidden."""
    rng = random.Random(0)
    cores = [("calm", 0, None), ("watch", 0, None),
             ("disruption", 0, "short"), ("disruption", 1, "short"),
             ("disruption", 0, "long"), ("disruption", 1, "long"),
             ("recovery", 0, None), ("recovery", 1, None),
             ("recovery", 2, None), ("false_alarm", 0, None)]
    n = 20000
    for core in cores:
        dist = dict(transition_dist(core, CFG))
        assert abs(sum(dist.values()) - 1) < 1e-12
        seen = {}
        h = HiddenState(*core)
        for _ in range(n):
            h2 = step_hidden(h, rng, CFG)
            k = canonical((h2.event_state, h2.event_age,
                           h2.disruption_type), CFG)
            seen[k] = seen.get(k, 0) + 1
        assert set(seen) == set(dist), core
        for k, p in dist.items():
            assert abs(seen[k] / n - p) < 0.02, (core, k)


def test_resolve_rel_mirrors_resolve_week():
    """The DP's relative pipeline encoding must reproduce the real Books
    machinery week by week on randomized hidden paths and orders."""
    rng = random.Random(42)
    for trial in range(60):
        books = Books(inventory=CFG.initial_inventory)
        pipe, inv = EMPTY_PIPE, CFG.initial_inventory
        h = HiddenState()
        for week in range(1, CFG.horizon_weeks + 1):
            h = step_hidden(h, rng, CFG)
            qty = rng.choice(CFG.order_quantities)
            route = rng.choice(("suez", "cape")) if qty else None
            arrived, costs = resolve_week(books, qty, route, h, week, CFG)
            core = (h.event_state, h.event_age, h.disruption_type)
            pipe, inv, arrived2, cost2 = resolve_rel(
                pipe, inv, qty, route, core, h.cape_local_congestion, CFG)
            assert arrived2 == arrived, (trial, week)
            assert inv == books.inventory, (trial, week)
            assert abs(cost2 - sum(costs.values())) < 1e-9, (trial, week)


def test_causal_oracle_within_bounds(causal):
    """Clairvoyance is luck-inclusive: the causal oracle can never beat
    it on any seed. causal_play also self-checks every step (obs-group
    uniqueness, cost and inventory agreement with the engine), and the
    belief support must never exceed the three crash-week atoms."""
    for seed in range(1, 9):
        cost, rows = causal_play(seed, oracle=causal)
        clair, _ = oracle_plan(seed, CFG)
        assert cost >= clair - 1e-6, seed
        assert all(r["belief_support"] <= 3 for r in rows), seed


# --- research surface (read-only API for the explainer UI) ---------------

def test_xray_gating_and_content():
    """The hidden tape is reachable live ONLY for research_mode episodes
    (the gate is set at creation, so an agent's episode physically cannot
    peek); benchmark episodes get a 403. Anon episodes still expose the
    canonical hidden state at /xray (an analysis-side artifact, R4)."""
    client = TestClient(app)

    # a normal (benchmark) episode cannot be x-rayed
    eid = client.post("/episodes", json={"seed": 5}).json()["episode_id"]
    assert client.get(f"/episodes/{eid}/xray").status_code == 403

    # a research episode can, and the tape grows as the episode advances
    rid = client.post("/episodes",
                      json={"seed": 5, "research_mode": True}).json()["episode_id"]
    wk0 = client.get(f"/episodes/{rid}/xray").json()["weeks"]
    assert len(wk0) == 1
    assert wk0[0]["event_state"] == "calm"
    assert "event_age" in wk0[0] and "disruption_type" in wk0[0]
    client.post(f"/episodes/{rid}/step", json={"qty": 20, "route": "suez"})
    assert len(client.get(f"/episodes/{rid}/xray").json()["weeks"]) == 2

    # anon research episode: hidden state stays canonical at /xray
    aid = client.post("/episodes",
                      json={"seed": 5, "semantics": "anon",
                            "research_mode": True}).json()["episode_id"]
    assert "event_state" in client.get(f"/episodes/{aid}/xray").json()["weeks"][0]


def test_benchmark_endpoint(causal):
    """The benchmark anchor set for a seed. The 122 s solve is bypassed by
    injecting the module-scoped causal fixture as the cached oracle."""
    import src.api.app as appmod

    saved = appmod._bench
    appmod._bench = {"status": "ready", "oracle": causal, "per_seed": {},
                     "lock": saved["lock"], "error": None}
    try:
        client = TestClient(app)
        body = client.get("/benchmark/3").json()
        assert body["status"] == "ready" and body["seed"] == 3
        assert body["causal"] >= body["clairvoyant"] - 1e-6
        assert body["naive_min"] == min(body["suez20"], body["cape20"],
                                        body["basestock"])
        assert body["luck_premium"] == body["causal"] - body["clairvoyant"]
        assert len(body["plan"]) == CFG.horizon_weeks
        assert client.get("/benchmark/-1").status_code == 422
    finally:
        appmod._bench = saved


def test_service_parity():
    """svc_* over a World yields the same obs/cost as driving it directly."""
    from src.agent.service import svc_observation, svc_briefing, svc_step
    a = World(); a.reset(3)
    b = World(); b.reset(3)
    # direct vs service, same scripted orders
    for qty, route in [(20, "suez"), (0, None), (40, "cape")]:
        oa, ca, da, _ = a.step({"qty": qty, "route": route})
        rb = svc_step(b, qty, route)
        assert rb["obs"] == oa and rb["cost"] == ca and rb["done"] == da
    # svc_observation reads the current obs (matches the trace tail)
    assert svc_observation(b) == b.trace[-1]["obs"]
