// Thin client for the FastAPI backend. Same-origin by default (the
// backend mounts this frontend as static files); set ?api=<base> to
// point elsewhere during development.
const BASE = new URLSearchParams(location.search).get('api') ?? '';

async function call(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.ok || res.status === 202) return res.json();
  let detail = res.statusText;
  try { detail = (await res.json()).detail ?? detail; } catch { /* not json */ }
  throw new Error(`${res.status}: ${detail}`);
}

export const api = {
  createEpisode: (seed, semantics, research) => call('POST', '/episodes', { seed, semantics, research_mode: research }),
  step: (id, qty, route, supplier) => call('POST', `/episodes/${id}/step`, { qty, route, supplier }),
  briefing: (id) => call('POST', `/episodes/${id}/briefing`),
  trace: (id) => call('GET', `/episodes/${id}/trace`),
  xray: (id) => call('GET', `/episodes/${id}/xray`),
  benchmark: (seed) => call('GET', `/benchmark/${seed}`),
};

// ---- semantics vocabulary -------------------------------------------------
// The engine speaks canonical names; "anon" episodes rename everything at
// the API boundary. We normalise observations back to canonical for the
// scene, and translate canonical -> display when sending actions.

const ROUTE_SEND = {
  real: { suez: 'suez', cape: 'cape' },
  anon: { suez: 'route_1', cape: 'route_2' },
};

const SUPPLIER_SEND = {
  real: { qualified: 'qualified', spot: 'spot' },
  anon: { qualified: 'source_a', spot: 'source_b' },
};

export const LABELS = {
  real: {
    suez: 'Suez Canal', bab: 'Bab el-Mandeb', cape: 'Cape of Good Hope',
    routeSuez: 'Suez', routeCape: 'Cape',
    origin: 'Shanghai', dest: 'Rotterdam',
    supQualified: 'Qualified', supSpot: 'Spot',
  },
  anon: {
    suez: 'Waterway One', bab: 'The Strait', cape: 'Waterway Two',
    routeSuez: 'Waterway 1', routeCape: 'Waterway 2',
    origin: 'Origin Port', dest: 'Destination',
    supQualified: 'Source A', supSpot: 'Source B',
  },
};

export function routeForWire(semantics, canonical) {
  return ROUTE_SEND[semantics][canonical];
}

export function supplierForWire(semantics, canonical) {
  return SUPPLIER_SEND[semantics][canonical];
}

export function normalizeObs(obs, semantics) {
  const anon = semantics === 'anon';
  return {
    week: obs.week,
    suezCount: anon ? obs.waterway1_count : obs.suez_count,
    babCount: anon ? obs.strait_count : obs.bab_count,
    capeCount: anon ? obs.waterway2_count : obs.cape_count,
    bulletin: obs.bulletin,
    inventory: obs.inventory,
    arrived: obs.arrived,
    costs: obs.cost_breakdown,
    pipeline: obs.pipeline.map((s) => ({
      qty: s.qty,
      dispatched: s.dispatched_week,
      eta: s.eta,
      route: s.route === 'route_2' || s.route === 'cape' ? 'cape' : 'suez',
      supplier: canonicalSupplier(s.supplier),
      status: s.status.startsWith('queued') ? 'queued'
        : s.status.startsWith('diverted') ? 'diverted' : 'at_sea',
    })),
    // factor 2: the OTIF scorecard (canonical ids), and what was sourced
    // this week derived from the newest shipment (an action fact, not an
    // emission fact — see spec A5).
    suppliers: (obs.suppliers ?? []).map((s) => ({
      id: canonicalSupplier(s.id),
      otif: s.otif,
      leadDays: s.lead_days,
      unitDelta: s.unit_discount != null ? -s.unit_discount : s.unit_premium,
    })),
    sourcing: sourcingFromPipeline(obs.pipeline, obs.week),
  };
}

// anon source_a/source_b (or already-canonical) -> qualified/spot
function canonicalSupplier(id) {
  return (id === 'source_b' || id === 'spot') ? 'spot' : 'qualified';
}

// The newest shipment dispatched THIS week tells us which supplier was
// sourced and how much actually shipped vs ordered. null if nothing shipped.
function sourcingFromPipeline(pipeline, week) {
  const fresh = pipeline.find((s) => s.dispatched_week === week);
  if (!fresh) return null;
  return { supplier: canonicalSupplier(fresh.supplier), shipped: fresh.qty };
}
