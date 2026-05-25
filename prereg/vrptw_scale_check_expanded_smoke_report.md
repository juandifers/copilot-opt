# VRPTW 18-instance expanded-action scale-check report

## 1. Purpose

This phase tests an expanded action ladder before any 56-instance full benchmark. The previous 18-instance scale-check survived but the action set (reuse / local repair) was too thin for a strong compute-aware benchmark. Here we add three middle/reference rungs so the benchmark can answer: *given a disruption and a claim family, which level of computational response is sufficient?*

## 2. Action ladder

| tier | action | role |
|---|---|---|
| 0 | `reuse_direct` | score baseline routes unchanged under the perturbed instance |
| 1 | `local_repair_insert` | OC-only — cheapest-feasible-insertion of new customers into the existing routes |
| 2 | `cheap_fresh_construct` | deterministic build-from-scratch insertion heuristic; ignores baseline; prebuilt-ProblemData fast path preserves the heuristic |
| 3 | `pyvrp_10s` | PyVRP metaheuristic, seed=1, 10 s budget |
| 4 | `pyvrp_60s_reference` | materialized from reference seed 1 (60 s budget) — no extra solve |

The cheap-action rule is unchanged: non-OC families use `reuse_direct` (tier 0); ORDER_CHANGE uses `local_repair_insert` (tier 1).

## 3. Dataset and setup

- **Instances** (1): C101
- **Perturbations** (2): TT_1, OC_1 (soft_grid magnitudes)
- **Seeds**: 1, 2, 3 (per perturbation cell)
- **Reference time limit per solve**: 60s
- **pyvrp_10s time limit**: 10s
- **n_jobs**: 6
- **Total wall-clock**: 70.8s
- **Wide rows**: 9
- **Long claim rows**: 36
- **Expected wide rows**: 9 (non-OC × 4 actions + OC × 5 actions) — OK
- **Expected long rows**: 36 — OK

## 4. Data-quality checks

- Cells where all 3 reference seeds feasible: 9 / 9
- Cells with any reference infeasible: 0 / 9
- Wide rows with `band_obj_distance=n/a`: 0
- Wide rows with `band_struct=n/a`:        0
- Wide rows with `band_schedule=n/a`:      0
- Action failures (action_valid=False) by action:
    - `reuse_direct`: 2 / 2
    - `local_repair_insert`: 1 / 1
    - `cheap_fresh_construct`: 0 / 2
    - `pyvrp_10s`: 0 / 2
    - `pyvrp_60s_reference`: 0 / 2

## 5. Reference stability

- `reference_obj_unstable` rate: 0.000
- `reference_struct_unstable` rate: 0.000
- median `reference_ari_min`: 1.000
- By perturbation family (obj_unstable, struct_unstable):
    - ORDER_CHANGE: obj=0.000  struct=0.000
    - TRAVEL_TIME: obj=0.000  struct=0.000

## 6. Action quality by claim family

Band counts in the long claim table, by action × claim family:

### OBJ

| action | easy | medium | hard | n/a |
|---|---:|---:|---:|---:|
| `reuse_direct` | 1 | 1 | 0 | 0 |
| `local_repair_insert` | 0 | 1 | 0 | 0 |
| `cheap_fresh_construct` | 0 | 0 | 2 | 0 |
| `pyvrp_10s` | 2 | 0 | 0 | 0 |
| `pyvrp_60s_reference` | 2 | 0 | 0 | 0 |

### PLAN_VALIDITY

| action | easy | medium | hard | n/a |
|---|---:|---:|---:|---:|
| `reuse_direct` | 0 | 0 | 2 | 0 |
| `local_repair_insert` | 0 | 0 | 1 | 0 |
| `cheap_fresh_construct` | 2 | 0 | 0 | 0 |
| `pyvrp_10s` | 2 | 0 | 0 | 0 |
| `pyvrp_60s_reference` | 2 | 0 | 0 | 0 |

### STRUCT

| action | easy | medium | hard | n/a |
|---|---:|---:|---:|---:|
| `reuse_direct` | 2 | 0 | 0 | 0 |
| `local_repair_insert` | 1 | 0 | 0 | 0 |
| `cheap_fresh_construct` | 0 | 2 | 0 | 0 |
| `pyvrp_10s` | 2 | 0 | 0 | 0 |
| `pyvrp_60s_reference` | 2 | 0 | 0 | 0 |

### SCHEDULE

| action | easy | medium | hard | n/a |
|---|---:|---:|---:|---:|
| `reuse_direct` | 2 | 0 | 0 | 0 |
| `local_repair_insert` | 1 | 0 | 0 | 0 |
| `cheap_fresh_construct` | 0 | 2 | 0 | 0 |
| `pyvrp_10s` | 2 | 0 | 0 | 0 |
| `pyvrp_60s_reference` | 2 | 0 | 0 | 0 |

## 7. Runtime by action

`action_runtime_s` distribution per action:

| action | n | mean (s) | median (s) | p90 (s) | max (s) |
|---|---:|---:|---:|---:|---:|
| `reuse_direct` | 2 | 0.001 | 0.001 | 0.002 | 0.002 |
| `local_repair_insert` | 1 | 0.128 | 0.128 | 0.128 | 0.128 |
| `cheap_fresh_construct` | 2 | 0.151 | 0.151 | 0.156 | 0.157 |
| `pyvrp_10s` | 2 | 10.005 | 10.005 | 10.005 | 10.005 |
| `pyvrp_60s_reference` | 2 | 60.008 | 60.008 | 60.009 | 60.010 |

## 8. Cost/quality ladder

For each claim family, the table shows the mean primary loss and the `sufficient_binary` rate (band ∈ {easy} ⇒ 1; medium/hard ⇒ 0; n/a ⇒ null and excluded from the rate) per action. A meaningful ladder shows monotonically decreasing loss and rising sufficiency as the tier rises.

### OBJ

| action | n | mean loss | easy_rate (sufficient) |
|---|---:|---:|---:|
| `reuse_direct` | 2 | 0.0687 | 0.500 |
| `local_repair_insert` | 1 | 0.1080 | 0.000 |
| `cheap_fresh_construct` | 2 | 0.1751 | 0.000 |
| `pyvrp_10s` | 2 | 0.0000 | 1.000 |
| `pyvrp_60s_reference` | 2 | 0.0000 | 1.000 |

### PLAN_VALIDITY

| action | n | mean loss | easy_rate (sufficient) |
|---|---:|---:|---:|
| `reuse_direct` | 2 | 1.0000 | 0.000 |
| `local_repair_insert` | 1 | 1.0000 | 0.000 |
| `cheap_fresh_construct` | 2 | 0.0000 | 1.000 |
| `pyvrp_10s` | 2 | 0.0000 | 1.000 |
| `pyvrp_60s_reference` | 2 | 0.0000 | 1.000 |

### STRUCT

| action | n | mean loss | easy_rate (sufficient) |
|---|---:|---:|---:|
| `reuse_direct` | 2 | 0.0329 | 1.000 |
| `local_repair_insert` | 1 | 0.0250 | 1.000 |
| `cheap_fresh_construct` | 2 | 0.2004 | 0.000 |
| `pyvrp_10s` | 2 | 0.0000 | 1.000 |
| `pyvrp_60s_reference` | 2 | 0.0000 | 1.000 |

### SCHEDULE

| action | n | mean loss | easy_rate (sufficient) |
|---|---:|---:|---:|
| `reuse_direct` | 2 | 0.0000 | 1.000 |
| `local_repair_insert` | 1 | 0.0000 | 1.000 |
| `cheap_fresh_construct` | 2 | 0.0244 | 0.000 |
| `pyvrp_10s` | 2 | 0.0000 | 1.000 |
| `pyvrp_60s_reference` | 2 | 0.0000 | 1.000 |

## 9. ORDER_CHANGE analysis

Total OC wide rows: **5** (1 OC perturbations × 1 instances × 5 actions = 5)

| action | rows | coverage_feasible | action_feasible | infeasibility_kind (non-`none`) |
|---|---:|---:|---:|---|
| `reuse_direct` | 1 | 0.000 | 0.000 | {"coverage": 1} |
| `local_repair_insert` | 1 | 1.000 | 0.000 | {"time_window": 1} |
| `cheap_fresh_construct` | 1 | 1.000 | 1.000 | {} |
| `pyvrp_10s` | 1 | 1.000 | 1.000 | {} |
| `pyvrp_60s_reference` | 1 | 1.000 | 1.000 | {} |

OC bands by action (cheap-action `local_repair_insert` first):

| action | OBJ easy | STRUCT easy | SCHEDULE easy | PV easy |
|---|---:|---:|---:|---:|
| `reuse_direct` | 0 | 1 | 1 | 0 |
| `local_repair_insert` | 0 | 1 | 1 | 0 |
| `cheap_fresh_construct` | 0 | 0 | 0 | 1 |
| `pyvrp_10s` | 1 | 1 | 1 | 1 |
| `pyvrp_60s_reference` | 1 | 1 | 1 | 1 |

## 10. Middle-action value

Comparisons between adjacent ladder rungs across all 4 claim families (long-table band-easy rates):

| comparison | OBJ Δeasy% | PV Δeasy% | STRUCT Δeasy% | SCHEDULE Δeasy% |
|---|---:|---:|---:|---:|
| reuse_direct → cheap_fresh_construct | -50.0 | +100.0 | -100.0 | -100.0 |
| cheap_fresh_construct → pyvrp_10s | +100.0 | +0.0 | +100.0 | +100.0 |
| pyvrp_10s → pyvrp_60s_reference | +0.0 | +0.0 | +0.0 | +0.0 |

- Cells where cheap action gave PV=hard but pyvrp_10s recovered PV=easy: **2 / 2** (100.0%)
- Cells where even pyvrp_10s gave PV=hard: **0 / 2** — of which pyvrp_60s_reference recovered: 0

## 11. Recommendation

Programmatic answers to the prompt's recommendation questions. Use these numbers; final prose is for the user.

Headline aggregates:

| metric | value |
|---|---:|
| wide rows | 9 |
| long claim rows | 36 |
| reference_struct_unstable rate | 0.000 |
| reference_obj_unstable rate | 0.000 |
| wall-clock | 71s |

- Wide parquet: `data/probes/vrptw_scale_check_expanded_smoke.parquet`
- Long parquet: `data/probes/vrptw_scale_check_expanded_smoke_claim_rows.parquet`
