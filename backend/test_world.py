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
from src.world.modules.disruption import (BULLETINS, HiddenState,
                                          analyst_briefing, news_bulletin,
                                          observe_counts, step_hidden)
from src.world.modules.supplier import (Contract, SupplierState, TERM_MENU,
                                        contract_open, observe_scorecard,
                                        step_supplier, terms_for)
from src.world.engine import HIDDEN_KEYS
from src.world.substrate import Books, resolve_week


CFG = WorldConfig()


def run_episode(seed, routes=("suez",), qty=20):
    world = World()
    world.reset(seed)
    i = 0
    while not world.done:
        if qty:
            world.step({"qty": qty, "supplier": "qualified",
                        "route": routes[i % len(routes)]})
        else:
            world.step({"qty": 0})
        i += 1
    return world


def counts(**kw):
    return tuple(observe_counts(HiddenState(**kw), CFG).values())


def sup_regime(**kw):
    return SupplierState(**kw).regime


def sup_frac(**kw):
    return SupplierState(**kw).fulfilled_fraction


def sail(weekly_hidden, orders=None, supplier="qualified", sup=None):
    """Drive Books through resolve_week with a scripted hidden sequence.
    orders = [(qty, route)] per week, default (20, "suez"). supplier defaults
    to qualified (always ships full) so existing voyage tests are unaffected.
    Returns (books, first_week1_shipment_or_None, weekly_costs)."""
    if sup is None:
        sup = SupplierState()  # reliable: full fulfilment
    books = Books(inventory=CFG.initial_inventory)
    first = None
    costs = []
    for week, h in enumerate(weekly_hidden, start=1):
        qty, route = orders[week - 1] if orders else (20, "suez")
        _, c = resolve_week(books, qty, supplier, route, h, sup, week, CFG)
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
    from src.world.modules.disruption import BRIEFINGS
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
    assert costs[0]["shipping"] == 40 * (CFG.suez_unit_cost
                                         + CFG.qualified_premium)
    assert costs[0]["in_transit"] == 40 * CFG.holding_cost
    assert first.qty == 40 and first.arrives_week == 4
    assert costs[3]["in_transit"] == 0  # the 40 landed at week 4


def test_books_conservation_and_stockout_billing():
    world = World()
    world.reset(5)
    inv = CFG.initial_inventory
    while not world.done:
        obs, _, _, _ = world.step({"qty": 20, "supplier": "qualified", "route": "suez"})
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
    obs, _, _, _ = world.step({"qty": 20, "supplier": "qualified", "route": "cape"})
    assert obs["cost_breakdown"]["briefing"] == CFG.briefing_cost  # charged once
    obs2, _, _, _ = world.step({"qty": 20, "supplier": "qualified", "route": "cape"})
    assert "briefing" not in obs2["cost_breakdown"]  # flag cleared


def test_step_validation():
    world = World()
    world.reset(1)
    with pytest.raises(ValueError):
        world.step({"qty": -5, "route": "suez", "supplier": "qualified"})
    with pytest.raises(ValueError):
        world.step({"qty": 20})  # qty > 0 needs a route
    world.step({"qty": 0})       # no route needed


def test_free_quantity_accepts_and_bounds():
    """Order qty is a free non-negative integer capped at order_max -- the
    {0,20,40} menu is gone; off-grid quantities are legal, out-of-range raise."""
    world = World()
    world.reset(1)
    world.step({"qty": 30, "route": "suez", "supplier": "qualified"})  # off-grid: legal now
    assert world.books.pipeline[-1].qty == 30
    with pytest.raises(ValueError):
        world.step({"qty": -5, "route": "suez", "supplier": "qualified"})
    with pytest.raises(ValueError):
        world.step({"qty": world.cfg.order_max + 1, "route": "suez",
                    "supplier": "qualified"})


def test_bulletin_present_and_matches_regime():
    world = World()
    obs = world.reset(1)
    assert obs["bulletin"] == BULLETINS["real"]["calm"]
    while not world.done:
        obs, _, _, info = world.step({"qty": 20, "supplier": "qualified", "route": "suez"})
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
        obs, *_ = world.step({"qty": 20, "supplier": "qualified", "route": "suez"})
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
        or_, cr, *_ = wr.step({"qty": 20, "supplier": "qualified", "route": "suez"})
        oa_, ca, *_ = wa.step({"qty": 20, "supplier": "qualified", "route": "suez"})
        assert cr == ca
        assert or_["inventory"] == oa_["inventory"]
        assert or_["suez_count"] == oa_["waterway1_count"]
        assert or_["cape_count"] == oa_["waterway2_count"]


def test_termination():
    world = run_episode(1)
    assert world.week == CFG.horizon_weeks
    with pytest.raises(RuntimeError):
        world.step({"qty": 20, "supplier": "qualified", "route": "suez"})


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
        r = client.post(f"/episodes/{episode_id}/step",
                        json={"qty": 20, "supplier": "qualified", "route": "suez"})
        assert r.status_code == 200
        done = r.json()["done"]

    assert client.post(f"/episodes/{episode_id}/step",
                       json={"qty": 20, "supplier": "qualified", "route": "suez"}).status_code == 409

    r = client.get(f"/episodes/{episode_id}/trace")
    assert r.status_code == 200
    body = r.json()
    assert len(body["trace"]) == CFG.horizon_weeks + 1
    assert "event_state" in body["trace"][0]["hidden"]

    assert client.post("/episodes/nope/step",
                       json={"qty": 20, "supplier": "qualified", "route": "suez"}).status_code == 404


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
    ok = client.post(f"/episodes/{eid}/step", json={"qty": 20, "supplier": "source_a", "route": "route_1"})
    assert ok.status_code == 200
    assert ok.json()["obs"]["cost_breakdown"]["briefing"] == CFG.briefing_cost


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
    client.post(f"/episodes/{rid}/step", json={"qty": 20, "supplier": "qualified", "route": "suez"})
    assert len(client.get(f"/episodes/{rid}/xray").json()["weeks"]) == 2

    # anon research episode: hidden state stays canonical at /xray
    aid = client.post("/episodes",
                      json={"seed": 5, "semantics": "anon",
                            "research_mode": True}).json()["episode_id"]
    assert "event_state" in client.get(f"/episodes/{aid}/xray").json()["weeks"][0]


def test_benchmark_returns_baselines_no_oracle():
    """/benchmark serves base-stock + fixed-policy baselines and a fill rate,
    synchronously, with no oracle fields."""
    from fastapi.testclient import TestClient
    from src.api.app import app
    with TestClient(app) as client:
        r = client.get("/benchmark/7")
        assert r.status_code == 200
        body = r.json()
        assert {"basestock", "suez20", "cape20", "naive_min",
                "basestock_fill"} <= body.keys()
        assert "causal" not in body and "luck_premium" not in body


def test_service_parity():
    """svc_* over a World yields the same obs/cost as driving it directly."""
    from src.agent.service import svc_observation, svc_briefing, svc_step
    a = World(); a.reset(3)
    b = World(); b.reset(3)
    # direct vs service, same scripted orders
    for qty, route in [(20, "suez"), (0, None), (40, "cape")]:
        sup = "qualified" if qty else None
        oa, ca, da, _ = a.step({"qty": qty, "route": route, "supplier": sup})
        rb = svc_step(b, qty, route, sup)
        assert rb["obs"] == oa and rb["cost"] == ca and rb["done"] == da
    # svc_observation reads the current obs (matches the trace tail)
    assert svc_observation(b) == b.trace[-1]["obs"]


def test_agent_tools_gating():
    """Tools mirror the 3 actions, leak no hidden state, and refuse a
    qty>0 order with no route (no fallback)."""
    from src.agent.tools import make_tools
    from src.world.engine import HIDDEN_KEYS

    class FakeRun:
        def __init__(self):
            self.world = World(); self.world.reset(3)
            self.events = []
        def record(self, week, kind, payload):
            self.events.append((week, kind))

    run = FakeRun()
    buy_briefing, place_order = make_tools(run)

    # the week-0 obs now reaches the agent via the kickoff message; no leak
    from src.agent.runner import kickoff_message
    msg = kickoff_message(run.world)
    assert not any(k in msg for k in HIDDEN_KEYS)

    # buy_briefing runs and records (regression: a trimmed import once
    # NameError'd here because buy_briefing fetched the week via svc_observation)
    out = buy_briefing.invoke({})
    assert "briefing" in out.lower()
    assert any(k == "buy_briefing" for _, k in run.events)

    # qty>0 with no route raises (no default route)
    with pytest.raises(Exception):
        place_order.invoke({"rationale": "t", "qty": 20,
                            "supplier": "qualified", "route": ""})

    # a valid order advances the world one week and records the event
    before = run.world.week
    out = place_order.invoke({"rationale": "stock up, lane calm", "qty": 20,
                              "supplier": "qualified", "route": "suez"})
    assert run.world.week == before + 1
    assert "Order placed" in out
    assert any(k == "place_order" for _, k in run.events)


def test_resume_roundtrip(tmp_path, monkeypatch):
    """An AgentRun's World survives save/load rng-faithfully: the loaded
    World's next step matches the un-pickled World's next step."""
    import src.agent.runner as runnermod
    monkeypatch.setattr(runnermod, "RUNS_DIR", tmp_path)
    from src.agent.runner import AgentRun

    run = AgentRun("test-run", seed=3, model_slug="x", mode="autonomous",
                   masked=False)  # plumbing test: simple qualified-incumbent world
    # advance the World two weeks through the same path the tools use
    run.world.step({"qty": 20, "supplier": "qualified", "route": "suez"})
    run.world.step({"qty": 0, "route": None})
    run.save()

    # a reference World driven identically, NOT pickled
    ref = AgentRun("ref-run", seed=3, model_slug="x", mode="autonomous",
                   masked=False)
    ref.world.step({"qty": 20, "supplier": "qualified", "route": "suez"})
    ref.world.step({"qty": 0, "route": None})

    loaded = AgentRun.load("test-run")
    assert loaded.seed == 3 and loaded.mode == "autonomous"
    # same next action -> identical obs/cost/done (rng restored exactly)
    o1, c1, d1, _ = loaded.world.step({"qty": 40, "supplier": "qualified", "route": "cape"})
    o2, c2, d2, _ = ref.world.step({"qty": 40, "supplier": "qualified", "route": "cape"})
    assert o1 == o2 and c1 == c2 and d1 == d2


def test_agent_sse_mock(monkeypatch):
    """SSE framing + event order from a scripted (mocked) agent — no LLM.
    Verifies thought -> tool_call -> tool_result -> done with correct event
    names, and that the run lifecycle works end to end via TestClient."""
    import src.api.app as appmod
    from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

    class FakeAgent:
        async def astream(self, agent_input, config, stream_mode=None):
            # one reasoning token (messages mode)
            yield ("messages", (AIMessageChunk(content="thinking about week 0"), {}))
            # a tool call decision (updates mode)
            yield ("updates", {"agent": {"messages": [
                AIMessage(content="", tool_calls=[
                    {"id": "c1", "name": "place_order",
                     "args": {"qty": 20, "supplier": "qualified", "route": "suez"}}])]}})
            # the tool result (updates mode)
            yield ("updates", {"tools": {"messages": [
                ToolMessage(content="Order placed", name="place_order",
                            tool_call_id="c1")]}})

    monkeypatch.setattr(appmod, "build_agent",
                        lambda slug, mode, tools, ckpt, sysprompt=None: FakeAgent())

    with TestClient(appmod.app) as client:  # context -> runs lifespan (sqlite saver)
        r = client.post("/agent/runs",
                        json={"seed": 3, "model": "x/cheap", "mode": "autonomous"})
        assert r.status_code == 201
        run_id = r.json()["run_id"]

        with client.stream("GET", f"/agent/runs/{run_id}/stream") as s:
            body = "".join(chunk for chunk in s.iter_text())

    # event names present and in order
    for ev in ("event: thought", "event: tool_call", "event: tool_result",
               "event: done"):
        assert ev in body, f"missing {ev} in:\n{body}"
    assert body.index("event: thought") < body.index("event: tool_call") \
        < body.index("event: tool_result") < body.index("event: done")
    # the tool_call carried the structured args
    assert '"name": "place_order"' in body and '"qty": 20' in body


def _parse_sse(frames):
    """Parse a list of raw SSE strings into [(event, data_dict), ...]."""
    import json as _json
    out = []
    for f in frames:
        if not f.strip():
            continue
        ev = data = None
        for line in f.splitlines():
            if line.startswith("event: "):
                ev = line[len("event: "):]
            elif line.startswith("data: "):
                data = _json.loads(line[len("data: "):])
        out.append((ev, data))
    return out


def test_place_order_event_carries_obs(tmp_path, monkeypatch):
    """The place_order tool_result SSE frame carries the post-step structured
    obs (obs/cost/done/week) read from the recorder tail, while a
    non-place_order tool_result (buy_briefing) carries no obs. No LLM."""
    import asyncio
    import src.agent.runner as runnermod
    monkeypatch.setattr(runnermod, "RUNS_DIR", tmp_path)
    from src.agent.runner import AgentRun, stream
    from src.agent.tools import make_tools
    from langchain_core.messages import ToolMessage

    # a real run + a genuine place_order event in the recorder
    run = AgentRun("po-run", seed=3, model_slug="x", mode="autonomous",
                   semantics="real", masked=False)  # plumbing: simple world
    place_order = next(t for t in make_tools(run) if t.name == "place_order")
    place_order.invoke({"rationale": "stock up, lane calm", "qty": 20,
                        "supplier": "qualified", "route": "suez"})
    assert run.recorder and run.recorder[-1]["kind"] == "place_order"

    # a scripted agent that emits a buy_briefing tool_result then a place_order
    # tool_result, AFTER the recorder already holds the place_order event
    class FakeAgent:
        async def astream(self, agent_input, config, stream_mode=None):
            yield ("updates", {"tools": {"messages": [
                ToolMessage(content="situation report", name="buy_briefing",
                            tool_call_id="g1")]}})
            yield ("updates", {"tools": {"messages": [
                ToolMessage(content="Order placed", name="place_order",
                            tool_call_id="p1")]}})

    async def _drive():
        return [chunk async for chunk in stream(run, lambda: FakeAgent(), None)]

    frames = _parse_sse(asyncio.run(_drive()))
    results = [(ev, data) for ev, data in frames if ev == "tool_result"]

    by_name = {data["name"]: data for _, data in results}
    assert "place_order" in by_name and "buy_briefing" in by_name

    po = by_name["place_order"]
    for key in ("obs", "cost", "done", "week"):
        assert key in po, f"place_order tool_result missing {key}: {po}"
    # the attached obs/cost/done/week are exactly the recorder tail's
    tail = run.recorder[-1]
    assert po["obs"] == tail["payload"]["obs"]
    assert po["cost"] == tail["payload"]["cost"]
    assert po["done"] == tail["payload"]["done"]
    assert po["week"] == tail["week"]

    # a non-place_order tool_result carries no world update
    gw = by_name["buy_briefing"]
    assert "obs" not in gw and "cost" not in gw


def test_supplier_regime_and_fulfilment():
    """The spot supplier's visible OTIF band collapses wobbling and the
    first week of degraded into one 'slipping' band (the supplier analogue
    of the disruption crash ambiguity); they separate one week later."""
    assert sup_regime() == "ontime"
    assert sup_regime(rel_state="wobbling") == "slipping"
    assert sup_regime(rel_state="degraded", rel_age=0) == "slipping"
    assert sup_regime(rel_state="degraded", rel_age=1) == "failing"
    assert sup_frac() == 1.0
    assert sup_frac(rel_state="wobbling") == 0.5
    assert sup_frac(rel_state="degraded") == 0.0



def test_step_supplier_matches_hand_distribution():
    """step_supplier's empirical transitions match the spec kernel (A3),
    drawn from the World rng (exogeneity). Mirrors the disruption MC-pin."""
    c = CFG
    # expected next-rel_state distribution from each (rel_state, rel_age) core
    expected = {
        ("reliable", 0): {"reliable": 1 - c.sup_onset_prob,
                          "wobbling": c.sup_onset_prob},
        ("wobbling", 0): {"degraded": c.sup_wobble_to_degraded,
                          "reliable": c.sup_wobble_to_reliable,
                          "wobbling": 1 - c.sup_wobble_to_degraded
                                        - c.sup_wobble_to_reliable},
        # degraded: the death hazard h fires first; the surviving (1-h) mass
        # splits recover/persist as before (R2 Lever 1).
        ("degraded", 0): {
            "defunct": c.sup_defunct_from_degraded,
            "degraded": (1 - c.sup_defunct_from_degraded) * c.sup_degraded_persist,
            "reliable": (1 - c.sup_defunct_from_degraded) * (1 - c.sup_degraded_persist)},
        ("degraded", 1): {
            "defunct": c.sup_defunct_from_degraded,
            "degraded": (1 - c.sup_defunct_from_degraded) * c.sup_degraded_persist,
            "reliable": (1 - c.sup_defunct_from_degraded) * (1 - c.sup_degraded_persist)},
    }
    rng = random.Random(0)
    n = 20000
    for (state, age), dist in expected.items():
        seen = {}
        s = SupplierState(rel_state=state, rel_age=age)
        for _ in range(n):
            s2 = step_supplier(s, rng, c)
            seen[s2.rel_state] = seen.get(s2.rel_state, 0) + 1
        assert set(seen) == set(dist), (state, age, set(seen))
        for k, pexp in dist.items():
            assert abs(seen[k] / n - pexp) < 0.02, (state, age, k)


def test_step_supplier_degraded_forced_exit():
    """A degraded spell cannot exceed sup_max_degraded: at the cap, the next
    state is always reliable (the semi-Markov forced exit, like max_short)."""
    rng = random.Random(1)
    s = SupplierState(rel_state="degraded", rel_age=CFG.sup_max_degraded - 1)
    for _ in range(2000):
        # at the cap a degraded supplier never persists: it either recovers or
        # dies (the death hazard, R2). It must NOT stay degraded.
        assert step_supplier(s, rng, CFG).rel_state in ("reliable", "defunct")


def test_defunct_is_absorbing_and_ships_zero():
    """A defunct supplier is dead for the episode: regime 'defunct',
    fulfilled_fraction 0.0, and step_supplier never revives it."""
    dead = SupplierState(rel_state="defunct")
    assert dead.regime == "defunct"
    assert dead.fulfilled_fraction == 0.0
    rng = random.Random(0)
    for _ in range(50):
        assert step_supplier(dead, rng, CFG).rel_state == "defunct"


def test_degraded_can_become_defunct():
    """From degraded, the supplier dies with hazard sup_defunct_from_degraded.
    Over many seeds at least one transition lands in defunct."""
    seen = set()
    for seed in range(400):
        rng = random.Random(seed)
        s = SupplierState(rel_state="degraded", rel_age=0)
        seen.add(step_supplier(s, rng, CFG).rel_state)
    assert "defunct" in seen, "degraded must be able to transition to defunct"
    # and non-degraded states never die directly
    rng = random.Random(1)
    for st in ("reliable", "wobbling"):
        outs = {step_supplier(SupplierState(rel_state=st), random.Random(k),
                              CFG).rel_state for k in range(200)}
        assert "defunct" not in outs, f"{st} must not jump straight to defunct"


def test_defunct_scorecard_row_shows_dead():
    """The scorecard row for a defunct spot shows OTIF None ('-') and band
    'defunct' -- the collapse is visible to the agent."""
    sc = scorecard(rel_state="defunct")
    row = _spot(sc)
    assert row["otif"] is None
    assert row.get("band") == "defunct"


def test_step_supplier_ages_in_place():
    """Staying in the same state increments rel_age; switching resets to 0."""
    s = SupplierState(rel_state="degraded", rel_age=0)
    # force a persist by exhausting rng draws that keep it degraded
    rng = random.Random(7)
    saw_persist = saw_exit = False
    for _ in range(200):
        s2 = step_supplier(s, rng, CFG)
        if s2.rel_state == "degraded":
            assert s2.rel_age == 1
            saw_persist = True
        else:
            assert s2.rel_age == 0
            saw_exit = True
    assert saw_persist and saw_exit



def roster(**spot_kw):
    """Build the 3-supplier roster with spot in the given hidden state and
    qualified/backup at their frozen-reliable defaults."""
    return {
        "qualified": SupplierState(),
        "spot": SupplierState(**spot_kw),
        "backup": SupplierState(),
    }


def scorecard(**spot_kw):
    return observe_scorecard(roster(**spot_kw), CFG)


def _row(sc, sid):
    return next(s for s in sc["suppliers"] if s["id"] == sid)


def _spot(sc):
    return _row(sc, "spot")


def _qual(sc):
    return _row(sc, "qualified")


def test_scorecard_structure_and_qualified_constant():
    """Two suppliers; qualified is constant regardless of the hidden spot
    state; spot reflects its regime band (A5)."""
    for state in ("reliable", "wobbling", "degraded"):
        sc = scorecard(rel_state=state)
        assert {s["id"] for s in sc["suppliers"]} == {"qualified", "spot", "backup"}
        q = _qual(sc)
        assert q["otif"] == 99 and q["lead_days"] == 14
        assert q["unit_premium"] == CFG.qualified_premium


def test_scorecard_backup_present_and_mid_tier():
    """R1: the roster gains backup (Hangzhou). Mid OTIF (95), its own
    unit delta, and a 1-week onboarding lead. Frozen-reliable in R1."""
    sc = scorecard()
    b = _row(sc, "backup")
    assert b["otif"] == 95
    from src.world.modules.supplier import SUPPLIERS as _SUP
    assert b["onboard_lead"] == _SUP["backup"]["onboard_weeks"]
    # backup is mid-priced: a small premium, not spot's discount
    assert b["unit_delta"] == CFG.backup_unit_delta


def test_scorecard_spot_reflects_regime_band():
    assert _spot(scorecard(rel_state="reliable"))["otif"] == 98
    assert _spot(scorecard(rel_state="wobbling"))["otif"] == 82
    assert _spot(scorecard(rel_state="degraded", rel_age=1))["otif"] == 55
    assert _spot(scorecard(rel_state="reliable"))["unit_discount"] == CFG.spot_unit_discount


def test_scorecard_slipping_ambiguity():
    """The supplier analogue of the crash ambiguity: wobbling and the onset
    week of degraded produce a BYTE-IDENTICAL spot scorecard row (slipping),
    separating one week later when degraded ages into failing."""
    wob = _spot(scorecard(rel_state="wobbling"))
    deg0 = _spot(scorecard(rel_state="degraded", rel_age=0))
    deg1 = _spot(scorecard(rel_state="degraded", rel_age=1))
    assert wob == deg0, "wobbling and degraded-onset must be indistinguishable"
    assert wob != deg1, "they must separate one week later"



def test_qualified_ships_full_regardless_of_spot_state():
    """Supplier Q has no hidden state: a degraded spot regime does not affect
    a qualified order -- it ships the full qty (no regression in voyage)."""
    _, s, _ = sail([CALM] * 5, orders=[(40, "suez")] * 5,
                   supplier="qualified",
                   sup=SupplierState(rel_state="degraded", rel_age=1))
    assert s.qty == 40 and s.supplier == "qualified"


def test_spot_ships_full_when_reliable():
    _, s, _ = sail([CALM] * 5, orders=[(40, "suez")] * 5,
                   supplier="spot", sup=SupplierState())  # reliable
    assert s.qty == 40 and s.supplier == "spot"


def test_spot_ships_half_when_wobbling():
    """fulfilled_fraction 0.5 -> a 40-unit spot order ships 20."""
    _, s, _ = sail([CALM] * 5, orders=[(40, "suez")] * 5,
                   supplier="spot", sup=SupplierState(rel_state="wobbling"))
    assert s.qty == 20 and s.supplier == "spot"


def test_spot_ships_zero_when_degraded():
    """fulfilled_fraction 0.0 -> no shipment created at all (qty 0 dispatch)."""
    books, s, _ = sail([CALM] * 5, orders=[(40, "suez")] * 5,
                       supplier="spot",
                       sup=SupplierState(rel_state="degraded", rel_age=1))
    # nothing dispatched in week 1: no week-1 shipment in the pipeline
    assert s is None
    assert all(sh.qty > 0 for sh in books.pipeline)


def test_voyage_dynamics_unchanged_on_shipped_qty():
    """The voyage stage is untouched: a qualified suez order still arrives
    on the clean-passage schedule (regression pin)."""
    _, s, _ = sail([CALM] * 5, supplier="qualified")
    assert (s.arrives_week, s.status) == (4, "at_sea")



# --- T5: cost coupling (the Becker JV term) -------------------------------

def test_unit_economics_spot_cheaper_qualified_dearer():
    """Spot undercuts the lane unit cost by spot_unit_discount; qualified
    adds qualified_premium. Compared on the SHIPPED qty (reliable -> full)."""
    books_q = Books(inventory=CFG.initial_inventory)
    _, cq = resolve_week(books_q, 40, "qualified", "suez", CALM,
                         SupplierState(), 1, CFG)
    books_s = Books(inventory=CFG.initial_inventory)
    _, cs = resolve_week(books_s, 40, "spot", "suez", CALM,
                         SupplierState(), 1, CFG)
    base = CFG.suez_unit_cost * 40
    assert cq["shipping"] == base + CFG.qualified_premium * 40
    assert cs["shipping"] == base - CFG.spot_unit_discount * 40


def test_couple_surcharge_only_when_disruption_active():
    """A spot shortfall during a watch/crash/blockage/crisis week incurs the
    scarcity surcharge kappa*(qty-shipped); in calm/recovery it does not."""
    WATCH = HiddenState("watch")
    # wobbling spot: orders 40, ships 20 -> shortfall 20
    sup = SupplierState(rel_state="wobbling")
    books_calm = Books(inventory=CFG.initial_inventory)
    _, c_calm = resolve_week(books_calm, 40, "spot", "suez", CALM, sup, 1, CFG)
    books_watch = Books(inventory=CFG.initial_inventory)
    _, c_watch = resolve_week(books_watch, 40, "spot", "suez", WATCH, sup, 1, CFG)
    assert c_calm.get("couple", 0.0) == 0.0
    expected = CFG.crisis_backorder_kappa * (40 - 20)
    assert c_watch["couple"] == expected


def test_couple_no_surcharge_for_qualified_or_full_spot():
    """No shortfall -> no coupling, even in a crisis week."""
    CRISIS = HiddenState("disruption", 1, "long")
    books_q = Books(inventory=CFG.initial_inventory)
    _, cq = resolve_week(books_q, 40, "qualified", "suez", CRISIS,
                         SupplierState(rel_state="degraded", rel_age=1), 1, CFG)
    assert cq.get("couple", 0.0) == 0.0  # qualified ships full
    books_s = Books(inventory=CFG.initial_inventory)
    _, cs = resolve_week(books_s, 40, "spot", "suez", CRISIS,
                         SupplierState(), 1, CFG)  # reliable spot ships full
    assert cs.get("couple", 0.0) == 0.0



# --- T6: engine wires the supplier factor ---------------------------------

def _spot_episode(seed, qty=20, route="suez"):
    """Drive an episode sourcing spot every week. Signs a spot contract up
    front and renews it whenever it opens (expiry or defunct), so the spot
    source stays live across the horizon."""
    world = World()
    obs = world.reset(seed)
    world.step({"qty": 0, "contract": {"action": "sign", "supplier": "spot"}})
    while not world.done:
        action = {"qty": qty} if not qty else {"qty": qty, "supplier": "spot",
                                              "route": route}
        if "spot" in obs.get("contract_open", []):
            action = {**action, "contract":
                      {"action": "renew", "supplier": "spot"}}
            if qty:  # if spot just died, can't source it this week
                alive = obs and any(s["id"] == "spot" and s.get("band") != "defunct"
                                    for s in obs["suppliers"])
                if not alive:
                    action = {"qty": 0, "contract":
                              {"action": "renew", "supplier": "spot"}}
        obs, *_ = world.step(action)
    return world


def test_step_accepts_supplier_and_emits_scorecard():
    world = World()
    obs0 = world.reset(3)
    assert "suppliers" in obs0  # scorecard present from week 0
    ids = {s["id"] for s in obs0["suppliers"]}
    assert ids == {"qualified", "spot", "backup"}
    world.step({"qty": 0, "contract": {"action": "sign", "supplier": "spot"}})
    obs, _, _, _ = world.step({"qty": 20, "supplier": "spot", "route": "suez"})
    assert "suppliers" in obs


def test_qty_without_supplier_raises():
    """No fallback: an order with qty>0 must name a supplier (like route)."""
    world = World()
    world.reset(3)
    import pytest
    with pytest.raises((ValueError, KeyError)):
        world.step({"qty": 20, "route": "suez"})  # missing supplier


def test_supplier_internals_never_leak():
    """The scorecard is the only supplier surface; rel_state/rel_age/regime
    never appear in any obs (extends the disruption leak gate)."""
    for rec in _spot_episode(3).trace:
        assert not (HIDDEN_KEYS & rec["obs"].keys())


def test_supplier_action_does_not_perturb_either_hidden_trajectory():
    """Exogeneity: the supplier CHOICE never changes the disruption OR the
    supplier reliability trajectory (both are seed-only functions)."""
    a = _spot_episode(11, qty=0)             # never orders
    b = _spot_episode(11, qty=40)            # orders spot every week
    assert [r["hidden"] for r in a.trace] == [r["hidden"] for r in b.trace]


def test_same_seed_same_two_factor_trace():
    assert _spot_episode(7).trace == _spot_episode(7).trace


# --- R3: contracts (a timer + terms; observed deterministic structure) -----

def test_contract_fields_and_books_list():
    """A Contract carries supplier, the tick window, and terms. Books holds a
    list of them (instance list, not a singleton -> dual-sourcing is legal by
    data shape, R6)."""
    c = Contract(supplier="spot", start_week=2, end_week=8,
                 unit_price=4.0, otif_floor=85, break_fee=10.0)
    assert c.supplier == "spot" and c.start_week == 2 and c.end_week == 8
    books = Books(inventory=0)
    assert books.contracts == []
    books.contracts.append(c)
    assert books.contracts[0] is c


def test_contract_open_when_expired():
    """The standing rule's predicate: a contract is OPEN (needs renewal) once
    week >= end_week. A condition, never a hard-coded date."""
    c = Contract(supplier="spot", start_week=0, end_week=5,
                 unit_price=4.0, otif_floor=85, break_fee=10.0)
    alive = {"spot": True, "qualified": True, "backup": True}
    assert not contract_open(c, week=4, alive=alive)
    assert contract_open(c, week=5, alive=alive)
    assert contract_open(c, week=9, alive=alive)


def test_contract_open_when_counterparty_defunct():
    """The EMERGENCE hook: a live (un-expired) contract becomes OPEN the moment
    its supplier is defunct -- so the defunct primitive (R2) triggers renewal
    with no scenario code. This is Lever-1 meeting Lever-2."""
    c = Contract(supplier="spot", start_week=0, end_week=20,
                 unit_price=4.0, otif_floor=85, break_fee=10.0)
    alive_ok = {"spot": True, "qualified": True, "backup": True}
    alive_dead = {"spot": False, "qualified": True, "backup": True}
    assert not contract_open(c, week=3, alive=alive_ok)   # mid-lock, supplier alive
    assert contract_open(c, week=3, alive=alive_dead)     # supplier died -> open!


# --- R4: standing rule + action mask in the engine (Lever 2 emergence) ------

def test_episode_starts_pre_contracted_to_qualified():
    """Week 0: the agent already holds a live qualified contract (you don't
    start a supply chain with no supplier). obs exposes it; nothing is open."""
    w = World()
    obs0 = w.reset(3)
    assert len(w.books.contracts) == 1
    c = w.books.contracts[0]
    assert c.supplier == "qualified" and c.start_week == 0
    assert obs0["contracts"] and obs0["contracts"][0]["supplier"] == "qualified"
    assert obs0["contract_open"] == []  # nothing to renew at the start


def test_cannot_source_supplier_without_a_live_contract():
    """Per-contract granularity: ordering from a supplier you are NOT
    contracted with raises (no fallback). Spot has no contract at start."""
    w = World()
    w.reset(3)
    with pytest.raises(ValueError):
        w.step({"qty": 20, "supplier": "spot", "route": "suez"})
    # but qualified (the live contract) is fine
    obs, *_ = w.step({"qty": 20, "supplier": "qualified", "route": "suez"})
    assert obs["week"] == 1


def test_sign_contract_action_then_source_it():
    """A `contract` sub-action signs a spot contract; afterwards spot is a
    legal sourcing choice."""
    w = World()
    w.reset(3)
    w.step({"qty": 0, "contract": {"action": "sign", "supplier": "spot"}})
    assert any(c.supplier == "spot" for c in w.books.contracts)
    # now sourcing spot is allowed
    obs, *_ = w.step({"qty": 20, "supplier": "spot", "route": "suez"})
    assert obs["week"] == 2


def test_expired_contract_surfaces_as_open():
    """A time-boxed SPOT contract (end_week=8) opens once week reaches it; the
    evergreen qualified incumbent never opens. Default length 8 wks (R4)."""
    w = World()
    w.reset(3)
    w.step({"qty": 0, "contract": {"action": "sign", "supplier": "spot"}})
    last = None
    for _ in range(9):
        last, *_ = w.step({"qty": 20, "supplier": "qualified", "route": "suez"})
    # the spot contract signed at week 0 (end_week=8) is now open; qualified isn't
    assert "spot" in last["contract_open"]
    assert "qualified" not in last["contract_open"]


def test_defunct_spot_auto_opens_its_contract_no_script():
    """THE EMERGENCE PROOF (unit level): sign a long spot contract, force spot
    to defunct, and the contract opens on its OWN -- no scripted week, no
    per-event code. Lever 1 (defunct) x Lever 2 (standing rule)."""
    w = World()
    w.reset(3)
    w.step({"qty": 0, "contract": {"action": "sign", "supplier": "spot"}})
    # forcibly kill spot (simulate the primitive having fired)
    w.suppliers["spot"] = SupplierState(rel_state="defunct")
    obs, *_ = w.step({"qty": 0})  # a do-nothing week
    assert "spot" in obs["contract_open"], "dead supplier must auto-open its contract"


# --- R5: negotiation menu (finite term offers, bounded to one tick) ---------

def test_term_menu_has_the_four_archetypes():
    """The menu is finite and named: short/long/strict/lenient. Each is a
    distinct (weeks, price, floor, break_fee) profile -- the spot-vs-contract
    trade-off as a choosable menu, not a bargaining loop."""
    assert set(TERM_MENU) == {"short", "long", "strict", "lenient"}
    short, long = TERM_MENU["short"], TERM_MENU["long"]
    assert short["weeks"] < long["weeks"]              # short locks briefly
    assert short["unit_price_mult"] < long["unit_price_mult"]  # long pays a lock premium
    assert TERM_MENU["strict"]["otif_floor"] > TERM_MENU["lenient"]["otif_floor"]


def test_terms_for_builds_contract_fields():
    """terms_for(menu_key, supplier, start, cfg) yields the concrete contract
    field values for that menu choice."""
    fields = terms_for("long", "spot", start=3, cfg=CFG)
    assert fields["end_week"] == 3 + TERM_MENU["long"]["weeks"]
    assert fields["unit_price"] == CFG.suez_unit_cost * TERM_MENU["long"]["unit_price_mult"]
    assert fields["otif_floor"] == TERM_MENU["long"]["otif_floor"]


def test_sign_with_terms_uses_the_chosen_profile():
    """Signing a spot contract with terms='short' produces a 4-week contract;
    'long' produces a 12-week one. The negotiation is this selection."""
    w = World()
    w.reset(3)
    w.step({"qty": 0, "contract": {"action": "sign", "supplier": "spot",
                                   "terms": "long"}})
    c = next(c for c in w.books.contracts if c.supplier == "spot")
    assert c.end_week == 0 + TERM_MENU["long"]["weeks"]


def test_obs_offers_term_menu_at_open():
    """At contract_open the obs carries the offered menu keys so the agent can
    choose. (Always present; it's a stable finite menu.)"""
    w = World()
    obs0 = w.reset(3)
    assert set(obs0["term_menu"]) == {"short", "long", "strict", "lenient"}


# --- R6: dual-source overhead (Lever 3) + the hard-gap ----------------------

def test_single_contract_has_no_dual_source_overhead():
    """One live contract (the evergreen incumbent) => no overhead charged."""
    w = World()
    w.reset(3)
    _, costs, *_ = w.step({"qty": 20, "supplier": "qualified", "route": "suez"})
    # cost_breakdown is in the obs; dual_source absent or zero with one contract
    obs = w.trace[-1]["obs"]
    assert obs["cost_breakdown"].get("dual_source", 0.0) == 0.0


def test_two_live_contracts_incur_dual_source_overhead():
    """Signing a second (spot) contract alongside the incumbent => the weekly
    dual_source_overhead is charged. The cost gradient that makes hedging a
    real trade-off."""
    w = World()
    w.reset(3)
    w.step({"qty": 0, "contract": {"action": "sign", "supplier": "spot"}})
    _, costs, *_ = w.step({"qty": 20, "supplier": "qualified", "route": "suez"})
    obs = w.trace[-1]["obs"]
    assert obs["cost_breakdown"]["dual_source"] == CFG.dual_source_overhead


def test_hard_gap_defunct_spot_leaves_you_stuck():
    """Locked decision (hard gap): when an exclusive spot supplier dies, you
    are STUCK -- you cannot even source it (its contract is now open), and
    backup needs onboarding. No scramble. The punishment is the absence of an
    escape hatch; proven from R2 (defunct) x R4 (the mask), not coded."""
    w = World()
    w.reset(3)
    w.step({"qty": 0, "contract": {"action": "sign", "supplier": "spot"}})
    w.suppliers["spot"] = SupplierState(rel_state="defunct")
    # a dead spot is no longer contractable: sourcing it raises (the hard gap).
    with pytest.raises(ValueError):
        w.step({"qty": 40, "supplier": "spot", "route": "suez"})
    # and even a renew cannot make a dead supplier sourceable this week
    w.suppliers["spot"] = SupplierState(rel_state="defunct")
    assert "spot" not in w._contracted_suppliers()


def test_supplier_module_drives_only_drifting_roster_ids():
    """The supplier module advances exactly the roster ids whose profile
    sets drifts=True (only spot in R1), read from SUPPLIERS -- no literal
    'spot' in the module record."""
    from src.world.registry import SUPPLIER
    from src.world.modules.supplier import SUPPLIERS
    assert SUPPLIER.drives == tuple(sid for sid, p in SUPPLIERS.items()
                                    if p["drifts"])
    assert SUPPLIER.drives == ("spot",)


def test_disruption_emit_byte_identical_to_handbuilt_obs():
    """The disruption module's emit reproduces the count keys (renamed
    through the per-semantics map) plus the bulletin, byte-for-byte, in
    BOTH semantics modes -- so swapping _build_obs to call emit cannot move
    a single byte."""
    from src.world.registry import DISRUPTION
    from src.world.modules.disruption import COUNT_KEYS
    states = [CALM, HiddenState("watch"), SHORT, LONG,
              HiddenState("disruption", 1, "short"),
              HiddenState("disruption", 1, "long"), RECOV,
              HiddenState("false_alarm"),
              HiddenState(cape_local_congestion=True)]
    for mode in ("real", "anon"):
        mcfg = WorldConfig(semantics=mode)
        keymap = COUNT_KEYS[mode]
        for h in states:
            hand = {keymap[k]: v
                    for k, v in observe_counts(h, mcfg).items()}
            hand["bulletin"] = news_bulletin(h, mcfg)
            assert DISRUPTION.emit(h, mcfg) == hand, (mode, h)


def test_supplier_emit_byte_identical_to_scorecard():
    """The supplier module's emit IS observe_scorecard -- byte-for-byte over
    the whole roster, in both semantics modes."""
    from src.world.registry import SUPPLIER
    for mode in ("real", "anon"):
        mcfg = WorldConfig(semantics=mode)
        for state in ("reliable", "wobbling", "degraded", "defunct"):
            rost = roster(rel_state=state)
            assert SUPPLIER.emit(rost, mcfg) == observe_scorecard(rost, mcfg), \
                (mode, state)


# --- emit-driven obs: the scorecard economics golden (DRIFT RISK net) -------

def test_scorecard_economics_golden_all_three_rows():
    """Folding the per-supplier economics into a profile lookup is the one
    place a number could silently drift. Pin the FULL economics fragment of
    every row (incl. backup) byte-for-byte. spot shows unit_discount, qualified
    unit_premium, backup neither -- only a signed unit_delta."""
    sc = scorecard(rel_state="wobbling")  # spot drifting -> slipping band
    rows = {r["id"]: r for r in sc["suppliers"]}
    assert rows["qualified"]["unit_premium"] == CFG.qualified_premium
    assert rows["qualified"]["unit_delta"] == CFG.qualified_premium
    assert "unit_discount" not in rows["qualified"]
    assert rows["spot"]["unit_discount"] == CFG.spot_unit_discount
    assert rows["spot"]["unit_delta"] == -CFG.spot_unit_discount
    assert "unit_premium" not in rows["spot"]
    assert rows["backup"]["unit_delta"] == CFG.backup_unit_delta
    assert "unit_discount" not in rows["backup"]
    assert "unit_premium" not in rows["backup"]
    # frozen OTIF/lead/onboard now live in the SUPPLIERS profile, not cfg
    from src.world.modules.supplier import SUPPLIERS
    assert rows["backup"]["otif"] == SUPPLIERS["backup"]["otif"] == 95
    assert rows["backup"]["lead_days"] == SUPPLIERS["backup"]["lead"] == 16
    assert rows["backup"]["onboard_lead"] == SUPPLIERS["backup"]["onboard_weeks"] == 1


def test_full_obs_unchanged_emit_driven():
    """The whole obs (a real episode, fixed seed) is assembled by iterating
    REGISTRY now. Drive two weeks sourcing spot and assert every obs key the
    modules own is present and the engine keys are intact -- the leak guard
    and the byte-identical emit pins (Task 1) are the deeper net."""
    w = World()
    obs0 = w.reset(3)
    # disruption slice + supplier slice both present from week 0
    assert {"suez_count", "bab_count", "cape_count", "bulletin"} <= obs0.keys()
    assert "suppliers" in obs0 and len(obs0["suppliers"]) == 3
    # engine-owned keys intact
    assert {"week", "inventory", "arrived", "pipeline", "cost_breakdown",
            "contracts", "contract_open", "term_menu"} <= obs0.keys()
    assert not (HIDDEN_KEYS & obs0.keys())


# --- _view presentation manifest (display-only; never a value channel) -----

def test_view_manifest_present_with_roles():
    """Every obs carries a _view map keyed by obs-key, each {role,label}. The
    count keys are scalars, the bulletin a series, the scorecard a roster-row.
    Raw value keys are unchanged -- _view is additive."""
    w = World()
    obs = w.reset(3)
    view = obs["_view"]
    assert view["suez_count"]["role"] == "scalar"
    assert view["bab_count"]["role"] == "scalar"
    assert view["cape_count"]["role"] == "scalar"
    assert view["bulletin"]["role"] == "series"
    assert view["suppliers"]["role"] == "roster-row"
    # additive: the raw value keys still exist untouched
    assert {"suez_count", "bab_count", "cape_count", "bulletin",
            "suppliers"} <= obs.keys()


def test_view_is_skipped_by_leak_guard_and_holds_no_hidden_key():
    """_view is exempt from the hidden-leak assert (it's presentation), but it
    must itself never name a hidden-state field."""
    for rec in run_episode(3).trace:
        v = rec["obs"]["_view"]
        assert not (HIDDEN_KEYS & v.keys())
        # the leak guard still holds over the value keys
        assert not (HIDDEN_KEYS & (rec["obs"].keys() - {"_view"}))


def test_view_labels_never_leak_real_names_in_anon():
    """Issue 4 anti-leak: _view labels come through the per-semantics maps (or
    are fixed UI words), so an anon episode's manifest exposes no real
    waterway/supplier referent -- a side channel the HIDDEN_KEYS guard would
    NOT catch."""
    w = World(WorldConfig(semantics="anon"))
    obs = w.reset(3)
    labels = " ".join(str(d.get("label", "")) for d in obs["_view"].values()).lower()
    for tok in FORBIDDEN_REAL_TOKENS:
        assert tok not in labels, f"anon _view leaks {tok!r}"
    # the anon count labels ARE the anon vocabulary (came through COUNT_KEYS)
    assert "waterway1_count" in labels and "waterway2_count" in labels


# --- module 3: demand (first goal-2 factor; RICH world only; noisy v2) -----

def test_demand_band_onset_ambiguity():
    """The deliberate 1-week ambiguity (mirrors disruption 'crash'): promo and
    seasonal ONSET (age 0) share the 'surge' MEAN -> indistinguishable in
    expectation; at age>=1 the means separate (promo 26 vs seasonal 30)."""
    from src.world.modules.demand import DemandState, DEMAND_MEANS
    promo0, seas0 = DemandState("promo_spike", 0), DemandState("seasonal_lift", 0)
    assert promo0.band == seas0.band == "surge"
    assert promo0.mean == seas0.mean == DEMAND_MEANS["surge"]
    promo1, seas1 = DemandState("promo_spike", 1), DemandState("seasonal_lift", 1)
    assert (promo1.band, seas1.band) == ("promo", "seasonal")
    assert promo1.mean != seas1.mean
    assert DemandState("normal").band == "base"
    assert DemandState("structural_decline").band == "depressed"


def test_demand_emit_is_noisy_pos_plus_forecast_no_leak():
    """emit exposes the realized POS + the forward forecast (per-week draws on
    the state), and NOTHING that leaks the hidden regime/age."""
    from src.world.modules.demand import DemandState, emit
    st = DemandState("seasonal_lift", 2, realized=33, forecast=28)
    assert emit(st, CFG) == {"pos_units": 33, "demand_forecast": 28}
    assert not ({"regime", "regime_age", "band"} & set(emit(st, CFG)))


def test_demand_realized_is_noisy_around_the_mean():
    """v2 fix for 'too deterministic': realized POS is a noisy draw around the
    regime mean, so it is NOT a flat constant and the regime must be filtered."""
    import random, statistics
    from src.world.modules.demand import DemandState, step_demand
    rng = random.Random(1)
    vals, s = [], DemandState("normal")
    for _ in range(500):
        s = step_demand(s, rng, CFG)
        if s.regime == "normal":
            vals.append(s.realized)
    assert len(set(vals)) > 5                      # genuinely noisy, not constant
    assert abs(statistics.mean(vals) - 20) < 1.5   # centered on the base mean


def test_demand_kernel_promo_fixed_length_decline_sticky():
    """promo is a fixed-length calendar event (exactly demand_promo_max wks);
    decline is sticky. Semi-Markov (age-driven). Noise draws don't change the
    regime logic."""
    import random
    from src.world.modules.demand import DemandState, step_demand
    rng = random.Random(0)
    s = DemandState("promo_spike", 0)
    for _ in range(CFG.demand_promo_max - 1):
        s = step_demand(s, rng, CFG)
        assert s.regime == "promo_spike"
    assert step_demand(s, rng, CFG).regime == "normal"  # deterministic exit at cap
    persists = sum(step_demand(DemandState("structural_decline", 1), rng, CFG).regime
                   == "structural_decline" for _ in range(400))
    assert persists / 400 > 0.9


def test_rich_world_demand_drives_consumption_and_is_deterministic():
    from src.world.registry import RICH
    def run(seed):
        w = World(registry=RICH); w.reset(seed); rows = []
        while not w.done:
            o, c, _, _ = w.step({"qty": 20, "route": "suez", "supplier": "qualified"})
            rows.append((o["pos_units"], o["demand_forecast"], round(c, 4)))
        return rows
    assert run(3) == run(3)  # deterministic despite the noise (seeded rng)
    bands = set()
    for seed in range(60):
        w = World(registry=RICH); w.reset(seed)
        while not w.done:
            w.step({"qty": 20, "route": "suez", "supplier": "qualified"})
            bands.add(w.module_states["demand"].band)
    assert {"surge", "seasonal", "promo", "depressed"} <= bands


def test_rich_world_obs_has_forward_forecast_channel():
    """The agent gets a FORWARD demand-sensing signal, not just backward POS."""
    from src.world.registry import RICH
    w = World(registry=RICH); obs = w.reset(7)
    assert "pos_units" in obs and "demand_forecast" in obs


# --- module 4: freight (noisy spot rate; cost-multiplier effect; RICH only) -

def test_freight_in_rich_registry_after_demand():
    """RICH appends factors in a fixed order after the base two; later factors
    append after freight, so each new factor's rng draws come last and the
    disruption golden is unperturbed."""
    from src.world.registry import REGISTRY, RICH
    assert tuple(m.id for m in REGISTRY) == ("disruption", "supplier")
    assert tuple(m.id for m in RICH)[:4] == ("disruption", "supplier", "demand", "freight")


def test_freight_band_gri_onset_ambiguity():
    """GRI-week ambiguity (mirrors disruption 'crash'): tightening & spike ONSET
    share the 'jump' mean; at age>=1 they separate (high plateau vs peak climb)."""
    from src.world.modules.freight import FreightState, FREIGHT_MEANS
    t0, s0 = FreightState("tightening", 0), FreightState("spike", 0)
    assert t0.band == s0.band == "jump"
    assert t0.mean == s0.mean == FREIGHT_MEANS["jump"]
    t1, s1 = FreightState("tightening", 1), FreightState("spike", 1)
    assert (t1.band, s1.band) == ("high", "peak")
    assert t1.mean != s1.mean
    assert FreightState("slack").band == "low" and FreightState("normal").band == "mid"


def test_freight_emit_index_outlook_no_leak():
    from src.world.modules.freight import FreightState, emit
    f = FreightState("spike", 2, realized_mult=4.2, outlook=3.7)
    assert emit(f, CFG) == {"freight_index": 420, "freight_outlook": 370}
    assert not ({"regime", "regime_age", "band", "realized_mult"} & set(emit(f, CFG)))


def test_freight_effect_scales_route_cost():
    """The freight effect multiplies the route base rate in resolve_week; a spike
    multiplier costs strictly more than normal for the same order."""
    from src.world.substrate.books import Books
    base = resolve_week(Books(80), 20, "qualified", "suez", HiddenState(),
                        SupplierState(), 1, CFG, effects={"freight_mult": 1.0})[1]
    spike = resolve_week(Books(80), 20, "qualified", "suez", HiddenState(),
                         SupplierState(), 1, CFG, effects={"freight_mult": 4.0})[1]
    assert spike["shipping"] > base["shipping"]
    # default world (no effects) == freight_mult 1.0 (byte-identical)
    none = resolve_week(Books(80), 20, "qualified", "suez", HiddenState(),
                        SupplierState(), 1, CFG)[1]
    assert none["shipping"] == base["shipping"]


def test_freight_kernel_spike_decays_slack_sticky():
    import random
    from src.world.modules.freight import FreightState, step_freight
    rng = random.Random(0)
    # spike is age-capped: it cannot persist past fr_spike_max
    s = FreightState("spike", 0)
    weeks = 0
    while s.regime == "spike" and weeks < 50:
        s = step_freight(s, rng, CFG); weeks += 1
    assert weeks <= CFG.fr_spike_max
    # slack is sticky
    persists = sum(step_freight(FreightState("slack"), rng, CFG).regime == "slack"
                   for _ in range(400))
    assert persists / 400 > 0.85


def test_rich_world_freight_deterministic_and_varies():
    from src.world.registry import RICH
    def run(seed):
        w = World(registry=RICH); w.reset(seed); rows = []
        while not w.done:
            o, c, _, _ = w.step({"qty": 20, "route": "suez", "supplier": "qualified"})
            rows.append((o["freight_index"], o["freight_outlook"], round(c, 4)))
        return rows
    assert run(3) == run(3)
    bands = set()
    for seed in range(80):
        w = World(registry=RICH); w.reset(seed)
        while not w.done:
            w.step({"qty": 20, "route": "suez", "supplier": "qualified"})
            bands.add(w.module_states["freight"].band)
    assert {"jump", "high", "peak", "low"} <= bands


def test_freight_lock_pins_rate_until_window_expires():
    """lock_freight is a within-week action (no advance) that FIXES the freight
    multiplier for `weeks` weeks: every locked week pays the locked rate even as
    the spot draw moves, then the window clears."""
    from src.world.registry import RICH
    w = World(registry=RICH); w.reset(3)
    locked = w.lock_freight(3)["rate"]
    assert w.week == 0                              # within-week: does not advance
    expected = 20 * (CFG.suez_unit_cost * locked + CFG.qualified_premium)
    drawn = []
    for _ in range(3):
        o, _, _, _ = w.step({"qty": 20, "route": "suez", "supplier": "qualified"})
        assert o["cost_breakdown"]["shipping"] == pytest.approx(expected)
        drawn.append(w.module_states["freight"].realized_mult)
    # the lock truly OVERRODE a different spot (not a coincidence of equal draws)
    assert any(abs(d - locked) > 0.01 for d in drawn)
    # window expired -> lock cleared, rate floats again
    assert w.books.freight_lock is None
    o, _, _, _ = w.step({"qty": 20, "route": "suez", "supplier": "qualified"})
    assert "freight_lock" not in o
    floated = 20 * (CFG.suez_unit_cost * w.module_states["freight"].realized_mult
                    + CFG.qualified_premium)
    assert o["cost_breakdown"]["shipping"] == pytest.approx(floated)


def test_lock_freight_tool_only_in_rich_world():
    """lock_freight exists only where a freight market does; the 2-factor world
    keeps the two-tool surface (and the oracle never sees a lock)."""
    from src.agent.tools import make_tools
    from src.world.registry import RICH

    class FakeRun:
        def __init__(self, registry):
            self.world = World(registry=registry); self.world.reset(3)
        def record(self, *a):
            pass

    base = [t.name for t in make_tools(FakeRun(None))]
    rich = [t.name for t in make_tools(FakeRun(RICH))]
    assert base == ["buy_briefing", "place_order"]
    assert "lock_freight" in rich


# --- module 5: port/customs (lead-time + demurrage effect; RICH only) ------

def test_port_in_rich_registry_after_freight():
    from src.world.registry import REGISTRY, RICH
    assert tuple(m.id for m in REGISTRY) == ("disruption", "supplier")
    ids = tuple(m.id for m in RICH)
    assert "port" in ids and ids.index("port") > ids.index("freight")


def test_port_band_onset_ambiguity():
    """congested & customs_hold ONSET share the 'slow' band (mirrors crash); at
    age>=1 a persisting hold/backlog reads 'congested'."""
    from src.world.modules.port import PortState
    c0, h0 = PortState("congested", 0), PortState("customs_hold", 0)
    assert c0.band == h0.band == "slow"
    assert c0.mean == h0.mean
    assert PortState("congested", 1).band == "congested"
    assert PortState("clear").band == "clear" and PortState("building").band == "building"


def test_port_emit_no_leak():
    from src.world.modules.port import PortState, emit
    p = PortState("congested", 2, berth_wait=17, wait_outlook=15)
    assert emit(p, CFG) == {"berth_wait": 17, "wait_outlook": 15}
    assert not ({"regime", "regime_age", "band", "blocked"} & set(emit(p, CFG)))


def test_port_blocked_holds_arrivals_and_charges_demurrage():
    """A blocked port holds this week's arrivals +1 week and charges demurrage;
    a clear port lands them (and the default world, no effect, lands them)."""
    from src.world.substrate.books import Books, Shipment
    def due():  # a ship due to arrive at week 5
        b = Books(80)
        b.pipeline = [Shipment(20, "suez", 2, "qualified", arrives_week=5)]
        return b
    clear_b = due()
    arrived, costs = resolve_week(clear_b, 0, None, None, HiddenState(),
                                  SupplierState(), 5, CFG, effects={})
    assert arrived == 20 and "demurrage" not in costs and not clear_b.pipeline
    block_b = due()
    arrived, costs = resolve_week(
        block_b, 0, None, None, HiddenState(), SupplierState(), 5, CFG,
        effects={"port_blocked": True, "demurrage_rate": CFG.port_demurrage_rate})
    assert arrived == 0
    assert costs["demurrage"] == CFG.port_demurrage_rate * 20
    assert block_b.pipeline[0].arrives_week == 6   # held a week


def test_port_kernel_congestion_capped_customs_short():
    import random
    from src.world.modules.port import PortState, step_port
    rng = random.Random(0)
    s, weeks = PortState("congested", 0), 0
    while s.regime == "congested" and weeks < 50:
        s = step_port(s, rng, CFG); weeks += 1
    assert weeks <= CFG.port_congest_max
    # a customs hold is short: usually clears within a couple of weeks
    cleared = sum(step_port(PortState("customs_hold"), rng, CFG).regime == "clear"
                  for _ in range(400))
    assert cleared / 400 > 0.6


def test_rich_world_port_deterministic_and_demurrage_occurs():
    from src.world.registry import RICH
    def run(seed):
        w = World(registry=RICH); w.reset(seed); rows = []
        while not w.done:
            o, c, _, _ = w.step({"qty": 20, "route": "suez", "supplier": "qualified"})
            rows.append((o["berth_wait"], round(c, 4)))
        return rows
    assert run(3) == run(3)
    charged = 0
    for seed in range(40):
        w = World(registry=RICH); w.reset(seed)
        while not w.done:
            o, _, _, _ = w.step({"qty": 20, "route": "suez", "supplier": "qualified"})
            charged += "demurrage" in o["cost_breakdown"]
    assert charged > 0


# --- module 6: quality (NOISY discrete AQL emission; RICH only) ------------

def test_quality_completes_the_six_factor_world():
    from src.world.registry import REGISTRY, RICH
    assert tuple(m.id for m in REGISTRY) == ("disruption", "supplier")
    assert tuple(m.id for m in RICH) == ("disruption", "supplier", "demand",
                                         "freight", "port", "quality")


def test_quality_aql_sample_is_noisy():
    """The distinctive feature: the observation is a NOISY discrete AQL sample,
    so no single reading identifies the regime (the belief never collapses)."""
    import random
    from src.world.modules.quality.factor import _sample_band
    rng = random.Random(0)
    ic = [_sample_band("in_control", rng) for _ in range(1000)]
    assert ic.count("accept") > 800 and "marginal" in ic    # noisy, mostly accept
    oc = [_sample_band("out_of_control", rng) for _ in range(1000)]
    assert oc.count("reject") > 600                          # mostly reject
    dr = [_sample_band("drifting", rng) for _ in range(1000)]
    assert len(set(dr)) == 3                                 # drifting straddles


def test_quality_emit_no_leak():
    from src.world.modules.quality import QualityState, emit
    q = QualityState("out_of_control", 3, sample_band="reject")
    assert emit(q, CFG) == {"aql_result": "reject"}
    assert not ({"regime", "regime_age"} & set(emit(q, CFG)))


def test_quality_defect_reduces_usable_arrivals_and_charges_rework():
    """Defective arrivals don't stock (effective shortfall) and incur rework;
    the default world (no effect) stocks everything, no rework key."""
    from src.world.substrate.books import Books, Shipment
    def due():
        b = Books(80)
        b.pipeline = [Shipment(40, "suez", 2, "qualified", arrives_week=5)]
        return b
    clean = due()
    arrived, costs = resolve_week(clean, 0, None, None, HiddenState(),
                                  SupplierState(), 5, CFG, effects={})
    assert arrived == 40 and "rework" not in costs
    defq = due()
    arrived, costs = resolve_week(
        defq, 0, None, None, HiddenState(), SupplierState(), 5, CFG,
        effects={"defect_fraction": 0.10, "rework_rate": CFG.quality_rework_cost})
    assert arrived == 36                                   # 4 of 40 defective
    assert costs["rework"] == CFG.quality_rework_cost * 4


def test_quality_drift_hazard_rises_with_age():
    """Semi-Markov 'gradual then sudden': drifting->out hazard rises with age."""
    import random
    from src.world.modules.quality import QualityState, step_quality
    rng = random.Random(0)
    def out_rate(age, n=3000):
        return sum(step_quality(QualityState("drifting", age), rng, CFG).regime
                   == "out_of_control" for _ in range(n)) / n
    assert out_rate(0) < out_rate(5)


def test_rich_six_factor_world_deterministic():
    from src.world.registry import RICH
    def run(seed):
        w = World(registry=RICH); w.reset(seed); rows = []
        while not w.done:
            o, c, _, _ = w.step({"qty": 20, "route": "suez", "supplier": "qualified"})
            rows.append((o["aql_result"], o["pos_units"], o["freight_index"],
                         o["berth_wait"], round(c, 4)))
        return rows
    assert run(5) == run(5)


# --- anti-leak: the cost/arrival side channels must NOT exactly reveal the regime

def test_quality_realized_defect_is_a_noisy_sample_not_an_exact_regime_readout():
    """Root-cause-#1 fix: the realized batch defect fraction is a NOISY finite-
    batch sample around the regime mean, so a fixed regime yields a RANGE of
    defective counts -- arrived/rework no longer invert to the regime exactly."""
    import random
    from src.world.modules.quality import QualityState, step_quality
    rng = random.Random(1)
    fr = [nq.realized_defect for _ in range(3000)
          if (nq := step_quality(QualityState("out_of_control", 2), rng, CFG)
              ).regime == "out_of_control"]
    assert len(fr) > 200
    counts = sorted({round(40 * f) for f in fr})       # defective count on a 40-batch
    assert len(counts) >= 3 and counts[0] != counts[-1]  # noisy, not a 1:1 readout


def test_quality_effect_passes_the_per_week_realized_fraction_not_the_table():
    from src.world.modules.quality import QualityState, effect
    q = QualityState("out_of_control", 2, realized_defect=0.075)
    assert effect(q, CFG)["defect_fraction"] == 0.075  # the realized draw, not 0.06


def test_rich_cost_keyset_does_not_leak_hidden_state():
    """The demurrage/rework keys are emitted EVERY week in RICH (0.0 when inert),
    so the cost_breakdown key SET is not a boolean readout of the hidden port/
    quality state. The default 2-factor world emits neither key (byte-identical)."""
    from src.world.registry import RICH
    w = World(registry=RICH); w.reset(7)
    while not w.done:
        o, _, _, _ = w.step({"qty": 20, "route": "suez", "supplier": "qualified"})
        assert "demurrage" in o["cost_breakdown"]
        assert "rework" in o["cost_breakdown"]
    w2 = World(); w2.reset(7)
    o2, _, _, _ = w2.step({"qty": 20, "route": "suez", "supplier": "qualified"})
    assert "demurrage" not in o2["cost_breakdown"]
    assert "rework" not in o2["cost_breakdown"]


# --- masked-distress supplier task (cfg.sup_mask_otif) -----------------------

MASKED = WorldConfig(sup_mask_otif=True)


def _spot_row(rel_state, rel_age=0, lead_slip=0.0, cfg=MASKED):
    rows = observe_scorecard(
        {"spot": SupplierState(rel_state, rel_age, lead_slip)}, cfg)["suppliers"]
    return rows[0]


def test_mask_otif_lags_true_regime():
    """The masked scorecard reads healthier than the truth: a wobble and the
    onset of degradation both still show 'ontime'; only deep failure surfaces
    (as a mild 'slipping'), and death always shows. The legacy world is
    byte-identical (true band, no lead-slip key)."""
    assert _spot_row("wobbling")["band"] == "ontime"        # a slip reads on-time
    assert _spot_row("degraded", 0)["band"] == "ontime"     # onset hidden
    assert _spot_row("degraded", 1)["band"] == "slipping"   # deep fail -> "slip"
    assert _spot_row("defunct")["band"] == "defunct"        # death always shows
    assert _spot_row("wobbling", lead_slip=4.2)["realized_lead_slip"] == 4.2
    legacy = _spot_row("wobbling", cfg=WorldConfig())
    assert legacy["band"] == "slipping" and legacy["otif"] == 82
    assert "realized_lead_slip" not in legacy


def test_audit_reveals_true_band_and_charges_once():
    w = World(MASKED); w.reset(7)
    w.suppliers["spot"] = SupplierState("degraded", 1)   # truly failing
    txt = w.request_audit()
    assert "failing" in txt                              # names the TRUE band
    assert w.request_audit() == txt                      # cached, same week
    w.step({"qty": 0})
    assert w.trace[-1]["obs"]["cost_breakdown"].get("audit") == w.cfg.audit_cost


def test_realized_fill_present_only_on_spot_order():
    w = World(MASKED); w.reset(7)        # masked task starts contracted to spot
    obs, *_ = w.step({"qty": 40, "supplier": "spot", "route": "suez"})
    assert obs["realized_fill"] == w.suppliers["spot"].fulfilled_fraction
    obs2, *_ = w.step({"qty": 0})        # absent when you didn't source spot
    assert "realized_fill" not in obs2


def test_masked_fill_is_noisy_not_deterministic():
    """Masked task: realized fill is a noisy per-week draw, so a single fill no
    longer pins the regime -- a healthy supplier can have an unlucky (<1.0) week.
    Legacy keeps the deterministic lookup (reliable==1.0 exactly)."""
    from src.world.modules.supplier import step_supplier
    rng = random.Random(3)
    fills, s = [], SupplierState()
    for _ in range(60):
        s = step_supplier(s, rng, MASKED)
        if s.rel_state == "reliable":
            fills.append(s.fulfilled_fraction)
    assert fills, "no reliable weeks sampled"
    assert any(f < 1.0 for f in fills) and all(0.0 <= f <= 1.0 for f in fills)
    assert SupplierState("reliable").fulfilled_fraction == 1.0   # legacy exact


def test_masked_starts_on_spot_not_qualified():
    """The masked task inverts the incumbent: you begin contracted to spot
    (evergreen), and qualified is an opt-in migration target."""
    w = World(MASKED); w.reset(7)
    assert w._contracted_suppliers() == {"spot"}
    # legacy world is unchanged: starts on qualified
    lw = World(); lw.reset(7)
    assert lw._contracted_suppliers() == {"qualified"}


def test_masked_obs_no_hidden_leak():
    w = World(MASKED); w.reset(7)
    obs, *_ = w.step({"qty": 20, "supplier": "spot", "route": "suez"})
    assert not (HIDDEN_KEYS & obs.keys())                # engine guard holds
    spot = next(r for r in obs["suppliers"] if "realized_lead_slip" in r)
    assert "rel_state" not in spot and "rel_age" not in spot  # row carries no regime


def test_masked_flag_off_draws_no_extra_rng():
    """Flag OFF must not perturb the supplier trajectory (no lead-slip draw), so
    the legacy world stays a function of the seed alone."""
    legacy = [SupplierState().rel_state]
    w = World(); w.reset(11)
    while not w.done:
        w.step({"qty": 0})
        legacy.append(w.suppliers["spot"].rel_state)
    w2 = World(); w2.reset(11)
    seq = [SupplierState().rel_state]
    while not w2.done:
        w2.step({"qty": 0})
        seq.append(w2.suppliers["spot"].rel_state)
    assert legacy == seq  # deterministic, unaffected by the masked-task code


def test_core_registry_runs_stochastic_demand():
    """CORE = (disruption, supplier, demand): the scored world emits a NOISY
    weekly POS that varies week to week (demand is no longer flat), and never
    leaks the hidden demand regime."""
    from src.world.registry import CORE
    assert [m.id for m in CORE] == ["disruption", "supplier", "demand"]
    w = World(WorldConfig(), registry=CORE)
    w.reset(7)
    pos = []
    while not w.done:
        obs, *_ = w.step({"qty": 0})
        assert "pos_units" in obs               # demand channel is live
        assert not (HIDDEN_KEYS & obs.keys())   # regime stays hidden
        pos.append(obs["pos_units"])
    assert len(set(pos)) > 1                     # stochastic, not the flat constant


def test_supplier_economics_read_profile_not_spot_literal():
    """resolve_week keys off the supplier PROFILE, not the "spot" literal:
    backup prices via its econ delta (+0.3, previously mis-billed as qualified's
    +1.0), and a drifting supplier still short-ships per its fulfilled_fraction."""
    from src.world.substrate.logistics import resolve_week
    from src.world.substrate.books import Books
    from src.world.modules.disruption import HiddenState
    from src.world.modules.supplier import SupplierState
    cfg = WorldConfig()
    # backup: non-drifting, econ delta +0.3 over the Suez base (4.0) -> 4.3/unit.
    books = Books(inventory=80)
    _arrived, costs = resolve_week(books, 20, "backup", "suez", HiddenState(),
                                   SupplierState(), week=0, cfg=cfg)
    assert costs["shipping"] == 20 * (cfg.suez_unit_cost + cfg.backup_unit_delta)
    # a drifting supplier (degraded) ships short, driven by its state, not "spot".
    books2 = Books(inventory=80)
    degraded = SupplierState(rel_state="degraded")     # fulfilled_fraction 0.0
    _a2, _c2 = resolve_week(books2, 20, "spot", "suez", HiddenState(),
                            degraded, week=0, cfg=cfg)
    assert books2.pipeline == []                        # 0 units shipped


def test_inventory_position_and_fill_rate():
    """inventory_position = on_hand + on_order (lost-sales, no backorders); the
    run-level fill_rate = served/demanded is well-formed."""
    from src.world.registry import CORE
    w = World(WorldConfig(), registry=CORE)
    obs = w.reset(7)
    assert obs["inventory_position"] == obs["inventory"] + obs["on_order"] == 80
    while not w.done:
        obs, *_ = w.step({"qty": 20, "route": "suez", "supplier": "qualified"})
        on_order = sum(s["qty"] for s in obs["pipeline"])
        assert obs["on_order"] == on_order
        assert obs["inventory_position"] == obs["inventory"] + on_order
    assert 0.0 <= w.fill_rate <= 1.0
    assert w.demand_total > 0 and w.served_total <= w.demand_total


def test_base_stock_beats_flat_ladder_under_demand():
    """On the CORE world (noisy demand), the order-up-to-S base-stock policy
    (free qty, service-level S) costs less than the flat always-20 ladder --
    the whole point of making the inventory decision carry weight."""
    from report_oracle import base_stock_cost, fixed_policy_cost
    cfg = WorldConfig()
    seeds = range(1, 11)
    bstock = sum(base_stock_cost(s, cfg) for s in seeds) / 10
    flat = sum(fixed_policy_cost(s, "suez", cfg) for s in seeds) / 10
    assert bstock < flat
