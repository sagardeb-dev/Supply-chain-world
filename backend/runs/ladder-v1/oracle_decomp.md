# Oracle reference for the cost decomposition

Fair-oracle per-week engine cost_breakdown under the exact oracle_refs protocol (20 reps, k=191..210), rep-mean per (seed, week), compared against each model's spend on its own diagnosed weeks. Seed-cluster paired bootstrap, N_BOOT=10000, rng seed 20260728. Caveat: week-t books reflect each policy's earlier decisions; this is spend on the same tape weeks, not a one-decision counterfactual.

## Model vs oracle, bucket $/wk on the model's own weeks (95% CI)

| model | class | side | procurement | holding | stockout | levers | incident | total |
|---|---|---|---|---|---|---|---|---|
| gpt-5.4 | DIAG | model | 61 [49,75] | 98 [93,104] | 20 [11,31] | 91 [76,107] | 30 [21,40] | 300 [273,328] |
| gpt-5.4 | DIAG | oracle | 65 [57,75] | 95 [92,98] | 37 [25,50] | 58 [43,75] | 34 [24,44] | 289 [261,317] |
| gpt-5.4 | UNDIAG | model | 66 [43,90] | 107 [99,115] | 5 [0,13] | 58 [32,86] | 2 [1,4] | 238 [204,272] |
| gpt-5.4 | UNDIAG | oracle | 65 [50,81] | 96 [91,100] | 23 [11,37] | 19 [7,36] | 5 [2,11] | 207 [184,234] |
| gpt-5.4 | CALM | model | 55 [49,61] | 111 [105,117] | 10 [4,19] | 28 [20,36] | 1 [0,1] | 204 [194,216] |
| gpt-5.4 | CALM | oracle | 65 [57,73] | 99 [97,100] | 13 [7,20] | 7 [5,10] | 1 [0,1] | 184 [174,194] |
| claude-sonnet-5 | DIAG | model | 70 [61,79] | 85 [81,88] | 32 [23,42] | 126 [110,142] | 29 [21,38] | 341 [318,365] |
| claude-sonnet-5 | DIAG | oracle | 65 [57,73] | 95 [92,98] | 34 [23,45] | 55 [40,70] | 32 [23,41] | 280 [254,305] |
| claude-sonnet-5 | UNDIAG | model | 69 [54,86] | 91 [85,98] | 14 [4,27] | 159 [125,193] | 19 [7,33] | 352 [302,404] |
| claude-sonnet-5 | UNDIAG | oracle | 69 [52,89] | 101 [95,106] | 31 [17,46] | 46 [24,71] | 23 [9,39] | 268 [228,313] |
| claude-sonnet-5 | CALM | model | 47 [42,52] | 83 [81,85] | 10 [5,16] | 39 [30,48] | 0 [0,1] | 179 [166,193] |
| claude-sonnet-5 | CALM | oracle | 65 [57,73] | 99 [97,100] | 13 [7,20] | 7 [5,10] | 1 [0,1] | 184 [174,194] |
| grok-4.5 | DIAG | model | 87 [77,96] | 120 [113,128] | 37 [24,52] | 81 [66,96] | 40 [29,53] | 365 [333,398] |
| grok-4.5 | DIAG | oracle | 67 [58,76] | 95 [92,98] | 33 [23,44] | 57 [41,73] | 32 [23,42] | 284 [258,311] |
| grok-4.5 | UNDIAG | model | 63 [47,81] | 124 [114,134] | 3 [0,6] | 85 [52,120] | 6 [0,15] | 280 [237,330] |
| grok-4.5 | UNDIAG | oracle | 63 [42,94] | 97 [90,104] | 32 [13,55] | 19 [7,37] | 11 [3,21] | 222 [183,273] |
| grok-4.5 | CALM | model | 60 [53,66] | 115 [109,122] | 13 [6,21] | 20 [15,25] | 0 [0,1] | 208 [196,222] |
| grok-4.5 | CALM | oracle | 65 [57,73] | 99 [97,100] | 13 [7,20] | 7 [5,10] | 1 [0,1] | 184 [174,194] |
| deepseek-v4-pro | DIAG | model | 98 [83,114] | 133 [121,145] | 37 [27,48] | 67 [51,83] | 45 [32,60] | 380 [343,421] |
| deepseek-v4-pro | DIAG | oracle | 68 [59,78] | 95 [92,98] | 37 [26,49] | 60 [43,77] | 35 [25,46] | 295 [267,324] |
| deepseek-v4-pro | UNDIAG | model | 61 [45,80] | 133 [120,147] | 5 [1,10] | 65 [42,89] | 13 [5,22] | 276 [239,315] |
| deepseek-v4-pro | UNDIAG | oracle | 61 [47,78] | 97 [91,102] | 33 [13,57] | 37 [20,56] | 13 [6,22] | 240 [206,278] |
| deepseek-v4-pro | CALM | model | 63 [56,71] | 129 [118,142] | 11 [5,19] | 25 [17,34] | 0 [0,1] | 229 [215,244] |
| deepseek-v4-pro | CALM | oracle | 65 [57,73] | 99 [97,100] | 13 [7,20] | 7 [5,10] | 1 [0,1] | 184 [174,194] |

## Pre-registered contrasts (STATS-GUIDELINES 2026-07-30)


F3: holding_total DIAG, model - oracle (Holm-4)

| contrast | mean | 95% CI | p | p(Holm) |
|---|---|---|---|---|
| gpt-5.4 holding_total DIAG model-oracle $/wk | +3.23 | [-2.54, +8.92] | 0.27 | 0.27 |
| claude-sonnet-5 holding_total DIAG model-oracle $/wk | -10.21 | [-13.87, -6.37] | 0.0 | 0.0 |
| grok-4.5 holding_total DIAG model-oracle $/wk | +25.47 | [+18.00, +33.52] | 0.0 | 0.0 |
| deepseek-v4-pro holding_total DIAG model-oracle $/wk | +37.60 | [+25.94, +49.67] | 0.0 | 0.0 |

F4: procurement DIAG, model - oracle (Holm-4)

| contrast | mean | 95% CI | p | p(Holm) |
|---|---|---|---|---|
| gpt-5.4 procurement DIAG model-oracle $/wk | -4.12 | [-13.74, +5.80] | 0.41 | 0.46 |
| claude-sonnet-5 procurement DIAG model-oracle $/wk | +4.97 | [-2.93, +13.28] | 0.23 | 0.46 |
| grok-4.5 procurement DIAG model-oracle $/wk | +19.55 | [+8.20, +31.19] | 0.0004 | 0.0012 |
| deepseek-v4-pro procurement DIAG model-oracle $/wk | +29.67 | [+14.45, +46.79] | 0.0 | 0.0 |

F5: sonnet air DIAG, model - oracle (single)

| contrast | mean | 95% CI | p | p(Holm) |
|---|---|---|---|---|
| sonnet air DIAG model-oracle $/wk | +65.36 | [+49.47, +83.05] | 0.0 | 0.0 |
