# Seed sweep report

n = 200 seeds

## 1. Score spread

| policy | mean | median | p10 | p90 |
|---|---|---|---|---|
| suez (fixed 20) | 7258 | 6720 | 5169 | 10172 |
| cape (fixed 20) | 8815 | 8303 | 6602 | 12163 |
| base-stock | 6661 | 6401 | 4881 | 8947 |
| oracle (k=50) | 6116 | 5893 | 4401 | 8230 |

- oracle beats base-stock: 82.0% of seeds
- base-stock beats both fixed policies: 77.0% of seeds

## 2. Headroom distribution

| decile | headroom |
|---|---|
| p10 | -484.4 |
| p20 | 58.9 |
| p30 | 248.7 |
| p40 | 407.1 |
| p50 | 593.2 |
| p60 | 772.9 |
| p70 | 1010.5 |
| p80 | 1249.0 |
| p90 | 1563.8 |

- near-zero-headroom seeds (|headroom| < 5% of basestock): 37 / 200

## 3. What kills headroom (bottom-decile vs top-decile headroom seeds)

| feature | bottom decile mean | top decile mean | gap |
|---|---|---|---|
| stress_port | 1.45 | 6.15 | 4.70 |
| port_block_longest | 1.10 | 4.95 | 3.85 |
| stress_freight | 1.15 | 2.45 | 1.30 |
| overlap_weeks | 4.65 | 5.35 | 0.70 |
| stress_quality | 0.80 | 1.20 | 0.40 |
| fog | 0.29 | 0.29 | -0.00 |
| max_overlap | 2.45 | 2.35 | -0.10 |
| spot_died | 0.20 | 0.05 | -0.15 |
| stress_disruption | 3.25 | 2.85 | -0.40 |
| stress_demand | 7.10 | 6.05 | -1.05 |
| stress_supplier | 6.00 | 2.25 | -3.75 |

- biggest feature gap: `stress_port` (bottom=1.45, top=6.15)

## 4. Ladder candidates

### EASY (max_overlap<=1, mid-to-high headroom)

| seed | headroom | max_overlap | overlap_weeks | fog | stressed factors |
|---|---|---|---|---|---|
| 157 | 1527.0 | 1 | 0 | 0.30 | disruption=2,freight=2,quality=2 |
| 25 | 1392.8 | 1 | 0 | 0.12 | disruption=2,port=5,supplier=1 |
| 24 | 1209.8 | 1 | 0 | 0.00 | disruption=1 |
| 112 | 1202.6 | 1 | 0 | 0.44 | demand=7 |
| 86 | 1049.1 | 1 | 0 | 0.25 | quality=2,supplier=1,demand=3 |
| 160 | 880.8 | 1 | 0 | 0.00 | port=2,supplier=4 |
| 91 | 872.4 | 1 | 0 | 0.10 | disruption=2,port=1,demand=4 |
| 178 | 833.2 | 1 | 0 | 0.17 | disruption=1,freight=2,port=3,demand=6 |
| 11 | 820.0 | 1 | 0 | 0.13 | freight=6,quality=2,supplier=2 |
| 189 | 775.2 | 1 | 0 | 0.75 | port=1,demand=8 |

### MEDIUM (max_overlap==2, positive headroom)

| seed | headroom | max_overlap | overlap_weeks | fog | stressed factors |
|---|---|---|---|---|---|
| 1 | 3016.2 | 2 | 7 | 0.23 | disruption=1,freight=1,port=8,demand=11 |
| 143 | 2816.9 | 2 | 3 | 0.47 | disruption=2,freight=6,port=9,supplier=4 |
| 172 | 2230.2 | 2 | 6 | 0.57 | port=7,supplier=3,demand=9 |
| 18 | 2150.1 | 2 | 3 | 0.00 | disruption=1,port=13,supplier=2 |
| 80 | 2007.8 | 2 | 4 | 0.31 | disruption=1,freight=5,port=1,quality=4,demand=4 |
| 198 | 1981.2 | 2 | 2 | 0.25 | disruption=2,port=8,quality=1,demand=4 |
| 95 | 1960.4 | 2 | 6 | 0.40 | freight=6,port=8,demand=9 |
| 29 | 1863.7 | 2 | 8 | 0.52 | disruption=1,port=8,quality=5,supplier=4,demand=8 |
| 70 | 1814.7 | 2 | 1 | 0.10 | disruption=2,port=2,supplier=3 |
| 135 | 1732.8 | 2 | 2 | 0.00 | port=6,supplier=1,demand=6 |

### HARD (max_overlap>=3 or high-fog overlap>=4, positive headroom)

| seed | headroom | max_overlap | overlap_weeks | fog | stressed factors |
|---|---|---|---|---|---|
| 21 | 2769.8 | 3 | 4 | 0.19 | disruption=6,port=1,quality=3,supplier=1,demand=8 |
| 172 | 2230.2 | 2 | 6 | 0.57 | port=7,supplier=3,demand=9 |
| 170 | 2100.8 | 3 | 7 | 0.18 | freight=9,port=8,supplier=1,demand=8 |
| 80 | 2007.8 | 2 | 4 | 0.31 | disruption=1,freight=5,port=1,quality=4,demand=4 |
| 99 | 1960.5 | 3 | 8 | 0.57 | disruption=4,port=10,supplier=2,demand=12 |
| 95 | 1960.4 | 2 | 6 | 0.40 | freight=6,port=8,demand=9 |
| 29 | 1863.7 | 2 | 8 | 0.52 | disruption=1,port=8,quality=5,supplier=4,demand=8 |
| 44 | 1741.7 | 3 | 10 | 0.22 | disruption=9,freight=5,port=6,supplier=9,demand=4 |
| 94 | 1720.4 | 3 | 10 | 0.45 | freight=5,port=5,quality=2,supplier=9,demand=8 |
| 154 | 1716.1 | 3 | 6 | 0.47 | disruption=5,freight=4,port=5,supplier=2,demand=8 |


## 5. Correlations (Pearson r vs headroom)

| feature | r |
|---|---|
| port_block_longest | 0.329 |
| stress_port | 0.319 |
| cost_cape | 0.277 |
| best_fixed | 0.253 |
| cost_suez | 0.251 |
| cost_basestock | 0.226 |
| fog_quality | 0.098 |
| stress_quality | 0.080 |
| stress_freight | 0.071 |
| fog_port | 0.037 |
| max_overlap | 0.023 |
| fog | 0.011 |
| overlap_weeks | 0.004 |
| fog_freight | 0.003 |
| stress_demand | -0.048 |
| fog_demand | -0.065 |
| stress_disruption | -0.071 |
| spot_died | -0.083 |
| fog_supplier | -0.112 |
| stress_supplier | -0.178 |
| cost_oracle | -0.423 |
| fog_disruption | nan |
