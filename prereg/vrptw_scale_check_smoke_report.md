# VRPTW 18-instance scale-check report

## 1. Purpose

This is an 18-instance scale-check before committing to a full VRPTW thesis benchmark. It uses the soft_grid from perturbation pilot v2 and exercises both cheap actions (`reuse_direct` for TRAVEL_TIME/TIME_WINDOW/SERVICE_TIME, `local_repair_insert` for ORDER_CHANGE).

## 2. Architecture changes

- New `src/vrp_copilot_bench/vrptw/` package — canonical import surface for new VRPTW code. Legacy paths (`vrp_copilot_bench.vrptw_instances`, `.vrptw_perturbations`, `.solvers.pyvrp_vrptw_wrapper`) untouched and still imported by the v1/v2 pilots.
- `vrptw/baselines.py`: JSON cache at `data/vrptw_baselines/{id}.json`; cache key is `(instance_id, seed, time_limit_seconds, pyvrp_version)`.
- `vrptw/actions.py`: `VRPTWAction` protocol + `ReuseDirect`, `LocalRepairInsert`. `cheap_action_for_family` is the canonical rule: ORDER_CHANGE → `local_repair_insert`, else `reuse_direct`.
- `vrptw/evaluation.py`: ARI, infeasibility-kind, reference-stability, schedule shifts, route-end-disruption, generalized cost.
- `vrptw/features.py`: leak-free feature extraction (baseline + perturbation + action only — no reference outputs).
- `vrptw/losses.py`: OBJ/PV/STRUCT/SCHEDULE primary losses and bands per spec.
- Wide table = one row per (instance, perturbation, action); long claim table = 4 rows per wide row (one per claim family).

## 3. Dataset and setup

- **Instances** (1): C101
- **Perturbations** (2): TT_1, OC_1 (soft_grid magnitudes)
- **Seeds**: 1, 2, 3 (per perturbation cell)
- **Time limit per solve**: 60s
- **n_jobs**: 6
- **Total wall-clock**: 121.4s
- **Wide rows**: 3
- **Long claim rows**: 12
- **Expected wide rows**: 3 (non-OC × 1 action + OC × 2 actions) — OK
- **Expected long rows**: 12 — OK

## 4. Data-quality checks

- Wide rows with null `loss_obj_distance`: 0
- Wide rows with null `loss_struct`: 0
- Wide rows with null `loss_schedule`: 0
- Cells where all 3 reference seeds feasible: 3 / 3
- Cells with any reference infeasible: 0 / 3
- Band-n/a counts by family: band_obj_distance: {}; band_obj_generalized: {}; band_struct: {}; band_schedule: {}
- Baseline cache files: `data/vrptw_baselines/*.json` (one per instance)

## 5. Reference stability

- `reference_obj_unstable` rate: 0.000
- `reference_struct_unstable` rate: 0.000
- median `reference_ari_min`: 1.000
- By perturbation family (obj_unstable, struct_unstable):
    - ORDER_CHANGE: obj=0.000  struct=0.000
    - TRAVEL_TIME: obj=0.000  struct=0.000

## 6. Wide-table action results

### local_repair_insert (1 rows)
- PLAN_VALIDITY: {"hard": 1}
- STRUCT: {"easy": 1}
- SCHEDULE: {"easy": 1}
- OBJ (distance): {"medium": 1}
- OBJ (generalized): {"medium": 1}

### reuse_direct (2 rows)
- PLAN_VALIDITY: {"hard": 2}
- STRUCT: {"easy": 2}
- SCHEDULE: {"easy": 2}
- OBJ (distance): {"easy": 1, "medium": 1}
- OBJ (generalized): {"easy": 1, "medium": 1}

## 7. Cheap-action results

Long-table rows where `is_cheap_action=True`: **8**

Bands by claim_family × perturbation_family:
- **OBJ**
    - ORDER_CHANGE: {"medium": 1}
    - TRAVEL_TIME: {"easy": 1}
- **PLAN_VALIDITY**
    - ORDER_CHANGE: {"hard": 1}
    - TRAVEL_TIME: {"hard": 1}
- **STRUCT**
    - ORDER_CHANGE: {"easy": 1}
    - TRAVEL_TIME: {"easy": 1}
- **SCHEDULE**
    - ORDER_CHANGE: {"easy": 1}
    - TRAVEL_TIME: {"easy": 1}

## 8. ORDER_CHANGE and local repair

- OC × reuse_direct rows with coverage failure: 1 / 1
- OC × local_repair_insert `coverage_feasible=True` rate: 1.000
- OC × local_repair_insert `action_feasible=True` rate: 0.000
- OC × local_repair_insert infeasibility kinds: {"time_window": 1}
- Mean `local_repair_objective_delta_vs_reuse` (vs OC reuse_direct on same cell): 47.0

## 9. SCHEDULE v2 analysis

- `loss_schedule` (affected-p90) distribution: min=0.0000, median=0.0000, p90=0.0000, max=0.0000

## 10. Feature sanity

- `affected_min_slack`: n=1, min=2, median=2, mean=2, max=2
- `affected_total_wait`: n=3, min=0, median=0, mean=0, max=0
- `action_time_warp`: n=3, min=0, median=23, mean=242.7, max=705
- `action_obj_delta_pct`: n=3, min=0, median=0, mean=0.001891, max=0.005672
- `action_generalized_delta_pct`: n=3, min=0, median=0.0001877, mean=0.00267, max=0.007822

## 11. Recommendation

Programmatic answers to the prompt's recommendation questions. Use these numbers; the prose interpretation is for the user to write.
- Overall `band_plan_validity=easy` rate: 0.000
- `band_struct` distribution: {"easy": 3}
- `band_schedule` (affected-p90, primary) distribution: {"easy": 3}
- Reference structural instability rate: 0.000

- Wide parquet: `data/probes/vrptw_scale_check_smoke.parquet`
- Long parquet: `data/probes/vrptw_scale_check_smoke_claim_rows.parquet`
