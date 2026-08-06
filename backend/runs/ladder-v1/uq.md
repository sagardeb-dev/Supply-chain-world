# UQ — paired bootstrap (10000 draws, seed 20260728), Wilcoxon signed-rank, Holm-corrected

| scope | quantity | n | mean | 95% CI | p | p(Holm) |
|---|---|---|---|---|---|---|
| ALL | gpt-5.4 mean skill | 49 | +0.618 | [+0.403, +0.831] | 1.7e-06 |  |
| ALL | claude-sonnet-5 mean skill | 49 | +0.492 | [+0.323, +0.652] | 2.2e-06 |  |
| ALL | grok-4.5 mean skill | 49 | -0.133 | [-0.385, +0.120] | 0.33 |  |
| ALL | deepseek-v4-pro mean skill | 49 | -0.234 | [-0.574, +0.078] | 0.56 |  |
| ISOLATED | gpt-5.4 mean skill | 11 | +0.214 | [-0.159, +0.588] |  |  |
| ISOLATED | claude-sonnet-5 mean skill | 11 | +0.540 | [+0.204, +0.842] |  |  |
| ISOLATED | grok-4.5 mean skill | 11 | -0.140 | [-0.469, +0.198] |  |  |
| ISOLATED | deepseek-v4-pro mean skill | 11 | -0.615 | [-1.355, +0.050] |  |  |
| PERSISTENT | gpt-5.4 mean skill | 15 | +0.548 | [+0.141, +0.941] |  |  |
| PERSISTENT | claude-sonnet-5 mean skill | 15 | +0.703 | [+0.495, +0.918] |  |  |
| PERSISTENT | grok-4.5 mean skill | 15 | -0.242 | [-0.565, +0.073] |  |  |
| PERSISTENT | deepseek-v4-pro mean skill | 15 | -0.684 | [-1.291, -0.169] |  |  |
| COMPOUND | gpt-5.4 mean skill | 23 | +0.857 | [+0.563, +1.150] |  |  |
| COMPOUND | claude-sonnet-5 mean skill | 23 | +0.331 | [+0.057, +0.586] |  |  |
| COMPOUND | grok-4.5 mean skill | 23 | -0.059 | [-0.534, +0.391] |  |  |
| COMPOUND | deepseek-v4-pro mean skill | 23 | +0.243 | [-0.171, +0.602] |  |  |
| ALL | gpt-5.4 - claude-sonnet-5 | 49 | +0.126 | [-0.108, +0.360] | 0.26 | 0.51 |
| ALL | gpt-5.4 - grok-4.5 | 49 | +0.751 | [+0.471, +1.046] | 3.4e-06 | 2e-05 |
| ALL | gpt-5.4 - deepseek-v4-pro | 49 | +0.852 | [+0.519, +1.207] | 1.8e-05 | 7.2e-05 |
| ALL | claude-sonnet-5 - grok-4.5 | 49 | +0.625 | [+0.367, +0.890] | 9.2e-06 | 4.6e-05 |
| ALL | claude-sonnet-5 - deepseek-v4-pro | 49 | +0.726 | [+0.400, +1.071] | 6.8e-05 | 0.0002 |
| ALL | grok-4.5 - deepseek-v4-pro | 49 | +0.101 | [-0.254, +0.469] | 0.8 | 0.8 |
| COMPOUND | gpt-5.4 - claude-sonnet-5 | 23 | +0.525 | [+0.264, +0.811] | 0.00048 | 0.0014 |
| COMPOUND | grok-4.5 - claude-sonnet-5 | 23 | -0.390 | [-0.883, +0.052] | 0.13 | 0.25 |
| COMPOUND | deepseek-v4-pro - claude-sonnet-5 | 23 | -0.089 | [-0.393, +0.230] | 0.64 | 0.64 |
| ALL | resolution (median contrast CI half-width) | 6 | +0.311 | [+0.234, +0.362] |  |  |
| ALL | gpt-5.4 detection rate | 50 | +0.932 | [+0.894, +0.964] |  |  |
| ALL | claude-sonnet-5 detection rate | 50 | +0.940 | [+0.911, +0.968] |  |  |
| ALL | grok-4.5 detection rate | 50 | +0.925 | [+0.892, +0.955] |  |  |
| ALL | deepseek-v4-pro detection rate | 50 | +0.891 | [+0.849, +0.929] |  |  |
| ALL | det rate gpt-5.4 - claude-sonnet-5 | 50 | -0.008 | [-0.038, +0.024] |  | 1.0 |
| ALL | det rate gpt-5.4 - grok-4.5 | 50 | +0.008 | [-0.019, +0.036] |  | 1.0 |
| ALL | det rate gpt-5.4 - deepseek-v4-pro | 50 | +0.041 | [+0.000, +0.083] |  | 0.21 |
| ALL | det rate claude-sonnet-5 - grok-4.5 | 50 | +0.015 | [-0.012, +0.042] |  | 1.0 |
| ALL | det rate claude-sonnet-5 - deepseek-v4-pro | 50 | +0.049 | [+0.012, +0.086] |  | 0.052 |
| ALL | det rate grok-4.5 - deepseek-v4-pro | 50 | +0.034 | [+0.004, +0.066] |  | 0.17 |
| ALL | gpt-5.4 detection lag (wk) | 50 | +0.399 | [+0.270, +0.581] |  |  |
| ALL | claude-sonnet-5 detection lag (wk) | 50 | +0.416 | [+0.233, +0.647] |  |  |
| ALL | grok-4.5 detection lag (wk) | 50 | +0.321 | [+0.170, +0.507] |  |  |
| ALL | deepseek-v4-pro detection lag (wk) | 50 | +0.316 | [+0.218, +0.431] |  |  |
| ALL | det lag gpt-5.4 - claude-sonnet-5 | 50 | -0.017 | [-0.172, +0.123] |  | 1.0 |
| ALL | det lag gpt-5.4 - grok-4.5 | 50 | +0.078 | [-0.132, +0.301] |  | 1.0 |
| ALL | det lag gpt-5.4 - deepseek-v4-pro | 50 | +0.083 | [-0.069, +0.274] |  | 1.0 |
| ALL | det lag claude-sonnet-5 - grok-4.5 | 50 | +0.095 | [-0.115, +0.324] |  | 1.0 |
| ALL | det lag claude-sonnet-5 - deepseek-v4-pro | 50 | +0.100 | [-0.075, +0.318] |  | 1.0 |
| ALL | det lag grok-4.5 - deepseek-v4-pro | 50 | +0.005 | [-0.147, +0.173] |  | 1.0 |
| ISOLATED | gpt-5.4 KDR | 12 | +0.048 | [+0.000, +0.128] |  |  |
| PERSISTENT | gpt-5.4 KDR | 15 | +0.176 | [+0.115, +0.236] |  |  |
| COMPOUND | gpt-5.4 KDR | 23 | +0.076 | [+0.039, +0.123] |  |  |
| ISOLATED | claude-sonnet-5 KDR | 12 | +0.097 | [+0.041, +0.153] |  |  |
| PERSISTENT | claude-sonnet-5 KDR | 15 | +0.219 | [+0.145, +0.290] |  |  |
| COMPOUND | claude-sonnet-5 KDR | 23 | +0.180 | [+0.127, +0.239] |  |  |
| ISOLATED | grok-4.5 KDR | 12 | +0.058 | [+0.000, +0.123] |  |  |
| PERSISTENT | grok-4.5 KDR | 15 | +0.176 | [+0.121, +0.234] |  |  |
| COMPOUND | grok-4.5 KDR | 23 | +0.130 | [+0.075, +0.187] |  |  |
| ISOLATED | deepseek-v4-pro KDR | 12 | +0.050 | [+0.000, +0.097] |  |  |
| PERSISTENT | deepseek-v4-pro KDR | 15 | +0.261 | [+0.172, +0.358] |  |  |
| COMPOUND | deepseek-v4-pro KDR | 23 | +0.137 | [+0.085, +0.191] |  |  |
| PERSISTENT | gpt-5.4 KDR persistent - rest | 50 | +0.105 | [+0.033, +0.175] |  | 0.018 |
| PERSISTENT | claude-sonnet-5 KDR persistent - rest | 50 | +0.058 | [-0.033, +0.145] |  | 0.23 |
| PERSISTENT | grok-4.5 KDR persistent - rest | 50 | +0.060 | [-0.014, +0.135] |  | 0.23 |
| PERSISTENT | deepseek-v4-pro KDR persistent - rest | 50 | +0.141 | [+0.037, +0.252] |  | 0.028 |
| ALL | gpt-5.4 stockout diag - undiag | 50 | +0.073 | [+0.011, +0.129] |  | 0.022 |
| ALL | claude-sonnet-5 stockout diag - undiag | 50 | +0.118 | [+0.054, +0.177] |  | 0.0012 |
| ALL | grok-4.5 stockout diag - undiag | 50 | +0.117 | [+0.063, +0.165] |  | 0.0 |
| ALL | deepseek-v4-pro stockout diag - undiag | 50 | +0.145 | [+0.102, +0.189] |  | 0.0 |
| ALL | median per-seed skill SE from oracle noise | 196 | +0.017 | [+0.006, +0.037] |  |  |
