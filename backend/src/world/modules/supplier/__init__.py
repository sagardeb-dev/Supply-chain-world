"""Supplier module — the spot reliability chain (second stochastic root,
visible as a noiseless OTIF scorecard) plus the supplier-stage observed
facts the substrate needs: contracts, the term menu, the display vocabulary,
the roster profile. Public surface re-exported for the registry and importers.

drives: the roster ids the kernel advances. Legacy (sup_all_drift off): only
spot. Phase 2 (sup_all_drift on): all three, each on its own personality."""

from .config import SUPPLIER_SCORECARD, SUPPLIERS
from .contracts import Contract, TERM_MENU, contract_open, terms_for
from .emission import (_supplier_row, emit, observe_scorecard,
                       supplier_audit, view)
from .factor import SUPPLIER_STATES, SupplierState, step_supplier
from .text import (SUPPLIER_BAND_DISPLAY, SUPPLIER_DISPLAY, SUPPLIER_PARSE)


def _drives(cfg):
    """A callable roster selector (like the demand module): WHO drifts this
    world. Legacy default advances only spot -- its per-week rng prefix is
    unchanged, so old trajectories/goldens stay byte-identical. Phase 2
    (cfg.sup_all_drift) advances all three; spot stays FIRST so its stream
    prefix is untouched and qualified/backup draws APPEND after (rng append
    discipline). A module-level function (NOT a lambda) so the World stays
    picklable for agent-run resume."""
    return ("spot", "qualified", "backup") if cfg.sup_all_drift else ("spot",)


DRIVES = _drives

__all__ = [
    "SupplierState", "step_supplier", "SUPPLIER_STATES",
    "observe_scorecard", "_supplier_row", "emit", "view", "supplier_audit",
    "Contract", "contract_open", "TERM_MENU", "terms_for",
    "SUPPLIER_DISPLAY", "SUPPLIER_PARSE", "SUPPLIER_BAND_DISPLAY",
    "SUPPLIERS", "SUPPLIER_SCORECARD", "DRIVES",
]
