# Phase 2R — Claim-Family-Specific Difficulty Labeling

This revision relabels the Phase 2 required corpus (n=210) with three independent
difficulty labels — one per claim family — using the metric that defines that family.
The Phase 2 single global label combined objective gap with ARI in series and produced
0% easy by construction (max ARI in the corpus is 0.567, easy threshold required ARI > 0.75).
No new instances, no new perturbations, no cheap-backend reruns. The only new solver
work is the budget-consistency rerun of PyVRP on the five scenarios named in §3.

Frozen cutoffs:

- objective (`objective_gap_rel`): easy `|gap|<0.05`; medium `0.05 <= |gap| < 0.15`; hard `|gap| >= 0.15`.
- assignment (`adjusted_rand`): easy `ARI > 0.75`; medium `0.50 < ARI <= 0.75`; hard `ARI <= 0.50`.
- ranking (top-3 route overlap by distance contribution): easy `overlap >= 0.67` (2 or 3 of top-3 match); medium `overlap == 0.33`; hard `overlap == 0.00`. Rows with fewer than three routes on either backend are marked `na` and excluded from the ranking distribution.

PyVRP protocol: seed=1, time_limit_sec=10 (Phase 2). Budget check rerun: time_limit_sec=60.

## 2.1 Distribution table per claim family

### Objective / resource-delta difficulty

| cheap_backend | family | n | easy | medium | hard | easy_pct | medium_pct | hard_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nearest_neighbor | capacity_reduction | 60 | 5 | 11 | 44 | 8.33 | 18.33 | 73.33 |
| nearest_neighbor | regional_distance_inflation | 45 | 3 | 5 | 37 | 6.67 | 11.11 | 82.22 |
| savings | capacity_reduction | 60 | 32 | 28 | 0 | 53.33 | 46.67 | 0.00 |
| savings | regional_distance_inflation | 45 | 10 | 35 | 0 | 22.22 | 77.78 | 0.00 |

### Assignment / structure difficulty

| cheap_backend | family | n | easy | medium | hard | easy_pct | medium_pct | hard_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nearest_neighbor | capacity_reduction | 60 | 0 | 1 | 59 | 0.00 | 1.67 | 98.33 |
| nearest_neighbor | regional_distance_inflation | 45 | 0 | 0 | 45 | 0.00 | 0.00 | 100.00 |
| savings | capacity_reduction | 60 | 0 | 6 | 54 | 0.00 | 10.00 | 90.00 |
| savings | regional_distance_inflation | 45 | 0 | 4 | 41 | 0.00 | 8.89 | 91.11 |

### Top-k ranking difficulty

| cheap_backend | family | n | easy | medium | hard | na | easy_pct | medium_pct | hard_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nearest_neighbor | capacity_reduction | 60 | 0 | 1 | 59 | 0 | 0.00 | 1.67 | 98.33 |
| nearest_neighbor | regional_distance_inflation | 45 | 0 | 0 | 45 | 0 | 0.00 | 0.00 | 100.00 |
| savings | capacity_reduction | 60 | 1 | 8 | 51 | 0 | 1.67 | 13.33 | 85.00 |
| savings | regional_distance_inflation | 45 | 0 | 11 | 34 | 0 | 0.00 | 24.44 | 75.56 |

`na` rows are excluded from the percentage denominator. None of the 210 required rows had fewer than three routes on either backend, so no rows were dropped from the ranking distribution.

## 2.2 Cross-family difficulty agreement

Each cell counts rows of the required corpus (n=210) with the row's two labels.

### objective × assignment

| objective \\ assignment | easy | medium | hard |
| --- | --- | --- | --- |
| easy   | 0 | 7 | 43 |
| medium | 0 | 4 | 75 |
| hard   | 0 | 0 | 81 |

### objective × ranking

| objective \\ ranking | easy | medium | hard |
| --- | --- | --- | --- |
| easy   | 1 | 13 | 36 |
| medium | 0 |  7 | 72 |
| hard   | 0 |  0 | 81 |

### assignment × ranking

| assignment \\ ranking | easy | medium | hard |
| --- | --- | --- | --- |
| easy   | 0 |  0 |   0 |
| medium | 0 |  9 |   2 |
| hard   | 1 | 11 | 187 |

Same-label agreement (diagonal sum / 210): objective × assignment 85/210 (40.48%), driven by the hard/hard cell (81); objective × ranking 89/210 (42.38%), again driven by hard/hard (81); assignment × ranking 196/210 (93.33%), with 187 of those in hard/hard. Off-diagonal mass is large for the first two pairs — same-row labels diverge across families, especially when one family says easy or medium.

## 2.3 Per-family difficulty against the perturbation grid

### Objective family

| perturbation_family | magnitude | cheap_backend | n | easy | medium | hard |
| --- | --- | --- | --- | --- | --- | --- |
| capacity_reduction | 0.80 | nearest_neighbor | 15 | 2 | 3 | 10 |
| capacity_reduction | 0.80 | savings          | 15 | 9 | 6 | 0 |
| capacity_reduction | 0.90 | nearest_neighbor | 15 | 1 | 3 | 11 |
| capacity_reduction | 0.90 | savings          | 15 | 7 | 8 | 0 |
| capacity_reduction | 0.95 | nearest_neighbor | 15 | 1 | 3 | 11 |
| capacity_reduction | 0.95 | savings          | 15 | 7 | 8 | 0 |
| capacity_reduction | 0.98 | nearest_neighbor | 15 | 1 | 2 | 12 |
| capacity_reduction | 0.98 | savings          | 15 | 9 | 6 | 0 |
| regional_distance_inflation | 1.10 | nearest_neighbor | 15 | 1 | 2 | 12 |
| regional_distance_inflation | 1.10 | savings          | 15 | 4 | 11 | 0 |
| regional_distance_inflation | 1.25 | nearest_neighbor | 15 | 1 | 2 | 12 |
| regional_distance_inflation | 1.25 | savings          | 15 | 3 | 12 | 0 |
| regional_distance_inflation | 1.50 | nearest_neighbor | 15 | 1 | 1 | 13 |
| regional_distance_inflation | 1.50 | savings          | 15 | 3 | 12 | 0 |

### Assignment family

| perturbation_family | magnitude | cheap_backend | n | easy | medium | hard |
| --- | --- | --- | --- | --- | --- | --- |
| capacity_reduction | 0.80 | nearest_neighbor | 15 | 0 | 1 | 14 |
| capacity_reduction | 0.80 | savings          | 15 | 0 | 0 | 15 |
| capacity_reduction | 0.90 | nearest_neighbor | 15 | 0 | 0 | 15 |
| capacity_reduction | 0.90 | savings          | 15 | 0 | 2 | 13 |
| capacity_reduction | 0.95 | nearest_neighbor | 15 | 0 | 0 | 15 |
| capacity_reduction | 0.95 | savings          | 15 | 0 | 2 | 13 |
| capacity_reduction | 0.98 | nearest_neighbor | 15 | 0 | 0 | 15 |
| capacity_reduction | 0.98 | savings          | 15 | 0 | 2 | 13 |
| regional_distance_inflation | 1.10 | nearest_neighbor | 15 | 0 | 0 | 15 |
| regional_distance_inflation | 1.10 | savings          | 15 | 0 | 1 | 14 |
| regional_distance_inflation | 1.25 | nearest_neighbor | 15 | 0 | 0 | 15 |
| regional_distance_inflation | 1.25 | savings          | 15 | 0 | 1 | 14 |
| regional_distance_inflation | 1.50 | nearest_neighbor | 15 | 0 | 0 | 15 |
| regional_distance_inflation | 1.50 | savings          | 15 | 0 | 2 | 13 |

### Ranking family

| perturbation_family | magnitude | cheap_backend | n | easy | medium | hard | na |
| --- | --- | --- | --- | --- | --- | --- | --- |
| capacity_reduction | 0.80 | nearest_neighbor | 15 | 0 | 1 | 14 | 0 |
| capacity_reduction | 0.80 | savings          | 15 | 1 | 1 | 13 | 0 |
| capacity_reduction | 0.90 | nearest_neighbor | 15 | 0 | 0 | 15 | 0 |
| capacity_reduction | 0.90 | savings          | 15 | 0 | 2 | 13 | 0 |
| capacity_reduction | 0.95 | nearest_neighbor | 15 | 0 | 0 | 15 | 0 |
| capacity_reduction | 0.95 | savings          | 15 | 0 | 2 | 13 | 0 |
| capacity_reduction | 0.98 | nearest_neighbor | 15 | 0 | 0 | 15 | 0 |
| capacity_reduction | 0.98 | savings          | 15 | 0 | 3 | 12 | 0 |
| regional_distance_inflation | 1.10 | nearest_neighbor | 15 | 0 | 0 | 15 | 0 |
| regional_distance_inflation | 1.10 | savings          | 15 | 0 | 3 | 12 | 0 |
| regional_distance_inflation | 1.25 | nearest_neighbor | 15 | 0 | 0 | 15 | 0 |
| regional_distance_inflation | 1.25 | savings          | 15 | 0 | 4 | 11 | 0 |
| regional_distance_inflation | 1.50 | nearest_neighbor | 15 | 0 | 0 | 15 | 0 |
| regional_distance_inflation | 1.50 | savings          | 15 | 0 | 4 | 11 | 0 |

## 2.4 Diagnostic summary

- objective: easy 23.81% (50/210), medium 37.62% (79/210), hard 38.57% (81/210). Easy band populated (>=10%).
- assignment: easy 0.00% (0/210), medium 5.24% (11/210), hard 94.76% (199/210). Easy band NOT populated.
- ranking: easy 0.48% (1/210), medium 9.52% (20/210), hard 90.00% (189/210), na 0/210. Easy band NOT populated.
- max ARI across required corpus: 0.5668 (assignment-easy threshold = 0.75).
- min |objective_gap_rel| across required corpus: 0.0045 (objective-easy threshold = 0.05; band populated).
- max top-3 route overlap across required corpus: 0.6667 (ranking-easy threshold = 0.67; one row at 2/3 is bucketed easy by the parenthetical "(2 or 3 of top 3 match)").
- ranking rows excluded as na (route_count < 3 on either backend): 0/210.

## 3. Budget-consistency check

Phase 2 ran PyVRP at 10 seconds; Phase 1 ran it at 60 seconds. We rerun PyVRP at 60s on five scenarios spanning the Phase 2 `objective_gap_rel` distribution.

### 3.1 Selected scenarios

Selection: one scenario per stratum, closest to the stratum midpoint, tiebreak by `instance_id` ascending.

| stratum | instance_id | family | magnitude | cheap_backend | gap_pct_at_10s |
| --- | --- | --- | --- | --- | --- |
| 0–5%   | X-n219-k73 | regional_distance_inflation | 1.25 | nearest_neighbor | 2.54 |
| 5–10%  | X-n110-k13 | regional_distance_inflation | 1.50 | savings          | 7.48 |
| 10–20% | X-n200-k36 | regional_distance_inflation | 1.25 | nearest_neighbor | 14.86 |
| 20–40% | X-n172-k51 | capacity_reduction          | 0.95 | nearest_neighbor | 30.07 |
| ≥40%   | X-n134-k13 | regional_distance_inflation | 1.50 | nearest_neighbor | 41.96 |

### 3.2 Rerun protocol

For each selected (instance, perturbation, magnitude), PyVRP was re-solved on the perturbed `.vrp` with `time_limit_sec=60`, `random_seed=1`, all other parameters identical to Phase 2. The cheap-backend artifacts were reused unchanged. Five SolutionArtifact JSONs are written to `data/processed/phase2r/budget_check/`.

### 3.3 Comparison

| stratum | obj_pyvrp_10s | obj_pyvrp_60s | pyvrp_improv_rel | gap_at_10s | gap_at_60s | ari_at_10s | ari_at_60s | overlap_at_10s | overlap_at_60s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0–5%   | 135074 | 135074 | 0.0000  | 0.0254 | 0.0254 | 0.3675 | 0.3675 | 0.000 | 0.000 |
| 5–10%  |  18782 |  18782 | 0.0000  | 0.0748 | 0.0748 | 0.4489 | 0.4489 | 0.000 | 0.000 |
| 10–20% |  64330 |  64026 | 0.00473 | 0.1486 | 0.1526 | 0.2661 | 0.2929 | 0.000 | 0.000 |
| 20–40% |  47767 |  47757 | 0.00021 | 0.3007 | 0.3008 | 0.1591 | 0.1329 | 0.000 | 0.000 |
| ≥40%   |  13120 |  13081 | 0.00297 | 0.4196 | 0.4213 | 0.3743 | 0.3224 | 0.000 | 0.000 |

Per-family difficulty labels at the two budgets:

| stratum | obj_10s → obj_60s | asn_10s → asn_60s | rnk_10s → rnk_60s |
| --- | --- | --- | --- |
| 0–5%   | easy   → easy   | hard → hard | hard → hard |
| 5–10%  | medium → medium | hard → hard | hard → hard |
| 10–20% | **medium → hard** | hard → hard | hard → hard |
| 20–40% | hard   → hard   | hard → hard | hard → hard |
| ≥40%   | hard   → hard   | hard → hard | hard → hard |

One label change: stratum 10–20% (X-n200-k36, regional_distance_inflation@1.25, NN). At 10s the cheap-vs-strong gap was 0.1486 (medium); at 60s PyVRP improved 0.47% and the gap rose to 0.1526, crossing the 0.15 hard cutoff. The change is a boundary crossing on the objective family only; assignment and ranking labels are unchanged.

### 3.4 Verdict

**Drift.** One scenario (10–20% stratum, X-n200-k36, regional_distance_inflation@1.25, nearest_neighbor) changed its objective-family difficulty label from medium to hard at the higher PyVRP budget.

Movement magnitudes:

- objective improvement of PyVRP at 60s vs 10s: max 0.47%, min 0.00% across the five scenarios.
- |ARI| movement at 60s vs 10s: max 0.0519, min 0.0000.
- top-3 overlap was 0.000 at both budgets on every selected scenario; no movement.

## 4. Decision

**REVISE.**

- Easy bands (≥10% of corpus): objective 23.81% ✓; assignment 0.00% ✗; ranking 0.48% ✗. One family meets the threshold; PROCEED requires at least two.
- Budget check: Drift (one scenario crosses the 0.15 objective cutoff at 60s).

Both REVISE conditions are triggered (fewer than two families meet the easy-band threshold; budget check shows Drift). STOP does not apply because the objective family's easy share (23.81%) exceeds 5%.
