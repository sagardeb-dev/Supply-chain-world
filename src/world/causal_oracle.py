"""Causal-aware oracle: the optimal NON-clairvoyant policy and the
benchmark anchor. Solves the belief-MDP exactly by finite-horizon
expectimax over the agent's information state, using the true kernel but
no knowledge of the future. Regret against this oracle is pure skill
deficit; (causal - clairvoyant) per seed is the luck premium.

Observations are noiseless functions of the regime, so reachable beliefs
are finitely supported: singletons everywhere except the crash week,
where the support is {false_alarm, short-onset, long-onset} — and
sub-beliefs of that when in-flight ships leak more (a ship queued at the
chokepoint rules out false_alarm; a Cape ETA slip reveals a long
crisis). The belief update therefore groups chance branches by the FULL
agent-visible outcome: regime, pipeline state, arrived qty.

Tractability comes from a canonical RELATIVE pipeline encoding: once a
ship's chokepoint has resolved, only (weeks-until-arrival, qty) matter;
queued ships are merged into one qty pool (they resolve identically).
The encoding is value-preserving — every cost in logistics.resolve_week
depends only on these sums — and test_world.py pins the agreement
against the real Books machinery on randomized scenarios.

  pipe = (e0, e1, queued_qty, (q_arr1, q_arr2, q_arr3))
  e0/e1 = (qty, route)|None — orders dispatched this week / last week
          (a chokepoint is met at elapsed == 2, so unresolved ships are
          at most two weeks old); q_arrK = qty landing K weeks out
          (max lead beyond the chokepoint is 3: diverted or congested).

V1_CHANGE_LOG.md 2026-06-11 (c) records the design decisions.
"""

from functools import lru_cache

from .config import REGIME_COUNTS, WorldConfig
from .engine import World
from .semantics import BRIEFINGS

# Hidden core = (event_state, event_age, disruption_type). The iid
# cape_local coin never persists, so it is integrated out at the resolve
# step rather than carried in the belief.

EMPTY_PIPE = (None, None, 0, (0, 0, 0))


def canonical(core: tuple, cfg: WorldConfig) -> tuple:
    """Collapse ages the kernel and the observation never distinguish.
    calm/watch/false_alarm: age-free. long: the regime splits age 0 vs
    >=1, the kernel is age-free. short/recovery: capped at max weeks."""
    s, age, dtype = core
    if s in ("calm", "watch", "false_alarm"):
        return (s, 0, None)
    if s == "disruption":
        cap = 1 if dtype == "long" else cfg.max_short_weeks - 1
        return (s, min(age, cap), dtype)
    return (s, min(age, cfg.max_recovery_weeks - 1), None)


@lru_cache(maxsize=None)
def transition_dist(core: tuple, cfg: WorldConfig) -> tuple:
    """Exact distribution mirror of transition.step_hidden, sans the iid
    cape_local coin. test_world.py pins the agreement Monte-Carlo."""
    s, age, dtype = core
    out: dict = {}

    def add(s2, age2, d2, p):
        if p <= 0:
            return
        k = canonical((s2, age2, d2), cfg)
        out[k] = out.get(k, 0.0) + p

    if s == "calm":
        add("watch", 0, None, cfg.onset_prob)
        add("calm", age + 1, None, 1 - cfg.onset_prob)
    elif s == "watch":
        pd = cfg.watch_to_disruption_prob
        add("disruption", 0, "short", pd * cfg.short_disruption_prob)
        add("disruption", 0, "long", pd * (1 - cfg.short_disruption_prob))
        add("false_alarm", 0, None, cfg.watch_to_false_alarm_prob)
        add("calm", 0, None, cfg.watch_to_calm_prob)
        add("watch", age + 1, None,
            1 - pd - cfg.watch_to_false_alarm_prob - cfg.watch_to_calm_prob)
    elif s == "disruption" and dtype == "short":
        p_over = (1.0 if age + 1 >= cfg.max_short_weeks
                  else 1 - cfg.short_persist_prob)
        add("recovery", 0, None, p_over)
        add("disruption", age + 1, "short", 1 - p_over)
    elif s == "disruption":
        add("recovery", 0, None, 1 - cfg.long_persist_prob)
        add("disruption", age + 1, "long", cfg.long_persist_prob)
    elif s == "recovery":
        p_over = (1.0 if age + 1 >= cfg.max_recovery_weeks
                  else 1 - cfg.recovery_persist_prob)
        add("calm", 0, None, p_over)
        add("recovery", age + 1, None, 1 - p_over)
    else:  # false_alarm: the scare resolves within the week
        add("calm", 0, None, 1.0)
    return tuple(out.items())


def regime_of(core: tuple) -> str:
    """Mirror of HiddenState.regime on a bare core."""
    s, age, dtype = core
    if s == "false_alarm":
        return "crash"
    if s == "disruption":
        return "crash" if age == 0 else ("blockage" if dtype == "short"
                                         else "crisis")
    return s


def resolve_rel(pipe: tuple, inventory: int, qty: int, route,
                core: tuple, cape_local: bool, cfg: WorldConfig):
    """One week of logistics on the relative encoding — the exact mirror
    of logistics.resolve_week (pinned by test). Returns
    (new_pipe, new_inventory, arrived, step_cost)."""
    e0, e1, queued, (a1, a2, a3) = pipe
    s, _age, dtype = core
    blocked = s == "disruption"
    recovery = s == "recovery"
    cape_congested = cape_local or (blocked and dtype == "long")

    shipping = 0.0
    if qty:
        unit = cfg.suez_unit_cost if route == "suez" else cfg.cape_unit_cost
        shipping = qty * unit
    new_e0 = (qty, route) if qty else None

    surcharge = 0.0
    arr = {1: 0, 2: 0, 3: 0}

    # the queued pool meets the canal again this week
    new_queued = 0
    if queued:
        if blocked:  # diverted around the Cape, billed at the Cape rate
            arr[cfg.divert_extra_weeks] += queued
            surcharge = (cfg.cape_unit_cost - cfg.suez_unit_cost) * queued
        else:        # released: through the canal, lands next week
            arr[cfg.suez_total_weeks - cfg.suez_chokepoint_offset] += queued

    # last week's order reaches its chokepoint (elapsed == 2)
    if e1 is not None:
        q1, r1 = e1
        if r1 == "suez":
            if blocked:
                new_queued += q1
            else:
                extra = cfg.recovery_queue_extra_weeks if recovery else 0
                arr[cfg.suez_total_weeks - cfg.suez_chokepoint_offset
                    + extra] += q1
        else:
            extra = cfg.cape_congested_extra_weeks if cape_congested else 0
            arr[cfg.cape_total_weeks - cfg.cape_chokepoint_offset
                + extra] += q1

    # stored arrivals shift one week closer; delta-1 lands now
    arrived = a1
    new_arr = (a2 + arr[1], a3 + arr[2], arr[3])

    inv = inventory + arrived
    served = min(inv, cfg.weekly_demand)
    shortfall = cfg.weekly_demand - served
    inv -= served

    in_transit = ((new_e0[0] if new_e0 else 0)
                  + (e0[0] if e0 else 0)
                  + new_queued + sum(new_arr))
    cost = (shipping + surcharge + cfg.holding_cost * inv
            + cfg.holding_cost * in_transit + cfg.stockout_cost * shortfall)
    new_pipe = (new_e0, e0, new_queued, new_arr)
    return new_pipe, inv, arrived, cost


# --- the exact belief-MDP DP --------------------------------------------

def _normalize(atoms: dict) -> tuple:
    mass = sum(atoms.values())
    return tuple(sorted((c, round(m / mass, 10)) for c, m in atoms.items()))


def _position(inventory: int, pipe: tuple) -> int:
    e0, e1, queued, arrs = pipe
    return (inventory + (e0[0] if e0 else 0) + (e1[0] if e1 else 0)
            + queued + sum(arrs))


class CausalOracle:
    """Exact expectimax over the belief-MDP. Build once per config (the
    memo is policy-wide, not per-seed); query decide() to play."""

    def __init__(self, cfg: WorldConfig | None = None):
        self.cfg = cfg or WorldConfig()
        cfg = self.cfg
        H = cfg.horizon_weeks
        self._orders = [(0, None)] + [(q, r) for q in cfg.order_quantities
                                      if q for r in ("suez", "cape")]
        orders = self._orders

        @lru_cache(maxsize=None)
        def V(week, belief, inventory, pipe):
            if week > H:
                return 0.0
            best = Q(week, belief, inventory, pipe)
            if len(belief) > 1:  # briefing has zero VOI on a singleton
                briefed = cfg.briefing_cost + sum(
                    p * Q(week, ((core, 1.0),), inventory, pipe)
                    for core, p in belief)
                best = min(best, briefed)
            return best

        @lru_cache(maxsize=None)
        def Q(week, belief, inventory, pipe):
            # dominance prune: never order past total remaining demand
            remaining = cfg.weekly_demand * (H - week + 1)
            acts = (orders if _position(inventory, pipe) < remaining
                    else [(0, None)])
            return min(self._expected(week, belief, inventory, pipe,
                                      qty, route, V)
                       for qty, route in acts)

        self._V, self._Q = V, Q

    def _chance_groups(self, week, belief, inventory, pipe, qty, route):
        """Enumerate chance branches, grouped by the agent-visible
        outcome. Returns {key: [mass, {core: mass}, inv2, pipe2, cost]}."""
        cfg = self.cfg
        # cape_local only matters when a Cape order meets its congestion
        # point this week (elapsed == 2, i.e. it sits in the e1 slot)
        cape_at_choke = pipe[1] is not None and pipe[1][1] == "cape"
        kbranches = ([(True, cfg.cape_local_prob),
                      (False, 1 - cfg.cape_local_prob)]
                     if cape_at_choke else [(False, 1.0)])
        groups: dict = {}
        for core, p in belief:
            for core2, q in transition_dist(core, cfg):
                for klocal, pk in kbranches:
                    mass = p * q * pk
                    pipe2, inv2, arrived, cost = resolve_rel(
                        pipe, inventory, qty, route, core2, klocal, cfg)
                    key = (regime_of(core2), pipe2, arrived)
                    g = groups.setdefault(key, [0.0, {}, inv2, pipe2, cost])
                    g[0] += mass
                    g[1][core2] = g[1].get(core2, 0.0) + mass
        return groups

    def _expected(self, week, belief, inventory, pipe, qty, route, V):
        total = 0.0
        for mass, atoms, inv2, pipe2, cost in self._chance_groups(
                week, belief, inventory, pipe, qty, route).values():
            total += mass * (cost + V(week + 1, _normalize(atoms),
                                      inv2, pipe2))
        return total

    # --- public surface ---------------------------------------------------

    def value(self) -> float:
        """Expected total cost of the optimal causal policy from reset."""
        return self._V(1, ((("calm", 0, None), 1.0),),
                       self.cfg.initial_inventory, EMPTY_PIPE)

    def decide(self, week, belief, inventory, pipe):
        """(brief?, qty, route) — optimal action at this info state. If
        brief is True, collapse the belief, then decide() again."""
        cfg = self.cfg
        if len(belief) > 1:
            no_brief = self._Q(week, belief, inventory, pipe)
            briefed = cfg.briefing_cost + sum(
                p * self._Q(week, ((core, 1.0),), inventory, pipe)
                for core, p in belief)
            if briefed < no_brief:
                return True, None, None
        remaining = cfg.weekly_demand * (cfg.horizon_weeks - week + 1)
        acts = (self._orders if _position(inventory, pipe) < remaining
                else [(0, None)])
        best = min(acts, key=lambda a: self._expected(
            week, belief, inventory, pipe, a[0], a[1], self._V))
        return False, best[0], best[1]


# --- playing the live engine from observations only ----------------------

_SUEZ_TO_REGIME = {v[0]: k for k, v in REGIME_COUNTS.items()}


def _briefing_collapse(belief, text, cfg):
    """Invert the briefing text to its key and condition the belief."""
    key = next(k for k, t in BRIEFINGS[cfg.semantics].items() if t == text)
    atoms = {c: p for c, p in belief
             if (c[2] if c[0] == "disruption" else c[0]) == key}
    return _normalize(atoms)


def _pipe_from_obs(obs: dict, cfg: WorldConfig) -> tuple:
    """Recover the relative pipeline encoding from an observation: a
    ship's chokepoint has resolved iff it is diverted or >=2 weeks old,
    in which case its displayed eta IS its arrival week."""
    week = obs["week"]
    e0 = e1 = None
    queued = 0
    arrs = [0, 0, 0]
    for s in obs["pipeline"]:
        elapsed = week - s["dispatched_week"]
        if s["status"] == "queued_at_suez":
            queued += s["qty"]
        elif s["status"] == "diverted_via_cape" or elapsed >= 2:
            arrs[s["eta"] - week - 1] += s["qty"]
        elif elapsed == 0:
            e0 = (s["qty"], s["route"])
        else:
            e1 = (s["qty"], s["route"])
    return (e0, e1, queued, tuple(arrs))


def causal_play(seed: int, cfg: WorldConfig | None = None,
                oracle: CausalOracle | None = None):
    """Run the causal-aware oracle on the live engine, deciding from
    observations only. Returns (total_cost, trace_rows). Every step
    cross-checks the engine's outcome against the DP branch."""
    cfg = cfg or WorldConfig()
    assert cfg.semantics == "real", "runner reads canonical obs keys"
    oracle = oracle or CausalOracle(cfg)
    w = World(cfg)
    obs = w.reset(seed)
    belief = ((("calm", 0, None), 1.0),)
    inv, pipe = cfg.initial_inventory, EMPTY_PIPE
    rows = []
    while not w.done:
        week = w.week + 1
        brief, qty, route = oracle.decide(week, belief, inv, pipe)
        if brief:
            belief = _briefing_collapse(belief, w.request_briefing(), cfg)
            _, qty, route = oracle.decide(week, belief, inv, pipe)

        groups = oracle._chance_groups(week, belief, inv, pipe, qty, route)
        obs, cost, done, _info = w.step(
            {"qty": qty, "route": route} if qty else {"qty": 0})

        regime = _SUEZ_TO_REGIME[obs["suez_count"]]
        obs_pipe = _pipe_from_obs(obs, cfg)
        matches = [g for (rg, p2, ar), g in groups.items()
                   if rg == regime and ar == obs["arrived"]
                   and p2 == obs_pipe]
        assert len(matches) == 1, f"ambiguous obs match at week {week}"
        _mass, atoms, inv2, pipe2, step_cost = matches[0]
        expected = step_cost + (cfg.briefing_cost if brief else 0.0)
        assert abs(cost - expected) < 1e-6, f"cost mismatch wk {week}"
        assert inv2 == obs["inventory"], f"inventory mismatch wk {week}"

        belief, inv, pipe = _normalize(atoms), inv2, pipe2
        rows.append({"week": week, "briefed": brief, "qty": qty,
                     "route": route, "belief_support": len(belief),
                     "cost": cost})
    return w.total_cost, rows


def causal_cost(seed: int, cfg: WorldConfig | None = None,
                oracle: CausalOracle | None = None) -> float:
    total, _ = causal_play(seed, cfg, oracle)
    return total
