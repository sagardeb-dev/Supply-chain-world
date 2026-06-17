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
