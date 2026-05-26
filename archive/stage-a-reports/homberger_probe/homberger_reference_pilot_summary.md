# Homberger reference-budget pilot — Stage 1 verdict

**Cells:** 9 (3 per instance class). 
**Pilot budget:** pyvrp_10s × 3 seeds.
**Decision rule:** every class needs ≥ 2 of 3 cells with `delta_ARI ≤ 0.05` (= reference ARI_min – pilot ARI_min).

## Verdict: **FAIL — do not launch Stage 2.**

| class | n | passing | pass-rate | min Δ | max Δ | median pilot ARI | median ref ARI |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C | 3 | 3 | 100% | -0.343 | +0.024 | 0.992 | 0.916 |
| R | 3 | 1 | 33% | -0.065 | +0.295 | 0.748 | 0.935 |
| RC | 3 | 2 | 67% | -0.013 | +0.263 | 0.737 | 0.932 |

## Per-cell detail

| class | instance | pert | family | ref ARI_min | pilot ARI_min | Δ ARI | pass |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C | C1_2_1 | OC_4 | ORDER_CHANGE | +1.000 | +0.997 | +0.003 | ✓ |
| C | C1_2_1 | ST_3 | SERVICE_TIME | +0.916 | +0.892 | +0.024 | ✓ |
| C | C2_2_2 | ST_4 | SERVICE_TIME | +0.649 | +0.992 | -0.343 | ✓ |
| R | R2_2_1 | TT_5 | TRAVEL_TIME | +1.000 | +0.768 | +0.232 | ✗ |
| R | R1_2_1 | TW_5 | TIME_WINDOW | +0.935 | +0.640 | +0.295 | ✗ |
| R | R2_2_1 | ST_3 | SERVICE_TIME | +0.683 | +0.748 | -0.065 | ✓ |
| RC | RC1_2_1 | OC_4 | ORDER_CHANGE | +1.000 | +0.737 | +0.263 | ✗ |
| RC | RC1_2_2 | TT_5 | TRAVEL_TIME | +0.932 | +0.906 | +0.026 | ✓ |
| RC | RC1_2_1 | TT_4 | TRAVEL_TIME | +0.697 | +0.710 | -0.013 | ✓ |

## Interpretation

At least one instance class failed the per-class gate: R. This is itself a finding: objective equivalence between pyvrp_10s and the reference budget does not extend to seed-stability equivalence on the affected class. Stage 2 will **not** launch under the v1.4 spec.
