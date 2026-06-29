export const meta = {
  name: 'preplan',
  description: 'Re-ground the codebase before writing a new-task spec: fan out read-only auditors over docs/AGENTS.md/READMEs/memory, scripts, the world engine, the agent layer, and tests/API; each judges what is stale, throwaway, or buggy RELATIVE TO the new direction; then synthesize one prioritized cleanup + bug list for the main agent to apply.',
  whenToUse: 'Before writing a spec for a new or changed benchmark task, when stale context spread across docs and scripts could poison the plan. Pass the new direction as args (a string); falls back to the embedded inventory-management direction.',
  phases: [
    { title: 'Audit' },
    { title: 'Synthesize' },
  ],
}

const ROOT = '/data/supply-chain-pomdp'

const DIRECTION = args || `The benchmark is being redesigned from "masked-distress supplier sourcing" to CLASSICAL INVENTORY MANAGEMENT.
- Company: an electronics brand importing a hero gadget (earbuds) by sea from Asia; the agent runs weekly replenishment.
- Problem: size the order/buffer to meet UNCERTAIN weekly demand at minimum total cost (holding $1/u/wk vs stockout $20/u, ~95% service implied), under disrupted lead times (Red Sea -> Cape reroute) and a silently-failing cheap supplier (the masked-distress task is now only a SUB-challenge, not the headline).
- v1 is SCORED on a 3-factor core (disruption + supplier + demand), but the world is genuinely 6-factor (disruption, supplier, demand, freight, port, quality) PLUS a multi-SKU/assembly future. Code must NOT hardcode 3 factors; the factored module registry must stay intact so adding factors/SKUs is a config change.
- The 2-factor CausalOracle (pinned value ~4251.96) is LEGACY and NOT a design constraint. Order qty {0,20,40} should become a free quantity. The prompt's anti-buffer steer ("do not carry a big buffer") is now WRONG -- we want right-sized safety stock. The demand module exists but is benched in the scored 2-factor task.
STALE = anything asserting: the masked-supplier task is THE benchmark; the oracle is a sacred pin; demand is flat/deterministic; buffers should be minimized; or code/docs that hardcode 2 or 3 factors.`

// One auditor's structured output.
const FINDINGS = {
  type: 'object',
  additionalProperties: false,
  properties: {
    dimension: { type: 'string' },
    stale_docs: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          file: { type: 'string' }, location: { type: 'string' },
          claim: { type: 'string' }, why_stale: { type: 'string' }, fix: { type: 'string' },
        },
        required: ['file', 'claim', 'why_stale', 'fix'],
      },
    },
    scripts: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          file: { type: 'string' }, purpose: { type: 'string' },
          verdict: { type: 'string', enum: ['keep', 'delete', 'uncertain'] },
          reason: { type: 'string' },
        },
        required: ['file', 'verdict', 'reason'],
      },
    },
    bugs: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          file: { type: 'string' }, symptom: { type: 'string' },
          severity: { type: 'string', enum: ['high', 'med', 'low'] },
          evidence: { type: 'string' },
        },
        required: ['file', 'symptom', 'severity'],
      },
    },
    reality_gaps: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          topic: { type: 'string' }, finding: { type: 'string' }, evidence: { type: 'string' },
        },
        required: ['topic', 'finding'],
      },
    },
  },
  required: ['dimension', 'stale_docs', 'scripts', 'bugs', 'reality_gaps'],
}

// The merged report.
const REPORT = {
  type: 'object',
  additionalProperties: false,
  properties: {
    summary: { type: 'string' },
    delete_scripts: {
      type: 'array',
      items: { type: 'object', additionalProperties: false,
        properties: { file: { type: 'string' }, reason: { type: 'string' } },
        required: ['file', 'reason'] },
    },
    doc_edits: {
      type: 'array',
      items: { type: 'object', additionalProperties: false,
        properties: { file: { type: 'string' }, change: { type: 'string' } },
        required: ['file', 'change'] },
    },
    bugs_ranked: {
      type: 'array',
      items: { type: 'object', additionalProperties: false,
        properties: { file: { type: 'string' }, symptom: { type: 'string' },
          severity: { type: 'string' }, fix_hint: { type: 'string' } },
        required: ['file', 'symptom', 'severity'] },
    },
    reality_gaps: {
      type: 'array',
      items: { type: 'object', additionalProperties: false,
        properties: { topic: { type: 'string' }, finding: { type: 'string' } },
        required: ['topic', 'finding'] },
    },
    open_questions_for_spec: { type: 'array', items: { type: 'string' } },
  },
  // ponytail: only summary is required; a large synthesis that omits one array
  // must not fail validation (that aborted the first run's StructuredOutput).
  required: ['summary'],
}

const DIMENSIONS = [
  { key: 'docs', targets:
    `Docs & memory. Read: ${ROOT}/backend/AGENTS.md, ${ROOT}/backend/src/world/AGENTS.md, ${ROOT}/backend/src/world/README.md, ${ROOT}/backend/src/agent/README.md, ${ROOT}/backend/README.md (if it exists), and every *.md under /home/azureuser/.claude/projects/-data-supply-chain-pomdp/memory/. Flag every CLAIM that is now false or misleading under the new direction (e.g. "masked-distress supplier task IS the benchmark", "CausalOracle is 2-factor only / its value is pinned", "place_order is the only week-advancing tool" if reframed, anything implying flat demand or minimal buffers). Put findings in stale_docs with the exact file + section/line + the claim + why it is stale + the concrete fix.` },
  { key: 'scripts', targets:
    `Top-level scripts. Read each of: ${ROOT}/backend/play.py, ${ROOT}/backend/report_oracle.py, ${ROOT}/backend/scan_scenarios.py, ${ROOT}/backend/scan_seeds.py, ${ROOT}/backend/scan_supplier_seeds.py. For EACH, decide keep vs delete vs uncertain. CRITICAL: before saying "delete", grep the codebase for imports of that module (e.g. report_oracle is imported by src/api/app.py and exposes base_stock_cost + fixed_policy_cost -- that is LOAD-BEARING, keep it). The scan_*.py files are likely throwaway dev scanners. Record each in scripts[] with purpose + verdict + reason (cite whether anything imports it).` },
  { key: 'world', targets:
    `The world engine. Read across ${ROOT}/backend/src/world/ : engine.py, config.py, registry.py, the modules/ subpackages (disruption, supplier, demand, freight, port, quality), substrate/, and oracle/. Report: (a) bugs or dead code; (b) reality-gaps vs the new direction -- is the demand module wired into the scored task or benched? does anything hardcode 2/3 factors or special-case the registry? is order qty enforced to {0,20,40}? what is the oracle's actual scope and is it coupled to anything that would block changing the default world? (c) how ready are the BOOKS (substrate) for multi-SKU (inventory is a single int today). Use bugs[] and reality_gaps[].` },
  { key: 'agent', targets:
    `The agent layer. Read across ${ROOT}/backend/src/agent/ : prompt.py, tools.py, runner.py, service.py, factory.py, play_agent.py. Report stale framing and bugs: the prompt's anti-buffer steer (quote the exact lines), any masked-task / freight-lock / 2-factor assumptions baked into defaults, whether the agent is shown an inventory-position number or must sum it by hand, and anything that would mislead an LLM doing inventory management. Use stale_docs[] for prompt text (file=prompt.py) and bugs[]/reality_gaps[] for code.` },
  { key: 'tests-api', targets:
    `Tests & API surface. Read ${ROOT}/backend/test_world.py (large -- scan its test names + the oracle/2-factor ones), ${ROOT}/backend/src/api/app.py, and ${ROOT}/frontend/js/api.js. Report which tests encode stale assumptions that would BLOCK the redesign (the CausalOracle().value() pin, masked-only or 2-factor-only benchmark assumptions, the qty-menu tests) and which API endpoints/baselines already exist for the new task (base_stock_cost? fixed_policy_cost? a benchmark endpoint?). Use bugs[]/reality_gaps[]; list pin/blocking tests under reality_gaps with file + test name.` },
]

phase('Audit')
const audits = (await parallel(DIMENSIONS.map(d => () =>
  agent(
    `You are a READ-ONLY auditor grounding a supply-chain POMDP benchmark codebase before its spec is rewritten.\n\n` +
    `NEW DIRECTION:\n${DIRECTION}\n\n` +
    `YOUR SCOPE (${d.key}):\n${d.targets}\n\n` +
    `Be specific: cite file paths and line numbers / section headers / test names. Do not speculate beyond what you read. ` +
    `STRICTLY READ-ONLY: do not edit, create, move, or delete any file -- only read and report. ` +
    `Set "dimension" to "${d.key}". Return empty arrays for categories you found nothing in.`,
    { label: `audit:${d.key}`, phase: 'Audit', schema: FINDINGS }
  )
))).filter(Boolean)

log(`audited ${audits.length}/${DIMENSIONS.length} dimensions`)

phase('Synthesize')
const report = await agent(
  `You are synthesizing a PREPLAN report: the codebase is about to have a new-task spec written, and stale context must be cleaned first.\n\n` +
  `NEW DIRECTION:\n${DIRECTION}\n\n` +
  `Here are the read-only audit findings as JSON:\n${JSON.stringify(audits, null, 1)}\n\n` +
  `Merge and de-duplicate into ONE prioritized, actionable report:\n` +
  `- delete_scripts: only files clearly safe to delete (nothing imports them; throwaway). Never list a load-bearing module.\n` +
  `- doc_edits: each stale doc claim -> the concrete change (file + what to change). Group by file.\n` +
  `- bugs_ranked: real bugs/dead code, highest severity first, with a short fix_hint.\n` +
  `- reality_gaps: things the spec author MUST know is already true (e.g. a baseline already exists, demand is benched, qty is enforced, a test pins X).\n` +
  `- open_questions_for_spec: genuine decisions the redesign must make (e.g. keep or delete the legacy oracle, lost-sales vs backorders, scored registry scope).\n` +
  `Keep it tight and concrete. Write "summary" as 2-3 sentences a human can read first.`,
  { label: 'synthesize', phase: 'Synthesize', schema: REPORT }
)

return report
