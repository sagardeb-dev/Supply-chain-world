# Cost decomposition — per-week replay of ladder-v1 episodes

200 episodes x 26 weeks replayed through the world engine and verified byte-for-byte against the trace's `WORLD ADVANCED` cost/cum banners. Seed-cluster paired bootstrap, N_BOOT=10000, rng seed 20260728.

## Per-model x class bucket means ($/week, 95% CI)

| model | class | n weeks | procurement | holding | stockout | levers | incident | total |
|---|---|---|---|---|---|---|---|---|
| gpt-5.4 | DIAG | 502 | 61 [49,75] | 98 [93,104] | 20 [11,31] | 91 [76,107] | 30 [21,40] | 300 [273,328] |
| gpt-5.4 | UNDIAG | 137 | 66 [43,90] | 107 [99,115] | 5 [0,13] | 58 [32,86] | 2 [1,4] | 238 [204,272] |
| gpt-5.4 | CALM | 623 | 55 [49,61] | 111 [105,117] | 10 [4,19] | 28 [20,36] | 1 [0,1] | 204 [194,216] |
| claude-sonnet-5 | DIAG | 515 | 70 [61,79] | 85 [81,88] | 32 [23,42] | 126 [110,142] | 29 [21,38] | 341 [318,365] |
| claude-sonnet-5 | UNDIAG | 124 | 69 [54,86] | 91 [85,98] | 14 [4,27] | 159 [125,193] | 19 [7,33] | 352 [302,404] |
| claude-sonnet-5 | CALM | 623 | 47 [42,52] | 83 [81,85] | 10 [5,16] | 39 [30,48] | 0 [0,1] | 179 [166,193] |
| grok-4.5 | DIAG | 544 | 87 [77,96] | 120 [113,128] | 37 [24,52] | 81 [66,96] | 40 [29,53] | 365 [333,398] |
| grok-4.5 | UNDIAG | 95 | 63 [47,81] | 124 [114,134] | 3 [0,6] | 85 [52,120] | 6 [0,15] | 280 [237,330] |
| grok-4.5 | CALM | 623 | 60 [53,66] | 115 [109,122] | 13 [6,21] | 20 [15,25] | 0 [0,1] | 208 [196,222] |
| deepseek-v4-pro | DIAG | 469 | 98 [83,114] | 133 [121,145] | 37 [27,48] | 67 [51,83] | 45 [32,60] | 380 [343,421] |
| deepseek-v4-pro | UNDIAG | 170 | 61 [45,80] | 133 [120,147] | 5 [1,10] | 65 [42,89] | 13 [5,22] | 276 [239,315] |
| deepseek-v4-pro | CALM | 623 | 63 [56,71] | 129 [118,142] | 11 [5,19] | 25 [17,34] | 0 [0,1] | 229 [215,244] |

## Per-lever DIAG-week means ($/week, 95% CI)

| model | air | inspect | briefing | audit | dual_source |
|---|---|---|---|---|---|
| gpt-5.4 | 85.7 [70.2,101.7] | 1.0 [0.4,1.8] | 0.9 [0.4,1.4] | 1.5 [0.8,2.4] | 1.9 [1.5,2.3] |
| claude-sonnet-5 | 116.4 [100.4,132.9] | 2.4 [1.4,3.7] | 2.1 [1.5,2.8] | 2.1 [1.6,2.6] | 2.5 [2.1,2.9] |
| grok-4.5 | 71.6 [56.1,87.1] | 2.9 [1.4,4.7] | 2.0 [1.4,2.7] | 2.7 [2.0,3.4] | 2.0 [1.6,2.3] |
| deepseek-v4-pro | 59.7 [44.1,75.7] | 3.2 [1.9,4.7] | 0.5 [0.1,1.0] | 0.6 [0.2,1.0] | 2.8 [2.4,3.2] |

## Pre-registered contrasts

Family 1 (per model, Holm-4): levers $/wk DIAG - CALM

| model | mean | 95% CI | p | p(Holm) |
|---|---|---|---|---|
| gpt-5.4 levers DIAG - CALM $/wk | +63.14 | [+46.05, +80.84] | 0.0 | 0.0 |
| claude-sonnet-5 levers DIAG - CALM $/wk | +86.97 | [+67.37, +107.01] | 0.0 | 0.0 |
| grok-4.5 levers DIAG - CALM $/wk | +61.46 | [+45.97, +77.30] | 0.0 | 0.0 |
| deepseek-v4-pro levers DIAG - CALM $/wk | +41.76 | [+24.31, +59.27] | 0.0 | 0.0 |

Family 2 (Holm-2):

| contrast | mean | 95% CI | p | p(Holm) |
|---|---|---|---|---|
| sonnet air$/DIAG-wk - gpt air$/DIAG-wk | +30.6300 | [+13.4640, +50.4900] | 0.0 | 0.0 |
| gpt stockout share DIAG - sonnet stockout share DIAG | -0.0330 | [-0.0630, -0.0040] | 0.026 | 0.026 |

## Summary (descriptive)

- **gpt-5.4**: DIAG-week total $300/wk vs CALM-week total $204/wk. Lever spend $91.0/wk on DIAG vs $27.9/wk on CALM. Stockout-side cost $20/wk on DIAG vs $10/wk on CALM.
- **claude-sonnet-5**: DIAG-week total $341/wk vs CALM-week total $179/wk. Lever spend $125.6/wk on DIAG vs $38.6/wk on CALM. Stockout-side cost $32/wk on DIAG vs $10/wk on CALM.
- **grok-4.5**: DIAG-week total $365/wk vs CALM-week total $208/wk. Lever spend $81.2/wk on DIAG vs $19.7/wk on CALM. Stockout-side cost $37/wk on DIAG vs $13/wk on CALM.
- **deepseek-v4-pro**: DIAG-week total $380/wk vs CALM-week total $229/wk. Lever spend $66.7/wk on DIAG vs $25.0/wk on CALM. Stockout-side cost $37/wk on DIAG vs $11/wk on CALM.
