// Episode controller: wires the API, the Three.js scene, and the HUD.
import { api, LABELS, routeForWire, supplierForWire, normalizeObs } from './api.js';
import { SceneView } from './scene.js';
import { UI } from './ui.js';
import { AgentPanel } from './agent.js';
import { Store } from './store.js';

const HORIZON = 26; // cfg.horizon_weeks

const scene = new SceneView(document.getElementById('scene'));

const state = {
  episodeId: null,
  semantics: 'real',
  totalCost: 0,
  done: false,
  busy: false,
  research: false,
  seed: null,
};

// The oracle solves lazily server-side (~2 min on first request, then
// cached). Poll until ready and fill the scoreboard in progressively;
// the reveal never blocks on it.
async function pollBenchmark(seed, yourCost, tries = 0) {
  try {
    const data = await api.benchmark(seed);
    if (data.status === 'solving' && tries < 40) {
      ui.showBenchmark(null, yourCost);
      setTimeout(() => pollBenchmark(seed, yourCost, tries + 1), 5000);
      return;
    }
    ui.showBenchmark(data, yourCost);
  } catch (err) {
    console.error(err);
  }
}

async function guard(fn) {
  if (state.busy) return;
  state.busy = true;
  ui.setBusy(true);
  try {
    await fn();
  } catch (err) {
    console.error(err);
    alert(err.message); // surfaced raw: 409/422s here mean a logic bug
  } finally {
    state.busy = false;
    ui.setBusy(state.done);
  }
}

const ui = new UI({
  async onStart(seed, semantics, research) {
    if (!Number.isFinite(seed)) return ui.startError('seed must be a number');
    try {
      const res = await api.createEpisode(seed, semantics, research);
      state.episodeId = res.episode_id;
      state.semantics = semantics;
      state.research = research;
      state.seed = seed;
      state.totalCost = 0;
      state.done = false;
      const labels = LABELS[semantics];
      ui.beginEpisode(labels);
      store.begin({ semantics, seed, research, labels, firstObs: res.obs });
      state.obs = normalizeObs(res.obs, semantics);  // seed for auto-sign
      if (research) {
        document.getElementById('xray-rail')?.classList.remove('hidden');
        ui.updateRail((await api.xray(state.episodeId)).weeks, HORIZON);
      }
    } catch (err) {
      ui.startError(err.message.includes('fetch')
        ? 'backend unreachable — is uvicorn running?' : err.message);
    }
  },

  onBriefing: () => guard(async () => {
    const res = await api.briefing(state.episodeId);
    ui.showBriefing(res.briefing);
  }),

  onCommit: (qty, route, supplier) => guard(async () => {
    const wireRoute = qty ? routeForWire(state.semantics, route) : null;
    const wireSupplier = qty ? supplierForWire(state.semantics, supplier) : null;
    // The act of sourcing IS contracting: if the chosen supplier has no
    // open contract this week, auto-sign one in the same step (the engine
    // mask refuses an uncontracted source -- this is the human's sign UI).
    let contract = null;
    if (qty && wireSupplier) {
      const live = new Set((state.obs?.contracts ?? [])
        .filter((c) => !(state.obs?.contractOpen ?? []).includes(c.supplier))
        .map((c) => c.supplier));
      if (!live.has(supplier)) contract = { action: 'sign', supplier: wireSupplier };
    }
    const res = await api.step(state.episodeId, qty, wireRoute, wireSupplier, contract);
    state.obs = store.applyObs(res.obs, res.cost);
    state.totalCost = store.totalCost;
    state.done = res.done;
    ui.clearBriefing();
    if (state.research) {
      ui.updateRail((await api.xray(state.episodeId)).weeks, HORIZON);
    }
    if (res.done) {
      const finalCost = state.totalCost;
      const seed = state.seed;
      // let the final sail-in play out before the reveal
      setTimeout(async () => {
        const trace = await api.trace(state.episodeId);
        ui.showEnd(trace);
        pollBenchmark(seed, finalCost);
      }, 1600);
    }
  }),
});

// Single visible-episode store: both human commits (above) and agent
// obs-events (Task 4) drive scene + ui through it. Exported so the agent
// wiring can import the same instance.
const store = new Store(scene, ui);

ui.showNewModal();

// agent panel — the agent drives the SAME store/scene/ui the human play
// path uses. beginAgentEpisode reveals the shared HUD and clears the scene
// to week 0; each place_order SSE event then moves the world via the store.
function beginAgentEpisode({ seed, semantics }) {
  document.body.dataset.mode = 'agent';
  const labels = LABELS[semantics];
  ui.beginEpisode(labels);                 // reveal shared HUD panels
  store.begin({ semantics, seed, research: false, labels, firstObs: null });
}
const agentPanel = new AgentPanel(store, beginAgentEpisode);

// mode toggle: swap the bottom control region (CSS shows/hides by
// body[data-mode]). It does not start or stop any run — the human start
// modal opens on load; the agent run starts on its own run ▶ button.
document.getElementById('mode-toggle').addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;
  const mode = btn.dataset.mode;
  document.body.dataset.mode = mode;
  for (const b of document.querySelectorAll('#mode-toggle button')) {
    b.classList.toggle('active', b.dataset.mode === mode);
  }
});

window.__agentOnDone = (seed, totalCost) => {
  pollBenchmark(seed, totalCost);
  const endModal = document.getElementById('modal-end');
  if (endModal) endModal.classList.remove('hidden');
  const endCost = document.getElementById('end-cost');
  if (endCost) endCost.textContent = '$' + Math.round(totalCost);
};

// Shared singletons for the agent wiring (Task 4): one scene, one ui, one
// store — the agent drives the same instances the human play path uses.
export { store, scene, ui };
