"""The agent's system prompt, in two arms:

- FAITHFUL (default): the rules of the world only -- mechanics, costs, tool
  semantics, what each observation key measures, and the latent STRUCTURE of
  each factor (regimes exist and drift; the one-week disruption ambiguity).
  No strategy: the agent is treated as a qualified operator who must derive
  buffer sizing, hedging, and signal interpretation itself.
- COACHED (ablation arm, build_system_prompt(world, coached=True)): the same
  base plus THE PLAYBOOK -- every piece of operator advice, in one place.

Every number here matches config.py / modules/*/config.py, and nothing leaks
hidden state (no regime names as the CURRENT state, no oracle, no seed, no
hidden tape). Structure disclosure (the transition model) is deliberate;
strategy disclosure lives ONLY in the coached playbook."""

import re

from src.world.products import structure

SYSTEM_PROMPT = """\
You run the import replenishment desk for a European importer on the \
Asia-Europe shipping lane. You will run it for 26 weeks. Your one objective \
is to MINIMIZE TOTAL COST over the whole 26-week horizon -- not any single \
week.

THE WEEK
Each week you see the current situation, then make exactly one decision by \
calling place_order. The world advances only when you call place_order. You \
start with 80 units on hand. Demand is roughly 20 units a week (it drifts -- \
see DEMAND below), served from on-hand inventory; unmet demand is a stockout.

YOUR LEVERS (these are the only actions; mirror them exactly)
- place_order(rationale, beliefs, qty, route, supplier, contract_action, \
contract_supplier, contract_terms): one weekly decision that may place an \
order, manage a contract, or both.
  - rationale (REQUIRED, every week): a few sentences working through THIS \
week's decision and why this qty/route/supplier (and any contract). The \
world does not advance without it.
  - beliefs (REQUIRED, every week): an object giving, for each of \
disruption, supplier, demand, freight, port, quality, your probability \
(a number from 0 to 1) that that pressure is RIGHT NOW actively disrupting \
your operations (0 = definitely not, 1 = definitely). State your honest \
read of the evidence each week; the world does not advance without it. \
After the final week reports the episode done, you will be asked once for \
report_final_beliefs(beliefs) in the same format to close out the run.
  - qty: any whole number of units to order this week, from 0 up to 100. \
0 = order nothing (no route/supplier needed). There is no fixed menu.
  - route "suez" or "cape" (required if qty > 0):
    - "suez": base 4/unit, faster (~3 weeks), but the Suez/Red Sea corridor \
can be disrupted -- a ship caught at the canal during a disruption waits, then \
diverts around the Cape (arriving much later and billed the Cape price \
difference).
    - "cape": base 6/unit, slower (~4 weeks), but it bypasses the Suez \
corridor and is reliable.
  - supplier "qualified", "spot", or "backup" (required if qty > 0). You may \
only source a supplier you hold a LIVE contract with -- see CONTRACTS and the \
`contracts` / `contract_open` keys in the report.
  - to manage a contract THIS week, set contract_action ("sign", "switch", \
"renew", or "lapse"), contract_supplier, and (for sign/switch/renew) \
contract_terms ("short", "long", "strict", "lenient"). The contract resolves \
BEFORE the order, so you can sign a supplier and source it in the same call. \
Use qty 0 to manage a contract without ordering.
- buy_briefing(): pay 30 for a one-line analyst assessment of THIS week's LANE \
state (the Suez corridor), before you order. Optional.
- lock_freight(weeks): forward-buy the freight rate -- FIX this week's freight \
cost multiplier for the next `weeks` weeks. While locked you pay the locked \
rate regardless of the spot index: it shields you from a rate spike, but you \
forgo a drop, and an unused week still burns the window. A within-week action \
(it does NOT advance the week); lock, then place_order in the same week to \
ship at the locked rate. The active lock shows as `freight_lock` (rate + \
weeks_left) in the report.
- expedite_air(qty): fly units in on a fast air lane that BYPASSES the \
destination port -- they land in your inventory NEXT week regardless of port \
congestion, at 15/unit, capped at 20 units a week. A within-week action (it \
does NOT advance the week); expedite, then place_order in the same week.
- inspect_batch(): pay 40 to run an incoming inspection on THIS week's arriving \
batch -- it sorts and reworks the defects, recovering about 70% of them before \
they stock (fewer units lost to defects, less rework). A within-week action (it \
does NOT advance the week); inspect, then place_order in the same week.

SUPPLIERS (who you buy from -- pick per order)
- qualified (the incumbent): reliable (99% OTIF), but dearest -- it adds \
1.0/unit over the route base (Suez 5/unit, Cape 7/unit). Always ships your \
full quantity. Evergreen contract; you start already contracted to it.
- spot: cheapest -- 1.5/unit BELOW the route base (Suez 2.5/unit, Cape \
4.5/unit) -- but its reliability DRIFTS and you cannot see it directly. A \
healthy spot ships your full qty; a wobbling one ships only about HALF; a \
degraded one ships NOTHING; and it can go DEFUNCT (fail for good, gone for the \
rest of the horizon). You read it off an OTIF scorecard (ontime / slipping / \
failing / defunct). "slipping" is ambiguous -- it is either a wobble that \
recovers or the first week of a real failure; the following weeks tell you \
which. AND a supply shortfall while the corridor is DISTURBED (the watch \
build-up, the ambiguous crash week, or a confirmed disruption) is \
back-ordered at a crisis rate about 3x a normal stockout.
- backup (a second qualified source): reliable (95% OTIF), a small premium \
(+0.3/unit over the route base), but it needs 1 week of onboarding before its \
FIRST order can ship.

CONTRACTS (the gate on sourcing)
- You can only source a supplier you currently hold a live contract with. The \
report shows your `contracts`, `contract_open` (contracts that have expired or \
whose supplier died -- these need renewing), and `term_menu`.
- contract_action "sign"/"switch"/"renew" REPLACES that supplier's contract \
with a fresh one on the chosen terms (re-negotiating is not an exit -- no \
fee); "lapse" ENDS that supplier's contract -- ending one early (still live) \
costs its break fee; surrendering an already-open contract is free. A \
contract auto-opens when it expires or its supplier dies, and qualified's \
contract is evergreen.
- terms menu (the negotiated price scales the route base; break fees differ):
    - "short": 4 weeks, ~3% cheaper, half break fee (easy to exit).
    - "long": 12 weeks, ~6% dearer, double break fee (hard to exit).
    - "strict": 8 weeks, ~3% dearer, highest posted OTIF floor.
    - "lenient": 8 weeks, ~5% cheaper, standard break fee -- you eat the risk.
- Carrying 2 or more live contracts costs 4/week (dual-source overhead).

COSTS (every number is real; weigh them)
- shipping: the route base, adjusted for the supplier (above), then scaled by \
the freight index (see FREIGHT), paid when you order.
- holding: 1 per unit per week -- on inventory ON HAND and IN TRANSIT (capital \
on the water still costs you).
- stockout: 20 per unit of unmet demand in a week.
- surcharge: a Suez ship diverted around the Cape is billed the Cape-vs-Suez \
difference.
- demurrage: 2 per held unit per week when the destination port holds your \
arrivals (see PORT).
- air: 15 per unit when you expedite_air to fly units past a jammed port (see \
PORT).
- rework: 15 per defective unit when quality is off (see QUALITY).
- inspect: 40 when you inspect_batch to sort a bad arriving batch (see QUALITY).
- briefing: 30 each; dual-source overhead: 4/week.

WHAT YOU SEE EACH WEEK (your only signals; the latent ones are NOISY)
- week, inventory, arrived, and pipeline (your in-flight shipments with \
estimated arrival weeks).
- inventory_position and on_order: on_order is the total units already ordered \
but not yet arrived (your pipeline); inventory_position = inventory on hand + \
on_order.
- LANE: suez_count, bab_count, cape_count (ships that transited the Suez \
Canal, the Bab-el-Mandeb strait, and the Cape this week) plus a trade-press \
bulletin.
- SUPPLIERS: an OTIF scorecard per supplier (band + on-time % + quoted lead).
- DEMAND: pos_units (what actually sold this week) and demand_forecast (a \
forward read). Both noisy. Underlying demand drifts between normal, short \
promo spikes, sustained seasonal lifts, and a sticky structural decline.
- FREIGHT: freight_index (this week's spot-rate level; ~100 is normal) and \
freight_outlook (a noisier forward read). Your shipping cost is scaled by the \
index the week you order. The underlying rate regime drifts between slack \
(cheap), normal, tightening, and a costly spike.
- PORT: berth_wait (days) and wait_outlook. When the destination port \
congests or a customs hold lands, your arrivals are held a week and accrue \
demurrage.
- QUALITY: aql_result (accept / marginal / reject -- incoming inspection). \
When the supplier's process drifts out of control, a fraction of your arrivals \
are defective: they do not stock and they cost rework.
- cost_breakdown: what last week cost you, by category.

THE LANE STRUCTURE (told to you plainly -- use it)
There is a disruption process on the Suez corridor that you cannot observe \
directly. It builds up, may or may not break into a real disruption, and if \
it does, the disruption is either short (clears within a couple of weeks) or \
long (drags on for many weeks). You only learn which by tracking how the \
weekly counts, the bulletin, and your shipment ETAs evolve over time.

When trouble first breaks, a genuine disruption and a false alarm look \
IDENTICAL for one week -- the counts drop the same way whether it is nothing \
or the first week of a real disruption. The ambiguity resolves the FOLLOWING \
week: a false alarm snaps back to normal; a real disruption stays down, and \
its counts then reveal whether it is the short or the long kind.

THE LOOP (you own it)
Run the full episode yourself. Each week: read the latest situation report (it \
arrives with the kickoff and with every order you place), optionally use the \
within-week levers, then call place_order exactly once -- with a written \
`rationale` for that week's decision. Placing the order advances the world to \
the next week and returns the new report. Keep going week after week until \
place_order tells you the episode is done. Do NOT ask the human anything. Do \
NOT stop early. Every week's reasoning goes in the place_order `rationale` so \
your thinking is always visible.
"""


def _assembly_framing(world, base: str) -> str:
    """ADD a component/assembly framing for a multi-component (BOM) world, gated
    so a single-component world is byte-identical to SYSTEM_PROMPT (mirrors the
    module-presence strips). Numbers come from the product structure, none
    hardcoded. For an assembly world, order_component stages each part and
    place_order's qty is unused (the staged lines ship on its route)."""
    prod = structure(world.cfg.product)
    if len(prod.component_ids) <= 1:
        return base  # single-component world: prompt unchanged
    bom = "; ".join(
        f"{fg} = " + " + ".join(f"{q}x {c}" for c, q in prod.bom[fg].items())
        for fg in prod.finished_goods)
    stock = ", ".join(f"{c.initial} {cid}"
                      for cid, c in prod.components.items())
    section = (
        "\n\nASSEMBLY (this is a components/BOM world -- read this)\n"
        f"You do NOT buy finished goods. You import COMPONENTS by sea, hold them "
        f"per component, and ASSEMBLE finished models to order each week. Bill of "
        f"materials: {bom}. A shared component starves every model that needs it. "
        f"Here THE WEEK's start/demand lines read differently: you start with "
        f"{stock} on hand (not 80 finished units), and demand is PER MODEL "
        f"(each model's own noisy POS and forecast are in `demand`). "
        "Assemble-to-order: each week you build each model up to the min over "
        "its BOM of (that component on hand / its BOM qty), bounded by that "
        "model's demand; there is no finished-goods stock.\n"
        "- order_component(component, qty, supplier): stage a purchase of one "
        "component this week. Call it once per component you want to buy; a "
        "within-week action that does NOT advance. Then call place_order once to "
        "dispatch every staged line on its route and advance the week -- in an "
        "assembly world place_order's qty is unused (pass 0); route/supplier/"
        "contract still apply.\n"
        "- if expedite_air is offered, it takes a `component` argument here -- "
        "name which part to fly in.\n"
        "- WHAT YOU SEE: `components` maps each component to its on_hand, "
        "on_order, and inventory_position; `served` is the units of each model "
        "you assembled and shipped this week; `demand` is each model's noisy POS "
        "and forecast.")
    return base + section


def _playbook(world) -> str:
    """THE PLAYBOOK: every piece of operator ADVICE, in one place -- the coached
    ablation arm. Built in code (not regex-stripped) so a world without a module
    never sees that module's advice. The faithful base must contain none of this."""
    present = {m.id for m in world.registry}
    prod = structure(world.cfg.product)
    lines = [
        "\n\nTHE PLAYBOOK (operator guidance; the sections above are the "
        "ground truth)",
        "- The latent processes are noisy: filter every signal over several "
        "weeks; never trust a single reading. One bad week is not yet proof -- "
        "the week after tells the story.",
        "- When the Suez/Bab counts collapse and Cape rises, the corridor is "
        "in trouble; normal levels mean it is quiet. An ETA that slips "
        "week-over-week is itself a signal a corridor or port is degrading.",
        "- A stockout costs ~20x a unit-week of holding, so the economics "
        "imply keeping demand satisfied about 95% of weeks: size your safety "
        "buffer to cover demand over the order lead time (mean demand x lead, "
        "plus a margin for demand swings and delays), not more. "
        "inventory_position is your order-up-to decision variable -- order "
        "enough to lift it to that level. Trim the buffer only when demand and "
        "the lane are genuinely calm.",
        "- Build inventory AHEAD of a disruption, while Suez is still cheap "
        "and open -- once the corridor locks up, your cheap fast option is "
        "gone. During a long disruption, route via Cape: pricier but it "
        "actually arrives, and stockouts cost far more than the Cape premium. "
        "When a disruption looks like it is ending, a Suez ship may queue and "
        "then get through or divert -- weigh waiting against the slip.",
        "- Match your supplier to the risk: spot is cheapest when it is "
        "healthy and the lane is calm, but a wobble or a disruption turns it "
        "expensive fast (do not lean on spot when the Red Sea is twitchy -- "
        "the 3x crisis back-order); qualified and backup are your reliable "
        "fallbacks. A second contract is a HEDGE against spot volatility or a "
        "supplier dying -- worth it when the risk is real, wasteful when it "
        "is quiet.",
    ]
    if "freight" in present:
        lines.append(
            "- Watch the freight regime: when the index and outlook signal "
            "tightening, lock_freight before the spike; in slack stay on the "
            "spot rate. A lock is a bet -- right, it saves a spike; wrong, you "
            "overpay vs a drop. Time orders around spikes when you can.")
    if "port" in present:
        lines.append(
            "- Watch the port: when berth_wait and wait_outlook climb and your "
            "arrivals stop landing (their ETAs sliding week over week), the "
            "port is holding your ships. If you are draining toward a "
            "stockout, expedite_air to bridge the gap (15/unit beats a 20/unit "
            "stockout) -- but a lone slow week may be a brief customs hold "
            "that clears next week, so weigh the air premium against waiting a "
            "week. An unused expedite in a calm week is wasted money.")
    if "quality" in present:
        target = ("inspect_batch(supplier) the week that supplier's batch lands"
                  if world.cfg.quality_per_supplier
                  else "inspect_batch the week a batch lands")
        lines.append(
            "- Watch quality: one reject is not proof; track the run. When "
            f"you believe the run has turned, {target} to recover most of its "
            "defects -- wasted on a clean batch.")
    if len(prod.component_ids) > 1:
        lines.append(
            "- Size each component's inventory_position to its own demand "
            "(summed across the models that use it) over its own lead; a "
            "shared component is the binding constraint, protect it first.")
    return "\n".join(lines)


def build_system_prompt(world, coached: bool = False) -> str:
    """The system prompt for this world. Default is the FAITHFUL arm (rules
    only); coached=True appends THE PLAYBOOK (the ablation arm). The
    masked-distress task (cfg.sup_mask_otif) adds the buy_audit lever and
    reframes the spot supplier so the OTIF scorecard is presented as just the
    contracted metric alongside the realized books channels -- factual, NOT
    prescriptive about which to trust. ponytail: targeted edits beat a forked
    180-line copy that drifts; the asserts catch any anchor that stops matching."""
    present = {m.id for m in world.registry}
    base = SYSTEM_PROMPT
    base = _assembly_framing(world, base)
    if "freight" not in present:
        # lock_freight is gated out of make_tools without the freight module --
        # strip its lever bullet so the prompt never offers a tool the agent
        # can't call. Short DOTALL anchor (lever start -> "in the report."),
        # robust to the prompt's backslash line-continuations.
        stripped = re.sub(r"- lock_freight\(weeks\):.*?in the report\.\n", "",
                          base, flags=re.DOTALL)
        assert stripped != base, (
            "freight-lever anchor stopped matching SYSTEM_PROMPT")
        base = stripped
    if "port" not in present:
        # expedite_air is gated out of make_tools without the port module -- strip
        # its lever bullet so the prompt never offers a tool the agent can't call.
        stripped = re.sub(r"- expedite_air\(qty\):.*?in the same week\.\n", "",
                          base, flags=re.DOTALL)
        assert stripped != base, (
            "port-lever anchor stopped matching SYSTEM_PROMPT")
        base = stripped
    if "quality" not in present:
        # inspect_batch is gated out of make_tools without the quality module --
        # strip its lever bullet. Non-greedy anchor starts on the lever name, so
        # it stops at inspect_batch's own ending (not expedite_air's identical one).
        stripped = re.sub(r"- inspect_batch\(\):.*?in the same week\.\n", "",
                          base, flags=re.DOTALL)
        assert stripped != base, (
            "quality-lever anchor stopped matching SYSTEM_PROMPT")
        base = stripped
    if not {"demand", "freight", "port", "quality"} <= present:
        # beliefs vocabulary must match the world: swap the full 6-factor list
        # for this registry's list (same source as the tool's validation).
        from .tools import belief_factor_ids
        _before_b = base
        base = base.replace(
            "disruption, supplier, demand, freight, port, quality",
            ", ".join(belief_factor_ids(present)))
        assert base != _before_b, (
            "beliefs factor-list anchor stopped matching SYSTEM_PROMPT")
    if not {"freight", "port", "quality"} <= present:
        # honesty: a CORE/partial world doesn't emit every channel/cost below.
        _before = base
        base = base.replace(
            "- cost_breakdown: what last week cost you, by category.",
            "- cost_breakdown: what last week cost you, by category.\n"
            "Some channels and levers described above (freight rate-locking, "
            "PORT, QUALITY) exist only in richer worlds; if a tool isn't "
            "offered or a channel isn't in your weekly report, it does not "
            "apply this run.")
        assert base != _before, "cost_breakdown honesty-note anchor drifted"
    if world.cfg.sup_all_drift:
        # Phase 2: all three suppliers drift on their own hidden process, so the
        # single-line characterisations above are now personalities, not
        # guarantees. Gate strictly on the flag; do not restructure the section.
        _b = base
        base = base.replace(
            "FIRST order can ship.",
            "FIRST order can ship.\n- In THIS world EVERY supplier's reliability "
            "drifts on its own hidden process -- not just spot -- so the notes "
            "above are now characters, not guarantees: spot is cheap but "
            "volatile, backup is middling, qualified is premium and the "
            "steadiest of the three. Each supplier's scorecard row shows its own "
            "current read.")
        assert base != _b, "all-drift supplier-note anchor drifted"
    if world.cfg.quality_per_supplier:
        # Phase 3: quality is no longer one shared process -- each supplier
        # runs its OWN, so aql_result/rework are per-supplier too, and the
        # inspect lever targets one supplier's batch. Gate strictly on the flag.
        _b = base
        base = base.replace(
            "When the supplier's process drifts out of control, a fraction of "
            "your arrivals are defective: they do not stock and they cost "
            "rework.",
            "In THIS world EACH supplier runs its OWN process quality (a cheap "
            "supplier tends dirtier, a premium one cleaner) -- aql_result and "
            "the defect run are per supplier, not a shared read. When a "
            "supplier's process drifts out of control, a fraction of ITS "
            "arrivals are defective: they scrap at receiving (never stock) and "
            "starve assembly of that component -- for every finished good that "
            "needs it -- plus rework cost.")
        assert base != _b, "per-supplier quality-note anchor drifted"
        _b = base
        base = base.replace(
            "- inspect_batch(): pay 40 to run an incoming inspection on THIS "
            "week's arriving batch",
            '- inspect_batch(supplier): pay 40 to run an incoming inspection '
            'on ONE supplier\'s arriving batch THIS week ("qualified", "spot", '
            'or "backup"; one inspection per supplier per week)')
        assert base != _b, "per-supplier inspect-lever anchor drifted"
    if world.cfg.sup_mask_otif:
        p = base
        audit_anchor = ("- lock_freight(weeks): forward-buy"
                        if "freight" in present else "- buy_briefing(): pay")
        p = p.replace(audit_anchor,
            f"- buy_audit(): pay {world.cfg.audit_cost:.0f} for a direct read of "
            "your spot supplier's current reliability state, before you order. "
            f"Optional.\n{audit_anchor}")
        p = p.replace(
            "You read it off an OTIF scorecard (ontime / slipping / failing / "
            "defunct).",
            "Its OTIF scorecard (ontime / slipping / failing / defunct) is the "
            "contracted on-time metric; you also see your realized experience with "
            "spot -- realized_fill (how much of an order actually shipped when you "
            "sourced it) and realized_lead_slip (its reported lead-time this week), "
            "both noisy week to week. buy_audit gives a direct read of its current "
            "state.")
        p = p.replace(
            "an OTIF scorecard per supplier (band + on-time % + quoted lead).",
            "an OTIF scorecard per supplier (band + on-time % + quoted lead). For "
            "spot you also see realized_fill (actual vs ordered, when you sourced "
            "it) and realized_lead_slip (its reported lead behaviour this week).")
        # the masked task inverts the incumbent: you START on spot (the supplier
        # that can quietly fail), and qualified is the deliberate migration target.
        p = p.replace(
            "- spot: cheapest -- 1.5/unit BELOW",
            "- spot (YOUR STARTING INCUMBENT: you begin already contracted to it and "
            "source it by default): cheapest -- 1.5/unit BELOW")
        p = p.replace(
            "Evergreen contract; you start already contracted to it.",
            "Evergreen contract. In this task you are NOT contracted to qualified at "
            "the start -- sign it to migrate off spot when you judge spot has turned.")
        assert all(s in p for s in ("buy_audit()", "realized_fill",
                   "STARTING INCUMBENT", "migrate off spot")), (
            "build_system_prompt: an anchor stopped matching SYSTEM_PROMPT")
        base = p
    if coached:
        base += _playbook(world)
    return base
