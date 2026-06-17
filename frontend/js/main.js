// Episode controller: wires the API, the Three.js scene, and the HUD.
import { api, LABELS, normalizeObs, routeForWire } from './api.js';
import { SceneView } from './scene.js';
import { UI } from './ui.js';

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
      scene.setLabels(labels);
      ui.beginEpisode(labels);
      const obs = normalizeObs(res.obs, semantics);
      scene.reset(obs);
      ui.update(obs, 0, HORIZON);
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

  onCommit: (qty, route) => guard(async () => {
    const wireRoute = qty ? routeForWire(state.semantics, route) : null;
    const res = await api.step(state.episodeId, qty, wireRoute);
    state.totalCost += res.cost;
    state.done = res.done;
    ui.clearBriefing();
    const obs = normalizeObs(res.obs, state.semantics);
    scene.applyObs(obs);
    ui.update(obs, state.totalCost, HORIZON);
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

ui.showNewModal();
