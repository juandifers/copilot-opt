# Stage A VRPTW run report

Stage A of the VRPTW sufficiency benchmark per `prereg/PREREG_v1.0_vrptw.md` (lock tag `prereg-v1.0-vrptw`).

## 1. Wall-clock by phase

| phase | seconds | hh:mm:ss |
|---|---:|---|
| baselines | 241.5 | 00:04:01 |
| references | 4804.5 | 01:20:04 |
| pyvrp_10s solves | 141.0 | 00:02:21 |
| row assembly | 100.1 | 00:01:40 |
| **total run-script** | 5287.1 | 01:28:07 |

## 2. Row counts (expected vs actual)

| table | expected | actual | match |
|---|---:|---:|---|
| wide | 340 | 340 | OK |
| long claim | 1360 | 1360 | OK |

Cached rows reused from checkpoint dir: 0 / 340

## 3. Reference feasibility

- Cells where all 3 reference seeds feasible: **74 / 80** (92.5%)
- Cells where at least one seed feasible: **74 / 80** (92.5%)
- Cells where all 3 seeds infeasible: **6 / 80** (7.5%)

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
- `reference_struct_unstable` rate (overall): **0.351**
- median `reference_ari_min` (overall): **0.989**

### By perturbation family

| family | n cells | obj_unstable | struct_unstable | median ari_min |
|---|---:|---:|---:|---:|
| ORDER_CHANGE | 20 | 0.000 | 0.333 | 0.990 |
| SERVICE_TIME | 20 | 0.000 | 0.500 | 0.888 |
| TIME_WINDOW | 20 | 0.000 | 0.400 | 1.000 |
| TRAVEL_TIME | 20 | 0.000 | 0.125 | 0.995 |

Compare against the 18-instance expanded-action pilot rates (obj=0.000, struct=0.194) and the Phase-1 unperturbed probe (struct=0.167, median ari_min=1.000).

## 6. Headline band distributions (long table)

### OBJ

| action | easy | medium | hard | n/a | easy_rate |
|---|---:|---:|---:|---:|---:|
| `construct_feasible` | 0 | 0 | 74 | 6 | 0.000 |
| `local_repair_insert` | 16 | 2 | 0 | 2 | 0.889 |
| `pyvrp_10s` | 74 | 0 | 0 | 6 | 1.000 |
| `pyvrp_60s_reference` | 74 | 0 | 0 | 6 | 1.000 |
| `reuse_direct` | 59 | 11 | 4 | 6 | 0.797 |

### PLAN_VALIDITY

| action | easy | medium | hard | n/a | easy_rate |
|---|---:|---:|---:|---:|---:|
| `construct_feasible` | 72 | 0 | 8 | 0 | 0.900 |
| `local_repair_insert` | 8 | 0 | 12 | 0 | 0.400 |
| `pyvrp_10s` | 74 | 0 | 6 | 0 | 0.925 |
| `pyvrp_60s_reference` | 74 | 0 | 6 | 0 | 0.925 |
| `reuse_direct` | 16 | 0 | 64 | 0 | 0.200 |

### STRUCT

| action | easy | medium | hard | n/a | easy_rate |
|---|---:|---:|---:|---:|---:|
| `construct_feasible` | 0 | 5 | 69 | 6 | 0.000 |
| `local_repair_insert` | 6 | 9 | 3 | 2 | 0.333 |
| `pyvrp_10s` | 40 | 25 | 9 | 6 | 0.541 |
| `pyvrp_60s_reference` | 74 | 0 | 0 | 6 | 1.000 |
| `reuse_direct` | 32 | 20 | 22 | 6 | 0.432 |

### SCHEDULE

| action | easy | medium | hard | n/a | easy_rate |
|---|---:|---:|---:|---:|---:|
| `construct_feasible` | 9 | 39 | 26 | 6 | 0.122 |
| `local_repair_insert` | 14 | 4 | 0 | 2 | 0.778 |
| `pyvrp_10s` | 64 | 7 | 3 | 6 | 0.865 |
| `pyvrp_60s_reference` | 74 | 0 | 0 | 6 | 1.000 |
| `reuse_direct` | 43 | 22 | 9 | 6 | 0.581 |


## 7. Anomalies / notes

- No exceptions, no cache hits — clean fresh run.

## 8. Artifacts

- Wide parquet: `data/homberger_probe_cells.parquet`
- Long parquet: `data/homberger_probe_claim_rows.parquet`
- Checkpoint dir: `data/homberger_probe_checkpoints`
- Failure records: `data/homberger_probe_checkpoints/_failures/` (0 records)

## 9. Config

- Instances: 10 from `instances/solomon100_stage_a.txt`
- Perturbations: 8 (soft_grid)
- Reference seeds: [1, 2, 3]
- Reference time limit: 120.0s per solve
- pyvrp_10s time limit: 10.0s
- Parallel workers: 6
