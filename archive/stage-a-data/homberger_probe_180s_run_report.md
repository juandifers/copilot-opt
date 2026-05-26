# Stage A VRPTW run report

Stage A of the VRPTW sufficiency benchmark per `prereg/PREREG_v1.0_vrptw.md` (lock tag `prereg-v1.0-vrptw`).

## 1. Wall-clock by phase

| phase | seconds | hh:mm:ss |
|---|---:|---|
| baselines | 361.8 | 00:06:01 |
| references | 5044.0 | 01:24:03 |
| pyvrp_10s solves | 100.8 | 00:01:40 |
| row assembly | 68.8 | 00:01:08 |
| **total run-script** | 5575.4 | 01:32:55 |

## 2. Row counts (expected vs actual)

| table | expected | actual | match |
|---|---:|---:|---|
| wide | 238 | 238 | OK |
| long claim | 952 | 952 | OK |

Cached rows reused from checkpoint dir: 0 / 238

## 3. Reference feasibility

- Cells where all 3 reference seeds feasible: **50 / 56** (89.3%)
- Cells where at least one seed feasible: **50 / 56** (89.3%)
- Cells where all 3 seeds infeasible: **6 / 56** (10.7%)

### All-3-seeds-infeasible cells

| instance | perturbation | failure_kind |
|---|---|---|
| R1_2_1 | TT_4 | all_infeasible |
| R1_2_1 | TT_5 | all_infeasible |
| R1_2_1 | OC_4 | all_infeasible |
| R1_2_1 | OC_5 | all_infeasible |
| R1_2_2 | TT_4 | all_infeasible |
| R1_2_2 | TT_5 | all_infeasible |

- Reference solves that raised exceptions: **0 keys** across **0 cells**.

## 4. Action failures by action

No action-level failures recorded.

### Failures by phase (full breakdown)

| phase | count |
|---|---:|
| (none) | 0 |

## 5. Reference stability

- `reference_obj_unstable` rate (overall): **0.000**
- `reference_struct_unstable` rate (overall): **0.400**
- median `reference_ari_min` (overall): **0.923**

### By perturbation family

| family | n cells | obj_unstable | struct_unstable | median ari_min |
|---|---:|---:|---:|---:|
| ORDER_CHANGE | 14 | 0.000 | 0.417 | 0.921 |
| SERVICE_TIME | 14 | 0.000 | 0.571 | 0.780 |
| TIME_WINDOW | 14 | 0.000 | 0.429 | 0.924 |
| TRAVEL_TIME | 14 | 0.000 | 0.100 | 0.961 |

Compare against the 18-instance expanded-action pilot rates (obj=0.000, struct=0.194) and the Phase-1 unperturbed probe (struct=0.167, median ari_min=1.000).

## 6. Headline band distributions (long table)

### OBJ

| action | easy | medium | hard | n/a | easy_rate |
|---|---:|---:|---:|---:|---:|
| `construct_feasible` | 0 | 0 | 50 | 6 | 0.000 |
| `local_repair_insert` | 12 | 0 | 0 | 2 | 1.000 |
| `pyvrp_10s` | 50 | 0 | 0 | 6 | 1.000 |
| `pyvrp_60s_reference` | 50 | 0 | 0 | 6 | 1.000 |
| `reuse_direct` | 45 | 5 | 0 | 6 | 0.900 |

### PLAN_VALIDITY

| action | easy | medium | hard | n/a | easy_rate |
|---|---:|---:|---:|---:|---:|
| `construct_feasible` | 48 | 0 | 8 | 0 | 0.857 |
| `local_repair_insert` | 8 | 0 | 6 | 0 | 0.571 |
| `pyvrp_10s` | 50 | 0 | 6 | 0 | 0.893 |
| `pyvrp_60s_reference` | 50 | 0 | 6 | 0 | 0.893 |
| `reuse_direct` | 10 | 0 | 46 | 0 | 0.179 |

### STRUCT

| action | easy | medium | hard | n/a | easy_rate |
|---|---:|---:|---:|---:|---:|
| `construct_feasible` | 0 | 0 | 50 | 6 | 0.000 |
| `local_repair_insert` | 4 | 5 | 3 | 2 | 0.333 |
| `pyvrp_10s` | 17 | 24 | 9 | 6 | 0.340 |
| `pyvrp_60s_reference` | 50 | 0 | 0 | 6 | 1.000 |
| `reuse_direct` | 19 | 13 | 18 | 6 | 0.380 |

### SCHEDULE

| action | easy | medium | hard | n/a | easy_rate |
|---|---:|---:|---:|---:|---:|
| `construct_feasible` | 5 | 26 | 19 | 6 | 0.100 |
| `local_repair_insert` | 10 | 2 | 0 | 2 | 0.833 |
| `pyvrp_10s` | 42 | 5 | 3 | 6 | 0.840 |
| `pyvrp_60s_reference` | 50 | 0 | 0 | 6 | 1.000 |
| `reuse_direct` | 34 | 11 | 5 | 6 | 0.680 |


## 7. Anomalies / notes

- No exceptions, no cache hits — clean fresh run.

## 8. Artifacts

- Wide parquet: `data/homberger_probe_cells_180s.parquet`
- Long parquet: `data/homberger_probe_claim_rows_180s.parquet`
- Checkpoint dir: `data/homberger_probe_180s_checkpoints`
- Failure records: `data/homberger_probe_180s_checkpoints/_failures/` (0 records)

## 9. Config

- Instances: 7 from `instances/solomon100_stage_a.txt`
- Perturbations: 8 (soft_grid)
- Reference seeds: [1, 2, 3]
- Reference time limit: 180.0s per solve
- pyvrp_10s time limit: 10.0s
- Parallel workers: 6
