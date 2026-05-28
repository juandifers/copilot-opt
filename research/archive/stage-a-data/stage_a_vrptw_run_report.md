# Stage A VRPTW run report

Stage A of the VRPTW sufficiency benchmark per `prereg/PREREG_v1.0_vrptw.md` (lock tag `prereg-v1.0-vrptw`).

## 1. Wall-clock by phase

| phase | seconds | hh:mm:ss |
|---|---:|---|
| baselines | 421.5 | 00:07:01 |
| references | 26897.0 | 07:28:17 |
| pyvrp_10s solves | 1505.4 | 00:25:05 |
| row assembly | 168.5 | 00:02:48 |
| **total run-script** | 28992.4 | 08:03:12 |

## 2. Row counts (expected vs actual)

| table | expected | actual | match |
|---|---:|---:|---|
| wide | 3808 | 3808 | OK |
| long claim | 15232 | 15232 | OK |

Cached rows reused from checkpoint dir: 0 / 3808

## 3. Reference feasibility

- Cells where all 3 reference seeds feasible: **889 / 896** (99.2%)
- Cells where at least one seed feasible: **889 / 896** (99.2%)
- Cells where all 3 seeds infeasible: **7 / 896** (0.8%)

### All-3-seeds-infeasible cells

| instance | perturbation | failure_kind |
|---|---|---|
| R101 | TT_4 | all_infeasible |
| R102 | TT_4 | all_infeasible |
| R103 | TT_4 | all_infeasible |
| R110 | OC_4 | all_infeasible |
| RC102 | OC_2 | all_infeasible |
| RC102 | OC_4 | all_infeasible |
| RC105 | TT_4 | all_infeasible |

- Reference solves that raised exceptions: **0 keys** across **0 cells**.

## 4. Action failures by action

No action-level failures recorded.

### Failures by phase (full breakdown)

| phase | count |
|---|---:|
| (none) | 0 |

## 5. Reference stability

- `reference_obj_unstable` rate (overall): **0.000**
- `reference_struct_unstable` rate (overall): **0.286**
- median `reference_ari_min` (overall): **1.000**

### By perturbation family

| family | n cells | obj_unstable | struct_unstable | median ari_min |
|---|---:|---:|---:|---:|
| ORDER_CHANGE | 224 | 0.000 | 0.312 | 1.000 |
| SERVICE_TIME | 224 | 0.000 | 0.295 | 1.000 |
| TIME_WINDOW | 224 | 0.000 | 0.295 | 1.000 |
| TRAVEL_TIME | 224 | 0.000 | 0.241 | 1.000 |

Compare against the 18-instance expanded-action pilot rates (obj=0.000, struct=0.194) and the Phase-1 unperturbed probe (struct=0.167, median ari_min=1.000).

## 6. Headline band distributions (long table)

### OBJ

| action | easy | medium | hard | n/a | easy_rate |
|---|---:|---:|---:|---:|---:|
| `construct_feasible` | 0 | 19 | 870 | 7 | 0.000 |
| `local_repair_insert` | 190 | 29 | 2 | 3 | 0.860 |
| `pyvrp_10s` | 889 | 0 | 0 | 7 | 1.000 |
| `pyvrp_60s_reference` | 889 | 0 | 0 | 7 | 1.000 |
| `reuse_direct` | 811 | 67 | 11 | 7 | 0.912 |

### PLAN_VALIDITY

| action | easy | medium | hard | n/a | easy_rate |
|---|---:|---:|---:|---:|---:|
| `construct_feasible` | 889 | 0 | 7 | 0 | 0.992 |
| `local_repair_insert` | 150 | 0 | 74 | 0 | 0.670 |
| `pyvrp_10s` | 889 | 0 | 7 | 0 | 0.992 |
| `pyvrp_60s_reference` | 889 | 0 | 7 | 0 | 0.992 |
| `reuse_direct` | 254 | 0 | 642 | 0 | 0.283 |

### STRUCT

| action | easy | medium | hard | n/a | easy_rate |
|---|---:|---:|---:|---:|---:|
| `construct_feasible` | 0 | 42 | 847 | 7 | 0.000 |
| `local_repair_insert` | 115 | 67 | 39 | 3 | 0.520 |
| `pyvrp_10s` | 776 | 71 | 42 | 7 | 0.873 |
| `pyvrp_60s_reference` | 889 | 0 | 0 | 7 | 1.000 |
| `reuse_direct` | 512 | 156 | 221 | 7 | 0.576 |

### SCHEDULE

| action | easy | medium | hard | n/a | easy_rate |
|---|---:|---:|---:|---:|---:|
| `construct_feasible` | 26 | 80 | 783 | 7 | 0.029 |
| `local_repair_insert` | 94 | 48 | 79 | 3 | 0.425 |
| `pyvrp_10s` | 795 | 13 | 81 | 7 | 0.894 |
| `pyvrp_60s_reference` | 889 | 0 | 0 | 7 | 1.000 |
| `reuse_direct` | 373 | 137 | 379 | 7 | 0.420 |


## 7. Anomalies / notes

- No exceptions, no cache hits — clean fresh run.

## 8. Artifacts

- Wide parquet: `/Users/jd/Documents/copilot-opt/data/stage_a_vrptw.parquet`
- Long parquet: `/Users/jd/Documents/copilot-opt/data/stage_a_vrptw_claim_rows.parquet`
- Checkpoint dir: `/Users/jd/Documents/copilot-opt/data/stage_a_vrptw_checkpoints`
- Failure records: `/Users/jd/Documents/copilot-opt/data/stage_a_vrptw_checkpoints/_failures/` (0 records)

## 9. Config

- Instances: 56 from `instances/solomon100_stage_a.txt`
- Perturbations: 16 (soft_grid)
- Reference seeds: [1, 2, 3]
- Reference time limit: 60.0s per solve
- pyvrp_10s time limit: 10.0s
- Parallel workers: 6
