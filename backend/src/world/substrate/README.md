# `substrate/` — Tier 2: the module-agnostic logistics

The agent's books (shipments, inventory, demand) and the weekly voyage
resolution. This tier knows **ships and inventory, not `"disruption"` or
`"supplier"` by name**. It reads hidden states only through their public visible
properties (e.g. `h.canal_blocked`) or through the merged `effects` dict that the
modules produce. There is **no randomness here** — given the weekly hidden
states, every outcome is deterministic.

| File | Contents |
|------|----------|
| `books.py` | `Shipment` and `Books`. Pure bookkeeping + `_advance`, which resolves one in-flight ship against this week's world. |
| `logistics.py` | `resolve_week(...)`: dispatch → sail → land → consume demand → total the cost. |
| `semantics.py` | The anon display maps (`ROUTE_DISPLAY`, `STATUS_DISPLAY`, …) used to translate canonical names for presentation. |

## Transit-week causality

A chokepoint affects the ships that are **at** it that week, never the ships
merely ordered that week:

- A **Suez** ship meets the canal at `dispatch + suez_chokepoint_offset`. The
  canal's state *that* week decides through / backlog. A **queued** ship waits a
  week, then proceeds if clear or **diverts** around the Cape (billed at the Cape
  rate — the diversion surcharge, so ordering Suez into a known crisis isn't a
  free Cape voyage).
- A **Cape** ship meets its congestion point at
  `dispatch + cape_chokepoint_offset`; local congestion (or a long disruption)
  adds extra weeks.

An `arrives_week` is fixed once a ship's chokepoint resolves; until then `eta()`
returns the no-incident baseline (which may slip — that is the point).

## `resolve_week` — one week of physics

`resolve_week(books, qty, supplier, route, h, sup, week, cfg, effects=None)`
returns `(arrived_qty, cost_breakdown)`. In order:

1. **Dispatch.** A spot order ships `round(qty × fulfilled_fraction)` (the
   supplier stage resolves at dispatch — a degraded spot order may leave short);
   qualified always ships full. Shipping cost uses the route base rate, scaled by
   the `freight_mult` effect, with the spot-discount / qualified-premium unit
   economics.
2. **Sail.** Every in-flight ship advances one week (`_advance`), accruing any
   diversion surcharge.
3. **Land.** Arrivals this week stock the inventory — unless the `port_blocked`
   effect holds them a week (accruing demurrage). A `defect_fraction` of arrivals
   don't stock and incur rework.
4. **Consume demand.** `demand` effect units (else `cfg.weekly_demand`) are
   served from inventory; the unserved part is a stockout.
5. **Total the cost.** shipping, surcharge, holding, in-transit holding,
   stockout, the `couple` term, and — in the rich world — demurrage and rework.
   Those two lines are emitted **every** rich-world week (value `0.0` when no
   arrival was held / no batch was defective), so the *set* of cost keys is
   constant and the presence of a line never side-channels the hidden
   port/quality state. The default world emits neither key.

## Effects: how the rich modules reach the physics

`resolve_week` reads the merged `effects` dict **with a default for every key**,
so a world missing a factor behaves exactly like the original constant-driven
world:

| effect key | producer | default |
|------------|----------|---------|
| `demand` | `demand` | `cfg.weekly_demand` |
| `freight_mult` | `freight` | `1.0` |
| `port_blocked` / `demurrage_rate` | `port` | `False` / `0.0` |
| `defect_fraction` / `rework_rate` | `quality` | `0.0` |

With `effects` empty (the default two-factor world), every branch collapses to
the original arithmetic — the world is **byte-identical**.

## The pinned mirror

`logistics.resolve_week` has a twin: `oracle/causal.py:resolve_rel`, which runs
the *same* physics on the DP's canonical relative-pipeline encoding. The two
operate on different state representations and are **deliberately not deduped**
(a shared abstraction would de-optimize the DP or leak `Books` mutability into
it). They are held in lockstep by `test_resolve_rel_mirrors_resolve_week` plus
the per-step `causal_play` cross-check. **Touch the cost arithmetic here and you
must mirror it there.**
