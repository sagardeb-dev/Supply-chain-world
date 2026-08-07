"""Automated post-episode trace auditor: the systematic version of "read the
trace and see if the world did what the docs promise" (the manual version of
this found D16). Replays the trace through the engine and asserts documented
cause -> effect for every tool call the agent actually made. bench.py runs it
after every episode; a trace that fails audit does not count as done.

Checks:
  A. structure   - 26 sequential advances, EPISODE DONE, cum telescopes
  B. replay      - engine reproduces every week's cost/cum exactly
  C. lever fx    - sign/lapse: contract set changes as documented
                 - lock_freight: books.freight_lock present after the call
                 - expedite_air: air $ billed that week (qty x air_unit_cost)
                 - inspect_batch / briefing / audit: fee billed that week
  D. beliefs(v2) - a valid beliefs statement (all factors, [0,1]) every
                   decision week + the final report (skipped for v1 traces)

    uv run python analysis/audit_trace.py <trace.chat.txt> --seed N [--v1]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.world.engine import World  # noqa: E402
from src.world.config import WorldConfig  # noqa: E402
from src.world.registry import RICH  # noqa: E402

CALL_RE = re.compile(r"^\s*>> (\w+)\((.*)\)\s*$")
ADV_RE = re.compile(r"^WORLD ADVANCED -> week (\d+)\s+week cost \$(-?\d+)\s+cum \$(-?\d+)")
BELIEF_RE = re.compile(r"^\s*BELIEFS:\s*(\{.*\})\s*$")
FINAL_RE = re.compile(r"^FINAL BELIEFS:\s*(\{.*\})")
FACTORS = ("disruption", "freight", "port", "quality", "supplier", "demand")


def parse_kwargs(raw):
    out = {}
    for part in raw.split(","):
        k, _, v = part.strip().partition("=")
        if k:
            out[k.strip()] = v.strip()
    return out


def audit(path: Path, seed: int, v2: bool = True) -> list[str]:
    """Return a list of failure strings; empty = clean."""
    fails = []
    lines = path.read_text().splitlines()

    # ---- parse into week bundles (call list + beliefs + banner) ----
    weeks = []           # (week, cost, cum)
    bundles = []         # [(tool, kwargs)] per advanced week
    beliefs_by_week = {}
    pending, week_ptr = [], 0
    final_beliefs = None
    for line in lines:
        m = CALL_RE.match(line)
        if m:
            pending.append((m.group(1), parse_kwargs(m.group(2))))
            continue
        m = BELIEF_RE.match(line)
        if m:
            try:
                beliefs_by_week[week_ptr] = json.loads(m.group(1))
            except json.JSONDecodeError:
                fails.append(f"wk{week_ptr}: unparseable BELIEFS line")
            continue
        m = FINAL_RE.match(line)
        if m and m.group(1) != "null":
            try:
                final_beliefs = json.loads(m.group(1))
            except json.JSONDecodeError:
                fails.append("unparseable FINAL BELIEFS line")
            continue
        m = ADV_RE.match(line)
        if m:
            k, cost, cum = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if k == week_ptr:      # phantom duplicate advance (known artifact)
                continue
            if k != week_ptr + 1:
                fails.append(f"week jump {week_ptr} -> {k}")
                return fails
            weeks.append((k, cost, cum))
            bundles.append(pending)
            pending, week_ptr = [], k

    # ---- A. structure ----
    if week_ptr != 26:
        fails.append(f"episode ended at week {week_ptr}, expected 26")
        return fails
    if "EPISODE DONE" not in path.read_text():
        fails.append("no EPISODE DONE marker")
    run_cum = 0
    for wk, cost, cum in weeks:
        run_cum += cost
        if abs(run_cum - cum) > len(weeks):  # printed ints round each week
            fails.append(f"wk{wk}: cum ${cum} != running sum ${run_cum}")

    # ---- B + C. replay with per-call effect assertions ----
    world = World(WorldConfig(sup_mask_otif=True), registry=RICH)
    world.reset(seed)
    for (wk, want_cost, want_cum), bundle in zip(weeks, bundles):
        fee_calls = {"buy_briefing": 0, "buy_audit": 0, "inspect_batch": 0}
        air_qty = 0
        place = None
        for tool, kw in bundle:
            try:
                if tool == "buy_briefing":
                    world.request_briefing(); fee_calls[tool] += 1
                elif tool == "buy_audit":
                    world.request_audit(); fee_calls[tool] += 1
                elif tool == "lock_freight":
                    world.lock_freight(int(kw["weeks"]))
                    if world.books.freight_lock is None:
                        fails.append(f"wk{wk}: lock_freight left no lock in books")
                elif tool == "expedite_air":
                    world.expedite_air(int(kw["qty"]), kw.get("component", ""))
                    air_qty += int(kw["qty"])
                elif tool == "inspect_batch":
                    world.inspect_batch(kw.get("supplier") or None)
                    fee_calls[tool] += 1
                elif tool in ("place_order", "report_final_beliefs", "write_todos"):
                    if tool == "place_order":
                        place = kw
                else:
                    fails.append(f"wk{wk}: unknown tool {tool} in trace")
            except (ValueError, RuntimeError):
                # the real call was REJECTED in-run and had no effect; fee
                # counters only increment on success, so nothing to undo here
                # (decrementing was a false-positive source: it subtracted a
                # legitimate earlier success in the same week).
                pass
        if place is None:
            fails.append(f"wk{wk}: no place_order call")
            return fails
        qty = int(place.get("qty", 0) or 0)
        supplier = (place.get("supplier") or None) if qty else None
        action = {"qty": qty, "route": place.get("route") or None,
                  "supplier": supplier}
        contract = None
        if place.get("contract_action"):
            contract = {"action": place["contract_action"],
                        "supplier": place.get("contract_supplier") or supplier,
                        "terms": place.get("contract_terms") or None}
            action["contract"] = contract
        before_contracted = set(world._contracted_suppliers())
        try:
            obs, cost, done, _ = world.step(action)
        except (ValueError, RuntimeError) as e:
            fails.append(f"wk{wk}: replay step raised: {e}")
            return fails
        # contract effect assertions (documented semantics)
        if contract:
            now = set(world._contracted_suppliers())
            cs = contract["supplier"]
            if contract["action"] in ("sign", "switch", "renew") and cs not in now:
                fails.append(f"wk{wk}: {contract['action']} {cs} but not contracted after")
            if contract["action"] == "lapse" and cs in now:
                fails.append(f"wk{wk}: lapse {cs} but still contracted after (D16 class)")
        # fee/effect assertions from the bill
        cb = world.trace[-1]["obs"]["cost_breakdown"]
        cfg = world.cfg
        expect = {"briefing": fee_calls["buy_briefing"] * cfg.briefing_cost,
                  "audit": fee_calls["buy_audit"] * cfg.audit_cost,
                  "inspect": fee_calls["inspect_batch"] * cfg.inspect_fee,
                  "air": air_qty * cfg.air_unit_cost}
        for key, want in expect.items():
            got = float(cb.get(key, 0.0))
            if abs(got - want) > 0.01:
                fails.append(f"wk{wk}: {key} billed {got} != documented {want}")
        # cost banner match
        if f"{cost:.0f}" != str(want_cost):
            fails.append(f"wk{wk}: replay cost {cost:.0f} != trace {want_cost}")
        if f"{world.total_cost:.0f}" != str(want_cum):
            fails.append(f"wk{wk}: replay cum {world.total_cost:.0f} != trace {want_cum}")

    # ---- D. beliefs coverage (v2 traces) ----
    if v2:
        for wk in range(26):  # decision weeks 0..25
            b = beliefs_by_week.get(wk)
            if b is None:
                fails.append(f"wk{wk}: no BELIEFS statement")
            else:
                bad = [f for f in FACTORS if not isinstance(b.get(f), (int, float))
                       or not 0 <= b[f] <= 1]
                if bad:
                    fails.append(f"wk{wk}: invalid belief values for {bad}")
        if final_beliefs is None:
            fails.append("no FINAL BELIEFS report")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--v1", action="store_true",
                    help="ladder-v1 trace: skip beliefs checks")
    a = ap.parse_args()
    p = Path(a.trace)
    seed = a.seed if a.seed is not None else int(
        re.search(r"seed(\d+)", p.name).group(1))
    fails = audit(p, seed, v2=not a.v1)
    if fails:
        print(f"AUDIT FAIL ({len(fails)}):")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    print("AUDIT CLEAN")


if __name__ == "__main__":
    main()
