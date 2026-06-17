// Agent panel: streams a live LLM episode and renders it into the log.
// Owns #agent-panel, #ag-run, #ag-advance, #agent-log.

const BASE = new URLSearchParams(location.search).get('api') ?? '';

// compact object → "k=v, k=v"
function compactArgs(args) {
  return Object.entries(args).map(([k, v]) => k + '=' + JSON.stringify(v)).join(', ');
}

export class AgentPanel {
  constructor() {
    this._src    = null;   // active EventSource
    this._runId  = null;
    this._lastThought = null;  // current thought div (for coalescing)

    this._log    = document.getElementById('agent-log');
    this._runBtn = document.getElementById('ag-run');
    this._advBtn = document.getElementById('ag-advance');

    this._runBtn.addEventListener('click', () => this.run());
    this._advBtn.addEventListener('click', () => this.advance());
  }

  // ── public ──────────────────────────────────────────────────────────────

  async run() {
    const model    = document.getElementById('ag-model').value.trim();
    const seed     = Number(document.getElementById('ag-seed').value);
    const mode     = document.getElementById('ag-mode').value;

    if (!model) return;
    this._closeSource();
    this._clearLog();
    this._setAdvance(false);

    let res;
    try {
      res = await fetch(BASE + '/agent/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seed, model, mode }),
      });
      if (!res.ok) throw new Error('POST /agent/runs → ' + res.status);
    } catch (err) {
      this._appendError(err.message);
      return;
    }

    const data = await res.json();
    this._runId = data.run_id;
    this._open('/agent/runs/' + this._runId + '/stream');
  }

  async advance() {
    if (!this._runId) return;
    this._closeSource();
    this._setAdvance(false);

    let res;
    try {
      res = await fetch(BASE + '/agent/runs/' + this._runId + '/advance', {
        method: 'POST',
      });
      if (!res.ok) throw new Error('POST /agent/runs/advance → ' + res.status);
    } catch (err) {
      this._appendError(err.message);
      return;
    }

    // advance returns an SSE body over POST — read it manually
    await this._readStream(res.body);
  }

  // ── stream plumbing ──────────────────────────────────────────────────────

  // open a GET SSE stream (initial run)
  _open(path) {
    this._closeSource();
    const src = new EventSource(BASE + path);
    this._src = src;

    for (const name of ['thought', 'tool_call', 'tool_result', 'interrupt', 'done', 'error']) {
      src.addEventListener(name, (e) => {
        let obj;
        try { obj = JSON.parse(e.data); } catch { obj = {}; }
        this._handle(name, obj);
      });
    }

    src.onerror = () => {
      // EventSource fires onerror on clean server close too; only show if still active
      if (this._src === src) {
        this._closeSource();
      }
    };
  }

  // read a POST SSE response body with a reader — used by advance()
  async _readStream(body) {
    const reader  = body.getReader();
    const decoder = new TextDecoder();
    let   buf     = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      // split on double newline (SSE frame boundary)
      const frames = buf.split('\n\n');
      buf = frames.pop(); // keep incomplete trailing frame

      for (const frame of frames) {
        if (!frame.trim()) continue;
        let eventName = 'message';
        let dataLine  = '';
        for (const line of frame.split('\n')) {
          if (line.startsWith('event:')) eventName = line.slice(6).trim();
          else if (line.startsWith('data:')) dataLine = line.slice(5).trim();
        }
        let obj;
        try { obj = JSON.parse(dataLine); } catch { obj = {}; }
        this._handle(eventName, obj);
      }
    }
  }

  _closeSource() {
    if (this._src) { this._src.close(); this._src = null; }
  }

  // ── unified event handler ────────────────────────────────────────────────

  _handle(name, data) {
    switch (name) {
      case 'thought':      this._onThought(data);     break;
      case 'tool_call':    this._onToolCall(data);    break;
      case 'tool_result':  this._onToolResult(data);  break;
      case 'interrupt':    this._onInterrupt(data);   break;
      case 'done':         this._onDone(data);        break;
      case 'error':        this._onError(data);       break;
    }
  }

  // ── event renderers ──────────────────────────────────────────────────────

  _onThought({ text }) {
    // coalesce consecutive chunks into one bubble
    if (!this._lastThought) {
      const div = document.createElement('div');
      div.className = 'ag-thought';
      this._log.appendChild(div);
      this._lastThought = div;
    }
    this._lastThought.textContent += text;
    this._scrollLog();
  }

  _onToolCall({ name, args }) {
    this._lastThought = null;  // break thought coalescing
    const div = document.createElement('div');
    div.className = 'ag-tool';
    div.innerHTML = '▸ <b>' + name + '</b>(' + compactArgs(args ?? {}) + ')';
    this._log.appendChild(div);
    this._scrollLog();
  }

  _onToolResult({ content }) {
    this._lastThought = null;
    const div = document.createElement('div');
    div.className = 'ag-result';
    const text = String(content ?? '');
    div.textContent = text.length > 400 ? text.slice(0, 400) + '…' : text;
    this._log.appendChild(div);
    this._scrollLog();
  }

  _onInterrupt({ proposals }) {
    this._lastThought = null;
    const compact = (proposals ?? [])
      .map(p => p.name + '(' + compactArgs(p.args ?? {}) + ')')
      .join(', ');
    const div = document.createElement('div');
    div.className = 'ag-interrupt';
    div.textContent = 'proposed: ' + compact + ' — click Advance';
    this._log.appendChild(div);
    this._scrollLog();
    this._setAdvance(true);
  }

  _onDone({ seed, total_cost }) {
    this._lastThought = null;
    this._closeSource();
    const div = document.createElement('div');
    div.className = 'ag-done';
    div.textContent = 'episode done · total cost $' + total_cost;
    this._log.appendChild(div);
    this._scrollLog();
    this._setAdvance(false);
    // wire into the existing oracle scoreboard
    if (typeof window.__agentOnDone === 'function') {
      window.__agentOnDone(seed, total_cost);
    }
  }

  _onError({ message }) {
    this._lastThought = null;
    this._closeSource();
    this._appendError(message);
    this._setAdvance(false);
  }

  // ── helpers ──────────────────────────────────────────────────────────────

  _appendError(msg) {
    const div = document.createElement('div');
    div.className = 'ag-error';
    div.textContent = 'error: ' + msg;
    this._log.appendChild(div);
    this._scrollLog();
  }

  _clearLog() {
    this._log.innerHTML = '';
    this._lastThought = null;
  }

  _scrollLog() {
    this._log.scrollTop = this._log.scrollHeight;
  }

  _setAdvance(enabled) {
    this._advBtn.disabled = !enabled;
  }
}
