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


def svc_step(world, qty: int, route: str | None) -> dict:
    """Commit this week's order and advance one week. `route` is canonical
    ("suez"|"cape") or None; required iff qty>0. The hidden-state `info`
    from the engine is dropped here and never returned."""
    if world.done:
        raise RuntimeError("episode is done")
    if qty not in world.cfg.order_quantities:
        raise ValueError(f"qty must be one of {world.cfg.order_quantities}")
    if qty and route not in ("suez", "cape"):
        raise ValueError(f"qty {qty} needs route suez or cape, got {route!r}")
    obs, cost, done, _info = world.step({"qty": qty, "route": route if qty else None})
    return {"obs": obs, "cost": cost, "done": done}
