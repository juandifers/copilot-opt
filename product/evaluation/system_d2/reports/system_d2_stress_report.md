# System D2 — stress evaluation report

D2 (D1 semantic intent adapter + D2 answerability and warning extension) vs D1 vs C0 across the four R2-S axes' C0-style surfaces (24 cases each).

## 1. Per-axis aggregate

| axis | n | C0 int | D1 int | D2 int | C0 ans | D1 ans | D2 ans | C0 beh | D1 beh | D2 beh |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| axis1_lookalike | 24 | 0.875 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| axis2_ood_premises | 24 | 0.708 | 0.958 | 0.958 | 0.750 | 0.917 | 1.000 | 0.750 | 0.917 | 1.000 |
| axis3_semantic | 24 | 0.417 | 0.792 | 0.792 | 0.417 | 0.792 | 0.792 | 0.417 | 0.667 | 0.792 |
| axis4_payload | 24 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

## 2. D2 target-5 cohort

- d2_target_5_fixed_count: **5** / 5  
- d2_target_5_fixed_rate: **1.000**

| case_id | axis | expected intent | gold warnings | D1 perf | D2 perf | fixed |
|---|---|---|---|:-:|:-:|:-:|
| A2D-03 | axis2_ood_premises | lateness_summary | false_premise_detected | ✗ | ✓ | ✓ |
| A2H-02 | axis2_ood_premises | feasibility_status | false_premise_detected | ✗ | ✓ | ✓ |
| S1D-08 | axis3_semantic | route_end_time | route_indexing_ambiguity | ✗ | ✓ | ✓ |
| S1D-09 | axis3_semantic | route_end_time | route_indexing_ambiguity | ✗ | ✓ | ✓ |
| S1H-10 | axis3_semantic | route_end_time | route_indexing_ambiguity | ✗ | ✓ | ✓ |

## 3. D1 target-18 cohort under D2

- target_18_under_d2_fixed_count: **18** / 18  


## 4. Must-not-regress 70-cohort

- must_not_regress_70_preserved_count: **68** / 70  
  - C0-side cases D2 evaluates directly: 62 / 64
  - Axis 4 model-A cases preserved by construction: 6

**Regressions in must-not-regress cohort:**

- A2H-10 (axis2_ood_premises): D2 intent=unknown, warnings=
- S1H-01 (axis3_semantic): D2 intent=unknown, warnings=
## 5. Axis 4 C0-like preservation

- axis4_fully_perfect_under_d2: **24** / 24

## 6. Over-firing checks

Only D2-introduced over-fires are counted (warning D2 emits that gold did NOT expect AND C0 did not emit either). Pre-existing C0 over-fires inherited unchanged are listed separately and are not attributable to D2.

- D2-introduced route_indexing_ambiguity over-fires: **0** cases
- D2-introduced false_premise_detected over-fires: **0** cases
- Pre-existing route_indexing_ambiguity over-fires inherited from C0: 1 cases (['A2H-06'])
- Pre-existing false_premise_detected over-fires inherited from C0: 0 cases ([])


## 7. Total stress improvement

- stress_total_improvement_vs_c0 (case fully-perfect delta): **+17** cases out of 96
- stress_total_improvement_vs_d1 (case fully-perfect delta): **+3** cases out of 96
