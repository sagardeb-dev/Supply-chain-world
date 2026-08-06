export const meta = {
  name: 'paper-check',
  description: 'Chain-of-evidence gate for the workshop paper: every claim verified against the ledger, code, traces, and citation APIs',
  whenToUse: 'Before sharing or submitting any paper draft. Run research/check.sh first (free); this is the judgment layer.',
  phases: [{ title: 'Verify' }],
}
// Chain-of-evidence design (2026-07-31, after Google's Science-One post):
// the verifiers consume the LIVING ledgers (RESULTS-LOG.md claim map,
// STATS-GUIDELINES.md verdicts, DEFECTS.md) as ground truth instead of a
// story hardcoded here. Rationale: the previous version of this file froze
// the 2026-07-15 narrative into its prompts and went stale when the D1/D2
// corrections landed — it would have flagged the CORRECTED paper as wrong.
// Never hardcode result numbers or verdicts in this file again; point the
// agents at the ledgers.
// Evolve dimensions as the paper grows. Re-invoke with {scriptPath};
// resumeFromRunId caches unchanged stages.
// All agents on sonnet (user usage limits — memory: sonnet-for-subagents).

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['blocker', 'warn', 'nit'] },
          location: { type: 'string' },
          problem: { type: 'string' },
          evidence: { type: 'string' },
        },
        required: ['severity', 'location', 'problem', 'evidence'],
      },
    },
  },
  required: ['findings'],
}

const PAPER = 'research/paper.tex'
const COMMON = `You are an adversarial verifier trying to BREAK a workshop paper before a real reviewer does. Repo root: /data/supply-chain-pomdp. Paper: ${PAPER}.
GROUND TRUTH IS THE LEDGER LAYER, read it before the paper:
- research/RESULTS-LOG.md — temporal ledger; its claim map names the ONLY file each paper number may come from; entries marked SUPERSEDED are dead numbers that must NOT appear in the paper.
- research/STATS-GUIDELINES.md — which claims are SUPPORTED / DISSOLVED / REFUTED, and the comparison-verb rule (any beats/worse/below/faster/flat sentence needs a CI + test in a canonical file).
- research/DEFECTS.md — known measurement defects; disclosures the paper must carry.
- research/CLAUDE.md and research/WRITING.md — house rules.
Do NOT trust any narrative summary (results.md, skill.md, case-studies.md, old TRACE-INSIGHTS) over the ledger + canonical CSVs. Report only real problems with file:line evidence; empty findings array if clean. severity=blocker means "a reviewer catching this sinks the paper".`

phase('Verify')
const DIMENSIONS = [
  {
    key: 'numbers',
    prompt: `${COMMON}
Dimension: NUMBERS (evidence-chain completeness). For EVERY numeric claim in the paper (skill scores, detection %, lags, KDR, costs, CIs, p-values, counts like episodes/seeds/weeks, dollar excesses): (1) find its claim-map row in RESULTS-LOG.md, (2) open the canonical file that row names, (3) confirm the number appears there (grep it; allow rounding stated in the file). Blockers: a number with no canonical source; a number that only exists in a SUPERSEDED entry's outputs (e.g. pre-correction detection/KDR values, any *.pre-airfix content, core-20-era or n=20-era leftovers); a number that mismatches its canonical file; a CI or p-value quoted differently from uq.csv/uq.md/cost_decomp.md/oracle_decomp.md.`,
  },
  {
    key: 'claims',
    prompt: `${COMMON}
Dimension: CLAIM SUPPORT (evidence-chain correctness). Read STATS-GUIDELINES.md fully — it lists every tested claim with its verdict. Then read the paper end to end. Blockers: any comparison-verb sentence (beats/worse/best/below/faster/slower/flat/same/peaks/excess) with no CI+test behind it in a canonical file; any claim STATS-GUIDELINES marks DISSOLVED or REFUTED stated in its strong form (check the exact softened phrasing the ledger prescribes, e.g. "fail to beat the floor" not "below the floor", "detect no slower" not "shortest lags", "no detectable difference" not "identical/flat"); any pre-registered contrast reported without its failed/unpredicted-sign siblings disclosed; any cross-bucket or cross-model comparison the ledger says was never tested; abstract/intro/results/discussion telling different strengths of the same claim; required disclosures missing (oracle knows-the-physics; stated-belief lower bound; single run per cell; seed-11 exclusion; compound oversampling; same-tape-weeks-not-counterfactual caveat on the oracle decomposition; severity confound beside KDR; the DEFECTS.md items the paper says it discloses).`,
  },
  {
    key: 'method-code',
    prompt: `${COMMON}
Dimension: METHOD-CODE ALIGNMENT. Compare every mechanism the paper describes against the implementation. Read the paper's world/method/metric sections, then verify each described mechanic in code: the world engine and cost mechanics (backend/src/ — find engine, logistics, costs), the six factor processes, the levers, the oracle (backend/oracle_policy.py + filters — exact per-factor HMM forward filters + rolling-horizon MPC, 20 reps k=191..210 per backend/bench_config.py), the skill formula ((basestock − llm)/(basestock − oracle)), the floor policy, the grading pipeline (backend/runs/grade_beliefs.py — engine-truth stockouts, week-26 exclusions, detection denominator), and the analysis machinery (backend/analysis/*.py — bootstrap N_BOOT/seed, bucket definitions, DIAG/UNDIAG/CALM classify rule). Blockers: prose that misdescribes what the code does (wrong formula, wrong protocol constant, a mechanism claimed that is not implemented, a filter type misnamed); warn for underspecification a reader could not reimplement from.`,
  },
  {
    key: 'score-verify',
    prompt: `${COMMON}
Dimension: SCORE VERIFICATION (independent re-run). The analysis layer is deterministic local compute with built-in gates. From /data/supply-chain-pomdp/backend run each of these with "uv run --with numpy python <script>" (add --with scipy if imported): analysis/uq.py (has FROZEN asserts that loudly fail on drift), analysis/cost_decomp.py, analysis/oracle_decomp.py (both have replay/refs gates). BEFORE running: copy the CSVs/mds they overwrite to a scratch dir (/tmp/claude-1000 scratch), run, then diff regenerated outputs against the committed canonical versions byte-wise or numerically, then RESTORE the originals if anything differs. Blockers: any script that errors or fails its own gate; any regenerated number that differs from the canonical file a paper claim cites. Warn: scripts that cannot run for environment reasons (say why). Report exactly what you ran and the diff result per file.`,
  },
  {
    key: 'quotes',
    prompt: `${COMMON}
Dimension: TRACE QUOTES. For every quoted or paraphrased trace excerpt (Results narrative + appendix exhibits), grep the actual trace under backend/runs/ladder-v1/<model>/seedN-rich.chat.txt and confirm wording, week numbers, and surrounding facts (inventory levels, costs, consecutive stockout weeks — recount from the trace, including any "cum $" arithmetic). The mds can drift; traces are ground truth. Flag any mismatch as blocker.`,
  },
  {
    key: 'citations',
    prompt: `${COMMON}
Dimension: CITATIONS. For every arXiv ID / cited paper in text and bibliography: fetch https://arxiv.org/abs/<id>, verify (a) it exists, (b) title/authors/venue match what we call it, (c) the specific claim we attach is supported by its abstract/content. Known trap: our RetailBench is 2603.16453, NOT 2606.15862. Any unresolved or mischaracterized citation = blocker (venues treat unverified LLM citations as integrity violations). Remaining \\todocite placeholders = warn before submission, blocker at submission.`,
  },
  {
    key: 'prose',
    prompt: `${COMMON}
Dimension: PROSE / WRITING.md compliance. Run the full WRITING.md greplist (including 2025-26 additions) against the paper; check structural tells (negative parallelism, summary closers, hedging boilerplate, em-dash density, uniform sentence shape); bolded mini-heading claim-sentences in Results/Discussion (author-banned — flowing prose only); undefined jargon on first use (author standard: a qualified reader without the codebase); cross-section repetition (the same finding restated in full in more than one place — cite both locations); contributions stated as falsifiable claims; limitations woven as prose. Blockers only for slop a reviewer would clock as AI-written or repetition that visibly pads the page budget; else warn/nit.`,
  },
]

const results = await parallel(
  DIMENSIONS.map(d => () =>
    agent(d.prompt, { label: `check:${d.key}`, phase: 'Verify', schema: FINDINGS, model: 'sonnet' })
  )
)

const all = results
  .map((r, i) => ({ r, key: DIMENSIONS[i].key }))
  .filter(x => x.r)
  .flatMap(x => x.r.findings.map(f => ({ dimension: x.key, ...f })))
const order = { blocker: 0, warn: 1, nit: 2 }
all.sort((a, b) => order[a.severity] - order[b.severity])
const dead = results.filter(r => !r).length
log(`${all.filter(f => f.severity === 'blocker').length} blockers, ${all.filter(f => f.severity === 'warn').length} warns, ${all.filter(f => f.severity === 'nit').length} nits${dead ? ` (${dead} verifier(s) died — rerun)` : ''}`)
return { findings: all }
