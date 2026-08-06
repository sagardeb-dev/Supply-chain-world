export const meta = {
  name: 'lit-survey',
  description: 'API-grounded literature survey: seed-snowball + keyword search, dedupe, triage, deep-read, cited synthesis',
  whenToUse: 'When you need related work discovered and verified against real APIs (arXiv, Semantic Scholar) instead of model memory. args: {question, seeds: [arXiv IDs], terms: [search strings], keep?: N}',
  phases: [
    { title: 'Discover', detail: 'snowball each seed + keyword-search each term via live APIs' },
    { title: 'Triage', detail: 'score candidate abstracts for relevance' },
    { title: 'Read', detail: 'deep-read top papers from arxiv HTML' },
    { title: 'Synthesize', detail: 'survey with only API-verified citations' },
  ],
}

// GROUNDING RULE (the whole point): every arXiv ID must be copy-pasted from a live
// API response captured in this run. Agents are forbidden to add papers from memory.

const a = typeof args === 'string' ? JSON.parse(args) : args
const q = a?.question
if (!q) throw new Error('args.question required, e.g. {question, seeds:["2502.15840"], terms:["LLM agent inventory benchmark"]}')
const seeds = a?.seeds ?? []
const terms = a?.terms ?? []
const KEEP = a?.keep ?? 12

const CANDIDATES = {
  type: 'object', required: ['papers'],
  properties: {
    papers: {
      type: 'array',
      items: {
        type: 'object', required: ['arxiv_id', 'title', 'source'],
        properties: {
          arxiv_id: { type: 'string', description: 'exactly as it appeared in the API response; empty string if paper has no arXiv ID' },
          title: { type: 'string' },
          source: { type: 'string', description: 'which API call surfaced it (citations|references|recommendations|arxiv-search)' },
          abstract: { type: 'string', description: 'from the API response if present, else empty' },
        },
      },
    },
  },
}

phase('Discover')
const groundingRule = `HARD RULE: report ONLY papers that appear in the raw API responses you fetch with curl in this task. Never add a paper from your own knowledge, no matter how relevant it seems. Copy IDs/titles verbatim from the JSON/XML. If an API call fails after 2 retries (sleep 5 between), skip it and note the failure in a paper entry with title "API-FAILURE: <what>".`

const discovered = await parallel([
  ...seeds.map(id => () => agent(
    `Snowball the citation neighborhood of arXiv:${id} using live APIs (curl via Bash).
Research question for context (do not filter hard yet, just skip clearly unrelated fields): ${q}

Run these, retrying 429s (sleep 10, max 3 tries), and if Semantic Scholar keeps 429ing note it and move on:
1. curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:${id}/citations?fields=title,abstract,externalIds&limit=40"
2. curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:${id}/references?fields=title,abstract,externalIds&limit=40"
3. curl -s "https://api.semanticscholar.org/recommendations/v1/papers/forpaper/arXiv:${id}?fields=title,abstract,externalIds&limit=20"

From the responses, return every paper plausibly related to the research question. arxiv_id comes from externalIds.ArXiv (empty string if absent). ${groundingRule}`,
    { label: `snowball:${id}`, schema: CANDIDATES, model: 'sonnet' })),
  ...terms.map(t => () => agent(
    `Keyword-search arXiv's API for papers relevant to: ${q}

Run (curl via Bash, URL-encode the query): curl -s "http://export.arxiv.org/api/query?search_query=all:${encodeURIComponent(t)}&start=0&max_results=30&sortBy=relevance"
Also try one or two rephrasings of the term "${t}" the same way if the first pass looks thin.
Parse the Atom XML: each <entry> has <id> (contains the arXiv ID), <title>, <summary> (abstract).
Return entries plausibly relevant to the question; source="arxiv-search". ${groundingRule}`,
    { label: `search:${t.slice(0, 30)}`, schema: CANDIDATES, model: 'sonnet' })),
])

// dedupe by arXiv ID (title-key for the rare no-ID entries); drop failure markers
const byId = new Map()
for (const r of discovered.filter(Boolean)) {
  for (const p of r.papers) {
    if (p.title.startsWith('API-FAILURE')) { log(`discovery gap: ${p.title}`); continue }
    const key = p.arxiv_id || `title:${p.title.toLowerCase().slice(0, 60)}`
    const prev = byId.get(key)
    if (!prev || (!prev.abstract && p.abstract)) byId.set(key, p)
  }
}
const pool = [...byId.values()]
log(`discovered ${pool.length} unique candidates from ${discovered.filter(Boolean).length} channels`)
if (!pool.length) return { error: 'no candidates discovered — all API channels failed?' }

phase('Triage')
const SCORES = {
  type: 'object', required: ['scores'],
  properties: {
    scores: {
      type: 'array',
      items: {
        type: 'object', required: ['arxiv_id', 'score', 'why'],
        properties: {
          arxiv_id: { type: 'string' },
          score: { type: 'integer', description: '0-3: 0 unrelated, 1 background, 2 relevant, 3 must-read/possible overlap' },
          why: { type: 'string', description: 'one sentence' },
        },
      },
    },
  },
}
// chunks of 25 so each triage agent stays small
const chunks = []
for (let i = 0; i < pool.length; i += 25) chunks.push(pool.slice(i, i + 25))
const scored = (await parallel(chunks.map((c, i) => () => agent(
  `Score each candidate paper 0-3 for relevance to this research question:\n${q}\n\nCandidates (id | title | abstract-or-empty):\n${c.map(p => `${p.arxiv_id || 'NO-ID'} | ${p.title} | ${(p.abstract || '').slice(0, 600)}`).join('\n')}\n\nScore 3 = must-read or potential novelty overlap with the question; 0 = unrelated. Judge from title+abstract only; no fetching. Return a score for every candidate, using the arxiv_id exactly as given (or NO-ID).`,
  { label: `triage:${i}`, schema: SCORES, model: 'sonnet' }
)))).filter(Boolean).flatMap(r => r.scores)

const scoreOf = new Map(scored.map(s => [s.arxiv_id, s]))
const ranked = pool
  .map(p => ({ ...p, score: scoreOf.get(p.arxiv_id || 'NO-ID')?.score ?? 0, why: scoreOf.get(p.arxiv_id || 'NO-ID')?.why ?? '' }))
  .sort((a, b) => b.score - a.score)
const toRead = ranked.filter(p => p.score >= 2 && p.arxiv_id).slice(0, KEEP)
log(`triage: ${ranked.filter(p => p.score >= 2).length} relevant; deep-reading top ${toRead.length}`)

phase('Read')
const NOTES = {
  type: 'object', required: ['arxiv_id', 'claims', 'overlap_verdict'],
  properties: {
    arxiv_id: { type: 'string' },
    claims: { type: 'array', items: { type: 'string' }, description: 'each: one finding/method claim relevant to the question, with a short verbatim quote in double quotes' },
    overlap_verdict: { type: 'string', description: 'one sentence: does this paper already claim what the research question is probing?' },
  },
}
const notes = (await parallel(toRead.map(p => () => agent(
  `Deep-read arXiv:${p.arxiv_id} ("${p.title}") for this research question:\n${q}\n\nFetch full text: curl -s "https://arxiv.org/html/${p.arxiv_id}" (if 404 or garbage, try "https://arxiv.org/abs/${p.arxiv_id}" for the abstract page and work from that; note the downgrade).\nExtract only claims/findings/methods that bear on the question, each backed by a SHORT verbatim quote (<25 words) copied from the fetched text. If you cannot fetch any text, return claims=[] and say so in overlap_verdict. Never quote from memory.`,
  { label: `read:${p.arxiv_id}`, schema: NOTES, model: 'sonnet' }
)))).filter(Boolean)

phase('Synthesize')
const allowedIds = toRead.map(p => p.arxiv_id).join(', ')
const survey = await agent(
  `Write a literature-survey briefing (markdown, plain prose, no hype words) answering:\n${q}\n\nSource notes (the ONLY papers you may cite — allowed IDs: ${allowedIds}):\n${JSON.stringify(notes, null, 1)}\n\nAlso list, as "adjacent, not read", the next tier that scored 2+ but wasn't deep-read:\n${ranked.filter(p => p.score >= 2 && !toRead.includes(p)).map(p => `${p.arxiv_id} ${p.title}`).join('\n')}\n\nStructure: (1) direct answer to the question, (2) per-paper notes with the verbatim quotes, (3) what appears NOT claimed anywhere (novelty space), (4) adjacent-not-read list. Every citation must be one of the allowed IDs, written as arXiv:ID. No other papers may be named, even famous ones.`,
  { label: 'synthesize', model: 'sonnet' })

// mechanical grounding check: every arXiv ID in the survey must be from this run's pool
// strip vN suffixes: pool entries like "2605.05379v1" must match cited "2605.05379"
const bare = id => id.replace(/v\d+$/, '')
const cited = [...new Set((survey.match(/\d{4}\.\d{4,5}/g) || []))]
const poolIds = new Set(pool.map(p => p.arxiv_id && bare(p.arxiv_id)).filter(Boolean))
const leaked = cited.filter(id => !poolIds.has(id))
if (leaked.length) log(`GROUNDING VIOLATION — IDs not from any API response: ${leaked.join(', ')} — treat those citations as hallucinated`)

return { survey, grounding_violations: leaked, read: toRead.map(p => p.arxiv_id), discovered: pool.length }
