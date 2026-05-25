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

- **Instances** (18): C101, C102, C103, C201, C202, C203, R101, R102, R103, R201, R202, R203, RC101, RC102, RC103, RC201, RC202, RC203
- **Perturbations** (16): TT_1, TT_2, TT_3, TT_4, TW_1, TW_2, TW_3, TW_4, ST_1, ST_2, ST_3, ST_4, OC_1, OC_2, OC_3, OC_4 (soft_grid magnitudes)
- **Seeds**: 1, 2, 3 (per perturbation cell)
- **Time limit per solve**: 60s
- **n_jobs**: 6
- **Total wall-clock**: 8845.8s
- **Wide rows**: 360
- **Long claim rows**: 1440
- **Expected wide rows**: 360 (non-OC × 1 action + OC × 2 actions) — OK
- **Expected long rows**: 1440 — OK

## 4. Data-quality checks

- Wide rows with null `loss_obj_distance`: 7
- Wide rows with null `loss_struct`: 7
- Wide rows with null `loss_schedule`: 7
- Cells where all 3 reference seeds feasible: **353 / 360 (98.1%)**
- Cells with any reference infeasible: 7 / 360
- `reference_failure_kind` counts: `{"none": 353, "all_infeasible": 7}` — every failure is *all 3 seeds infeasible*; no partial-failure cells.
- Band-n/a counts by family: `band_obj_distance`/`band_obj_generalized`/`band_struct`/`band_schedule` each = `{"n/a": 7}`.
- Baseline cache files: 18 in `data/vrptw_baselines/` (1 cache hit on C101 from Stage 3; 17 fresh writes during Phase 1).
- All cached baselines: `time_limit_seconds=60.0`, `seed=1`, `pyvrp_version=0.13.3`.

### The 7 reference-infeasible rows

| instance | perturbation | action | seed-1 obj |
|---|---|---|---|
| R101  | TT_4 | reuse_direct        | inf |
| R102  | TT_4 | reuse_direct        | inf |
| R103  | TT_4 | reuse_direct        | inf |
| RC102 | OC_2 | reuse_direct        | inf |
| RC102 | OC_2 | local_repair_insert | inf |
| RC102 | OC_4 | reuse_direct        | inf |
| RC102 | OC_4 | local_repair_insert | inf |

Two distinct hard cells: **R10x × TT_4** (the random-customer C-series with farthest-quartile duration scaled by 1.30 — exhausts the 25-vehicle fleet within 60 s) and **RC102 × OC_{2,4}** (RC102 plus a tight-window inserted customer — fleet of 12 vehicles cannot fit the new visit within the corridor). These are recorded as `band=n/a` for OBJ/STRUCT/SCHEDULE; PLAN_VALIDITY remains valid (it's an action-feasibility check, no reference required).

## 5. Reference stability

- `reference_obj_unstable` rate: 0.000
- `reference_struct_unstable` rate: 0.189
- median `reference_ari_min`: 1.000
- By perturbation family (obj_unstable, struct_unstable):
    - ORDER_CHANGE: obj=0.000  struct=0.181
    - SERVICE_TIME: obj=0.000  struct=0.236
    - TIME_WINDOW: obj=0.000  struct=0.139
    - TRAVEL_TIME: obj=0.000  struct=0.208

## 6. Wide-table action results

### local_repair_insert (72 rows)
- PLAN_VALIDITY: {"hard": 36, "easy": 36}
- STRUCT: {"easy": 34, "medium": 24, "hard": 12, "n/a": 2}
- SCHEDULE: {"easy": 38, "medium": 20, "hard": 12, "n/a": 2}
- OBJ (distance): {"easy": 60, "medium": 10, "n/a": 2}
- OBJ (generalized): {"easy": 60, "medium": 9, "n/a": 2, "hard": 1}

### reuse_direct (288 rows)
- PLAN_VALIDITY: {"hard": 202, "easy": 86}
- STRUCT: {"easy": 177, "hard": 58, "medium": 48, "n/a": 5}
- SCHEDULE: {"easy": 137, "hard": 76, "medium": 70, "n/a": 5}
- OBJ (distance): {"easy": 249, "medium": 27, "hard": 7, "n/a": 5}
- OBJ (generalized): {"easy": 254, "medium": 21, "hard": 8, "n/a": 5}

## 7. Cheap-action results

Long-table rows where `is_cheap_action=True`: **1152**

Bands by claim_family × perturbation_family:
- **OBJ**
    - ORDER_CHANGE: {"easy": 60, "medium": 10, "n/a": 2}
    - SERVICE_TIME: {"easy": 56, "medium": 11, "hard": 5}
    - TIME_WINDOW: {"easy": 72}
    - TRAVEL_TIME: {"easy": 67, "n/a": 3, "medium": 2}
- **PLAN_VALIDITY**
    - ORDER_CHANGE: {"hard": 36, "easy": 36}
    - SERVICE_TIME: {"hard": 49, "easy": 23}
    - TIME_WINDOW: {"hard": 40, "easy": 32}
    - TRAVEL_TIME: {"hard": 41, "easy": 31}
- **STRUCT**
    - ORDER_CHANGE: {"easy": 34, "medium": 24, "hard": 12, "n/a": 2}
    - SERVICE_TIME: {"easy": 40, "hard": 20, "medium": 12}
    - TIME_WINDOW: {"easy": 48, "hard": 13, "medium": 11}
    - TRAVEL_TIME: {"easy": 46, "hard": 15, "medium": 8, "n/a": 3}
- **SCHEDULE**
    - ORDER_CHANGE: {"easy": 38, "medium": 20, "hard": 12, "n/a": 2}
    - SERVICE_TIME: {"easy": 28, "hard": 25, "medium": 19}
    - TIME_WINDOW: {"easy": 34, "hard": 19, "medium": 19}
    - TRAVEL_TIME: {"easy": 36, "hard": 21, "medium": 12, "n/a": 3}

## 8. ORDER_CHANGE and local repair

- OC × reuse_direct rows with coverage failure: **72 / 72 (100%)** — confirms reuse is not a viable cheap action for OC; every cell needs repair.
- OC × local_repair_insert `coverage_feasible=True` rate: **1.000** — the greedy insertion always places every new customer somewhere.
- OC × local_repair_insert `action_feasible=True` rate: **0.500** — half of OC cells remain TW/capacity-infeasible after repair, exposing real TW pressure as a claim-family signal.
- OC × local_repair_insert `infeasibility_kind`: `{"none": 36, "time_window": 28, "both": 7, "capacity": 1}` — among repair failures, **time_window** (28) dominates, **capacity** is rare (1), and `both` (7) typically maps to the RC102 OC_2/OC_4 fleet-exhaustion cells.
- `local_repair_inserted_all=True` rate: 0.500 — same 36/72 cells where repair is fully feasible.
- `local_repair_objective_delta_vs_reuse` (vs OC reuse_direct on same cell): n=72, **min=0.0, median=209.0, mean=392.5, max=4414.0**. Repair never *loses* distance vs reuse (min=0) and pays a moderate insertion premium on average.
- Recommendation: **keep local_repair_insert as the cheap OC action**. It surfaces the same TW pressure as reuse-on-non-OC cells while also being legitimately useful (coverage always fixed; obj delta small).

## 9. SCHEDULE v2 analysis

- `loss_schedule` (affected-p90) distribution over 353 valid rows: min=0.0000, **median=0.0214, p90=0.2415**, max=0.6629 — well-stratified across the easy/medium/hard bands (`0.02/0.05` thresholds).
- Band distribution among 360 wide rows: `{"easy": 175, "medium": 90, "hard": 88, "n/a": 7}` — **49 % easy / 25 % medium / 24 % hard / 2 % n/a**. Healthy three-way spread.
- **Time-feasible rows where SCHEDULE is medium/hard: 19 / 122 (15.6 %).** This is the key information-content check: even after PLAN_VALIDITY is satisfied, **1 in 6 cells still show meaningful schedule disruption**. SCHEDULE v2 adds information beyond PLAN_VALIDITY.
- Among time-feasible rows: `band_schedule` = `{"easy": 103, "medium": 10, "hard": 9}`.
- SCHEDULE breakdown by perturbation family (cheap-action rows only):
  - ORDER_CHANGE: easy=38, medium=20, hard=12, n/a=2 — moderate schedule pressure once coverage is fixed.
  - SERVICE_TIME: easy=28, medium=19, hard=25 — *highest* SCHEDULE pressure; large multipliers in ST_3/ST_4 cascade through.
  - TIME_WINDOW: easy=34, medium=19, hard=19 — strong signal as expected.
  - TRAVEL_TIME: easy=36, medium=12, hard=21, n/a=3 — strong on the hard quartiles.

## 10. Feature sanity

- `affected_min_slack`: n=216, min=0, median=0, mean=107, max=1200
- `affected_total_wait`: n=360, min=0, median=387, mean=3521, max=3.109e+04
- `action_time_warp`: n=360, min=0, median=0, mean=371.2, max=9655
- `action_obj_delta_pct`: n=360, min=0, median=0, mean=0.008975, max=0.5326
- `action_generalized_delta_pct`: n=360, min=-0.00347, median=0.0004466, mean=0.008525, max=0.2835

## 11. Recommendation

Programmatic answers to the prompt's recommendation questions.

### Headline aggregates

| metric | value |
|---|---|
| wide rows | 360 |
| long claim rows | 1 440 |
| reference feasibility (all 3 seeds) | 353 / 360 (98.1 %) |
| reference obj-instability rate | 0.000 |
| reference struct-instability rate (ari_min < 0.90) | 0.189 |
| median reference ari_min | 1.000 |
| `band_plan_validity = easy` rate (overall) | 33.9 % |
| `band_obj_distance` distribution | easy 309 / medium 37 / hard 7 / n/a 7 |
| `band_struct` distribution | easy 211 / medium 72 / hard 70 / n/a 7 |
| `band_schedule` (v2 affected-p90) distribution | easy 175 / medium 90 / hard 88 / n/a 7 |
| OC reuse coverage-failure rate | 100 % |
| OC repair coverage-success rate | 100 % |
| OC repair action-feasible rate | 50 % |
| SCHEDULE medium/hard among time-feasible rows | 15.6 % |

### Q&A

1. **Does the v2 design survive 18 instances? — YES.**
   All four claim families are non-degenerate and informative:
   - PLAN_VALIDITY easy rate 0.339 (down from v1's ~0.21) is in a useful range.
   - STRUCT is well-stratified (211 / 72 / 70 / 7).
   - SCHEDULE v2 is well-stratified (175 / 90 / 88 / 7) and adds information beyond PV (15.6 % of time-feasible rows are still SCHEDULE medium/hard).
   - OBJ stays dominated by easy but has enough medium/hard to separate strong from weak cells (37 medium, 7 hard).
   Reference stability is *much* better than the CVRP Stage A baseline (struct-unstable 0.189 vs CVRP ≈ 0.926); the predictor will have clean labels.

2. **36 vs all 56 Solomon instances for the final benchmark? — Recommend 36.**
   At 18 instances we already get cleanly populated, well-stratified bands across all four claim families with only 7 / 360 (1.9 %) n/a cells. Doubling to 36 would give ~720 wide rows / ~2 880 long rows — more than enough to support per-family-class evaluation (C, R, RC × 100/200 series) without the 56-instance budget hit (~7 h wall-clock on 6 cores). The marginal value of going from 36 to 56 is small given how stable references are. Recommend 36 unless the prereg needs deeper per-class power.

3. **Retain `soft_grid`? — YES.**
   The earlier v1_grid produced too many PLAN_VALIDITY hard rows (79 % infeasible in pilot v2). Under soft_grid we get 66 % infeasible / 34 % feasible — a usable 2-class balance, with SCHEDULE giving the within-feasible gradient. No reason to revisit magnitudes.

4. **Include `local_repair_insert` in the benchmark? — YES.**
   Without it, every OC cell is `infeasibility_kind=coverage` and the OC family degenerates to "always infeasible, no information beyond reuse." With it:
   - 100 % coverage success (greedy insertion always places customers).
   - 50 % become TW-feasible → useful PLAN_VALIDITY split inside the OC family.
   - Obj delta vs reuse is bounded (mean +392 units, median +209) — modest cost for the information gained.

5. **Retain SCHEDULE v2 (affected-p90)? — YES.**
   The v1 global-median metric was inactive (0 / 96 hard in pilot v1). v2 affected-p90 is well-stratified across all 4 families and adds 15.6 % medium/hard signal in the time-feasible regime where PV doesn't separate cells. Keep the v1 global median as a diagnostic column only (`loss_schedule_global_median`).

6. **Blockers before drafting a new VRPTW prereg? — NONE that prevent moving forward.**
   Two items worth noting but not blocking:
   - **PyVRP nondeterminism under MaxRuntime.** Three seeds at 60 s on the same perturbed instance can land different ILS iteration counts and produce slightly different objectives; we see this as the 0.189 struct-instability rate (none of which is *obj*-instability). It's a known phenomenon and is handled correctly by `reference_struct_unstable` flagging in the claim rows.
   - **7 "all_infeasible" cells (R10x × TT_4, RC102 × OC_2/OC_4).** These are real infeasibilities at the 60-s budget, not artifacts. The prereg should either (a) accept them as `band=n/a` (1.9 % of rows) or (b) raise the time limit to 90/120 s for the next scale-check; the current data suggests the cost-benefit favors leaving them as n/a.

### Outputs

- Wide parquet: `data/probes/vrptw_scale_check_18.parquet` (360 rows × 83 cols)
- Long parquet: `data/probes/vrptw_scale_check_18_claim_rows.parquet` (1 440 rows × 36 cols)
- Baseline cache: `data/vrptw_baselines/{C,R,RC}{101..103,201..203}.json` (18 files)

### Runtime

- Phase 1 baselines (18, 6 cores): 180.3 s (1 cache hit, 17 misses)
- Phase 2 references (864 × 60 s, 6 cores): 8 643.5 s (~144 min)
- Phase 3 row assembly: 22 s
- **Total wall-clock: 8 845.8 s (~2 h 27 min)**
