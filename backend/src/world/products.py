"""Product structure for the assembly world (substrate-level, NOT a latent
factor): the bill of materials mapping each finished good to the components you
must import and assemble. Selected by cfg.product.

The default `single` is a degenerate one-finished-good-from-one-component (1:1)
structure, so the per-component substrate reproduces the legacy single-SKU
physics byte-for-byte (initial stock still comes from cfg.initial_inventory).
`earbuds` is the assembly config the scored v2 world uses: two models sharing a
battery, with a pricey long-lead ANC chip.

ponytail: the initials / leads / cost deltas below are calibration knobs -- the
tuning workstream sweeps them; grounded starting points, not final."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Component:
    """A purchasable part. `lead_extra` is production/handling lead ADDED on top
    of the sea transit (the scarce chip takes longer to make); `cost_delta` is a
    per-unit surcharge over the route base cost (the pricey ANC chip)."""
    initial: int             # starting on-hand stock (single: overridden by cfg)
    lead_extra: int = 0      # weeks added before it ships (production lead)
    cost_delta: float = 0.0  # per-unit cost over the route base


@dataclass(frozen=True)
class Product:
    bom: dict                # finished good -> {component: qty_per_unit}
    components: dict         # component id -> Component

    @property
    def finished_goods(self) -> tuple:
        return tuple(self.bom)

    @property
    def component_ids(self) -> tuple:
        return tuple(self.components)


# degenerate single-SKU: one finished good from one component, 1:1. Its initial
# stock is seeded from cfg.initial_inventory at reset (not the value below), so
# every legacy world/test that sets initial_inventory keeps identical physics.
SINGLE = Product(
    bom={"unit": {"unit": 1}},
    components={"unit": Component(initial=80)},
)

# the earbuds line: `standard` and `pro` both need a `battery` (shared -- a
# battery shortage starves BOTH models), plus a model-specific chip. `chip_pro`
# is the pricey, longer-lead part (the real "chip shortage" pressure).
EARBUDS = Product(
    bom={"standard": {"battery": 1, "chip_std": 1},
         "pro":      {"battery": 1, "chip_pro": 1}},
    components={
        "battery":  Component(initial=80),
        "chip_std": Component(initial=40),
        "chip_pro": Component(initial=40, lead_extra=1, cost_delta=2.0),
    },
)

PRODUCTS = {"single": SINGLE, "earbuds": EARBUDS}


def structure(name: str) -> Product:
    if name not in PRODUCTS:
        raise ValueError(f"unknown product {name!r}; choose from {list(PRODUCTS)}")
    return PRODUCTS[name]


if __name__ == "__main__":  # ponytail self-check: BOM/component wiring is consistent
    for name, p in PRODUCTS.items():
        comps = {c for bom in p.bom.values() for c in bom}
        assert comps == set(p.components), (name, comps, set(p.components))
        assert all(q > 0 for bom in p.bom.values() for q in bom.values())
    print("products ok:", {n: (p.finished_goods, p.component_ids) for n, p in PRODUCTS.items()})
