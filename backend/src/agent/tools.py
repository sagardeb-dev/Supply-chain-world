"""The agent's three tools, mirroring the world's three actions 1:1.
Built per-run via make_tools(run); each tool drives run.world through the
svc_* service layer and records a structured event. Tools return readable
text for the model. No fallback logic: bad input raises, surfaced upstream."""

import json

from langchain_core.tools import tool

from src.world.engine import HIDDEN_KEYS
from .service import svc_observation, svc_briefing, svc_step


def make_tools(run):
    """Three tools closed over a run (exposes .world and .record(week,kind,payload))."""

    def _obs_text(obs: dict) -> str:
        # Defensive: the agent must never see hidden state.
        leaked = HIDDEN_KEYS & obs.keys()
        assert not leaked, f"hidden state leaked into observation: {leaked}"
        return json.dumps(obs, indent=2)

    @tool
    def get_week() -> str:
        """Read the current week's situation report: the week number, the
        transit counts (suez_count, bab_count, cape_count), the trade-press
        bulletin, your on-hand inventory, units that arrived, your in-flight
        shipments with ETAs, and last week's cost breakdown. Free."""
        obs = svc_observation(run.world)
        run.record(obs.get("week"), "get_week", {"obs": obs})
        return _obs_text(obs)

    @tool
    def buy_briefing() -> str:
        """Pay 30 for a one-line analyst assessment of THIS week's situation,
        before you commit your order. Optional."""
        r = svc_briefing(run.world)
        week = svc_observation(run.world).get("week")
        run.record(week, "buy_briefing", r)
        return f"Analyst briefing (cost {r['cost']}): {r['briefing']}"

    @tool
    def place_order(qty: int, route: str = "") -> str:
        """Place exactly one order this week and advance the world one week.
        qty must be 0, 20, or 40. If qty > 0 you MUST pass route "suez" or
        "cape". Returns the new week's situation report and whether the
        episode is finished."""
        canonical = route if route else None
        r = svc_step(run.world, qty, canonical)  # raises on bad qty/route — no fallback
        obs = r["obs"]
        run.record(obs.get("week"), "place_order",
                   {"qty": qty, "route": canonical, "cost": r["cost"],
                    "done": r["done"], "obs": obs})
        tail = "  EPISODE DONE." if r["done"] else ""
        return (f"Order placed: qty={qty} route={canonical}. "
                f"Week cost {r['cost']}.{tail}\nNew situation:\n{_obs_text(obs)}")

    return [get_week, buy_briefing, place_order]
