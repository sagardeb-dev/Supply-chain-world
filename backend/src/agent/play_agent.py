"""Headless runner: play one episode with the LLM agent (or a fixed policy)
and print an aligned per-week trace -- the visible observation + the action +
the cost on one line, the HIDDEN truth of every latent factor beneath it. This
is the debugging view: scan for a week where the action was reasonable given
what was visible but the world did something odd given what was hidden.

  uv run python -m src.agent.play_agent --seed 7 --model <openrouter-slug>
  uv run python -m src.agent.play_agent --seed 7 --model <slug> --rich
  uv run python -m src.agent.play_agent --seed 7 --policy suez --rich   # no LLM

--model is required (no default) unless --policy is given. Oracle scoring is
deliberately out of scope here (see the README discussion); this prints the
agent's own cost, broken down -- compare runs/models on the same seed.
"""

import argparse
import textwrap
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from src.world import World, WorldConfig
from src.world.registry import RICH

STATUS_MARK = {"at_sea": "", "queued_at_suez": "Q", "diverted_via_cape": "D"}


# --- running -------------------------------------------------------------

def run_agent(seed, model, mode, semantics, rich):
    """Stream the agent through the episode, printing it as a chat as it goes:
    the agent's reasoning, the order it places, then the world's reply with the
    hidden tape annotated. Returns (world, the printed chat as one string)."""
    from langchain_core.messages import AIMessage, ToolMessage
    from langgraph.checkpoint.memory import MemorySaver
    from .runner import AgentRun, kickoff_message
    from .tools import make_tools
    from .factory import build_agent
    from .prompt import build_system_prompt

    run = AgentRun(uuid4().hex, seed, model, mode, semantics,
                   registry=RICH if rich else None)
    agent = build_agent(model, mode, make_tools(run), MemorySaver(),
                        build_system_prompt(run.world))
    config = {"configurable": {"thread_id": run.run_id}, "recursion_limit": 200}
    kickoff = {"messages": [{"role": "user", "content": kickoff_message(run.world)}]}

    log = []
    def emit(s=""):           # print live AND keep it, so main can save the file
        print(s, flush=True)
        log.append(s)

    wk0 = run.world.trace[0]
    emit(f"{model} on seed {seed} ({'RICH 6-factor' if rich else '2-factor'})\n")
    emit(f"WEEK 0  {_obs_summary(wk0['obs'], rich)}")
    emit(f"        hidden: {_fmt_hidden(wk0, rich)}")
    for update in agent.stream(kickoff, config, stream_mode="updates"):
        if not isinstance(update, dict):
            continue
        for _node, delta in update.items():
            if not isinstance(delta, dict):
                continue
            for m in delta.get("messages", []):
                if isinstance(m, AIMessage):
                    txt = _msg_text(m)
                    if txt:
                        emit("\nAGENT  " + textwrap.fill(
                            txt, 78, subsequent_indent="       "))
                    for tc in (m.tool_calls or []):
                        args = {k: v for k, v in (tc.get("args") or {}).items()
                                if v not in ("", None)}
                        rat = args.pop("rationale", None)  # the required per-week reasoning
                        if rat:
                            emit("\nREASON " + textwrap.fill(
                                str(rat), 78, subsequent_indent="       "))
                        emit("  >> " + tc["name"] + "("
                             + ", ".join(f"{k}={v}" for k, v in args.items()) + ")")
                elif isinstance(m, ToolMessage) and m.name == "place_order":
                    p, rec = run.recorder[-1]["payload"], run.world.trace[-1]
                    emit(f"WORLD  week {rec['week']}  cost ${p['cost']:.0f}  "
                         f"cum ${run.world.total_cost:.0f}"
                         + ("  ** DONE **" if p["done"] else ""))
                    emit(f"       {_obs_summary(p['obs'], rich)}")
                    emit(f"       hidden: {_fmt_hidden(rec, rich)}")
                elif isinstance(m, ToolMessage) and m.name == "buy_briefing":
                    emit("  ANALYST: " + str(m.content))
                elif isinstance(m, ToolMessage) and m.name == "buy_audit":
                    emit("  AUDIT: " + str(m.content))
                elif isinstance(m, ToolMessage) and m.name == "lock_freight":
                    emit("  FREIGHT: " + str(m.content))
    return run.world, "\n".join(log)


def _msg_text(m) -> str:
    """Pull the agent's think-out-loud text off an AIMessage, coping with both
    plain-string content and the block-list / reasoning shapes some providers
    (OpenRouter reasoning models) use."""
    c = m.content
    if isinstance(c, str):
        text = c
    elif isinstance(c, list):
        out = []
        for b in c:
            if isinstance(b, str):
                out.append(b)
            elif isinstance(b, dict):
                out.append(b.get("text") or b.get("reasoning") or "")
        text = "\n".join(s for s in out if s)
    else:
        text = ""
    if not text.strip():  # some models stash reasoning beside content
        text = (getattr(m, "additional_kwargs", {}) or {}).get("reasoning") or ""
    return text.strip()


def run_policy(seed, policy, semantics, rich):
    """Drive a fixed policy (no LLM) through the same World/trace -- the
    renderer's runnable check, and a cheap reference run."""
    # masked too, so a policy baseline shares the agent's masked trajectory (the
    # lead-slip rng draw shifts the seed's trajectory vs the legacy world).
    world = World(WorldConfig(semantics=semantics, sup_mask_otif=True),
                  registry=RICH if rich else None)
    world.reset(seed)
    while not world.done:
        world.step(_policy_action(policy, world))
    return world


def _policy_action(policy, world):
    if policy in ("suez", "cape"):
        return {"qty": 20, "route": policy, "supplier": "qualified"}
    # basestock: order up to ~80 via Suez/qualified
    on_order = sum(s.qty for s in world.books.pipeline)
    deficit = 80 - world.books.inventory - on_order
    qty = 40 if deficit >= 40 else 20 if deficit >= 20 else 0
    return ({"qty": qty, "route": "suez", "supplier": "qualified"} if qty
            else {"qty": 0})


# --- rendering -----------------------------------------------------------

def _fmt_action(a):
    if not a:
        return "(start)"
    parts = []
    if a.get("briefing"):
        parts.append("brief")
    c = a.get("contract")
    if c:
        parts.append(f"{c['action']} {c['supplier']}"
                     + (f":{c['terms']}" if c.get("terms") else ""))
    if a.get("qty"):
        parts.append(f"{a['qty']} {a.get('route')} {a.get('supplier')}")
    else:
        parts.append("hold")
    return "; ".join(parts)


def _fmt_counts(obs):
    c = [obs.get(k) for k in ("suez_count", "bab_count", "cape_count")]
    if c[0] is None:  # anon vocabulary
        c = [obs.get(k) for k in ("waterway1_count", "strait_count", "waterway2_count")]
    return "/".join(str(x) for x in c)


def _fmt_pipe(obs):
    return ",".join(f"{s['qty']}@{s['eta']}{s['route'][0]}{STATUS_MARK.get(s['status'], '')}"
                    for s in obs["pipeline"]) or "-"


def _fmt_spot(obs):
    """Masked-task signals on one line: the drifting supplier's displayed
    OTIF/band (lagging) and the realized books channels (lead-slip sensor +
    this week's spot fill, if you sourced it). Empty in the legacy world."""
    rows = obs.get("suppliers") or []
    spot = next((r for r in rows if "realized_lead_slip" in r), None)
    if spot is None:
        return ""
    fill = obs.get("realized_fill")
    fill_s = f" fill{fill:.0%}" if fill is not None else ""
    return (f"  spot[{spot['band']} otif{spot['otif'] if spot['otif'] is not None else '-'}"
            f" slip{spot['realized_lead_slip']}{fill_s}]")


def _regime(hs, factor):
    st = hs.get(factor)
    return st.get("regime", "-") if isinstance(st, dict) else "-"


def _fmt_hidden(rec, rich):
    hs = rec.get("hidden_states", {})
    spot = hs.get("supplier", {}).get("spot", {}).get("rel_state", "-")
    s = f"lane={_regime(hs, 'disruption')} spot={spot}"
    if rich:
        s += (f" dem={_regime(hs, 'demand')} frt={_regime(hs, 'freight')}"
              f" prt={_regime(hs, 'port')} qly={_regime(hs, 'quality')}")
    # masked task: flag the weeks the scorecard hides spot's true distress -- the
    # crux is whether the agent reads the books on exactly these weeks.
    row = next((r for r in rec["obs"].get("suppliers", []) if r["id"] == "spot"), {})
    if row.get("band") == "ontime" and spot in ("wobbling", "degraded"):
        s += "  <<MASKED: card reads ontime>>"
    return s


def render_trace(world, rich):
    print("\nlegend: line 1 = what the agent SAW + did + cost;  "
          "line 2 (HID) = the hidden truth it could not see\n")
    cum = 0.0
    for rec in world.trace:
        obs, wk = rec["obs"], rec["week"]
        cum += rec["cost"]
        line = (f"wk{wk:2} {_fmt_counts(obs):>9} inv{obs['inventory']:3} "
                f"arr{obs['arrived']:2} pipe[{_fmt_pipe(obs)}]")
        if rich:
            line += (f" pos{obs.get('pos_units', '-')}/fc{obs.get('demand_forecast', '-')}"
                     f" frt{obs.get('freight_index', '-')} aql={obs.get('aql_result', '-')}")
        line += _fmt_spot(obs)
        line += f"  ->  {_fmt_action(rec['action']):26} ${rec['cost']:6.0f} cum${cum:8.0f}"
        print(line)
        print(f"       HID {_fmt_hidden(rec, rich)}")


def print_summary(world):
    cats = {}
    for rec in world.trace:
        for k, v in rec["obs"].get("cost_breakdown", {}).items():
            cats[k] = cats.get(k, 0.0) + v
    print(f"\nTOTAL COST  ${world.total_cost:,.0f}   over {world.week} weeks")
    line = "  ".join(f"{k}=${v:,.0f}" for k, v in
                     sorted(cats.items(), key=lambda x: -x[1]) if v)
    print("by category: " + (line or "-"))


def print_supplier_summary(world):
    """Masked-task scorecard for the run: the reasoning behaviours, not the cost.
    Did the agent lean on spot, sense via audit, and -- the headline -- how many
    weeks was the card masking real distress while it kept sourcing spot?"""
    if not world.cfg.sup_mask_otif:
        return
    spot_orders = fill_short = audits = masked_wks = masked_while_spot = 0
    collapse = None
    for rec in world.trace:
        a, obs = rec["action"] or {}, rec["obs"]
        true = rec["hidden_states"].get("supplier", {}).get("spot", {}).get("rel_state")
        if true == "defunct" and collapse is None:
            collapse = rec["week"]
        row = next((r for r in obs.get("suppliers", []) if r["id"] == "spot"), {})
        masked = row.get("band") == "ontime" and true in ("wobbling", "degraded")
        masked_wks += masked
        if a.get("audited"):
            audits += 1
        if a.get("supplier") == "spot" and a.get("qty"):
            spot_orders += 1
            fill_short += round(a["qty"] * (1 - obs.get("realized_fill", 1.0)))
            masked_while_spot += masked
    print(f"supplier: sourced spot {spot_orders}x (fill short {fill_short}u)  "
          f"audits {audits} (${audits * world.cfg.audit_cost:.0f})  "
          f"weeks card MASKED true distress: {masked_wks} "
          f"({masked_while_spot} while still sourcing spot)  "
          + (f"spot DIED wk{collapse}" if collapse else "spot survived"))


def _obs_summary(obs, rich) -> str:
    """One compact, human line of the visible situation -- not raw JSON."""
    parts = [f"inv {obs['inventory']}", f"Suez {_fmt_counts(obs)}",
             f"arrived {obs['arrived']}", f"pipe [{_fmt_pipe(obs)}]"]
    if rich:
        parts += [f"demand {obs.get('pos_units', '-')}/{obs.get('demand_forecast', '-')}",
                  f"freight {obs.get('freight_index', '-')}",
                  f"port {obs.get('berth_wait', '-')}d",
                  f"qual {obs.get('aql_result', '-')}"]
    return "  ".join(str(p) for p in parts) + _fmt_spot(obs)


# --- entry ---------------------------------------------------------------

def main():
    load_dotenv()  # backend/.env -> OPENROUTER_API_KEY, like the API server
    ap = argparse.ArgumentParser(
        description="Run the LLM agent (or a fixed policy) on the world and "
                    "print an aligned trace with the hidden tape.")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--model", help="OpenRouter model slug (required unless --policy)")
    ap.add_argument("--policy", choices=["suez", "cape", "basestock"],
                    help="run a fixed policy instead of the LLM (no model needed)")
    ap.add_argument("--rich", action="store_true",
                    help="six-factor RICH world (default: two-factor)")
    ap.add_argument("--mode", choices=["autonomous", "step_gated"],
                    default="autonomous")
    ap.add_argument("--semantics", choices=["real", "anon"], default="real")
    args = ap.parse_args()
    if not args.policy and not args.model:
        ap.error("--model is required (no default) unless you pass --policy")

    if args.policy:
        world = run_policy(args.seed, args.policy, args.semantics, args.rich)
        render_trace(world, args.rich)         # no reasoning to show for a policy
        print_summary(world)
        print_supplier_summary(world)
    else:
        world, chat = run_agent(args.seed, args.model, args.mode,
                                args.semantics, args.rich)
        print_summary(world)
        print_supplier_summary(world)
        # persist: the user hit "where's the trace?" twice -- stdout isn't enough
        out = Path("runs") / f"seed{args.seed}-{args.model.replace('/', '-')}.chat.txt"
        out.parent.mkdir(exist_ok=True)
        out.write_text(chat + "\n")
        print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
