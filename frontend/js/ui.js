// DOM-side HUD: order deck, bulletin, books, modals. Pure view layer —
// main.js owns the episode state and feeds normalised observations in.
const $ = (id) => document.getElementById(id);

const REGIME_COLORS = {
  calm: '#3a7d52', watch: '#b8932e', crash: '#c2622a',
  blockage: '#9333ea', crisis: '#dc2626', recovery: '#2e7fb8',
};

// One week-cell for a regime strip (shared by the x-ray rail and the
// end-of-episode reveal). `marks` is an optional short overlay string.
function regimeCell(week, regime, tip, marks = '') {
  const cell = document.createElement('div');
  cell.className = 'wk';
  cell.style.background = REGIME_COLORS[regime] ?? '#333';
  cell.innerHTML = `<span class="marks">${marks}</span>${week}`;
  cell.title = tip;
  return cell;
}

export class UI {
  constructor(handlers) {
    this.handlers = handlers;
    this.qty = 0;
    this.route = 'suez';
    this.supplier = 'qualified';
    this.routeLabels = { suez: 'Suez', cape: 'Cape' };
    this.supplierLabels = { qualified: 'Incumbent', spot: 'Spot', backup: 'Backup' };
    this.contractOpen = [];  // suppliers whose contract needs renewal

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
    $('supplier-seg').addEventListener('click', (e) => {
      const btn = e.target.closest('button');
      if (!btn || btn.disabled) return;
      this.supplier = btn.dataset.supplier;
      this.syncDeck();
    });
    $('btn-commit').addEventListener('click',
      () => handlers.onCommit(this.qty, this.route, this.supplier));
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
    $('xray-rail').classList.add('hidden');
    this.routeLabels = { suez: labels.routeSuez, cape: labels.routeCape };
    this.supplierLabels = { qualified: labels.supQualified, spot: labels.supSpot,
                            backup: labels.supBackup };
    const [sBtn, cBtn] = $('route-seg').querySelectorAll('button');
    sBtn.firstChild.textContent = labels.routeSuez;
    cBtn.firstChild.textContent = labels.routeCape;
    const [qBtn, pBtn, bBtn] = $('supplier-seg').querySelectorAll('button');
    qBtn.firstChild.textContent = labels.supQualified;
    pBtn.firstChild.textContent = labels.supSpot;
    if (bBtn) bBtn.firstChild.textContent = labels.supBackup;
    $('modal-new').classList.add('hidden');
    for (const id of ['week-pill', 'total-cost', 'news', 'books', 'deck']) {
      $(id).classList.remove('hidden');
    }
    this.qty = 0;
    this.route = 'suez';
    this.supplier = 'qualified';
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
    for (const b of $('supplier-seg').querySelectorAll('button')) {
      b.disabled = this.qty === 0;
      b.classList.toggle('active',
        this.qty !== 0 && b.dataset.supplier === this.supplier);
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

  // The obs→view boundary. EXTENSION POINT (hidden-factor scaling): a 2nd
  // latent module adds fields to obs; render them as additional rows here
  // (books / counts), not a bespoke panel per factor. The scene geometry is
  // world-specific and extended separately when a new factor lands.
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
      chip.className = `chip ${k === 'stockout' || k === 'surcharge' || k === 'couple' ? 'bad' : ''}`;
      chip.textContent = `${k.replace('_', ' ')} $${Math.round(v)}`;
      chips.appendChild(chip);
    }

    this._renderScorecard(obs);
  }

  // factor 2 HUD: a two-row OTIF scorecard. Severity accent by OTIF band
  // (green >=95 / amber 80-94 / red <80); the amber 'slipping' band is the
  // visible 1-week ambiguity. The sourced supplier gets a "<- sourced" mark.
  _renderScorecard(obs) {
    const rows = $('scorecard-rows');
    if (!rows) return;
    rows.innerHTML = '';
    const sourced = obs.sourcing?.supplier ?? null;
    const contracted = new Set((obs.contracts ?? []).map((c) => c.supplier));
    for (const s of obs.suppliers ?? []) {
      // band-driven severity: defunct = dead (the collapse is visible).
      const accent = s.band === 'defunct' ? 'level-dead'
        : s.band === 'failing' ? 'level-alert'
        : s.band === 'slipping' ? 'level-warn' : '';
      const li = document.createElement('div');
      li.className = `sc-row ${accent} ${s.id === sourced ? 'sourced' : ''}`;
      const name = this.supplierLabels[s.id] ?? s.id;
      const otif = s.otif == null ? '—' : `${s.otif}%`;
      const delta = s.unitDelta >= 0 ? `+$${s.unitDelta}` : `−$${Math.abs(s.unitDelta)}`;
      const marks = [];
      if (contracted.has(s.id)) marks.push('◆ contracted');
      if (s.id === sourced) marks.push('← sourced');
      if (s.onboardLead) marks.push(`${s.onboardLead}wk onboard`);
      const mark = marks.length
        ? `<span class="sc-mark">${marks.join('  ·  ')}</span>` : '';
      const dead = s.band === 'defunct' ? ' <span class="sc-dead">DEFUNCT</span>' : '';
      li.innerHTML = `<span class="sc-name">${name}${dead}</span>
        <span class="sc-otif">OTIF ${otif}</span>
        <span class="sc-lead">lead ${s.leadDays ?? '—'}d</span>
        <span class="sc-unit">${delta}/u</span>${mark}`;
      rows.appendChild(li);
    }
    this._renderContracts(obs);
  }

  // The contract HUD: active contracts (supplier, ends-week, terms) + the
  // auto-renewal PROMPT. When obs.contractOpen is non-empty, a banner appears
  // -- this is the emergence surfacing in the UI, fired by the world's own
  // standing rule (expiry or a defunct supplier), not by any scripted week.
  _renderContracts(obs) {
    const host = $('contract-rows');
    if (!host) return;
    host.innerHTML = '';
    for (const c of obs.contracts ?? []) {
      const name = this.supplierLabels[c.supplier] ?? c.supplier;
      const ends = c.endWeek == null ? 'evergreen' : `ends wk ${c.endWeek}`;
      const open = (obs.contractOpen ?? []).includes(c.supplier);
      const chip = document.createElement('div');
      chip.className = `contract-chip ${open ? 'open' : ''}`;
      chip.innerHTML = `<span class="ct-sup">${name}</span>
        <span class="ct-ends">${ends}</span>
        <span class="ct-price">$${c.unitPrice.toFixed(1)}/u</span>`;
      host.appendChild(chip);
    }
    const banner = $('contract-prompt');
    if (banner) {
      const open = obs.contractOpen ?? [];
      if (open.length) {
        const names = open.map((id) => this.supplierLabels[id] ?? id).join(', ');
        banner.textContent = `⚠ contract open: ${names} — renew, switch, or let lapse`;
        banner.classList.remove('hidden');
      } else {
        banner.classList.add('hidden');
      }
    }
  }

  // The post-mortem: hidden regimes per week, with order/briefing marks.
  showEnd(traceData) {
    $('end-cost').textContent = `$${Math.round(traceData.total_cost)}`;
    const strip = $('trace-strip');
    strip.innerHTML = '';
    for (const rec of traceData.trace) {
      const h = rec.hidden;
      const marks = [];
      if (rec.action?.briefing) marks.push('B');
      if (rec.action?.qty) marks.push(rec.action.route?.[0]?.toUpperCase() ?? '?');
      let tip = `week ${rec.week}: ${h.event_state}`;
      if (h.disruption_type) tip += ` (${h.disruption_type})`;
      if (h.cape_local_congestion) tip += ' + cape congestion';
      if (rec.action?.qty) tip += ` — ordered ${rec.action.qty} via ${rec.action.route}`;
      if (rec.action?.briefing) tip += ' — bought briefing';
      strip.appendChild(regimeCell(rec.week, h.regime, tip, marks.join('')));
    }
    const legend = $('trace-legend');
    legend.innerHTML = Object.entries(REGIME_COLORS)
      .map(([k, c]) => `<span><i style="background:${c}"></i>${k}</span>`)
      .join('') + '<span><b>B</b> = briefing, <b>S/C</b> = order route</span>';
    $('modal-end').classList.remove('hidden');
  }

  // The regret scoreboard: your cost between the clairvoyant lower bound
  // and the best naive policy, anchored on the causal oracle. Decomposes
  // your gap into skill (vs the oracle) and luck (oracle vs clairvoyant).
  showBenchmark(data, yourCost) {
    const board = $('scoreboard');
    if (!data || data.status === 'solving') {
      board.innerHTML = '<span class="dim">oracle solving — first run takes ~2 min…</span>';
      return;
    }
    const rows = [
      ['clairvoyant', data.clairvoyant, 'lower bound (sees the future)'],
      ['causal oracle', data.causal, 'the anchor (best play without the future)'],
      ['you', yourCost, ''],
      ['best naive', data.naive_min, 'best fixed policy'],
    ];
    const max = Math.max(...rows.map(([, v]) => v));
    board.innerHTML = rows.map(([label, v, note]) => `
      <div class="bench-row ${label === 'you' ? 'you' : ''}">
        <span class="bench-label">${label}</span>
        <span class="bench-bar"><i style="width:${(v / max) * 100}%"></i></span>
        <span class="bench-val">$${Math.round(v)}</span>
        <span class="bench-note">${note}</span>
      </div>`).join('');
    const skill = Math.round(yourCost - data.causal);
    const luck = Math.round(data.luck_premium);
    board.innerHTML += `<div class="bench-decomp">your regret vs the oracle =
      <b>$${skill}</b> (skill) · oracle − clairvoyant = <b>$${luck}</b> (luck premium)</div>`;

    // the oracle's weekly plan, same seed — its own strip of cells
    const strip = $('ghost-strip');
    strip.innerHTML = '';
    for (const r of data.plan) {
      const marks = [];
      if (r.briefed) marks.push('B');
      if (r.qty) marks.push((r.route?.[0] ?? '?').toUpperCase());
      const cell = document.createElement('div');
      cell.className = 'wk ghost';
      cell.innerHTML = `<span class="marks">${marks.join('')}</span>${r.week}`;
      cell.title = `week ${r.week}: ` + (r.qty
        ? `ordered ${r.qty} via ${r.route}` : 'held')
        + (r.briefed ? ' · bought briefing' : '');
      strip.appendChild(cell);
    }
    const briefs = data.plan.filter(r => r.briefed).length;
    $('ghost-caption').textContent =
      `the causal oracle's plan for seed ${data.seed} — it bought ${briefs} briefings`
      + (briefs === 0 ? ' (the chokepoint leak is free information)' : '');
  }

  // Live hidden tape for research-mode episodes. Revealed weeks show the
  // regime colour with the in-state age as a superscript; future weeks
  // stay neutral. Age is the semi-Markov clock — what makes duration
  // inferable from a sequence of identical-looking weeks.
  updateRail(weeks, horizon) {
    const strip = $('xray-strip');
    strip.innerHTML = '';
    for (const w of weeks) {
      const tip = `week ${w.week}: ${w.regime} (age ${w.event_age})`
        + (w.disruption_type ? ` · ${w.disruption_type}` : '');
      strip.appendChild(regimeCell(w.week, w.regime, tip, String(w.event_age)));
    }
    for (let wk = weeks.length; wk <= horizon; wk++) {
      const cell = document.createElement('div');
      cell.className = 'wk future';
      cell.innerHTML = `<span class="marks"></span>?`;
      strip.appendChild(cell);
    }
  }
}
