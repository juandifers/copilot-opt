# discovery_report.md — read-only audit for the LLM-in-the-loop closing experiment

Audit scope: `spec.md` at repo root. No code, data, or configs were modified.
Read date: 2026-05-18.

## 1. Spec summary

An end-to-end test of the methodology at the language layer. An operator's
natural-language question is classified into one of four claim families
(OBJ, PV, STRUCT, SCHEDULE); the locked Stage A sufficiency predictor for
that family decides whether the cheap action's output is good enough or
whether to escalate to `pyvrp_10s`; the chosen action runs; a frontier LLM
generates a grounded natural-language answer from the action output; and a
three-axis scorer (faithfulness, sufficiency, operational validity) grades
each answer. 48 prompts (12/family) span a 2×2 stratification on
sufficiency × policy-decision, mixing synthetic templates with
LLM-generated variants and including a 12-prompt Homberger cross-scale
slice. Scoring is LLM-as-judge calibrated on a 20-prompt human pilot, with
25% human verification. Success requires ≥ 3 of 4 pre-registered claims
(axis separability, policy effect, sufficiency manifestation, cross-scale
stability) to hold.

## 2. Existing artifacts

### Stage A cell-level results

- **Cell-level (one row per (instance, perturbation, action)):**
  - exists: yes
  - path: `data/stage_a_vrptw_consolidated.parquet` (preferred; carries
    the 120s-reference recollection patch) and unconsolidated sibling
    `data/stage_a_vrptw.parquet`
  - rows: 3808 (consolidated) / 3808 (unconsolidated); 94 / 91 cols
  - bytes: 468,757 / 465,492
  - exact column names (consolidated, 94):
    `instance_id`, `perturbation_id`, `perturbation_family`,
    `perturbation_magnitude`, `action`, `action_tier`,
    `action_tier_index`, `is_middle_action`, `is_reference_action`,
    `cheap_action_for_cell`, `is_cheap_action`, `n_affected_customers`,
    `affected_demand_share`, `affected_route_share`,
    `n_inserted_customers`, `affected_customers`,
    `affected_baseline_routes`, `baseline_obj`,
    `baseline_generalized_cost`, `baseline_n_routes`,
    `reference_obj_s1`, `reference_obj_s2`, `reference_obj_s3`,
    `reference_obj_best_feasible`, `reference_s1_feasible`,
    `reference_s2_feasible`, `reference_s3_feasible`,
    `reference_any_feasible`, `reference_all_feasible`,
    `reference_n_routes_s1`, `reference_n_routes_s2`,
    `reference_n_routes_s3`, `reference_ari_s1s2`, `reference_ari_s1s3`,
    `reference_ari_s2s3`, `reference_ari_min`, `reference_obj_unstable`,
    `reference_struct_unstable`, `reference_failure_kind`, `action_obj`,
    `action_generalized_cost`, `action_feasible`,
    `action_feasible_capacity_only`, `action_feasible_tw_only`,
    `coverage_feasible`, `n_unserved_customers`,
    `action_total_time_warp`, `action_total_wait`,
    `action_total_duration`, `action_n_late_customers`,
    `action_max_lateness`, `infeasibility_kind`, `loss_obj_distance`,
    `band_obj_distance`, `loss_obj_generalized`, `band_obj_generalized`,
    `loss_plan_validity`, `band_plan_validity`, `loss_struct`,
    `band_struct`, `loss_schedule`, `band_schedule`,
    `loss_schedule_global_median`, `loss_schedule_affected_median`,
    `loss_schedule_affected_p90`, `loss_schedule_affected_max`,
    `schedule_eval_n_customers`, `schedule_disruption_route_end_max`,
    `local_repair_inserted_all`, `local_repair_total_insertions`,
    `local_repair_opened_new_route`,
    `local_repair_objective_delta_vs_reuse`, `runtime_baseline_s`,
    `runtime_reference_s`, `runtime_action_s`, `action_runtime_s`,
    `action_solver_time_limit`, `action_seed`, `action_valid`,
    `pyvrp_version`, `baseline_total_wait`, `baseline_min_route_slack`,
    `baseline_mean_route_slack`, `baseline_n_tight_customers`,
    `affected_service_time_share`, `affected_min_slack`,
    `affected_mean_slack`, `affected_total_wait`,
    `action_obj_delta_pct`, `action_generalized_delta_pct`,
    `action_time_warp`, `reference_recollected`,
    `reference_ari_min_60s`, `reference_time_limit_s`

- **Long table (one row per (instance, perturbation, action, claim_family)) — this is the file with `sufficient_binary`:**
  - exists: yes
  - path: `data/stage_a_vrptw_consolidated_claim_rows.parquet` (also
    `data/stage_a_vrptw_claim_rows.parquet`)
  - rows: 15,232 (3808 × 4 families); 44 cols; bytes 250,278
  - exact column names:
    `instance_id`, `perturbation_id`, `perturbation_family`, `action`,
    `action_tier`, `action_tier_index`, `is_middle_action`,
    `is_reference_action`, `action_runtime_s`, `action_solver_time_limit`,
    `action_seed`, `action_valid`, `cheap_action_for_cell`,
    `is_cheap_action`, `claim_family`, `loss`, `band`,
    `sufficient_binary`, `reference_valid`, `reference_struct_unstable`,
    `reference_obj_unstable`, `action_feasible`, `infeasibility_kind`,
    `baseline_n_routes`, `baseline_obj`, `baseline_generalized_cost`,
    `baseline_total_wait`, `baseline_min_route_slack`,
    `baseline_mean_route_slack`, `baseline_n_tight_customers`,
    `n_affected_customers`, `affected_route_share`,
    `affected_demand_share`, `affected_service_time_share`,
    `affected_min_slack`, `affected_mean_slack`, `affected_total_wait`,
    `action_obj_delta_pct`, `action_generalized_delta_pct`,
    `action_time_warp`, `action_total_wait`, `action_total_duration`,
    `action_n_late_customers`, `action_max_lateness`

- **Per-action raw checkpoint rows (one JSON per (instance, perturbation, action)):**
  - exists: yes
  - dir: `data/stage_a_vrptw_checkpoints/rows/` (each row a complete
    superset of the parquet columns above)
  - top-level JSON keys: same 89 keys for every action (`action`,
    `action_feasible`, `action_feasible_capacity_only`,
    `action_feasible_tw_only`, `action_generalized_cost`,
    `action_generalized_delta_pct`, `action_max_lateness`,
    `action_n_late_customers`, `action_obj`, `action_obj_delta_pct`,
    `action_runtime_s`, `action_seed`, `action_solver_time_limit`,
    `action_tier`, `action_tier_index`, `action_time_warp`,
    `action_total_duration`, `action_total_time_warp`,
    `action_total_wait`, `action_valid`, `affected_baseline_routes`,
    `affected_customers`, `affected_demand_share`,
    `affected_mean_slack`, `affected_min_slack`, `affected_route_share`,
    `affected_service_time_share`, `affected_total_wait`,
    `band_obj_distance`, `band_obj_generalized`, `band_plan_validity`,
    `band_schedule`, `band_struct`, `baseline_generalized_cost`,
    `baseline_mean_route_slack`, `baseline_min_route_slack`,
    `baseline_n_routes`, `baseline_n_tight_customers`, `baseline_obj`,
    `baseline_total_wait`, `cheap_action_for_cell`, `coverage_feasible`,
    `infeasibility_kind`, `instance_id`, `is_cheap_action`,
    `is_middle_action`, `is_reference_action`,
    `local_repair_inserted_all`,
    `local_repair_objective_delta_vs_reuse`,
    `local_repair_opened_new_route`, `local_repair_total_insertions`,
    `loss_obj_distance`, `loss_obj_generalized`, `loss_plan_validity`,
    `loss_schedule`, `loss_schedule_affected_max`,
    `loss_schedule_affected_median`, `loss_schedule_affected_p90`,
    `loss_schedule_global_median`, `loss_struct`,
    `n_affected_customers`, `n_inserted_customers`,
    `n_unserved_customers`, `perturbation_family`, `perturbation_id`,
    `perturbation_magnitude`, `pyvrp_version`, `reference_all_feasible`,
    `reference_any_feasible`, `reference_ari_min`, `reference_ari_s1s2`,
    `reference_ari_s1s3`, `reference_ari_s2s3`, `reference_failure_kind`,
    `reference_n_routes_s1`, `reference_n_routes_s2`,
    `reference_n_routes_s3`, `reference_obj_best_feasible`,
    `reference_obj_s1`, `reference_obj_s2`, `reference_obj_s3`,
    `reference_obj_unstable`, `reference_s1_feasible`,
    `reference_s2_feasible`, `reference_s3_feasible`,
    `reference_struct_unstable`, `runtime_action_s`,
    `runtime_baseline_s`, `runtime_reference_s`,
    `schedule_disruption_route_end_max`, `schedule_eval_n_customers`)

- **Per-cell deep solver dump (richer route/schedule structure than the parquet):**
  - exists: yes
  - dir: `data/stage_a_vrptw_checkpoints/pyvrp10s/` (one JSON per
    (instance, perturbation)) — top-level keys: `objective`, `feasible`,
    `routes`, `assignment`, `route_costs`, `runtime_seconds`,
    `pyvrp_version`, `n_routes`, `total_duration`, `route_summaries`
    (list of per-route dicts with `route_idx`, `n_customers`,
    `start_time`, `end_time`, `distance`, `duration`, `wait_duration`,
    `service_duration`, `travel_duration`, `time_warp`, `slack`,
    `is_feasible`, `has_time_warp`, `has_excess_load`,
    `min_slack_to_tw_late`, `mean_slack_to_tw_late`,
    `n_late_customers`), `per_customer_schedule` (dict id→
    `customer_id`, `route_idx`, `arrival`, `start_service`,
    `end_service`, `wait_duration`, `service_duration`, `time_warp`,
    `tw_early`, `tw_late`, `slack_to_tw_late`).
  - parallel dir `data/stage_a_vrptw_checkpoints/refs/` holds 60s seeds
    1/2/3 in the same shape (`*__seedN.json`).

- **Predictor OOF predictions (the per-cell `pred_proba` for every (model, feature_set, claim_family) combo):**
  - exists: yes
  - path: `reports/predictor_models/predictor_oof_predictions.csv`
  - rows: 60,571; 13 cols
  - exact column names: `instance_id`, `perturbation_id`,
    `perturbation_family`, `claim_family`, `instance_class`, `action`,
    `fold`, `sufficient_binary`, `action_feasible`, `action_runtime_s`,
    `model`, `feature_set`, `pred_proba`

### Homberger OOD slice (equivalent of Stage A on Homberger-200)

- **Cell-level:**
  - exists: yes
  - paths: `data/homberger_probe_cells_merged.parquet` (use this; merges
    the 120s baseline with 180s fallback for 28 unstable cells),
    `data/homberger_probe_cells.parquet` (120s only),
    `data/homberger_probe_cells_180s.parquet` (180s subset)
  - rows: 340 / 340 / 238; 92 / 91 / 91 cols
  - bytes: 105,420 / 104,430 / 92,043
  - exact column names (merged, 92): same 91 columns as
    `stage_a_vrptw.parquet` above, plus one extra:
    `reference_time_limit_s`

- **Long table with `sufficient_binary`:**
  - exists: yes
  - path: `data/homberger_probe_claim_rows_merged.parquet` (also
    `…_claim_rows.parquet` and `…_claim_rows_180s.parquet`)
  - rows: 1,360 / 1,360 / 952; 45 / 44 / 44 cols
  - exact column names (merged, 45): same 44 as Stage A claim rows
    above, plus `reference_time_limit_s`

- **Homberger predictor zero-shot OOF predictions:**
  - exists: yes
  - path: `reports/homberger_probe/homberger_probe_predictor_oof.csv`
  - rows: 1,208; 13 cols
  - exact column names: `instance_id`, `perturbation_id`,
    `perturbation_family`, `claim_family`, `instance_class`, `action`,
    `sufficient_binary`, `action_feasible`, `action_runtime_s`, `fold`,
    `model`, `feature_set`, `pred_proba`

- **Homberger predictor eval summary:**
  - exists: yes
  - path: `reports/homberger_probe/homberger_probe_predictor_eval.csv`
  - rows: 16; columns: `model`, `feature_set`, `claim_family`, `n_rows`,
    `pos_rate`, `auroc_homberger`, `auprc_homberger`, `brier_homberger`

### `deployment_config.csv`

- exists: yes
- path: `reports/predictor_models/deployment_config.csv`; 16 rows × 12 cols
- columns: `claim_family`, `correctness_floor`, `model`, `feature_set`,
  `chosen_threshold`, `final_correctness`, `average_compute_cost_s`,
  `accepted_coverage`, `accepted_precision`, `false_accept_rate`,
  `floor_met`, `note`
- spec's per-family thresholds match the `correctness_floor=0.90`
  rows tagged `note=deployment_active`:
  - OBJ → `hist_gradient_boosting / C_clean / threshold 0.50`
  - PLAN_VALIDITY → `hist_gradient_boosting / B_pre_cheap / threshold 0.50`
    (spec wording is "PV"; the CSV uses the longer label
    `PLAN_VALIDITY`)
  - STRUCT → `hist_gradient_boosting / C_clean / threshold 0.95`
  - SCHEDULE → `hist_gradient_boosting / C_clean / threshold 0.98`

### Locked predictor weights / serialized models per family

- exists: **no**
- No `.pkl` / `.joblib` / `.onnx` / `.pt` artifacts exist outside the
  Python venvs. The only persisted predictor outputs are the OOF
  probability CSVs (`predictor_oof_predictions.csv`,
  `homberger_probe_predictor_oof.csv`) and the four decision-tree text
  exports at `reports/predictor_models/predictor_tree_exports/`
  (`B_pre_cheap__OBJ.txt`, `…__PLAN_VALIDITY.txt`,
  `…__SCHEDULE.txt`, `…__STRUCT.txt`,
  `C_clean__{OBJ,PLAN_VALIDITY,SCHEDULE,STRUCT}.txt`).
- The training code is at
  `src/vrp_copilot_bench/predictor_models/training.py` /
  `…/models.py` / `…/features.py`. Fits are produced on demand from
  `stage_a_vrptw_consolidated_claim_rows.parquet` against the fold map
  at `reports/predictor_baselines/fold_assignments.csv`.

### Prior prompt set, scoring rubric, LLM-experiment scaffolding

- exists: **no**
- The pre-registration document
  `prereg/PREREG_v1.2_vrptw.md §14.3` describes a 40-prompt closing
  experiment and references `closing/faithfulness_rubric_vrptw.md`,
  but that file does not exist in the repo and there is no
  `closing/` directory.
- No code, prompt templates, judge configs, or rubric files reference
  "faithfulness", "operator_prompt", "three_axis", "llm_judge",
  or "rubric" anywhere under `src/`, `scripts/`, `tests/`, `docs/`,
  or `prereg/data/`.

### Action solver outputs (fields each action emits per cell)

- exists: yes (under
  `data/stage_a_vrptw_checkpoints/rows/<instance>__<perturbation>__<action>.json`
  and `data/homberger_probe_checkpoints/rows/…`). Schemas in §5.

## 3. Cell-count audit

**Important methodology note before reading the tables.** The repo does
not contain a utility that, given a cell, returns the policy decision
defined in `deployment_config.csv`. I therefore implemented the lookup
inline for the audit only (read-only): for each `(instance, perturbation,
claim_family)` I (1) filtered the long-table to the cheap action via
`is_cheap_action == True`; (2) joined the OOF predictions filtered to
the deployment `(model, feature_set, claim_family)` combo on
`(instance_id, perturbation_id, action)`; (3) labelled
`accept = pred_proba >= deployment_threshold[claim_family]`. Cells with
NaN `sufficient_binary` or NaN `pred_proba` are dropped from the
cross-tab and reported under `missing_rows`. **This logic is not
implemented as a reusable utility yet — flagged in §6.**

Thresholds applied (from `deployment_config.csv`, rows
`correctness_floor=0.90` & `note=deployment_active`):
OBJ=0.50 (HistGB/C_clean), PLAN_VALIDITY=0.50 (HistGB/B_pre_cheap),
STRUCT=0.95 (HistGB/C_clean), SCHEDULE=0.98 (HistGB/C_clean).

**Stage A (Solomon-100; 56 instances × 16 perturbations × 4 families)**

| family   | suff × accept | suff × escalate | insuff × accept | insuff × escalate | dropped (missing) |
| -------- | ------------- | ---------------- | ---------------- | ----------------- | ----------------- |
| OBJ      | 796           | 17               | 18               | 58                | 7                 |
| PV       | 326           | 78               | 81               | 411               | 0                 |
| STRUCT   | 198           | 299              | 12               | 380               | 7                 |
| SCHEDULE | 45            | 324              | 4                | 516               | 7                 |

Cell totals after dropping NaNs: OBJ 889, PV 896, STRUCT 889, SCHEDULE 889
(total cells per family before drop = 896).

Cells with fewer than 3 entries: **none** in Stage A.

**Homberger (10 instances × 8 perturbations × 4 families)**

| family   | suff × accept | suff × escalate | insuff × accept | insuff × escalate | dropped (missing) |
| -------- | ------------- | ---------------- | ---------------- | ----------------- | ----------------- |
| OBJ      | 57            | 3                | 3                | 11                | 6                 |
| PV       | 11            | 13               | 8                | 48                | 0                 |
| STRUCT   | 3             | 26               | 2                | 43                | 6                 |
| SCHEDULE | 0             | 45               | 0                | 29                | 6                 |

Cell totals after dropping NaNs: OBJ 74, PV 80, STRUCT 74, SCHEDULE 74.

**Cells flagged with fewer than 3 entries in Homberger:**

- SCHEDULE × `suff × accept` = 0 (the predictor at threshold 0.98 never
  accepts a Homberger SCHEDULE cell that the label says is sufficient)
- SCHEDULE × `insuff × accept` = 0 (predictor never accepts on
  insufficient SCHEDULE cells either — at t=0.98 it never accepts)
- STRUCT × `insuff × accept` = 2
- OBJ × `suff × escalate` = 3 (borderline — exactly 3)
- OBJ × `insuff × accept` = 3 (borderline — exactly 3)

## 4. Reusable utilities

Importable from `vrp_copilot_bench` (package installed at
`src/vrp_copilot_bench/`).

### Running an action on a cell

The action layer is at `src/vrp_copilot_bench/vrptw/actions.py`. Every
action implements the `VRPTWAction` protocol with `name: str` and
`apply(perturbed, baseline_routes) -> ActionResult`. Concrete classes:

```python
from vrp_copilot_bench.vrptw.actions import (
    ReuseDirect,           # tier 0 — score baseline routes as-is
    LocalRepairInsert,     # tier 1 — greedy cheapest-feasible insertion (OC only)
    ConstructFeasible,     # tier 2 — deterministic build-from-scratch heuristic
    PyvrpSolve,            # tier 3 — pyvrp_10s (seed=1, time_limit_seconds=10.0)
    materialize_reference_action,   # tier 4 — build pyvrp_60s_reference from a precomputed ref
    ActionResult,          # dataclass: name, routes, evaluation, runtime_seconds, …
    CHEAP_ACTION_FOR_FAMILY,        # {TRAVEL_TIME→reuse_direct, TIME_WINDOW→reuse_direct,
                                    #  SERVICE_TIME→reuse_direct, ORDER_CHANGE→local_repair_insert}
    cheap_action_for_family,        # (family: str) -> str
    actions_for_family,             # (family: str, *, expanded: bool) -> tuple[str, ...]
    ACTION_TIER,                    # {name: (tier_idx, tier_label, is_middle, is_reference)}
)
```

`ActionResult` exposes `evaluation: EvaluatedVRPTW`, `routes`,
`runtime_seconds`, `local_repair: LocalRepairResult | None`,
`solver_seed`, `solver_time_limit_seconds`.

The "evaluate a route plan without solving" entry point:
`vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper.evaluate_vrptw_solution(instance, fixed_routes) -> EvaluatedVRPTW`
(re-exported from `vrp_copilot_bench.vrptw.solver`).

The "solve from scratch" entry point:
`vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper.solve_vrptw(instance, SolveConfig(time_limit_seconds=..., seed=...)) -> VRPTWSolveResult`.

### Evaluating sufficiency from an action output

`src/vrp_copilot_bench/vrptw/losses.py`:

```python
from vrp_copilot_bench.vrptw.losses import (
    compute_losses,        # (instance, perturbed, action_eval: EvaluatedVRPTW,
                           #  ref_s1: VRPTWSolveResult) -> LossBundle
    LossBundle,
    OBJ_EASY, OBJ_MEDIUM,
    STRUCT_EASY, STRUCT_MEDIUM,
    SCHEDULE_EASY, SCHEDULE_MEDIUM,
)
```

`LossBundle` carries `loss_obj_distance`/`band_obj_distance`,
`loss_plan_validity`/`band_plan_validity`, `loss_struct`/`band_struct`,
`loss_schedule`/`band_schedule` (= affected-p90), plus the schedule
diagnostics. `band == "easy"` is the canonical "sufficient" gate per
family (see Stage A claim_rows for `sufficient_binary`).

Supporting primitives in `src/vrp_copilot_bench/vrptw/evaluation.py`:
`ari_on_common`, `infeasibility_kind`, `reference_stability`,
`schedule_shifts`, `route_end_disruption_max`, `generalized_cost`,
`depot_horizon_scaled`.

### Applying the locked predictor for a family

There is **no** "score one new cell with the deployment predictor"
function. What exists:

```python
from vrp_copilot_bench.predictor_models.training import (
    train_oof,             # fits HistGB / LR / DT OOF and returns probs
    train_all,
    attach_folds,
    oof_to_long_frame,
)
from vrp_copilot_bench.predictor_models.features import (
    FEATURE_SETS, PER_FAMILY_FEATURE_SETS, build_feature_matrix,
)
from vrp_copilot_bench.predictor_models.models import (
    MODEL_NAMES, make_model, expanded_feature_names,
    extract_coefficients_or_importance,
)
```

`train_oof` fits a pipeline per fold from
`stage_a_vrptw_consolidated_claim_rows.parquet` and returns OOF
predictions; it does not persist the trained estimator. To score a new
prompt's cell against the deployment predictor today, you must (a) fit
on the full Stage A frame and predict on the new row, or (b) join the
new row onto the precomputed OOF / Homberger OOF CSVs if it is already
in those tables.

`reports/predictor_models/predictor_oof_predictions.csv` and
`reports/homberger_probe/homberger_probe_predictor_oof.csv` are the
materialized `pred_proba` arrays. Use them as a lookup table.

### Computing operational-validity checks

No dedicated "operational validity" utility exists. Each axis is
computable from `EvaluatedVRPTW` fields and the action's
`ActionResult`:

- **OBJ** tolerance (within 0.5%):
  `abs(answer_obj − action_eval.objective) / action_eval.objective ≤ 0.005`.
  `action_eval.objective` is `EvaluatedVRPTW.objective` (= total distance
  with `unit_duration_cost=0`).
- **PV** feasibility match: `EvaluatedVRPTW.feasible` (and the
  capacity/TW/coverage breakdowns from
  `evaluation.infeasibility_kind`).
- **STRUCT** route count: `len(EvaluatedVRPTW.routes)` (or
  `VRPTWSolveResult.n_routes` for solver outputs). Assignment claims
  resolved against `EvaluatedVRPTW.assignment: dict[int, int]`.
- **SCHEDULE** timing (1-minute tolerance): per-customer
  `EvaluatedVRPTW.per_customer_schedule[customer_id].start_service`
  and `RouteSummary.end_time` for route-end claims. Note that
  solver-emitted times are in the scaled unit system (×
  `SCALING_FACTOR = 10`); divide by 10 to get Solomon-native minutes
  before comparing to a "1 minute" tolerance.

The repo also has policy-level utilities in
`src/vrp_copilot_bench/predictor_baselines/{policies.py,metrics.py,data.py,runner.py}`:
`build_cheap_eval_frame`, `build_escalation_frame`,
`compute_policy_metrics`, `block_rule_predictions`,
`feasibility_only_predictions`, `oracle_predictions`. These operate on
the long table; none of them apply the per-family
`deployment_config.csv` threshold automatically.

## 5. Action output schemas

Per the spec the action types are `reuse_direct, nearest_neighbor,
clarke_wright, pyvrp_10s, pyvrp_60s`. **In the VRPTW pipeline the spec
targets, the actually-implemented action set is**
`reuse_direct, local_repair_insert, construct_feasible, pyvrp_10s,
pyvrp_60s_reference` (see `vrp_copilot_bench.vrptw.actions.ACTION_TIER`).
The name mismatch is flagged in §6.

All five VRPTW actions return an identical Python `ActionResult` shape;
the persisted JSON row carries the same 89 keys regardless of action
(listed in §2 under "Per-action raw checkpoint rows"). What differs is
which fields are populated.

### Common in-memory shape (`ActionResult` from `actions.py`)

```
name: str
routes: list[list[int]]
evaluation: EvaluatedVRPTW
runtime_seconds: float
local_repair: LocalRepairResult | None
solver_seed: int | None
solver_time_limit_seconds: float | None
```

`EvaluatedVRPTW` fields:
`objective, feasible, feasible_capacity_only, feasible_tw_only,
is_complete, has_time_warp, total_time_warp, total_duration,
total_wait, total_distance, n_late_customers, max_lateness, routes,
assignment, route_summaries, per_customer_schedule,
unserved_customers`.

`RouteSummary` fields:
`route_idx, n_customers, start_time, end_time, distance, duration,
wait_duration, service_duration, travel_duration, time_warp, slack,
is_feasible, has_time_warp, has_excess_load, min_slack_to_tw_late,
mean_slack_to_tw_late, n_late_customers`.

`VisitSchedule` fields (per customer):
`customer_id, route_idx, arrival, start_service, end_service,
wait_duration, service_duration, time_warp, tw_early, tw_late,
slack_to_tw_late`.

### Per-action emissions (fields each action populates / specializes)

- **`reuse_direct`** — scores the baseline routes under the perturbed
  instance. Populates the full `evaluation`; `local_repair`, `solver_seed`,
  `solver_time_limit_seconds` are `None`. On ORDER_CHANGE cells
  `evaluation.is_complete=False`, `coverage_feasible=False`, and the new
  customers appear in `evaluation.unserved_customers`.
- **`local_repair_insert`** — populates the same `evaluation` plus
  `local_repair: LocalRepairResult` (from
  `vrp_copilot_bench.vrptw_perturbations.repair`). The persisted row
  fields `local_repair_inserted_all` (bool),
  `local_repair_total_insertions` (int),
  `local_repair_opened_new_route` (bool),
  `local_repair_objective_delta_vs_reuse` (float) are non-null only on
  this action. `solver_seed` / `solver_time_limit_seconds` are `None`.
- **`construct_feasible`** — deterministic build-from-scratch
  heuristic. Same `evaluation` shape. `local_repair=None`,
  `solver_seed=None`, `solver_time_limit_seconds=None`. The row field
  `action_tier_index=2` and `is_middle_action=True`.
- **`pyvrp_10s`** — runs PyVRP with `seed=1`, `time_limit_seconds=10.0`.
  Populates `evaluation` plus `solver_seed=1` and
  `solver_time_limit_seconds=10.0`. The deeper per-cell solver dump at
  `data/stage_a_vrptw_checkpoints/pyvrp10s/<cell>.json` carries:
  `objective, feasible, routes, assignment, route_costs,
  runtime_seconds, pyvrp_version, n_routes, total_duration,
  route_summaries (list), per_customer_schedule (dict)`.
- **`pyvrp_60s_reference`** — materialized from a precomputed
  reference-seed-1 solve via `materialize_reference_action`. Same
  `evaluation` shape, `solver_seed=1`, `solver_time_limit_seconds=60.0`
  (or whatever the reference budget was; some Homberger cells used
  120s / 180s — see `reference_time_limit_s` in the merged parquet).
  `is_reference_action=True` in the persisted row.

## 6. Gaps

1. **No per-family policy-decision utility.** Nothing in `src/` reads
   `deployment_config.csv` and emits an `accept_cheap | escalate` label
   for a given cell. `predictor_baselines/runner.py` has policy-level
   helpers (`block_rule_predictions`, `feasibility_only_predictions`,
   `oracle_predictions`) and `compute_policy_metrics`, but they don't
   apply per-family thresholds from `deployment_config.csv`. I had to
   reimplement the decision rule inline to produce §3.
2. **No serialized predictor models per family.** No `.pkl` /
   `.joblib` / `.onnx` artifacts exist for the locked HistGB
   predictors. The only persisted outputs are the OOF prediction CSVs
   (`predictor_oof_predictions.csv`,
   `homberger_probe_predictor_oof.csv`) and the decision-tree text
   exports. To score a new prompt's cell with the deployment predictor
   requires re-fitting (`train_oof`) on the full Stage A frame or
   joining onto the OOF CSV by cell key — fine for the 48-prompt
   experiment whose cells must come from existing Stage A / Homberger
   data, but flagged so the next prompt knows the limitation.
3. **No "score the deployment predictor on one new row" function.**
   `train_oof` produces OOF predictions per (model, feature_set,
   claim_family) but doesn't expose a `predict_one(row, family,
   deploy_config) -> proba` shortcut.
4. **No prompt set, scoring rubric, or LLM-experiment scaffolding.**
   The pre-registration (`prereg/PREREG_v1.2_vrptw.md §14.3`) refers to
   `closing/faithfulness_rubric_vrptw.md`, but no `closing/`
   directory exists, and no prompt templates, judge configs, three-axis
   scorers, classifier prompts, or answer-generator templates exist
   anywhere in `src/`, `scripts/`, or `docs/`. The closing experiment
   has to be built from scratch.
5. **Action-name mismatch with the spec.** Spec §"Action output schemas"
   lists `reuse_direct, nearest_neighbor, clarke_wright, pyvrp_10s,
   pyvrp_60s`. The CVRP-only Stage A (`data/stage_a.parquet`) does have
   `nearest_neighbor` and `clarke_wright` actions; the VRPTW Stage A,
   which is the only place the four claim families OBJ/PV/STRUCT/SCHEDULE
   are scored, uses `local_repair_insert` and `construct_feasible`
   instead (and `pyvrp_60s_reference` rather than `pyvrp_60s`). The
   spec's "PV" maps to the long-table label `PLAN_VALIDITY`.
6. **No operational-validity utility.** Op-validity checks for each
   family (OBJ within 0.5%, PV feasibility flag match, STRUCT route-count
   exact match, SCHEDULE within-1-min) must be implemented from
   `EvaluatedVRPTW` / `VRPTWSolveResult` fields. The unit-system
   gotcha (`SCALING_FACTOR=10`; PyVRP times are scaled, Solomon
   minutes are not) is documented in
   `solvers/pyvrp_vrptw_wrapper.py` but no helper hides it.
7. **No claim-family classifier scaffolding.** No frontier-LLM client
   wrappers, no structured-output schemas, no few-shot exemplar bank,
   no validation set of 20 hand-labelled prompts exists.
8. **Homberger SCHEDULE has zero `accept` cells at the deployment
   threshold.** At the locked SCHEDULE threshold of 0.98 the
   Homberger predictor accepts no cells (0 in `suff × accept`, 0 in
   `insuff × accept`; see §3). This is a data-availability gap for
   any 2×2 stratified prompt sampling on the Homberger slice for the
   SCHEDULE family.
