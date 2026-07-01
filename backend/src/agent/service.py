"""Pure service functions over a World; the single path for HTTP handlers
and the future agent tool layer. No HTTP, no episode ids, no anon vocab."""


def svc_observation(world) -> dict:
    """The current week's observation -- exactly what the agent/HTTP client
    sees. Read from the trace tail; never rebuild via private engine paths."""
    return world.trace[-1]["obs"]


def svc_briefing(world) -> dict:
    """Buy the pre-decision analyst briefing for the current week. Charged
    once per week by the engine; repeat calls return the same text."""
    if world.done:
        raise RuntimeError("episode is done")
    return {"briefing": world.request_briefing(), "cost": world.cfg.briefing_cost}


def svc_audit(world) -> dict:
    """Buy the pre-decision supplier audit for the current week (masked task).
    Charged once per week by the engine; repeat calls return the same text."""
    if world.done:
        raise RuntimeError("episode is done")
    return {"audit": world.request_audit(), "cost": world.cfg.audit_cost}


def svc_lock(world, weeks: int) -> dict:
    """Forward-buy the current freight rate for `weeks` weeks. A within-week
    action (does not advance). Mirrors svc_briefing; the engine validates."""
    if world.done:
        raise RuntimeError("episode is done")
    return world.lock_freight(weeks)


def svc_expedite(world, qty: int) -> dict:
    """Fly units in on the air fast-lane past a jammed port (port lever). A
    within-week action (does not advance). Mirrors svc_lock; the engine validates."""
    if world.done:
        raise RuntimeError("episode is done")
    return world.expedite_air(qty)


def svc_inspect(world) -> dict:
    """Run an incoming inspection on this week's batch (quality lever). A
    within-week action (does not advance). Mirrors svc_expedite; the engine validates."""
    if world.done:
        raise RuntimeError("episode is done")
    return world.inspect_batch()


def svc_step(world, qty: int, route: str | None,
             supplier: str | None = None, contract: dict | None = None) -> dict:
    """Commit this week's order (and optional contract sub-action) and advance
    one week. `route`/`supplier` are canonical or None. The engine is the
    single validator (no fallback) -- we do NOT re-check here. The hidden-state
    `info` is dropped and never returned."""
    if world.done:
        raise RuntimeError("episode is done")
    action = {"qty": qty, "route": route if qty else None,
              "supplier": supplier if qty else None}
    if contract:
        action["contract"] = contract
    obs, cost, done, _info = world.step(action)
    return {"obs": obs, "cost": cost, "done": done}
