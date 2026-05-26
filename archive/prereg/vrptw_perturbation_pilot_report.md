# VRPTW Perturbation Pilot — Report
Generated: 2026-05-13T00:40:44
## Purpose and research question
Does VRPTW remain structurally and operationally well-defined under realistic perturbations, and do the claim families OBJ, PLAN_VALIDITY, STRUCT, and SCHEDULE produce non-trivial sufficiency patterns?
Exploratory companion to the preregistered CVRP Stage A benchmark. **No prereg changes** and no CVRP code modifications.
## Dataset and solver setup
- Instances: C101, C201, R101, R201, RC101, RC201 (Solomon-100, PyVRP `Instances` mirror, CVRPLIB-extended VRPTW `.vrp` format).
- Seeds (per perturbation cell): 1, 2, 3.
- Time limit: 60s per PyVRP solve.
- Solver: PyVRP 0.13.3 via `pyvrp.solve(..., stop=MaxRuntime, display=False, collect_stats=False)`.
- Workers: joblib loky, `n_jobs=6`.
- Total cells: 96 (6 instances × 16 perturbations).
## Perturbation grid
Grid (4 per family) — selection logic uses the baseline schedule (seed=1 60s PyVRP on the unperturbed instance):
| ID | Family | Selector | Magnitude |
|---|---|---|---|
| TT_1 | TRAVEL_TIME | route w/ highest total waiting | ×1.10 duration |
| TT_2 | TRAVEL_TIME | route w/ lowest min slack-to-tw_late | ×1.20 |
| TT_3 | TRAVEL_TIME | densest customer quartile | ×1.30 |
| TT_4 | TRAVEL_TIME | farthest customer quartile | ×1.50 |
| TW_1 | TIME_WINDOW | route w/ highest mean slack | tighten 10% |
| TW_2 | TIME_WINDOW | route w/ lowest mean slack | tighten 20% |
| TW_3 | TIME_WINDOW | final third of every route | shift earlier 10% |
| TW_4 | TIME_WINDOW | first third of every route | shift later 10% |
| ST_1 | SERVICE_TIME | route w/ highest total waiting | ×1.10 service |
| ST_2 | SERVICE_TIME | route w/ lowest min slack | ×1.25 |
| ST_3 | SERVICE_TIME | densest customer quartile | ×1.50 |
| ST_4 | SERVICE_TIME | top-demand quartile | ×2.00 |
| OC_1 | ORDER_CHANGE | +1 cust near highest-slack route, flexible TW | demand 0.05·cap |
| OC_2 | ORDER_CHANGE | +1 cust near lowest-slack route, tight TW | demand 0.05·cap |
| OC_3 | ORDER_CHANGE | +3 clust near densest region, flexible TW | demand 0.15·cap |
| OC_4 | ORDER_CHANGE | +3 clust near low-slack route, tight TW | demand 0.20·cap |
## Scaling convention
Same as the Phase 1 probe: all distance, duration, time-window, and service-time integers are multiplied by **10** before being handed to PyVRP. Stability and schedule metrics in this report are scale-invariant; absolute objectives are in ×10 distance units.
TRAVEL_TIME perturbations modify the duration matrix only; distances are unchanged. So OBJ changes there reflect either (a) PyVRP picking different routes under the perturbed timing or (b) reuse on tighter-than-feasible timing — not raw distance scaling.
## Aggregate band rates by claim family
| Loss | easy | medium | hard |
|---|---|---|---|
| band_obj | 79 (82.3%) | 11 (11.5%) | 5 (5.2%) |
| band_struct | 54 (56.2%) | 21 (21.9%) | 21 (21.9%) |
| band_schedule | 90 (93.8%) | 6 (6.2%) | 0 (0.0%) |
PLAN_VALIDITY (binary):

| Loss | easy (feasible) | hard (infeasible) |
|---|---|---|
| band_plan_validity | 20 (20.8%) | 76 (79.2%) |
## Aggregate band rates by perturbation family
### TRAVEL_TIME (24 cells)
| Loss | easy | medium | hard |
|---|---|---|---|
| band_obj | 21 (87.5%) | 1 (4.2%) | 1 (4.2%) |
| band_struct | 14 (58.3%) | 4 (16.7%) | 6 (25.0%) |
| band_schedule | 22 (91.7%) | 2 (8.3%) | 0 (0.0%) |
PLAN_VALIDITY: easy/hard → 6 (25.0%) | 18 (75.0%)
### TIME_WINDOW (24 cells)
| Loss | easy | medium | hard |
|---|---|---|---|
| band_obj | 24 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| band_struct | 14 (58.3%) | 4 (16.7%) | 6 (25.0%) |
| band_schedule | 24 (100.0%) | 0 (0.0%) | 0 (0.0%) |
PLAN_VALIDITY: easy/hard → 7 (29.2%) | 17 (70.8%)
### SERVICE_TIME (24 cells)
| Loss | easy | medium | hard |
|---|---|---|---|
| band_obj | 16 (66.7%) | 5 (20.8%) | 3 (12.5%) |
| band_struct | 10 (41.7%) | 7 (29.2%) | 7 (29.2%) |
| band_schedule | 20 (83.3%) | 4 (16.7%) | 0 (0.0%) |
PLAN_VALIDITY: easy/hard → 7 (29.2%) | 17 (70.8%)
### ORDER_CHANGE (24 cells)
| Loss | easy | medium | hard |
|---|---|---|---|
| band_obj | 18 (75.0%) | 5 (20.8%) | 1 (4.2%) |
| band_struct | 16 (66.7%) | 6 (25.0%) | 2 (8.3%) |
| band_schedule | 24 (100.0%) | 0 (0.0%) | 0 (0.0%) |
PLAN_VALIDITY: easy/hard → 0 (0.0%) | 24 (100.0%)
## Reference stability summary
- Reference objective-instability rate (3-seed `(max-min)/min > 0.02`): **0.000** (0/96 cells)
- Reference structural-instability rate (3-seed pairwise `ari_min < 0.90`): **0.156** (15/96 cells)
- Median reference `ari_min`: **1.000**
## PLAN_VALIDITY infeasibility breakdown
| infeasibility_kind | count | share |
|---|---|---|
| none | 20 | 20.8% |
| capacity | 0 | 0.0% |
| time_window | 52 | 54.2% |
| both | 0 | 0.0% |
| coverage | 24 | 25.0% |
## SCHEDULE summary
- Median `loss_schedule` (vs reference seed-1 schedule): **0.0000**
- Median `schedule_disruption` (vs baseline unperturbed schedule): **0.0000**
- Cells schedule-feasible (time_warp=0) but `band_schedule=hard`: **0/96** (0.0% — schedule shifts without TW violation)
## Interpretation
- **Non-trivial labels?** Hard rates: OBJ 0.05, STRUCT 0.22, SCHEDULE 0.00, PLAN_VALIDITY 0.79. The pilot produces a mix of easy/medium/hard cells if these are away from 0 and 1.
- **STRUCT stability under perturbations:** the structural reference is unstable on **16%** of cells. This is the equivalent of CVRP Stage A's `reference_struct_unstable` flag for the perturbed VRPTW instance.
- **Is SCHEDULE adding information beyond PLAN_VALIDITY?** If a non-trivial fraction of cells have `schedule_feasibility_loss=0` (no TW violation) but `band_schedule != easy` (the schedule still shifts materially), SCHEDULE is signaling something PLAN_VALIDITY misses: here, **0/96** cells fit that pattern.
## Caveats
- **Exploratory.** Not preregistered. Magnitudes are pilot-only and may be re-tuned before any larger benchmark.
- **n = 96 cells** (6 instances × 16 perturbations). Statistical conclusions are directional.
- **Solomon-100 only.** No Homberger / Gehring benchmarks.
- **No BKS / quality validation.** Objectives are in ×10 distance units.
- **`infeasibility_kind='coverage'`** is a small spec extension for ORDER_CHANGE cells where the existing routes are capacity- and TW-feasible but inserted customers are unserved by the baseline plan.

Parquet output: `data/probes/vrptw_perturbation_pilot.parquet`
