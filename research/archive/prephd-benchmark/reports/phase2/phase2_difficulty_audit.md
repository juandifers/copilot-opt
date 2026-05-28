# Phase 2 - Difficulty Audit & Conditional Gap Validation

This audit tests whether the cheap-vs-strong quality gap is **conditional** on instance, perturbation family, magnitude, and claim family — not a uniform property of the dataset. The PROCEED decision requires a populated easy/medium/hard spectrum, a meaningful middle backend (Clarke-Wright), and activation from both required perturbation families.

## 0. Protocol settings

- PyVRP seed: `1`
- PyVRP time limit: `10` seconds
- Cheap backends: `nearest_neighbor` (baseline) and `savings` (Clarke-Wright parallel, deterministic, capacity-respecting)
- Required perturbations: `capacity_reduction` factors=[0.98, 0.95, 0.9, 0.8], `regional_distance_inflation` factors=[1.1, 1.25, 1.5]
- Exploratory perturbations: `localized_demand_inflation` factors=[1.1, 1.25], `customer_insertion` counts=[1, 3]

## 1. Difficulty distribution

| cheap_backend | family | easy | medium | hard | unknown | n | easy_pct | medium_pct | hard_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nearest_neighbor | capacity_reduction | 0 | 1 | 59 | 0 | 60 | 0.0% | 1.7% | 98.3% |
| nearest_neighbor | regional_distance_inflation | 0 | 0 | 45 | 0 | 45 | 0.0% | 0.0% | 100.0% |
| savings | capacity_reduction | 0 | 6 | 54 | 0 | 60 | 0.0% | 10.0% | 90.0% |
| savings | regional_distance_inflation | 0 | 4 | 41 | 0 | 45 | 0.0% | 8.9% | 91.1% |

### Required-rows rollup (decision input)

- Total required difficulty rows: **210**
- easy: **0** (0.0%)
- medium: **11** (5.2%)
- hard: **199** (94.8%)

### Nominal-only difficulty (reference)

Nominal cheap-vs-strong rows: medium=3, hard=27

## 2. Backend quality comparison

Nominal-scenario objectives (smaller is better). **Question: does Clarke-Wright create a meaningful middle tier?**

| instance_id | nn_obj | cw_obj | py_obj | nn_gap_rel | cw_gap_rel | cw_improves_nn_rel |
| --- | --- | --- | --- | --- | --- | --- |
| X-n101-k25 | 4.152e+04 | 2.894e+04 | 27591 | 50.5% | 4.9% | 90.3% |
| X-n110-k13 | 1.93e+04 | 1.587e+04 | 14971 | 28.9% | 6.0% | 79.3% |
| X-n120-k6 | 1.585e+04 | 1.454e+04 | 13425 | 18.1% | 8.3% | 54.0% |
| X-n134-k13 | 1.653e+04 | 1.152e+04 | 10987 | 50.4% | 4.9% | 90.4% |
| X-n148-k46 | 5.658e+04 | 4.515e+04 | 43448 | 30.2% | 3.9% | 87.0% |
| X-n153-k22 | 3.232e+04 | 2.264e+04 | 21419 | 50.9% | 5.7% | 88.8% |
| X-n162-k11 | 1.755e+04 | 1.549e+04 | 14162 | 23.9% | 9.4% | 60.9% |
| X-n172-k51 | 6.498e+04 | 4.823e+04 | 45684 | 42.2% | 5.6% | 86.8% |
| X-n181-k23 | 2.77e+04 | 2.654e+04 | 25600 | 8.2% | 3.7% | 55.2% |
| X-n190-k8 | 1.999e+04 | 1.802e+04 | 17111 | 16.8% | 5.3% | 68.3% |
| X-n200-k36 | 6.933e+04 | 6.119e+04 | 58887 | 17.7% | 3.9% | 78.0% |
| X-n214-k11 | 1.487e+04 | 1.2e+04 | 10926 | 36.1% | 9.8% | 72.8% |
| X-n219-k73 | 1.201e+05 | 1.184e+05 | 117606 | 2.2% | 0.6% | 69.9% |
| X-n228-k23 | 3.926e+04 | 2.702e+04 | 25807 | 52.1% | 4.7% | 91.0% |
| X-n247-k50 | 5.334e+04 | 4.083e+04 | 37712 | 41.4% | 8.3% | 80.1% |

- CW obj is strictly intermediate (PyVRP ≤ CW ≤ NN) on **100%** of nominal instances
- Median NN gap vs PyVRP: **30.2%**  |  Median CW gap vs PyVRP: **5.3%**
- Median fraction of the NN–PyVRP gap that CW closes: **79.3%**

## 3. Perturbation behavior

For each required perturbation family: activation rate, structural impact, and difficulty distribution.

| family | backend | nonzero_rate | structural_rate | mean_obj_rel_change | mean_ari |
| --- | --- | --- | --- | --- | --- |
| capacity_reduction | nearest_neighbor | 0.85 | 0.8833 | 0.07719 | 0.5352 |
| capacity_reduction | pyvrp | 0.8167 | 0.9 | 0.07536 | 0.4802 |
| capacity_reduction | savings | 0.8167 | 0.8833 | 0.07361 | 0.5718 |
| regional_distance_inflation | nearest_neighbor | 1 | 0.8667 | 0.1298 | 0.6832 |
| regional_distance_inflation | pyvrp | 1 | 0.8444 | 0.1015 | 0.6062 |
| regional_distance_inflation | savings | 1 | 1 | 0.1144 | 0.6852 |

### Difficulty distribution by (family, magnitude, cheap backend)

| family | cheap_backend | magnitude | n | easy | medium | hard |
| --- | --- | --- | --- | --- | --- | --- |
| capacity_reduction | nearest_neighbor | 0.8 | 15 | 0 | 1 | 14 |
| capacity_reduction | nearest_neighbor | 0.9 | 15 | 0 | 0 | 15 |
| capacity_reduction | nearest_neighbor | 0.95 | 15 | 0 | 0 | 15 |
| capacity_reduction | nearest_neighbor | 0.98 | 15 | 0 | 0 | 15 |
| capacity_reduction | savings | 0.8 | 15 | 0 | 0 | 15 |
| capacity_reduction | savings | 0.9 | 15 | 0 | 2 | 13 |
| capacity_reduction | savings | 0.95 | 15 | 0 | 2 | 13 |
| capacity_reduction | savings | 0.98 | 15 | 0 | 2 | 13 |
| regional_distance_inflation | nearest_neighbor | 1.1 | 15 | 0 | 0 | 15 |
| regional_distance_inflation | nearest_neighbor | 1.25 | 15 | 0 | 0 | 15 |
| regional_distance_inflation | nearest_neighbor | 1.5 | 15 | 0 | 0 | 15 |
| regional_distance_inflation | savings | 1.1 | 15 | 0 | 1 | 14 |
| regional_distance_inflation | savings | 1.25 | 15 | 0 | 1 | 14 |
| regional_distance_inflation | savings | 1.5 | 15 | 0 | 2 | 13 |

**Question: do different perturbations create different regimes?**

- Max vs min structural-activation spread across required families: **1.5%** (larger = more differentiation)

## 4. Conditionality evidence

Cheap-correctness proxy varies across difficulty bands, perturbation types, and claim families.

### Mean claim error by difficulty × claim family

| difficulty_label | assignment_structure | objective_resource_delta | topk_route_ranking |
| --- | --- | --- | --- |
| hard | 0.6999 | 0.1517 | 0.9782 |
| medium | 0.4677 | 0.03411 | 0.7273 |

### Mean claim error by perturbation family × claim family

| family | assignment_structure | objective_resource_delta | topk_route_ranking |
| --- | --- | --- | --- |
| capacity_reduction | 0.6916 | 0.1355 | 0.9694 |
| regional_distance_inflation | 0.6827 | 0.1589 | 0.9593 |

### Mean claim error by cheap backend × difficulty

| cheap_backend | hard | medium |
| --- | --- | --- |
| nearest_neighbor | 0.6612 | 0.369 |
| savings | 0.5539 | 0.4138 |

## 5. Claim-family interaction

Which claim families fail under which conditions? Correlation between claim error and the two observable scalars that define difficulty — objective gap and ARI.

| claim_family | n | mean_claim_error | corr_with_objective_gap_rel | corr_with_adjusted_rand |
| --- | --- | --- | --- | --- |
| objective_resource_delta | 210 | 0.1455 | 1 | -0.6748 |
| topk_route_ranking | 210 | 0.9651 | 0.3073 | -0.477 |
| assignment_structure | 210 | 0.6878 | 0.6748 | -1 |

## 6. Exploratory perturbation families (informational)

These do **not** determine the Phase 2 decision unless artifacts are inconsistent. Reported for situational awareness.

| cheap_backend | family | n | easy | medium | hard |
| --- | --- | --- | --- | --- | --- |
| nearest_neighbor | localized_demand_inflation | 30 | 0 | 0 | 30 |
| nearest_neighbor | customer_insertion | 30 | 0 | 0 | 30 |
| savings | localized_demand_inflation | 30 | 0 | 3 | 27 |
| savings | customer_insertion | 30 | 0 | 0 | 30 |

### Exploratory perturbation activation

| family | backend | nonzero_rate | structural_rate |
| --- | --- | --- | --- |
| customer_insertion | nearest_neighbor | 0.7333 | 0.9333 |
| customer_insertion | pyvrp | 0.4 | 1 |
| customer_insertion | savings | 0.5 | 0.7 |
| localized_demand_inflation | nearest_neighbor | 0.7 | 0.7667 |
| localized_demand_inflation | pyvrp | 0.7 | 0.8667 |
| localized_demand_inflation | savings | 0.6667 | 0.8 |

## 6.5 Data diagnostic (observed facts)

- required rows with `|gap| < 0.05`: **23.8%** (n=50/210)
- required rows with `ARI > 0.75`: **0.0%** (n=0/210)
- required rows with both conditions (= easy label): **0.0%**
- **max ARI observed across all required rows: 0.567** (easy threshold = 0.750)

## 7. Decision

**REVISE**

- REVISE: band share<20% for: easy=0%, medium=5%

### Gate readings

- difficulty share `easy`: **0.0%** (n=0/210); threshold 20%
- difficulty share `medium`: **5.2%** (n=11/210); threshold 20%
- difficulty share `hard`: **94.8%** (n=199/210); threshold 20%
- PyVRP failure rate on required scenarios: **0.0%** (STOP threshold 10%)
- CW intermediate rate (PyVRP ≤ CW ≤ NN): **100.0%** (PROCEED threshold 80%)
- structural activation `capacity_reduction`: **88.9%** (PROCEED threshold 50%)
- structural activation `regional_distance_inflation`: **90.4%** (PROCEED threshold 50%)
