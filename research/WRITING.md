# WRITING.md — paper-writing playbook (compiled 2026-07-07 from sourced research)

Rules for any prose written in this directory. Sources verified by web research
2026-07-07; URLs at bottom. Claude: re-read this file before drafting or editing
any paper section.

## A. Craft — how the paper is built

1. **One key idea, stated in one sentence.** If the paper's contribution can't be
   said in 1–2 sentences, the story isn't ready. Ours: *a fair (non-privileged)
   Bayes-filter oracle makes the knowing-doing gap a computable, cost-weighted
   number.* Everything that doesn't serve this gets cut. (Peyton Jones)
2. **Story arc, not lab log:** problem → why it's hard → idea → evidence. Never
   narrate what we tried chronologically.
3. **Contributions = itemized, falsifiable claims** in the intro ("we introduce X",
   "we measure Y"), not topic statements.
4. **Related work goes near the END.** In the intro, differentiate only enough to
   position (2–3 nearest neighbors, one falsifiable reason each doesn't suffice).
   (Peyton Jones; ICLR reviewer Q2 is "well-placed in the literature?")
5. **Figure 1 is the paper.** A reader should get the whole idea from Figure 1 +
   caption alone. Invest there first. (Foerster)
6. **Method-anchored prose until results freeze** — findings live in [SLOT] blocks,
   written last; abstract written very last. (house rule, see memory
   no-premature-findings)
7. **Lipton/Steinhardt tripwires** — reviewers are primed to catch:
   - stating WHY something works when we only showed THAT it works (flag
     mechanisms as hypotheses unless ablated);
   - misattributing gains (for us: skill differences must not be attributable to
     prompt/budget differences between models — same prompt, same levers);
   - mathiness (every equation must sharpen a claim; else cut);
   - loaded words ("understands", "reasons", "knows") doing work the evidence
     hasn't earned. NB: our whole paper is about "knowing" — define it
     operationally on first use (stated rationale text) and stick to it.

## B. Benchmark-paper-specific bar

Reviewers judge benchmark papers on impact narrative, not technical novelty
(NeurIPS D&B chairs: scores compress high, differentiation happens on the
"why this matters" case). Top rejection reasons, mapped to us:

| Rejection reason | Our answer (must be in the paper) |
|---|---|
| "Yet another benchmark" — weak differentiation | Name RetailBench/AIM-Bench/Vending-Bench and the specific gap: privileged oracle vs our fair one; no controlled compound axis elsewhere |
| Construct validity — what does it NOT measure | Say explicitly: measures stated-belief→action conversion; does NOT measure internal belief (lower bound), single SKU, single domain |
| No trivial/null baseline | Base-stock floor IS the null baseline — say so explicitly |
| Single-seed, no variance | Oracle = 20-rep means with SE reported; LLM runs: report what we have honestly, n in every table caption |
| Unfair baselines | Oracle sees identical observations + identical action menu — state this in one prominent sentence, it's the paper's spine |
| Contamination | Ours is generative (seeded tapes, not scraped data) — one sentence noting tapes can't be in training data, seeds published |
| Data/code availability | Release harness + tapes + traces; persistent hosting if archival venue |

## C. Workshop-paper specifics

- 4–6 pages → ONE core claim, ONE key figure, dense citations with brief
  discussion, secondary analysis to appendix.
- Preliminary is fine and expected — frame as "early evidence toward X", never
  oversell maturity. Rigorous limitations are an ACCEPTANCE criterion at many
  workshops ("papers that downplay limitations will not be accepted" — MechInterp
  CFP), not politeness.
- Reviewers are often junior/reciprocal: spell out why the problem matters more
  explicitly than for main track; the first read must land clean (little rebuttal
  recovery).
- Non-archival → don't over-polish; this draft feeds a later archival version.

## D. AI-assisted writing — hard rules

The author uses Claude to help draft. To keep that safe and undetectable-as-slop:

1. **Never emit a citation from model memory.** Every reference verified against
   arXiv/Semantic Scholar before entering the bibliography. NeurIPS names
   unverified LLM references as an integrity violation (publication revocable);
   arXiv bans for a year. All arXiv IDs currently in draft/notes came from the
   lit-scan agents — RE-VERIFY each one at paper.tex time.
2. **Never emit a number from model memory.** Every number traces to
   `backend/runs/...` files. Missing → [PENDING], never estimated. (existing house
   rule, now venue-backed)
3. **Slop-word greplist** — before any draft is shown or submitted, grep and
   rewrite hits (Kobak et al.; "Why ChatGPT delves" Table 2):
   `delve|delves|delved|delving|intricate|intricac|underscor|showcas|surpass|boast|garner|groundbreaking|advancement|meticulous|realm|crucial|pivotal|moreover|furthermore|leverag|comprehending|aligns`
   Also structural tells: "not X but Y" reframes, rule-of-three lists, every
   paragraph shaped topic-sentence→3-supports→summary, hedge-heavy topic
   sentences, uniform sentence lengths, bold-header+bullet formula.
4. **Em dashes:** keep them rare; a weak tell alone but compounds with others.
5. **Overclaiming bias is baked into RLHF prose** — strip confident inflation
   ("significantly", "remarkably", "novel") unless the number next to it earns it.
6. **Related-work prose is never generated from scratch** — LLM finds and
   verifies candidates; the comparative "differs from us because…" analysis is
   written specifically, per-paper, from the actual abstracts.
7. **Disclosure:** follow the strictest plausible target venue. NeurIPS: disclose
   if LLM use is a non-standard component (writing assistance per se: no
   disclosure needed, but full author responsibility). ICLR 2026: ANY LLM use
   must be disclosed in paper + form. ACL/ARR: language-polish exempt,
   content-drafting must be disclosed in checklist. AAAI: LLM-generated prose
   banned outright (edit/polish OK). Practical rule: author rewrites/owns every
   sentence; keep a one-line acknowledgment ready ("LLM assistance was used for
   editing and literature search; all content verified by the authors").
   Over-disclosing costs ~nothing; discovery of undisclosed use is desk-reject
   territory. Detection tooling (Pangram-class: FPR <0.1%) is good enough that
   "nobody will notice" is not a plan.
8. **No prompt-injection games ever** (hidden text targeting LLM reviewers) —
   automatic desk reject at ICML, ethics violation at ICLR. Obvious, but stated.

## E. Pre-submission mechanical checklist

- [ ] Page limit, margins, font untouched (style violations = desk reject)
- [ ] Anonymized: no repo links that identify, no "our prior work [X]"
- [ ] Every citation clicked and verified (title/authors/year/venue)
- [ ] Every number traced to a runs/ file; no [PENDING] left
- [ ] Slop-greplist run on final text (rule D3)
- [ ] Limitations section present and honest (C)
- [ ] One sentence stating oracle fairness (identical observations) — the spine
- [ ] Group means only from re-badged skill.md (never the old EASY/MED/HARD means)
- [ ] Figure 1 + caption standalone-readable
- [ ] AI-use disclosure per venue rule (D7)

## Sources (key ones)

- Peyton Jones, How to Write a Great Research Paper — simon.peytonjones.org/great-research-paper/
- Lipton & Steinhardt, Troubling Trends in ML Scholarship — arxiv.org/abs/1807.03341
- ICML 2026 Reviewer Instructions — icml.cc/Conferences/2026/ReviewerInstructions
- ICLR 2026 Reviewer Guide — iclr.cc/Conferences/2026/ReviewerGuide
- NeurIPS D&B CFP + chairs' 2025 retrospective — neurips.cc/Conferences/2025/CallForDatasetsBenchmarks ; blog.neurips.cc/2025/09/30/
- Construct validity in LLM benchmarks — openreview.net/pdf?id=mdA5lVvNcU
- Kobak et al., excess vocabulary — arxiv.org/html/2406.07016v1
- Why Does ChatGPT "Delve" So Much — arxiv.org/html/2412.11385v1
- Citation hallucination rates (18–55% fabricated on niche topics) — jmir.org/2024/1/e53164
- Venue LLM policies: neurips.cc/Conferences/2025/LLM ; iclr.cc/FAQ/LLM ; icml.cc/Conferences/2026/Intro-LLM-Policy ; aaai.org AAAI-26 CFP ; arXiv genAI policy
- Voice-preserving workflow — alexgude.com/blog/how-i-write-with-llms-revised/
