"""Supplier contracts: the second supplier submodule (after reliability).

A contract is a TIMER + TERMS the agent set -- observed, deterministic, no
hidden state, no kernel. It adds no belief dimension. Per-contract sourcing
means you may only order from a supplier you hold a live contract with
(R4 enforces the mask); per-order sourcing is the degenerate 1-tick contract.

contract_open is the standing rule's predicate. It reads ONLY conditions --
never a date, never a named scenario -- so the auto-renewal prompt EMERGES
when the defunct primitive (R2) makes a counterparty die, with zero per-event
code. This is Lever 1 meeting Lever 2 from spec 004."""

from dataclasses import dataclass


@dataclass
class Contract:
    supplier: str          # which roster supplier this binds
    start_week: int
    end_week: int | None   # the contract is OPEN once week >= end_week;
                           # None = evergreen (the incumbent anchor, never lapses)
    unit_price: float      # locked price for the duration (price-lock teeth)
    otif_floor: int        # OTIF below which a penalty clause triggers (R5)
    break_fee: float       # cost to exit before end_week (early-exit teeth)


def contract_open(contract: Contract, week: int, alive: dict) -> bool:
    """The standing rule: a contract is OPEN (the agent must renew/switch)
    when it has EXPIRED or its counterparty has DIED. A pure function of
    conditions -- the emergence hinges on this never naming a tick or scenario.

        open := (end_week is not None AND week >= end_week)
                 OR  not alive[supplier]

    An evergreen contract (end_week=None) only opens if its counterparty dies.
    """
    expired = contract.end_week is not None and week >= contract.end_week
    return expired or not alive[contract.supplier]

# The negotiation MENU: four finite term archetypes. "Negotiating" is selecting
# one (one action eval -- bounded to a tick, never a bargaining loop). Grounded
# in the spot-vs-long-term trade-off: a longer lock pays a price premium for
# certainty; a strict OTIF floor buys a penalty clause the supplier owes you.
#   weeks            -- contract length in ticks
#   unit_price_mult  -- multiplier on the base lane unit cost (the lock premium)
#   otif_floor       -- OTIF below which the penalty clause triggers (R-later)
#   break_fee_mult   -- multiplier on cfg.contract_break_fee (irreversibility)
TERM_MENU = {
    "short":   {"weeks": 4,  "unit_price_mult": 0.97, "otif_floor": 80,
                "break_fee_mult": 0.5},   # agile, cheap, easy to exit
    "long":    {"weeks": 12, "unit_price_mult": 1.06, "otif_floor": 85,
                "break_fee_mult": 2.0},   # price-lock, dearer, hard to exit
    "strict":  {"weeks": 8,  "unit_price_mult": 1.03, "otif_floor": 92,
                "break_fee_mult": 1.0},   # high floor: supplier owes you on a slip
    "lenient": {"weeks": 8,  "unit_price_mult": 0.95, "otif_floor": 70,
                "break_fee_mult": 1.0},   # cheapest, no real penalty -- you eat risk
}


def terms_for(menu_key: str, supplier: str, start: int, cfg) -> dict:
    """Concrete contract field values for a menu selection. qualified stays
    evergreen regardless of the chosen length (the incumbent never lapses)."""
    if menu_key not in TERM_MENU:
        raise ValueError(f"unknown terms {menu_key!r}; choose from {list(TERM_MENU)}")
    m = TERM_MENU[menu_key]
    end = None if supplier == "qualified" else start + m["weeks"]
    return {
        "end_week": end,
        "unit_price": cfg.suez_unit_cost * m["unit_price_mult"],
        "otif_floor": m["otif_floor"],
        "break_fee": cfg.contract_break_fee * m["break_fee_mult"],
    }

