# Case-study material for the paper (verified trace excerpts, 2026-07-07)

Every quote below was read directly from the named trace file. Line refs may
drift if traces are regenerated — verify by grepping the quoted text.

## Exhibit A: the knowing-doing gap — sonnet-5, seed 1 (PERSISTENT)
Trace: backend/runs/ladder-v1/anthropic-claude-sonnet-5/seed1-rich.chat.txt
Truth: port congested wk17-24; promo_spike wk9-12; seasonal_lift wk20-26.

- Wk16 (detection correct, action = freeze): "Port congestion has spiked
  severely (berth_wait 10 days...) ... I'll skip placing a new sea order this
  week ... and reassess next week once conditions hopefully ease."
- Wk17 (misses demand regime off one noisy dip): "demand has genuinely
  softened (pos_units 12, forecast 9) versus the ~20-25 baseline... I have
  ~6+ weeks of cover... I'll place no order this week."
- Wk22 (THE quote; inventory 0, stockout in progress): "Despite the current
  0 on-hand inventory, I already have a very large pipeline: 104 units in
  transit... roughly 4-5 weeks of cover... ordering more now would only add
  to an already oversized pipeline... given berth_wait is still elevated (15
  days)." -> counts units trapped behind the congestion it itself diagnosed
  as sellable cover; orders zero; 4 consecutive zero-inventory weeks
  (wk21-24, $600-800/wk stockout costs).
- Contrast: the fair oracle keeps placing modest sea orders THROUGH the
  congestion (they arrive after it clears). gpt-5.4 fails the same way on
  this seed (3 zero-inventory weeks) plus a rigid 60-or-0 order-size habit.

## Exhibit B: over-reaction — deepseek-v4-pro, seed 25 (ISOLATED)
Trace: backend/runs/ladder-v1/deepseek-deepseek-v4-pro/seed25-rich.chat.txt
Truth: canal disruption wk4-5 ONLY (brief); scattered 1-2wk customs holds.

- Wk4: "Disruption confirmed — Suez counts crashed to 28/25... Cape is now
  the only safe route. Locked freight at 1.02x for 4 weeks. Ordering 40 via
  Cape."
- Wk5: "Suez fully blocked... Expedited 20 air units... Ordering 40 via
  Cape/spot for weeks 9-10 coverage."
- Wk6 it correctly says "Suez reopening — short disruption" — but has already
  stacked a freight lock + 80 units + premium air against ~20/wk demand on
  top of 78 already in pipeline. Weeks 5-8 cost $814/$669/$610/$674, almost
  all self-inflicted fees+holding. Final $7,950 vs base-stock $6,100 ->
  skill -1.45 on an easy seed. Detection was flawless throughout.

## The two failure modes in one line
Sonnet freezes (see danger -> stop acting -> starve); DeepSeek flails (see
danger -> pull every lever -> drown in fees). Neither is a detection failure.

## Seed dossier (true hidden-factor timelines, from action-independent tape replay)
Regenerate: replay World with empty actions, read filters._true_regime per week
(pattern in backend/sweep/run_sweep.py).

- 157 ISOLATED: canal wk12-13; quality wk23-24; freight spike wk25-26.
- 25  ISOLATED: canal wk4-5; customs holds wk6-7/12/21/26; supplier wk20.
- 112 ISOLATED: demand only — decline wk13-14, seasonal_lift wk20-24.
- 1   PERSISTENT: port congested wk17-24 x seasonal_lift wk20-26; promo wk9-12.
- 172 PERSISTENT: port congested wk5-11 x promo wk9-12; supplier degrades wk24-26.
- 170 PERSISTENT: freight spike wk3-8 x port congested wk5-12; promos wk2-5,15-18; freight again wk24-26.
- 21  COMPOUND: seasonal wk10-17; then wk21-26 pileup: canal + quality + supplier.
- 143 COMPOUND: freight wk5-10 -> port wk10-17; supplier wk2-5; canal wk15,25.
- 99  COMPOUND: 3 port episodes, 2 canal closures, 3 demand regimes (marathon).
- New 11 (60,24,86 / 95,29,58,108 / 44,94,154,85): timelines not yet dumped —
  regenerate with the replay above if needed.

## Flagged, unverified
- deepseek seed 99 skill 1.85 (beat oracle mean on hardest seed): suspected
  fat-buffer accident, trace NOT yet read. Verify before citing.
