// DOM-side HUD: order deck, bulletin, books, modals. Pure view layer —
// main.js owns the episode state and feeds normalised observations in.
const $ = (id) => document.getElementById(id);

const REGIME_COLORS = {
  calm: '#3a7d52', watch: '#b8932e', crash: '#c2622a',
  blockage: '#9333ea', crisis: '#dc2626', recovery: '#2e7fb8',
};

export class UI {
  constructor(handlers) {
    this.handlers = handlers;
    this.qty = 0;
    this.route = 'suez';
    this.routeLabels = { suez: 'Suez', cape: 'Cape' };

    $('qty-seg').addEventListener('click', (e) => {
      const btn = e.target.closest('button');
      if (!btn) return;
      this.qty = Number(btn.dataset.qty);
      this.syncDeck();
    });
    $('route-seg').addEventListener('click', (e) => {
      const btn = e.target.closest('button');
      if (!btn || btn.disabled) return;
      this.route = btn.dataset.route;
      this.syncDeck();
    });
    $('btn-commit').addEventListener('click', () => handlers.onCommit(this.qty, this.route));
    $('btn-briefing').addEventListener('click', handlers.onBriefing);
    $('btn-start').addEventListener('click', () => handlers.onStart(
      Number($('inp-seed').value), $('inp-semantics').value, $('inp-research').checked));
    $('btn-new-episode').addEventListener('click', () => this.showNewModal());
    $('btn-again').addEventListener('click', () => {
      $('modal-end').classList.add('hidden');
      this.showNewModal();
    });
  }

  showNewModal() {
    $('inp-seed').value = Math.floor(Math.random() * 10000);
    $('new-error').classList.add('hidden');
    $('modal-new').classList.remove('hidden');
  }

  startError(msg) {
    const el = $('new-error');
    el.textContent = msg;
    el.classList.remove('hidden');
  }

  // episode started — reveal the HUD, adapt labels to the semantics mode
  beginEpisode(labels) {
    this.routeLabels = { suez: labels.routeSuez, cape: labels.routeCape };
    const [sBtn, cBtn] = $('route-seg').querySelectorAll('button');
    sBtn.firstChild.textContent = labels.routeSuez;
    cBtn.firstChild.textContent = labels.routeCape;
    $('modal-new').classList.add('hidden');
    for (const id of ['week-pill', 'total-cost', 'news', 'books', 'deck']) {
      $(id).classList.remove('hidden');
    }
    this.qty = 0;
    this.route = 'suez';
    this.clearBriefing();
    this.syncDeck();
  }

  syncDeck() {
    for (const b of $('qty-seg').querySelectorAll('button')) {
      b.classList.toggle('active', Number(b.dataset.qty) === this.qty);
    }
    for (const b of $('route-seg').querySelectorAll('button')) {
      b.disabled = this.qty === 0;
      b.classList.toggle('active', this.qty !== 0 && b.dataset.route === this.route);
    }
  }

  setBusy(busy) {
    $('btn-commit').disabled = busy;
    $('btn-briefing').disabled = busy;
  }

  showBriefing(text) {
    $('briefing-text').textContent = text;
    $('briefing-card').classList.remove('hidden');
  }

  clearBriefing() {
    $('briefing-card').classList.add('hidden');
  }

  update(obs, totalCost, horizon) {
    $('week-label').textContent = `Week ${obs.week} / ${horizon}`;
    $('week-fill').style.width = `${(obs.week / horizon) * 100}%`;
    $('total-cost').querySelector('b').textContent = `$${Math.round(totalCost)}`;

    // bulletin, with a severity accent driven by the observed suez count
    $('bulletin-text').textContent = obs.bulletin;
    const ratio = obs.suezCount / 70;
    $('news').className = `panel ${ratio < 0.5 ? 'level-alert' : ratio < 0.95 ? 'level-warn' : ''}`;

    // books
    $('inv-num').textContent = obs.inventory;
    $('arrived-num').textContent = obs.arrived;
    const fill = $('inv-fill');
    fill.style.width = `${Math.min(100, (obs.inventory / 160) * 100)}%`;
    fill.classList.toggle('low', obs.inventory < 20);

    const list = $('pipeline-list');
    list.innerHTML = '';
    if (!obs.pipeline.length) {
      list.innerHTML = '<li class="dim">no shipments at sea</li>';
    }
    for (const s of obs.pipeline) {
      const li = document.createElement('li');
      const st = s.status === 'at_sea' ? 'at sea' : s.status;
      li.innerHTML = `<span class="route-dot ${s.route}"></span>
        <span>${s.qty}u · ${this.routeLabels[s.route]} · eta wk ${s.eta}</span>
        <span class="st ${s.status}">${st}</span>`;
      list.appendChild(li);
    }

    const chips = $('cost-chips');
    chips.innerHTML = '';
    const entries = Object.entries(obs.costs).filter(([, v]) => v > 0);
    if (!entries.length) chips.innerHTML = '<span class="dim">—</span>';
    for (const [k, v] of entries) {
      const chip = document.createElement('span');
      chip.className = `chip ${k === 'stockout' || k === 'surcharge' ? 'bad' : ''}`;
      chip.textContent = `${k.replace('_', ' ')} $${Math.round(v)}`;
      chips.appendChild(chip);
    }
  }

  // The post-mortem: hidden regimes per week, with order/briefing marks.
  showEnd(traceData) {
    $('end-cost').textContent = `$${Math.round(traceData.total_cost)}`;
    const strip = $('trace-strip');
    strip.innerHTML = '';
    for (const rec of traceData.trace) {
      const h = rec.hidden;
      const cell = document.createElement('div');
      cell.className = 'wk';
      cell.style.background = REGIME_COLORS[h.regime] ?? '#333';
      const marks = [];
      if (rec.action?.briefing) marks.push('B');
      if (rec.action?.qty) marks.push(rec.action.route?.[0]?.toUpperCase() ?? '?');
      cell.innerHTML = `<span class="marks">${marks.join('')}</span>${rec.week}`;
      let tip = `week ${rec.week}: ${h.event_state}`;
      if (h.disruption_type) tip += ` (${h.disruption_type})`;
      if (h.cape_local_congestion) tip += ' + cape congestion';
      if (rec.action?.qty) tip += ` — ordered ${rec.action.qty} via ${rec.action.route}`;
      if (rec.action?.briefing) tip += ' — bought briefing';
      cell.title = tip;
      strip.appendChild(cell);
    }
    const legend = $('trace-legend');
    legend.innerHTML = Object.entries(REGIME_COLORS)
      .map(([k, c]) => `<span><i style="background:${c}"></i>${k}</span>`)
      .join('') + '<span><b>B</b> = briefing, <b>S/C</b> = order route</span>';
    $('modal-end').classList.remove('hidden');
  }
}
