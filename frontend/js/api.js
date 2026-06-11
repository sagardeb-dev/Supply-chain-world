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
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* not json */ }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export const api = {
  createEpisode: (seed, semantics) => call('POST', '/episodes', { seed, semantics }),
  step: (id, qty, route) => call('POST', `/episodes/${id}/step`, { qty, route }),
  briefing: (id) => call('POST', `/episodes/${id}/briefing`),
  trace: (id) => call('GET', `/episodes/${id}/trace`),
};

// ---- semantics vocabulary -------------------------------------------------
// The engine speaks canonical names; "anon" episodes rename everything at
// the API boundary. We normalise observations back to canonical for the
// scene, and translate canonical -> display when sending actions.

const ROUTE_SEND = {
  real: { suez: 'suez', cape: 'cape' },
  anon: { suez: 'route_1', cape: 'route_2' },
};

export const LABELS = {
  real: {
    suez: 'Suez Canal', bab: 'Bab el-Mandeb', cape: 'Cape of Good Hope',
    routeSuez: 'Suez', routeCape: 'Cape',
    origin: 'Shanghai', dest: 'Rotterdam',
  },
  anon: {
    suez: 'Waterway One', bab: 'The Strait', cape: 'Waterway Two',
    routeSuez: 'Waterway 1', routeCape: 'Waterway 2',
    origin: 'Origin Port', dest: 'Destination',
  },
};

export function routeForWire(semantics, canonical) {
  return ROUTE_SEND[semantics][canonical];
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
      status: s.status.startsWith('queued') ? 'queued'
        : s.status.startsWith('diverted') ? 'diverted' : 'at_sea',
    })),
  };
}
