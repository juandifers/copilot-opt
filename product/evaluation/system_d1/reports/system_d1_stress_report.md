# System D1 — stress evaluation report

D1 (semantic intent adapter + locked downstream contract) vs C0 (locked classifier + locked downstream contract) across the four R2-S axes' C0-style surfaces (24 cases each).

## 1. Per-axis aggregate

| axis | n | C0 intent | D1 intent | C0 ans | D1 ans | C0 beh | D1 beh |
|---|---:|---:|---:|---:|---:|---:|---:|
| axis1_lookalike | 24 | 0.875 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| axis2_ood_premises | 24 | 0.750 | 1.000 | 0.750 | 0.917 | 0.750 | 0.917 |
| axis3_semantic | 24 | 0.625 | 1.000 | 0.625 | 1.000 | 0.625 | 0.875 |
| axis4_payload | 24 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

## 2. Target-18 cohort

- target_18_fixed_count: **18** / 18  
- target_18_fixed_rate: **1.000**

| case_id | axis | expected | C0 | D1 | fixed |
|---|---|---|---|---|:-:|
| A1D-11 | axis1_lookalike | objective_value | objective_delta | objective_value | ✓ |
| A1D-12 | axis1_lookalike | objective_value | objective_delta | objective_value | ✓ |
| A1H-11 | axis1_lookalike | objective_value | objective_delta | objective_value | ✓ |
| A2D-06 | axis2_ood_premises | before_after_comparison | single_customer_route_membership | before_after_comparison | ✓ |
| A2H-05 | axis2_ood_premises | before_after_comparison | single_customer_route_membership | before_after_comparison | ✓ |
| A2H-06 | axis2_ood_premises | before_after_comparison | unknown | before_after_comparison | ✓ |
| A2D-08 | axis2_ood_premises | objective_delta | objective_value | objective_delta | ✓ |
| A2H-08 | axis2_ood_premises | objective_delta | objective_value | objective_delta | ✓ |
| A2H-09 | axis2_ood_premises | before_after_comparison | unknown | before_after_comparison | ✓ |
| S1D-07 | axis3_semantic | full_route_listing | unknown | full_route_listing | ✓ |
| S1D-08 | axis3_semantic | route_end_time | unknown | route_end_time | ✓ |
| S1D-09 | axis3_semantic | route_end_time | unknown | route_end_time | ✓ |
| S1D-12 | axis3_semantic | lateness_summary | unknown | lateness_summary | ✓ |
| S1H-07 | axis3_semantic | full_route_listing | unknown | full_route_listing | ✓ |
| S1H-08 | axis3_semantic | full_route_listing | unknown | full_route_listing | ✓ |
| S1H-09 | axis3_semantic | route_end_time | unknown | route_end_time | ✓ |
| S1H-10 | axis3_semantic | route_end_time | unknown | route_end_time | ✓ |
| S1H-12 | axis3_semantic | lateness_summary | unknown | lateness_summary | ✓ |

## 3. Must-not-regress 70-cohort

- must_not_regress_70_preserved_count: **70** / 70  
- must_not_regress_70_preserved_rate: **1.000**

  - C0-side cases D1 evaluates directly: 64 / 64
  - Axis 4 model-A cases preserved by construction (D1 does not run model A): 6

_No regression in the 70-case cohort._

## 4. Adapter call accounting

- adapter_invocation_count: **31**  
- adapter_override_count: **18**  
- adapter_fallback_count: **13**

Override source distribution (D1 intent != C0 intent):

| source | n |
|---|---:|
| semantic_adapter | 18 |

## 5. Total improvement vs C0 (stress surface only)

- stress_total_improvement_vs_c0 (intent-correct delta): **+18** cases out of 96
