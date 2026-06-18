"""Tier 1 — the supplier latent module (sealed box).

The spot supplier's reliability chain: its own states, its own visible OTIF
band, its own kernel. Plus the supplier-stage data the substrate needs as
plain observed facts: the Contract record, the standing-rule predicate, the
negotiation term menu, and the supplier display vocabulary. Everything the
sourcing factor owns lives here.

SEALED BOX: this file NEVER imports the disruption module (transition +
observation independence => the joint belief stays factored, Becker Def. 2).
It imports only config (shared knobs/tables) — config is not a tier-1 peer.
"""

import random
from dataclasses import dataclass, asdict

from ..config import SUPPLIERS, SUPPLIER_SCORECARD, WorldConfig

SUPPLIER_STATES = ("reliable", "wobbling", "degraded", "defunct")


# --- state ----------------------------------------------------------------

@dataclass(frozen=True)
class SupplierState:
    """The spot supplier's reliability factor -- the second latent module.
    Independent of HiddenState; its own kernel advances it.

    Visible band (regime) collapses two states into one for exactly one week,
    mirroring the disruption "crash" ambiguity: a fresh "wobbling" and the
    onset week of "degraded" both read "slipping" on the scorecard, then
    separate the following week (degraded ages into "failing")."""

    rel_state: str = "reliable"
    rel_age: int = 0  # weeks the supplier has been in degraded

    @property
    def regime(self) -> str:
        """Scorecard-band key. wobbling and degraded-onset share "slipping";
        defunct (the dead supplier, Lever 1) is its own absorbing band."""
        if self.rel_state == "reliable":
            return "ontime"
        if self.rel_state == "wobbling":
            return "slipping"
        if self.rel_state == "defunct":
            return "defunct"
        # degraded
        return "slipping" if self.rel_age == 0 else "failing"

    @property
    def fulfilled_fraction(self) -> float:
        """Share of a spot order this supplier actually ships this week."""
        return {"reliable": 1.0, "wobbling": 0.5,
                "degraded": 0.0, "defunct": 0.0}[self.rel_state]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["regime"] = self.regime
        return d


# --- kernel ---------------------------------------------------------------

def step_supplier(sup: SupplierState, rng: random.Random,
                  cfg: WorldConfig) -> SupplierState:
    """Advance the spot supplier's reliability factor. Sibling of step_hidden,
    same rng (exogeneity: actions never consume it). Reads ONLY SupplierState
    -- never the disruption state -- so the two latent modules are transition
    independent (Becker Def. 2) and debuggable in isolation.

    Runs UNCONDITIONALLY every week (the supplier drifts whether or not you
    source from it), which is what makes the scorecard a free side-channel."""
    s, age = sup.rel_state, sup.rel_age
    if s == "reliable":
        nxt = "wobbling" if rng.random() < cfg.sup_onset_prob else "reliable"
    elif s == "wobbling":
        r = rng.random()
        if r < cfg.sup_wobble_to_degraded:
            nxt = "degraded"
        elif r < cfg.sup_wobble_to_degraded + cfg.sup_wobble_to_reliable:
            nxt = "reliable"
        else:
            nxt = "wobbling"
    elif s == "defunct":
        # Lever 1: absorbing. A dead supplier stays dead for the episode.
        return sup
    else:  # degraded
        # First check the death hazard (degraded is the only entry to defunct);
        # then the recover-or-persist branch as before.
        if rng.random() < cfg.sup_defunct_from_degraded:
            nxt = "defunct"
        else:
            over = (age + 1 >= cfg.sup_max_degraded
                    or rng.random() > cfg.sup_degraded_persist)
            nxt = "reliable" if over else "degraded"
    return SupplierState(rel_state=nxt, rel_age=0 if nxt != s else age + 1)


# --- supplier display vocabulary (real/anon ablation, identical info) ------

SUPPLIER_DISPLAY = {
    "real": {"qualified": "qualified", "spot": "spot", "backup": "backup"},
    "anon": {"qualified": "source_a", "spot": "source_b", "backup": "source_c"},
}
SUPPLIER_PARSE = {mode: {v: k for k, v in d.items()}
                  for mode, d in SUPPLIER_DISPLAY.items()}
SUPPLIER_BAND_DISPLAY = {
    "real": {"ontime": "ontime", "slipping": "slipping", "failing": "failing"},
    "anon": {"ontime": "band_0", "slipping": "band_1", "failing": "band_2"},
}


# --- emission (noiseless OTIF scorecard over the roster) -------------------

def _supplier_row(sid: str, sup: SupplierState, cfg: WorldConfig) -> dict:
    """One scorecard row, fully driven by the supplier's profile (config.
    SUPPLIERS) -- no instance-name branch. A drifting supplier reads its
    OTIF/lead/band from the visible band of its reliability chain (the
    deliberate 1-week 'slipping' ambiguity, A5); a frozen supplier shows the
    constants its profile declares. NEVER reads the disruption state
    (observation independence). Adding supplier #4 is one SUPPLIERS entry."""
    prof = SUPPLIERS[sid]
    if prof["drifts"]:
        band = sup.regime  # ontime|slipping|failing|defunct (Lever 1)
        otif, lead = SUPPLIER_SCORECARD[band]
    else:
        band, otif, lead = "ontime", prof["otif"], prof["lead"]
    row = {"id": sid, "otif": otif, "lead_days": lead, "band": band,
           "onboard_lead": prof["onboard_weeks"]}
    # unit economics, per supplier. The profile names the cfg field holding
    # the magnitude (cfg stays the single source of truth -- no number is
    # duplicated here) plus the sign and the optional extra display key. A
    # discount shows unit_discount, a premium shows unit_premium; backup shows
    # neither, just the signed delta.
    econ = prof["econ"]
    magnitude = getattr(cfg, econ["attr"])
    if econ["key"]:
        row[econ["key"]] = magnitude
    row["unit_delta"] = econ["sign"] * magnitude
    return row


def observe_scorecard(suppliers: dict, cfg: WorldConfig) -> dict:
    """The supplier factor's emission: a noiseless OTIF scorecard over the
    whole roster {id: SupplierState}, one row per supplier (A5). Order is
    fixed (registry order) so the readout is stable for the agent."""
    return {"suppliers": [_supplier_row(sid, suppliers[sid], cfg)
                          for sid in SUPPLIERS if sid in suppliers]}


# --- contracts: a TIMER + TERMS the agent set (observed, no hidden state) --
# Per-contract sourcing means you may only order from a supplier you hold a
# live contract with; per-order sourcing is the degenerate 1-tick contract.
# contract_open is the standing rule's predicate -- it reads ONLY conditions,
# never a date or named scenario, so the auto-renewal prompt EMERGES when the
# defunct primitive makes a counterparty die, with zero per-event code.

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


# --- the module's emit/view (registry composes them into a Module record) --
# This file does NOT import the registry (which imports this file): modules are
# pure state+kernel+emission, and registry.py is the sole place that knows the
# Module record shape. That one-way dependency is what breaks the cycle.

def emit(suppliers: dict, cfg: WorldConfig) -> dict:
    """The scorecard slice: {"suppliers": [...]}, byte-identical to today."""
    return observe_scorecard(suppliers, cfg)


def view(cfg: WorldConfig) -> dict:
    # the "suppliers" key is the whole roster (rows carry their own ids), so
    # its label is a fixed UI word, not an instance name -- inherently leak-
    # free in both semantics modes. Per-row labels come from the row data.
    return {"suppliers": {"role": "roster-row", "label": "scorecard"}}


# drives the roster ids whose profile sets drifts=True (only spot in R1).
DRIVES = tuple(sid for sid, p in SUPPLIERS.items() if p["drifts"])
