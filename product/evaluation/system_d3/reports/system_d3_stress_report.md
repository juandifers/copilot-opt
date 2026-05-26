# System D3 — stress evaluation report

D3 (D1 intent + D2 answerability/warning + D3 causal-unsupported warning) vs D2 vs D1 vs C0 across the four R2-S axes' C0-style surfaces.

## 1. D3 v2 overlay cohort (5 schema-gap cases)

- d3_target_5_fixed_count (against v2 overlay gold): **5 / 5**  
- d3_target_5_fixed_rate: **1.000**

| case_id | D2 (v1 gold) | D3 (v1 gold) | D3 (v2 overlay gold) | D3 emitted warnings |
|---|:-:|:-:|:-:|---|
| A2D-10 | ✓ | ✗ | ✓ | route_indexing_ambiguity;causal_mechanism_unsupported |
| A2D-11 | ✓ | ✗ | ✓ | causal_mechanism_unsupported |
| A2D-12 | ✓ | ✗ | ✓ | causal_mechanism_unsupported |
| A2H-11 | ✓ | ✗ | ✓ | causal_mechanism_unsupported |
| A2H-12 | ✓ | ✗ | ✓ | causal_mechanism_unsupported |

## 2. D2 target-5 preserved under D3

- d2_target_5_preserved_under_d3_count: **5 / 5**

## 3. D1 target-18 preserved under D3

- target_18_under_d3_fixed_count: **18 / 18**

## 4. Must-not-regress 70-cohort

- must_not_regress_70_preserved_count: **68 / 70**
  - C0-side cases D3 evaluates directly: 62 / 64
  - Axis 4 model-A cases preserved by construction: 6

## 5. Axis 4 C0-like preservation

- axis4_d3_perfect: **24 / 24**
- axis4_regressions: []

## 6. Off-target causal emissions

D3's causal-warning detector is conservative; this section checks how many non-overlay cases D3 emitted `causal_mechanism_unsupported` on. Those emissions are potential over-fires under v1 grading.

- off_target_causal_emission_count: **0**
