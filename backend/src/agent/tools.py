"""The agent's two tools: buy_briefing (paid intel) and place_order (act +
advance). Built per-run via make_tools(run); each drives run.world through the
svc_* service layer and records a structured event. Tools return readable text
for the model. No fallback logic: bad input raises, surfaced upstream. The
week-0 obs is delivered in the kickoff message (runner.kickoff_message), not a
tool -- a stateful agent already holds every later obs from place_order."""

import json

from langchain_core.tools import tool

from src.world.engine import HIDDEN_KEYS
from .service import svc_audit, svc_briefing, svc_lock, svc_step


def make_tools(run):
    """Two tools closed over a run (exposes .world and .record(week,kind,payload))."""

    def _obs_text(obs: dict) -> str:
        # Defensive: the agent must never see hidden state.
        leaked = HIDDEN_KEYS & obs.keys()
        assert not leaked, f"hidden state leaked into observation: {leaked}"
        return json.dumps(obs, indent=2)

    @tool
    def buy_briefing() -> str:
        """Pay 30 for a one-line analyst assessment of THIS week's situation,
        before you commit your order. Optional."""
        r = svc_briefing(run.world)
        run.record(run.world.week, "buy_briefing", r)
        return f"Analyst briefing (cost {r['cost']}): {r['briefing']}"

    @tool
    def buy_audit() -> str:
        """Pay for a direct assessment of your spot supplier's CURRENT
        reliability state, before you commit your order. Optional."""
        r = svc_audit(run.world)
        run.record(run.world.week, "buy_audit", r)
        return f"Supplier audit (cost {r['cost']}): {r['audit']}"

    @tool
    def lock_freight(weeks: int) -> str:
        """Forward-buy the freight rate: FIX this week's freight cost multiplier
        for the next `weeks` weeks (weeks >= 1). While locked you pay the locked
        rate regardless of the spot index -- it shields you from a spike but you
        forgo a drop, and an unused week still burns the window. A within-week
        action: it does NOT advance the week. Lock when you believe the rate
        regime is about to tighten."""
        r = svc_lock(run.world, weeks)
        run.record(run.world.week, "lock_freight", r)
        return (f"Freight locked at {r['rate']:.2f}x for {r['weeks_left']} "
                f"weeks. You now pay this rate regardless of spot.")

    @tool
    def place_order(rationale: str, qty: int, route: str = "",
                    supplier: str = "qualified", contract_action: str = "",
                    contract_supplier: str = "", contract_terms: str = "") -> str:
        """Commit this week's decision AND/OR manage a supplier contract, then
        advance the world one week. Each week is exactly one call.

        rationale (REQUIRED): a few sentences of your reasoning for THIS week --
        read your demand/inventory position, the lane/disruption risk, freight,
        and sourcing, and say why this qty/route/supplier (and any contract).
        The week does not advance without it; it is your visible thinking.

        Ordering: qty must be 0, 20, or 40. If qty > 0 you MUST pass route
        ("suez" or "cape") and supplier ("qualified", "spot", or "backup").
        You may only source a supplier you hold a LIVE contract with (see
        `contracts` / `contract_open` in the weekly report).

        Contracts (optional): to sign/switch/renew/lapse a contract this week,
        set contract_action to "sign", "switch", "renew", or "lapse",
        contract_supplier to the supplier id, and (for sign/switch/renew)
        contract_terms to one of "short", "long", "strict", "lenient". The
        contract resolves BEFORE the order, so you can sign a supplier and
        source it in the same call. Use qty 0 to manage a contract without
        ordering. Returns the new week's situation report and whether the
        episode is finished."""
        canonical = route if route else None
        sup = supplier if qty else None
        contract = None
        if contract_action:
            contract = {"action": contract_action,
                        "supplier": contract_supplier or supplier,
                        "terms": contract_terms or None}
        r = svc_step(run.world, qty, canonical, sup, contract)  # raises on bad input
        obs = r["obs"]
        run.record(obs.get("week"), "place_order",
                   {"rationale": rationale, "qty": qty, "route": canonical,
                    "supplier": sup, "contract": contract, "cost": r["cost"],
                    "done": r["done"], "obs": obs})
        tail = "  EPISODE DONE." if r["done"] else ""
        cmsg = f" contract={contract}" if contract else ""
        return (f"Order placed: qty={qty} route={canonical} supplier={sup}.{cmsg} "
                f"Week cost {r['cost']}.{tail}\nNew situation:\n{_obs_text(obs)}")

    tools = [buy_briefing, place_order]
    # buy_audit only exists in the masked-distress task, where the OTIF scorecard
    # lags; in the default world the scorecard is noiseless and an audit is moot.
    if run.world.cfg.sup_mask_otif:
        tools.insert(1, buy_audit)
    # lock_freight only exists where a freight market does (rich worlds); in the
    # 2-factor world there is nothing to lock (and the oracle never sees it).
    if any(m.id == "freight" for m in run.world.registry):
        tools.append(lock_freight)
    return tools
