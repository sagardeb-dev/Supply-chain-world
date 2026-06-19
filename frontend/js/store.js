// Single source of truth for the visible episode. BOTH human commits and
// agent obs-events drive the world through applyObs() — one renderer, two
// drivers. No world logic here; it only routes normalized obs to scene + ui.
//
// EXTENSION POINT (hidden-factor scaling): a future 2nd latent module adds
// fields to the raw obs. normalizeObs() maps them and ui.update() renders
// them as additional rows — additive here, not a bespoke panel per factor.
import { normalizeObs } from './api.js';

const HORIZON = 26; // cfg.horizon_weeks

export class Store {
  constructor(scene, ui) {
    this.scene = scene;
    this.ui = ui;
    this.reset();
  }

  reset() {
    this.totalCost = 0;
    this.done = false;
    this.semantics = 'real';
    this.seed = null;
    this.research = false;
  }

  // Begin a fresh episode view (human OR agent). `firstObs` is the week-0
  // raw obs, or null when the caller has no week-0 obs yet (agent runs: the
  // scene clears to an empty week-0 lane and the first place_order obs moves
  // it forward). null is an explicit "no obs yet" signal, not a fallback.
  begin({ semantics, seed, research, labels, firstObs }) {
    this.reset();
    this.semantics = semantics;
    this.seed = seed;
    this.research = research;
    this.scene.setLabels(labels);
    if (firstObs) {
      const obs = normalizeObs(firstObs, semantics);
      this.scene.reset(obs);
      this.ui.update(obs, 0, HORIZON);
    } else {
      const obs = this._emptyObs();
      this.scene.reset(obs);
      this.ui.update(obs, 0, HORIZON);
    }
  }

  // The ONE coupling point. `rawObs` is API/agent-shaped; `cost` is this
  // week's delta added to the running total. Drives scene + books + pill.
  // Returns the normalized obs so callers can read week/done if needed.
  applyObs(rawObs, cost) {
    const obs = normalizeObs(rawObs, this.semantics);
    if (typeof cost === 'number') this.totalCost += cost;
    this.scene.applyObs(obs);
    this.ui.update(obs, this.totalCost, HORIZON);
    return obs;
  }

  // A blank week-0 view, in the ALREADY-NORMALIZED shape scene.applyObs and
  // ui.update consume (the begin() else-branch passes it through without
  // normalizeObs). Empty pipeline, calm baseline counts, full books. Used
  // when an agent run starts before any obs has streamed.
  _emptyObs() {
    return {
      week: 0, suezCount: 70, babCount: 70, capeCount: 60,
      bulletin: '', inventory: 80, arrived: 0,
      costs: {}, pipeline: [],
      // factor 2 calm default: both suppliers nominal, nothing sourced yet
      suppliers: [
        { id: 'qualified', otif: 99, leadDays: 14, unitDelta: 1.0 },
        { id: 'spot', otif: 98, leadDays: 14, unitDelta: -1.5 },
      ],
      sourcing: null,
    };
  }
}
