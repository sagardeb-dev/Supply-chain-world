"""Supplier module — the spot reliability chain (second stochastic root,
visible as a noiseless OTIF scorecard) plus the supplier-stage observed
facts the substrate needs: contracts, the term menu, the display vocabulary,
the roster profile. Public surface re-exported for the registry and importers.

drives: the roster ids whose profile sets drifts=True (only spot in R1)."""

from .config import SUPPLIER_SCORECARD, SUPPLIERS
from .contracts import Contract, TERM_MENU, contract_open, terms_for
from .emission import _supplier_row, emit, observe_scorecard, view
from .factor import SUPPLIER_STATES, SupplierState, step_supplier
from .text import (SUPPLIER_BAND_DISPLAY, SUPPLIER_DISPLAY, SUPPLIER_PARSE)

DRIVES = tuple(sid for sid, p in SUPPLIERS.items() if p["drifts"])

__all__ = [
    "SupplierState", "step_supplier", "SUPPLIER_STATES",
    "observe_scorecard", "_supplier_row", "emit", "view",
    "Contract", "contract_open", "TERM_MENU", "terms_for",
    "SUPPLIER_DISPLAY", "SUPPLIER_PARSE", "SUPPLIER_BAND_DISPLAY",
    "SUPPLIERS", "SUPPLIER_SCORECARD", "DRIVES",
]
