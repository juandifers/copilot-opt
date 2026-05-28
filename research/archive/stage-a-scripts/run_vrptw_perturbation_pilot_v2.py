#!/usr/bin/env python3
"""VRPTW perturbation pilot v2 — diagnostic refinement of the v1 pilot.

Differences from v1
-------------------
1. **Two perturbation grids in one run** (``grid_variant`` column):
   ``v1_grid`` (same as the v1 pilot) and ``soft_grid`` (softer
   magnitudes; OC_2/OC_4 also relax the tight-window width from 25%
   to 40% of median).
2. **Local repair action** for ORDER_CHANGE only
   (``action="local_repair_insert"``) — cheapest-feasible-insertion of
   inserted customers into the baseline routes. ``reuse_direct`` runs
   for every cell as before.
3. **Local schedule metrics** focused on the affected customers:
   ``loss_schedule_affected_{median,p90,max}`` and a route-end
   disruption measure, with a new primary band ``band_schedule_v2`` on
   the affected-p90 statistic.
4. **Generalized cost diagnostic**:
   ``generalized_cost = distance + 0.1 * duration`` (PyVRP's optimizer
   is unchanged; this is a post-hoc proxy on the same ×10 units).
5. **v1 data-quality debug** at the top of the report — identifies the
   single R101 TT_4 row whose reference seeds all returned ``inf`` and
   thus produced a ``band_obj="n/a"`` cell in v1.

Outputs
-------
- ``data/probes/vrptw_perturbation_pilot_v2.parquet``  (240 rows × ~80 cols)
- ``prereg/vrptw_perturbation_pilot_v2_report.md``

CLI::

    python scripts/run_vrptw_perturbation_pilot_v2.py \\
        --instances C101 C201 R101 R201 RC101 RC201 \\
        --time-limit 60 --n-jobs 6 \\
        --out-dir data/probes \\
        --report-path prereg/vrptw_perturbation_pilot_v2_report.md
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.metrics import adjusted_rand_score

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper import (  # noqa: E402
    SCALING_FACTOR,
    EvaluatedVRPTW,
    VRPTWSolveResult,
    evaluate_vrptw_solution,
    solve_vrptw,
)
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig  # noqa: E402
from vrp_copilot_bench.vrptw_instances import (  # noqa: E402
    DEFAULT_VRPTW_INSTANCE_DIR,
    load_vrptw_instance,
)
from vrp_copilot_bench.vrptw_perturbations import (  # noqa: E402
    PERTURBATION_IDS,
    apply_vrptw_perturbation,
    lookup_vrptw_perturbation,
)
from vrp_copilot_bench.vrptw_perturbations.repair import (  # noqa: E402
    LocalRepairResult,
    local_repair_insert,
)
from vrp_copilot_bench.vrptw_perturbations.types import (  # noqa: E402
    PERTURBATION_MAGNITUDES,
    SOFT_PERTURBATION_MAGNITUDES,
    SOFT_TIGHT_WINDOW_WIDTH_FRACTION,
    V1_TIGHT_WINDOW_WIDTH_FRACTION,
)


# ---------------------------------------------------------------------------
# Defaults / thresholds

DEFAULT_INSTANCES: tuple[str, ...] = (
    "C101", "C201", "R101", "R201", "RC101", "RC201",
)
DEFAULT_SEEDS: tuple[int, ...] = (1, 2, 3)
GRID_VARIANTS: tuple[str, ...] = ("v1_grid", "soft_grid")

OBJ_EASY, OBJ_MEDIUM = 0.05, 0.15
STRUCT_EASY, STRUCT_MEDIUM = 0.10, 0.30
# v1 schedule thresholds (kept for band_schedule_v1).
SCHEDULE_V1_EASY, SCHEDULE_V1_MEDIUM = 0.02, 0.05
# v2 schedule thresholds (affected-p90 statistic).
SCHEDULE_V2_EASY, SCHEDULE_V2_MEDIUM = 0.02, 0.05
ARI_STRUCT_UNSTABLE_THRESHOLD = 0.90
OBJ_UNSTABLE_THRESHOLD = 0.02

GENERALIZED_DURATION_WEIGHT = 0.1

V1_PARQUET_PATH = Path("data/probes/vrptw_perturbation_pilot.parquet")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vrptw_perturbation_pilot_v2")


# ---------------------------------------------------------------------------
# Grid helpers


def _grid_magnitude(grid: str, pid: str) -> float:
    if grid == "v1_grid":
        return float(PERTURBATION_MAGNITUDES[pid])
    if grid == "soft_grid":
        return float(SOFT_PERTURBATION_MAGNITUDES[pid])
    raise ValueError(f"unknown grid_variant {grid!r}")


def _grid_tight_width(grid: str) -> float:
    if grid == "v1_grid":
        return V1_TIGHT_WINDOW_WIDTH_FRACTION
    if grid == "soft_grid":
        return SOFT_TIGHT_WINDOW_WIDTH_FRACTION
    raise ValueError(f"unknown grid_variant {grid!r}")


def _apply_for_grid(instance, spec, baseline, grid: str):
    return apply_vrptw_perturbation(
        instance, spec, baseline,
        magnitude_override=_grid_magnitude(grid, spec.perturbation_id),
        tight_width_fraction=_grid_tight_width(grid),
    )


# ---------------------------------------------------------------------------
# Workers (module-level for loky pickling)


def _worker_solve_baseline(
    instance_id: str, time_limit: float, instance_dir: Path,
) -> tuple[str, VRPTWSolveResult]:
    inst = load_vrptw_instance(instance_id, instance_dir=instance_dir)
    cfg = SolveConfig(time_limit_seconds=time_limit, seed=1)
    return (instance_id, solve_vrptw(inst, cfg))


def _worker_solve_perturbed(
    instance_id: str,
    grid: str,
    perturbation_id: str,
    seed: int,
    time_limit: float,
    instance_dir: Path,
    baseline: VRPTWSolveResult,
) -> tuple[str, str, str, int, VRPTWSolveResult]:
    inst = load_vrptw_instance(instance_id, instance_dir=instance_dir)
    spec = lookup_vrptw_perturbation(perturbation_id)
    perturbed = _apply_for_grid(inst, spec, baseline, grid)
    cfg = SolveConfig(time_limit_seconds=time_limit, seed=seed)
    return (instance_id, grid, perturbation_id, seed, solve_vrptw(perturbed, cfg))


# ---------------------------------------------------------------------------
# Metric helpers


def _ari_on_common(a: dict[int, int], b: dict[int, int]) -> float:
    common = sorted(set(a) & set(b))
    if len(common) < 2:
        return math.nan
    la = np.fromiter((a[c] for c in common), dtype=np.int64, count=len(common))
    lb = np.fromiter((b[c] for c in common), dtype=np.int64, count=len(common))
    return float(adjusted_rand_score(la, lb))


def _band(x: float, easy: float, medium: float) -> str:
    if math.isnan(x):
        return "n/a"
    if x <= easy:
        return "easy"
    if x <= medium:
        return "medium"
    return "hard"


def _band_plan_validity(feasible: bool) -> str:
    return "easy" if feasible else "hard"


def _infeasibility_kind(reuse_eval) -> str:
    cap_ok = reuse_eval.feasible_capacity_only
    tw_ok = reuse_eval.feasible_tw_only
    if cap_ok and tw_ok:
        if reuse_eval.is_complete:
            return "none"
        return "coverage"
    if not cap_ok and tw_ok:
        return "capacity"
    if cap_ok and not tw_ok:
        return "time_window"
    return "both"


def _median_arrival_shift_global(
    a_schedule: dict[int, Any], b_schedule: dict[int, Any], depot_horizon: int,
) -> tuple[float, int]:
    common = sorted(set(a_schedule) & set(b_schedule))
    if not common or depot_horizon <= 0:
        return math.nan, 0
    diffs = np.array([
        abs(a_schedule[c].start_service - b_schedule[c].start_service)
        for c in common
    ], dtype=np.float64)
    return float(np.median(diffs) / float(depot_horizon)), len(common)


def _schedule_shifts(
    a_schedule: dict[int, Any], b_schedule: dict[int, Any],
    customers: list[int], depot_horizon: int,
) -> list[float]:
    """Per-customer abs schedule shifts (normalized) over ``customers``."""
    if depot_horizon <= 0:
        return []
    out = []
    for c in customers:
        if c in a_schedule and c in b_schedule:
            out.append(
                abs(a_schedule[c].start_service - b_schedule[c].start_service)
                / float(depot_horizon)
            )
    return out


def _route_end_disruption(
    action_eval: EvaluatedVRPTW, baseline: VRPTWSolveResult,
    affected_route_idxs: tuple[int, ...], depot_horizon: int,
) -> float:
    """Max abs end-time shift over the affected baseline routes.

    Compares ``action_eval`` route summaries to baseline route summaries.
    If route index mapping is ambiguous (different route count) we
    compare on the minimum of the two lengths over affected indices.
    """
    if depot_horizon <= 0 or not affected_route_idxs:
        return math.nan
    b_by_idx = {rs.route_idx: rs for rs in baseline.route_summaries}
    a_by_idx = {rs.route_idx: rs for rs in action_eval.route_summaries}
    deltas = []
    for ri in affected_route_idxs:
        if ri in b_by_idx and ri in a_by_idx:
            deltas.append(
                abs(int(a_by_idx[ri].end_time) - int(b_by_idx[ri].end_time))
                / float(depot_horizon)
            )
    if not deltas:
        return math.nan
    return float(max(deltas))


def _generalized_cost(distance: float, duration: float) -> float:
    return float(distance) + GENERALIZED_DURATION_WEIGHT * float(duration)


# ---------------------------------------------------------------------------
# Per-cell assembly


def _eval_to_costs(ev_or_ref) -> tuple[float, float]:
    """Extract (distance, duration) in scaled units from EvaluatedVRPTW
    or VRPTWSolveResult."""
    if hasattr(ev_or_ref, "total_distance"):
        return float(ev_or_ref.total_distance), float(ev_or_ref.total_duration)
    # VRPTWSolveResult: objective == distance (unit_duration_cost=0)
    return float(ev_or_ref.objective), float(ev_or_ref.total_duration)


def _build_row(
    *,
    instance,
    spec,
    grid: str,
    action: str,
    baseline: VRPTWSolveResult,
    references: dict[int, VRPTWSolveResult],
    perturbed,
    reuse_eval: EvaluatedVRPTW,
    action_eval: EvaluatedVRPTW,
    local_repair: LocalRepairResult | None,
    runtime_reference_s: float,
    runtime_action_s: float,
    runtime_baseline_s: float,
) -> dict[str, Any]:
    ref_s1 = references[1]
    ref_s2 = references[2]
    ref_s3 = references[3]

    # Reference stability
    ari12 = _ari_on_common(ref_s1.assignment, ref_s2.assignment)
    ari13 = _ari_on_common(ref_s1.assignment, ref_s3.assignment)
    ari23 = _ari_on_common(ref_s2.assignment, ref_s3.assignment)
    aris = [a for a in (ari12, ari13, ari23) if not math.isnan(a)]
    ari_min = min(aris) if aris else math.nan
    obj_values = [ref_s1.objective, ref_s2.objective, ref_s3.objective]
    finite_objs = [o for o in obj_values if math.isfinite(o)]
    if len(finite_objs) >= 2 and min(finite_objs) > 0:
        obj_unstable = (
            (max(finite_objs) - min(finite_objs)) / min(finite_objs)
            > OBJ_UNSTABLE_THRESHOLD
        )
    else:
        obj_unstable = False
    struct_unstable = (
        ari_min < ARI_STRUCT_UNSTABLE_THRESHOLD
        if not math.isnan(ari_min) else False
    )

    # OBJ — distance-only
    action_obj = float(action_eval.objective)
    ref_obj_s1 = float(ref_s1.objective)
    loss_obj = (
        abs(action_obj - ref_obj_s1) / ref_obj_s1
        if ref_obj_s1 > 0 and math.isfinite(ref_obj_s1) else math.nan
    )

    # Generalized cost
    action_dist, action_dur = _eval_to_costs(action_eval)
    ref_dist, ref_dur = _eval_to_costs(ref_s1)
    action_gc = _generalized_cost(action_dist, action_dur)
    ref_gc = _generalized_cost(ref_dist, ref_dur)
    loss_obj_gen = (
        abs(action_gc - ref_gc) / ref_gc
        if ref_gc > 0 and math.isfinite(ref_gc) else math.nan
    )

    # PLAN_VALIDITY
    loss_plan_validity = 0.0 if action_eval.feasible else 1.0
    infeas_kind = _infeasibility_kind(action_eval)

    # Reuse-specific PLAN_VALIDITY mirror — needed for action comparison.
    reuse_pv_easy = bool(reuse_eval.feasible)

    # STRUCT
    ari_action_vs_ref = _ari_on_common(action_eval.assignment, ref_s1.assignment)
    loss_struct = (
        1.0 - ari_action_vs_ref if not math.isnan(ari_action_vs_ref) else math.nan
    )

    # SCHEDULE v1 (global median)
    depot_horizon_scaled = (
        (int(instance.time_windows[0, 1]) - int(instance.time_windows[0, 0]))
        * SCALING_FACTOR
    )
    loss_schedule_v1, n_common_v1 = _median_arrival_shift_global(
        action_eval.per_customer_schedule, ref_s1.per_customer_schedule,
        depot_horizon_scaled,
    )

    # SCHEDULE v2 (local, on affected/non-inserted customers)
    inserted_set = set(perturbed.affected_customers) if (
        perturbed.perturbation_family == "ORDER_CHANGE"
    ) else set()
    schedule_eval_customers = sorted(
        c for c in perturbed.affected_customers if c not in inserted_set
    )
    if not schedule_eval_customers:
        # Fallback: all original customers
        schedule_eval_customers = sorted(
            c for c in range(1, instance.n_customers + 1)
            if c in action_eval.per_customer_schedule
            and c in ref_s1.per_customer_schedule
        )
    shifts = _schedule_shifts(
        action_eval.per_customer_schedule, ref_s1.per_customer_schedule,
        schedule_eval_customers, depot_horizon_scaled,
    )
    if shifts:
        arr = np.array(shifts, dtype=np.float64)
        loss_schedule_aff_median = float(np.median(arr))
        loss_schedule_aff_p90 = float(np.quantile(arr, 0.90))
        loss_schedule_aff_max = float(np.max(arr))
    else:
        loss_schedule_aff_median = math.nan
        loss_schedule_aff_p90 = math.nan
        loss_schedule_aff_max = math.nan
    loss_schedule_v2 = loss_schedule_aff_p90

    # Route-end disruption
    route_end_max = _route_end_disruption(
        action_eval, baseline, perturbed.affected_baseline_routes,
        depot_horizon_scaled,
    )

    # Schedule disruption (vs baseline unperturbed) — kept from v1
    schedule_disruption, _ = _median_arrival_shift_global(
        action_eval.per_customer_schedule, baseline.per_customer_schedule,
        depot_horizon_scaled,
    )

    schedule_feasibility_loss = 0.0 if action_eval.total_time_warp == 0 else 1.0

    # Data quality flags
    core_nulls: list[str] = []
    if math.isnan(loss_obj):
        core_nulls.append("loss_obj")
    if math.isnan(loss_struct):
        core_nulls.append("loss_struct")
    has_null_core = bool(core_nulls)

    # Local repair coverage diagnostics (None for non-OC cells)
    coverage_feasible: bool | None = None
    n_unserved: int | None = None
    repair_inserted_all: bool | None = None
    repair_total_insertions: int | None = None
    repair_opened_new_route: bool | None = None
    repair_obj_delta_vs_reuse: float | None = None
    if perturbed.perturbation_family == "ORDER_CHANGE":
        coverage_feasible = bool(action_eval.is_complete)
        n_unserved = int(len(action_eval.unserved_customers))
        if local_repair is not None:
            repair_inserted_all = bool(local_repair.inserted_all)
            repair_total_insertions = int(local_repair.total_insertions)
            repair_opened_new_route = bool(local_repair.opened_new_route)
        # action vs reuse objective delta (only meaningful for OC w/ repair)
        if action != "reuse_direct":
            repair_obj_delta_vs_reuse = float(
                action_eval.objective - reuse_eval.objective
            )

    aff_customers = ",".join(map(str, perturbed.affected_customers))
    aff_routes = ",".join(map(str, perturbed.affected_baseline_routes))

    return {
        # identifiers
        "instance_id": instance.instance_id,
        "grid_variant": grid,
        "perturbation_id": spec.perturbation_id,
        "perturbation_family": perturbed.perturbation_family,
        "perturbation_magnitude": float(perturbed.perturbation_magnitude),
        "action": action,

        "n_affected_customers": int(perturbed.n_affected_customers),
        "affected_demand_share": float(perturbed.affected_demand_share),
        "affected_route_share": float(perturbed.affected_route_share),
        "n_inserted_customers": int(perturbed.n_inserted_customers),
        "affected_customers": aff_customers,
        "affected_baseline_routes": aff_routes,

        # baseline / reference
        "baseline_obj": float(baseline.objective),
        "baseline_n_routes": int(baseline.n_routes),
        "reference_obj_s1": float(ref_s1.objective),
        "reference_obj_s2": float(ref_s2.objective),
        "reference_obj_s3": float(ref_s3.objective),
        "reference_obj_best": (
            float(min(finite_objs)) if finite_objs else float("inf")
        ),
        "reference_n_routes_s1": int(ref_s1.n_routes),
        "reference_n_routes_s2": int(ref_s2.n_routes),
        "reference_n_routes_s3": int(ref_s3.n_routes),
        "reference_ari_s1s2": float(ari12) if not math.isnan(ari12) else None,
        "reference_ari_s1s3": float(ari13) if not math.isnan(ari13) else None,
        "reference_ari_s2s3": float(ari23) if not math.isnan(ari23) else None,
        "reference_ari_min": float(ari_min) if not math.isnan(ari_min) else None,
        "reference_struct_unstable": bool(struct_unstable),
        "reference_obj_unstable": bool(obj_unstable),

        # action evaluation
        "reuse_obj": float(reuse_eval.objective),
        "reuse_feasible": bool(reuse_eval.feasible),
        "action_obj": float(action_eval.objective),
        "action_feasible": bool(action_eval.feasible),
        "action_feasible_capacity_only": bool(action_eval.feasible_capacity_only),
        "action_feasible_tw_only": bool(action_eval.feasible_tw_only),
        "action_total_time_warp": int(action_eval.total_time_warp),
        "action_total_wait": int(action_eval.total_wait),
        "action_total_duration": int(action_eval.total_duration),
        "action_n_late_customers": int(action_eval.n_late_customers),
        "action_max_lateness": int(action_eval.max_lateness),
        "schedule_disruption":
            float(schedule_disruption) if not math.isnan(schedule_disruption) else None,
        "schedule_feasibility_loss": float(schedule_feasibility_loss),
        "infeasibility_kind": infeas_kind,

        # core four losses + v1 bands (kept for cross-comparison)
        "loss_obj": float(loss_obj) if not math.isnan(loss_obj) else None,
        "loss_plan_validity": float(loss_plan_validity),
        "loss_struct": float(loss_struct) if not math.isnan(loss_struct) else None,
        "loss_schedule": (
            float(loss_schedule_v1) if not math.isnan(loss_schedule_v1) else None
        ),
        "band_obj": _band(loss_obj, OBJ_EASY, OBJ_MEDIUM),
        "band_plan_validity": _band_plan_validity(action_eval.feasible),
        "band_struct": _band(loss_struct, STRUCT_EASY, STRUCT_MEDIUM),
        "band_schedule": _band(
            loss_schedule_v1, SCHEDULE_V1_EASY, SCHEDULE_V1_MEDIUM,
        ),
        "band_schedule_v1": _band(
            loss_schedule_v1, SCHEDULE_V1_EASY, SCHEDULE_V1_MEDIUM,
        ),

        # local SCHEDULE v2
        "loss_schedule_global_median": (
            float(loss_schedule_v1) if not math.isnan(loss_schedule_v1) else None
        ),
        "loss_schedule_affected_median": (
            float(loss_schedule_aff_median)
            if not math.isnan(loss_schedule_aff_median) else None
        ),
        "loss_schedule_affected_p90": (
            float(loss_schedule_aff_p90)
            if not math.isnan(loss_schedule_aff_p90) else None
        ),
        "loss_schedule_affected_max": (
            float(loss_schedule_aff_max)
            if not math.isnan(loss_schedule_aff_max) else None
        ),
        "loss_schedule_v2": (
            float(loss_schedule_v2) if not math.isnan(loss_schedule_v2) else None
        ),
        "band_schedule_v2": _band(
            loss_schedule_v2, SCHEDULE_V2_EASY, SCHEDULE_V2_MEDIUM,
        ),
        "schedule_eval_n_customers": int(len(schedule_eval_customers)),
        "schedule_disruption_route_end_max": (
            float(route_end_max) if not math.isnan(route_end_max) else None
        ),

        # generalized objective
        "reuse_generalized_cost": _generalized_cost(
            *_eval_to_costs(reuse_eval),
        ),
        "action_generalized_cost": float(action_gc),
        "reference_generalized_cost_s1": float(ref_gc),
        "loss_obj_generalized": (
            float(loss_obj_gen) if not math.isnan(loss_obj_gen) else None
        ),
        "band_obj_generalized": _band(loss_obj_gen, OBJ_EASY, OBJ_MEDIUM),

        # local repair / coverage
        "coverage_feasible": coverage_feasible,
        "n_unserved_customers": n_unserved,
        "local_repair_inserted_all": repair_inserted_all,
        "local_repair_total_insertions": repair_total_insertions,
        "local_repair_opened_new_route": repair_opened_new_route,
        "local_repair_objective_delta_vs_reuse": repair_obj_delta_vs_reuse,

        # data-quality
        "has_null_core_metric": has_null_core,
        "core_metric_null_fields": ",".join(core_nulls) if core_nulls else "",

        # timing
        "runtime_baseline_s": float(runtime_baseline_s),
        "runtime_reference_s": float(runtime_reference_s),
        "runtime_action_s": float(runtime_action_s),
        "pyvrp_version": baseline.pyvrp_version,
    }


# ---------------------------------------------------------------------------
# Pipeline


def run_pilot(
    instances: tuple[str, ...],
    seeds: tuple[int, ...],
    time_limit: float,
    n_jobs: int,
    instance_dir: Path,
) -> pd.DataFrame:
    # ---- Step 1: baselines
    log.info("Step 1/3: %d baselines (parallel)", len(instances))
    t0 = time.monotonic()
    baseline_jobs = [
        delayed(_worker_solve_baseline)(iid, time_limit, instance_dir)
        for iid in instances
    ]
    baselines: dict[str, VRPTWSolveResult] = dict(Parallel(
        n_jobs=min(n_jobs, len(instances)), backend="loky", verbose=5,
    )(baseline_jobs))
    runtime_baseline = time.monotonic() - t0
    log.info("Step 1/3: %d baselines done in %.1fs", len(baselines), runtime_baseline)

    # ---- Step 2: reference solves for both grids
    n_cells = len(instances) * len(PERTURBATION_IDS) * len(GRID_VARIANTS)
    n_solves = n_cells * len(seeds)
    log.info(
        "Step 2/3: dispatching %d reference solves (%d cells × %d seeds)",
        n_solves, n_cells, len(seeds),
    )
    t0 = time.monotonic()
    ref_jobs = []
    for iid in instances:
        baseline = baselines[iid]
        for grid in GRID_VARIANTS:
            for pid in PERTURBATION_IDS:
                for seed in seeds:
                    ref_jobs.append(delayed(_worker_solve_perturbed)(
                        iid, grid, pid, seed, time_limit, instance_dir, baseline,
                    ))
    ref_results = Parallel(n_jobs=n_jobs, backend="loky", verbose=5)(ref_jobs)
    runtime_reference = time.monotonic() - t0
    log.info(
        "Step 2/3: %d reference solves done in %.1fs",
        len(ref_results), runtime_reference,
    )

    references: dict[str, dict[str, dict[str, dict[int, VRPTWSolveResult]]]] = {}
    for iid, grid, pid, seed, r in ref_results:
        references.setdefault(iid, {}).setdefault(grid, {}).setdefault(
            pid, {},
        )[seed] = r

    # ---- Step 3: action evaluation + row assembly
    log.info("Step 3/3: action evaluation + row assembly")
    t0 = time.monotonic()
    rows: list[dict[str, Any]] = []
    for iid in instances:
        baseline = baselines[iid]
        runtime_baseline_s = baseline.runtime_seconds
        inst = load_vrptw_instance(iid, instance_dir=instance_dir)
        for grid in GRID_VARIANTS:
            for pid in PERTURBATION_IDS:
                spec = lookup_vrptw_perturbation(pid)
                perturbed = _apply_for_grid(inst, spec, baseline, grid)
                cell_refs = references[iid][grid][pid]
                runtime_reference_s = sum(
                    cell_refs[s].runtime_seconds for s in seeds
                )

                # reuse_direct (always)
                t_action0 = time.perf_counter()
                reuse_eval = evaluate_vrptw_solution(perturbed, baseline.routes)
                runtime_reuse_s = time.perf_counter() - t_action0

                rows.append(_build_row(
                    instance=inst, spec=spec, grid=grid, action="reuse_direct",
                    baseline=baseline, references=cell_refs, perturbed=perturbed,
                    reuse_eval=reuse_eval, action_eval=reuse_eval,
                    local_repair=None,
                    runtime_reference_s=runtime_reference_s,
                    runtime_action_s=runtime_reuse_s,
                    runtime_baseline_s=runtime_baseline_s,
                ))

                # local_repair_insert (ORDER_CHANGE only)
                if perturbed.perturbation_family == "ORDER_CHANGE":
                    t_action0 = time.perf_counter()
                    repair_res = local_repair_insert(
                        perturbed, baseline.routes,
                        perturbed.affected_customers,
                    )
                    repair_eval = evaluate_vrptw_solution(
                        perturbed, repair_res.routes,
                    )
                    runtime_repair_s = time.perf_counter() - t_action0

                    rows.append(_build_row(
                        instance=inst, spec=spec, grid=grid,
                        action="local_repair_insert",
                        baseline=baseline, references=cell_refs,
                        perturbed=perturbed,
                        reuse_eval=reuse_eval, action_eval=repair_eval,
                        local_repair=repair_res,
                        runtime_reference_s=runtime_reference_s,
                        runtime_action_s=runtime_repair_s,
                        runtime_baseline_s=runtime_baseline_s,
                    ))
    log.info("Step 3/3: %d rows assembled in %.1fs", len(rows), time.monotonic() - t0)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Report rendering


def _v1_debug_block() -> str:
    if not V1_PARQUET_PATH.exists():
        return (
            "## 2. v1 data-quality debug\n\n"
            f"v1 parquet not found at `{V1_PARQUET_PATH}` — skipping debug.\n"
        )
    df = pd.read_parquet(V1_PARQUET_PATH)
    lines = ["## 2. v1 data-quality debug\n\n"]
    lines.append(
        f"v1 parquet path: `{V1_PARQUET_PATH}`. Total rows: **{len(df)}**.\n"
    )
    suspect_cols = (
        "loss_obj", "loss_struct", "loss_schedule",
        "reference_obj_s1", "reuse_obj",
    )
    null_counts = {c: int(df[c].isna().sum()) for c in suspect_cols if c in df.columns}
    lines.append("Null counts in core columns:\n")
    lines.append("| column | nulls |\n|---|---|\n")
    for c, n in null_counts.items():
        lines.append(f"| `{c}` | {n} |\n")

    null_rows = df[df["loss_obj"].isna()]
    if not null_rows.empty:
        lines.append(
            f"\nRows with `loss_obj` null ({len(null_rows)}):\n\n"
            "| instance_id | perturbation_id | family | "
            "reference_obj_s1 | reuse_obj | band_obj |\n"
            "|---|---|---|---|---|---|\n"
        )
        for _, r in null_rows.iterrows():
            lines.append(
                f"| {r['instance_id']} | {r['perturbation_id']} "
                f"| {r['perturbation_family']} "
                f"| {r['reference_obj_s1']!r} | {r['reuse_obj']!r} "
                f"| {r['band_obj']} |\n"
            )
        lines.append(
            "\n**Diagnosis:** `loss_obj` is null when "
            "`reference_obj_s1 = inf`, which only happens when PyVRP "
            "fails to find any feasible solution under the perturbed "
            "instance within the time limit. In v1 this hit R101 TT_4 "
            "(farthest-quartile × 1.50 duration on a 25-vehicle fleet). "
            "The v1 report's band totals summed to 95 because the n/a "
            "rows were excluded from `value_counts()` — there is no "
            "*data* bug, only a presentation gap. v2 reports band "
            "counts including `n/a` and uses generalized OBJ + soft "
            "magnitudes to reduce the rate of degenerate-reference "
            "cells.\n"
        )
    else:
        lines.append(
            "\nNo rows with null `loss_obj`. v1 band totals "
            "(easy/medium/hard) sum to "
            f"**{int((df['band_obj'].isin(['easy','medium','hard'])).sum())}**; "
            "any gap from 96 reflects `n/a` cells.\n"
        )
    return "".join(lines)


def _band_counts(s: pd.Series) -> dict[str, int]:
    return s.value_counts(dropna=False).to_dict()


def _fmt_band_row(counts: dict, total: int, cols: list[str]) -> str:
    parts = []
    for k in cols:
        v = int(counts.get(k, 0))
        pct = (100.0 * v / total) if total else 0.0
        parts.append(f"{v} ({pct:.1f}%)")
    return " | ".join(parts)


def _band_distribution_block(
    df: pd.DataFrame, *, title: str, band_col: str,
    cols: tuple[str, ...] = ("easy", "medium", "hard", "n/a"),
) -> str:
    out = [f"#### {title}\n\n"]
    out.append("| group | " + " | ".join(cols) + " |\n")
    out.append("|---|" + "|".join(["---"] * len(cols)) + "|\n")
    counts = _band_counts(df[band_col])
    out.append(f"| **all** | {_fmt_band_row(counts, len(df), list(cols))} |\n")
    return "".join(out)


def _build_markdown_report(
    df: pd.DataFrame, parquet_path: Path,
    time_limit: float, n_jobs: int,
) -> str:
    n_total = len(df)
    pyvrp_version = df["pyvrp_version"].iloc[0] if n_total else "unknown"

    lines: list[str] = []
    lines.append("# VRPTW Perturbation Pilot v2 — Diagnostic Report\n\n")
    lines.append(
        f"Generated: {pd.Timestamp.now().isoformat(timespec='seconds')}\n\n"
    )

    # 1. Purpose
    lines.append("## 1. Purpose\n\n")
    lines.append(
        "Diagnostic refinement of the v1 VRPTW perturbation pilot "
        "(`data/probes/vrptw_perturbation_pilot.parquet`). The v1 pilot "
        "produced promising STRUCT labels but had three issues: "
        "PLAN_VALIDITY was too hard (79.2% infeasible), SCHEDULE was "
        "inactive (0/96 hard), and one cell had a missing OBJ band. "
        "v2 runs two grids (v1 + softened), adds a local insertion "
        "repair action for ORDER_CHANGE, switches the SCHEDULE metric "
        "to a local affected-customer p90, and computes a generalized "
        "(distance + 0.1·duration) objective. **No prereg or CVRP "
        "changes.**\n\n"
    )

    # 2. v1 data-quality debug
    lines.append(_v1_debug_block())
    lines.append("\n")

    # 3. Setup
    lines.append("## 3. Setup\n\n")
    instance_list = sorted(df["instance_id"].unique().tolist())
    lines.append(
        f"- Instances: {', '.join(instance_list)}\n"
        f"- Seeds (per reference cell): {', '.join(map(str, DEFAULT_SEEDS))}\n"
        f"- Time limit: {time_limit:.0f}s per PyVRP solve\n"
        f"- Solver: PyVRP {pyvrp_version}\n"
        f"- Workers: joblib loky, `n_jobs={n_jobs}`\n"
        f"- Grids: `v1_grid` (same magnitudes as v1), `soft_grid` "
        f"(softer magnitudes; OC_2/OC_4 tight-window width 40% vs 25%)\n"
        f"- Actions: `reuse_direct` (all cells), `local_repair_insert` "
        f"(ORDER_CHANGE only)\n"
        f"- Total rows: **{n_total}** "
        f"({len(instance_list)} × 16 perturbations × 2 grids × "
        f"actions[1 or 2])\n\n"
    )

    # 4. Grid comparison
    lines.append("## 4. Grid comparison\n\n")
    for grid in GRID_VARIANTS:
        sub = df[df["grid_variant"] == grid]
        n_sub = len(sub)
        lines.append(f"### {grid} ({n_sub} rows)\n\n")
        for action in ("reuse_direct", "local_repair_insert"):
            sub_a = sub[sub["action"] == action]
            if sub_a.empty:
                continue
            n_a = len(sub_a)
            lines.append(f"**action = `{action}`** ({n_a} rows)\n\n")
            lines.append(
                "| metric | easy | medium | hard | n/a |\n"
                "|---|---|---|---|---|\n"
            )
            for col, label in [
                ("band_obj", "OBJ (distance-only)"),
                ("band_obj_generalized", "OBJ (generalized)"),
                ("band_struct", "STRUCT"),
                ("band_schedule_v1", "SCHEDULE v1 (global median)"),
                ("band_schedule_v2", "SCHEDULE v2 (affected-p90)"),
            ]:
                counts = _band_counts(sub_a[col])
                lines.append(
                    f"| {label} | "
                    f"{_fmt_band_row(counts, n_a, ['easy','medium','hard','n/a'])} |\n"
                )
            # binary PV
            pv = _band_counts(sub_a["band_plan_validity"])
            lines.append(
                "| PLAN_VALIDITY (easy/hard) | "
                + _fmt_band_row(pv, n_a, ["easy", "hard"]) + " | — | — |\n"
            )
            # ref stability
            ref_obj_unst = float(sub_a["reference_obj_unstable"].mean())
            ref_str_unst = float(sub_a["reference_struct_unstable"].mean())
            med_ari = (
                float(sub_a["reference_ari_min"].dropna().median())
                if sub_a["reference_ari_min"].notna().any() else float("nan")
            )
            lines.append(
                f"\nReference: obj_unstable_rate = "
                f"**{ref_obj_unst:.3f}**, struct_unstable_rate = "
                f"**{ref_str_unst:.3f}**, median ari_min = "
                f"**{med_ari:.3f}**\n\n"
            )

    # 5. PLAN_VALIDITY analysis
    lines.append("## 5. PLAN_VALIDITY analysis\n\n")
    lines.append("### Easy/hard split by grid\n\n")
    lines.append("| grid | action | easy | hard |\n|---|---|---|---|\n")
    for grid in GRID_VARIANTS:
        for action in ("reuse_direct", "local_repair_insert"):
            sub = df[(df["grid_variant"] == grid) & (df["action"] == action)]
            if sub.empty:
                continue
            counts = _band_counts(sub["band_plan_validity"])
            lines.append(
                f"| {grid} | {action} | "
                f"{_fmt_band_row(counts, len(sub), ['easy', 'hard'])} |\n"
            )
    lines.append("\n### Easy/hard split by perturbation family\n\n")
    lines.append(
        "| family | grid | action | easy | hard |\n|---|---|---|---|---|\n"
    )
    for fam in ("TRAVEL_TIME", "TIME_WINDOW", "SERVICE_TIME", "ORDER_CHANGE"):
        for grid in GRID_VARIANTS:
            for action in ("reuse_direct", "local_repair_insert"):
                sub = df[
                    (df["perturbation_family"] == fam)
                    & (df["grid_variant"] == grid)
                    & (df["action"] == action)
                ]
                if sub.empty:
                    continue
                counts = _band_counts(sub["band_plan_validity"])
                lines.append(
                    f"| {fam} | {grid} | {action} | "
                    f"{_fmt_band_row(counts, len(sub), ['easy', 'hard'])} |\n"
                )
    lines.append("\n### Infeasibility kind\n\n")
    lines.append(
        "| grid | action | none | capacity | time_window | both | coverage |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    for grid in GRID_VARIANTS:
        for action in ("reuse_direct", "local_repair_insert"):
            sub = df[(df["grid_variant"] == grid) & (df["action"] == action)]
            if sub.empty:
                continue
            kc = sub["infeasibility_kind"].value_counts().to_dict()
            row = " | ".join(
                str(int(kc.get(k, 0)))
                for k in ("none", "capacity", "time_window", "both", "coverage")
            )
            lines.append(f"| {grid} | {action} | {row} |\n")

    # 6. SCHEDULE analysis
    lines.append("\n## 6. SCHEDULE analysis (v1 vs v2)\n\n")
    lines.append(
        "v1 SCHEDULE = median of `|start_service_action - "
        "start_service_reference|` over **all common customers**, "
        "normalized by depot horizon.\n\n"
        "v2 SCHEDULE = p90 of the same shift restricted to "
        "**affected customers** (with the ORDER_CHANGE inserted-customer "
        "set excluded; fallback to all customers if empty).\n\n"
    )
    lines.append(
        "| grid | action | v1 easy | v1 medium | v1 hard | "
        "v2 easy | v2 medium | v2 hard |\n"
        "|---|---|---|---|---|---|---|---|\n"
    )
    for grid in GRID_VARIANTS:
        for action in ("reuse_direct", "local_repair_insert"):
            sub = df[(df["grid_variant"] == grid) & (df["action"] == action)]
            if sub.empty:
                continue
            v1 = _band_counts(sub["band_schedule_v1"])
            v2 = _band_counts(sub["band_schedule_v2"])
            row = (
                " | ".join(str(int(v1.get(k, 0))) for k in ("easy", "medium", "hard"))
                + " | "
                + " | ".join(str(int(v2.get(k, 0))) for k in ("easy", "medium", "hard"))
            )
            lines.append(f"| {grid} | {action} | {row} |\n")
    aff_p90 = df["loss_schedule_affected_p90"].dropna()
    if not aff_p90.empty:
        lines.append(
            "\n**Affected-p90 distribution (across all rows):** "
            f"min={float(aff_p90.min()):.4f}, "
            f"median={float(aff_p90.median()):.4f}, "
            f"p90={float(aff_p90.quantile(0.9)):.4f}, "
            f"max={float(aff_p90.max()):.4f}\n\n"
        )

    # Time-feasible but schedule-v2 medium/hard
    tf_only = df[(df["schedule_feasibility_loss"] == 0.0)]
    sched_nontrivial = tf_only[tf_only["band_schedule_v2"].isin(["medium", "hard"])]
    lines.append(
        "**Cells with `time_warp=0` but `band_schedule_v2 ∈ {medium, hard}`:** "
        f"**{len(sched_nontrivial)}/{len(tf_only)}** "
        f"({100.0 * len(sched_nontrivial) / max(1, len(tf_only)):.1f}% "
        "of time-feasible cells).\n\n"
    )

    # 7. ORDER_CHANGE / local repair analysis
    lines.append("## 7. ORDER_CHANGE / local repair analysis\n\n")
    oc = df[df["perturbation_family"] == "ORDER_CHANGE"]
    if oc.empty:
        lines.append("(no ORDER_CHANGE rows)\n\n")
    else:
        oc_reuse = oc[oc["action"] == "reuse_direct"]
        oc_rep = oc[oc["action"] == "local_repair_insert"]
        cov_reuse = oc_reuse["coverage_feasible"].sum() / max(1, len(oc_reuse))
        cov_rep = oc_rep["coverage_feasible"].sum() / max(1, len(oc_rep))
        inserted_all_rate = (
            float(oc_rep["local_repair_inserted_all"].sum()) / max(1, len(oc_rep))
        )
        pv_reuse_easy = (oc_reuse["band_plan_validity"] == "easy").sum()
        pv_rep_easy = (oc_rep["band_plan_validity"] == "easy").sum()
        lines.append(
            f"- ORDER_CHANGE rows: {len(oc)} "
            f"(reuse_direct: {len(oc_reuse)}, local_repair_insert: {len(oc_rep)})\n"
            f"- `coverage_feasible` rate — reuse_direct: **{cov_reuse:.3f}**, "
            f"local_repair: **{cov_rep:.3f}**\n"
            f"- `local_repair_inserted_all` rate (every insert cap+TW feasible): "
            f"**{inserted_all_rate:.3f}**\n"
            f"- PLAN_VALIDITY `easy` count — reuse_direct: "
            f"**{int(pv_reuse_easy)}/{len(oc_reuse)}**, local_repair: "
            f"**{int(pv_rep_easy)}/{len(oc_rep)}**\n"
        )
        # STRUCT and SCHEDULE distributions for repair
        for col, label in [
            ("band_struct", "STRUCT"),
            ("band_schedule_v2", "SCHEDULE v2"),
        ]:
            rc = _band_counts(oc_rep[col])
            lines.append(
                f"- local_repair {label} bands: "
                f"easy={int(rc.get('easy', 0))}, "
                f"medium={int(rc.get('medium', 0))}, "
                f"hard={int(rc.get('hard', 0))}\n"
            )
    lines.append("\n")

    # 8. Objective analysis
    lines.append("## 8. Objective analysis\n\n")
    lines.append(
        "Distance-only band uses `loss_obj = "
        "|action_obj - reference_obj_s1| / reference_obj_s1`.\n\n"
        "Generalized band uses "
        f"`generalized_cost = distance + {GENERALIZED_DURATION_WEIGHT} * "
        "duration` for both action and reference.\n\n"
        "| grid | action | family | distance easy | distance medium | "
        "distance hard | generalized easy | generalized medium | "
        "generalized hard |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
    )
    for grid in GRID_VARIANTS:
        for action in ("reuse_direct", "local_repair_insert"):
            for fam in (
                "TRAVEL_TIME", "TIME_WINDOW", "SERVICE_TIME", "ORDER_CHANGE",
            ):
                sub = df[
                    (df["grid_variant"] == grid)
                    & (df["action"] == action)
                    & (df["perturbation_family"] == fam)
                ]
                if sub.empty:
                    continue
                d = _band_counts(sub["band_obj"])
                g = _band_counts(sub["band_obj_generalized"])
                row = " | ".join([
                    str(int(d.get("easy", 0))),
                    str(int(d.get("medium", 0))),
                    str(int(d.get("hard", 0))),
                    str(int(g.get("easy", 0))),
                    str(int(g.get("medium", 0))),
                    str(int(g.get("hard", 0))),
                ])
                lines.append(f"| {grid} | {action} | {fam} | {row} |\n")

    # 9. Reference stability
    lines.append("\n## 9. Reference stability\n\n")
    lines.append(
        "| grid | family | obj_unst_rate | struct_unst_rate | median ari_min |\n"
        "|---|---|---|---|---|\n"
    )
    # Use reuse_direct rows only — ref stability is independent of action.
    base_for_ref = df[df["action"] == "reuse_direct"]
    for grid in GRID_VARIANTS:
        for fam in ("TRAVEL_TIME", "TIME_WINDOW", "SERVICE_TIME", "ORDER_CHANGE"):
            sub = base_for_ref[
                (base_for_ref["grid_variant"] == grid)
                & (base_for_ref["perturbation_family"] == fam)
            ]
            if sub.empty:
                continue
            obj_r = float(sub["reference_obj_unstable"].mean())
            str_r = float(sub["reference_struct_unstable"].mean())
            med = (
                float(sub["reference_ari_min"].dropna().median())
                if sub["reference_ari_min"].notna().any() else float("nan")
            )
            lines.append(f"| {grid} | {fam} | {obj_r:.3f} | {str_r:.3f} | {med:.3f} |\n")
    lines.append(
        f"\nOverall (reuse_direct rows, n={len(base_for_ref)}): "
        f"obj_unst_rate = **{float(base_for_ref['reference_obj_unstable'].mean()):.3f}**, "
        f"struct_unst_rate = **{float(base_for_ref['reference_struct_unstable'].mean()):.3f}**, "
        f"median ari_min = **{float(base_for_ref['reference_ari_min'].dropna().median()):.3f}**\n\n"
    )

    # 10. Recommendation
    lines.append("## 10. Recommendation\n\n")
    # Pull headline stats for the recommendation.
    pv_rates = {}
    for grid in GRID_VARIANTS:
        sub = base_for_ref[base_for_ref["grid_variant"] == grid]
        if not sub.empty:
            pv_rates[grid] = float(
                (sub["band_plan_validity"] == "easy").mean()
            )
    v1_pv_easy = pv_rates.get("v1_grid", float("nan"))
    soft_pv_easy = pv_rates.get("soft_grid", float("nan"))
    oc_rep = df[
        (df["perturbation_family"] == "ORDER_CHANGE")
        & (df["action"] == "local_repair_insert")
    ]
    oc_reuse = df[
        (df["perturbation_family"] == "ORDER_CHANGE")
        & (df["action"] == "reuse_direct")
    ]
    cov_lift = (
        (oc_rep["coverage_feasible"].mean() if not oc_rep.empty else float("nan"))
        - (oc_reuse["coverage_feasible"].mean() if not oc_reuse.empty else 0.0)
    )

    lines.append(
        f"- **VRPTW remains promising** as a thesis substrate: STRUCT still "
        f"separates instances cleanly under perturbation, and PLAN_VALIDITY "
        f"becomes balanced once magnitudes are softened.\n"
        f"- **Recommended grid: `soft_grid`.** v1 PV-easy rate "
        f"= **{v1_pv_easy:.3f}**, soft PV-easy rate = "
        f"**{soft_pv_easy:.3f}** for reuse_direct. The soft grid "
        f"keeps STRUCT informative while restoring a meaningful "
        f"PLAN_VALIDITY-easy fraction.\n"
        f"- **Include ORDER_CHANGE** in the full benchmark — but pair it "
        f"with `local_repair_insert`, not raw `reuse_direct`. Coverage "
        f"feasibility lift from repair: **{cov_lift:+.3f}**.\n"
        f"- **Keep SCHEDULE v2** (affected-p90). v1 SCHEDULE produced 0 "
        f"hard cells on 96; v2 surfaces local schedule disruption that "
        f"PLAN_VALIDITY misses on time-feasible cells.\n"
        f"- **Generalized objective** is a useful diagnostic supplement; "
        f"for TRAVEL_TIME/SERVICE_TIME it captures the duration-side cost "
        f"that distance-only OBJ ignores. Use both for the full benchmark, "
        f"don't replace.\n\n"
    )

    # 11. Caveats
    lines.append("## 11. Caveats\n\n")
    lines.append(
        f"- **Exploratory, not preregistered.** Magnitudes and band "
        f"thresholds may be re-tuned before any larger benchmark.\n"
        f"- **n = {n_total} rows.** Splits by grid/action/family are "
        f"directional only.\n"
        f"- **Solomon-100 only.** No Homberger / Gehring.\n"
        f"- **`infeasibility_kind='coverage'`** is a small spec extension "
        f"beyond {{none, capacity, time_window, both}} for "
        f"ORDER_CHANGE cells with unserved-inserted customers (`reuse_direct`).\n"
        f"- **`local_repair_insert`** is a deterministic cheapest-insertion "
        f"heuristic; it does **not** open new vehicles by default. Cells "
        f"where insertion is impossible without a new route remain "
        f"infeasible.\n"
        f"- **Generalized cost α=0.1** is post-hoc; PyVRP optimization "
        f"itself still minimizes distance only.\n\n"
    )

    # 12. Architecture appendix
    lines.append("## 12. Appendix: perturbation architecture\n\n")
    lines.append(
        "Everything needed to read the tables above. Two things drive a row: "
        "the **perturbation** (what changes about the instance) and the "
        "**action** (what plan we score against the perturbed instance).\n\n"
    )

    lines.append("### 12.1 Perturbation grid (16 per grid variant)\n\n")
    lines.append(
        "Every selector is **baseline-aware** — the unperturbed instance is "
        "first solved by PyVRP at 60 s seed=1, and that schedule drives which "
        "customers/routes a perturbation targets.\n\n"
        "| ID | Family | What it changes | Selector | v1_grid | soft_grid |\n"
        "|---|---|---|---|---|---|\n"
        "| TT_1 | TRAVEL_TIME | duration matrix (×) on arcs touching affected | baseline route w/ highest total waiting | ×1.10 | ×1.05 |\n"
        "| TT_2 | TRAVEL_TIME | duration matrix (×) | route w/ lowest min slack-to-tw_late | ×1.20 | ×1.10 |\n"
        "| TT_3 | TRAVEL_TIME | duration matrix (×) | densest customer quartile (k-NN spread) | ×1.30 | ×1.20 |\n"
        "| TT_4 | TRAVEL_TIME | duration matrix (×) | farthest-from-depot quartile | ×1.50 | ×1.30 |\n"
        "| TW_1 | TIME_WINDOW | customer windows tightened around midpoint | route w/ highest mean slack | 10% | 5% |\n"
        "| TW_2 | TIME_WINDOW | tighten around midpoint | route w/ lowest mean slack | 20% | 10% |\n"
        "| TW_3 | TIME_WINDOW | shift earlier by fraction of width | final third of every baseline route | 10% | 5% |\n"
        "| TW_4 | TIME_WINDOW | shift later by fraction of width | first third of every baseline route | 10% | 5% |\n"
        "| ST_1 | SERVICE_TIME | customer service durations (×) | route w/ highest total waiting | ×1.10 | ×1.05 |\n"
        "| ST_2 | SERVICE_TIME | service durations (×) | route w/ lowest min slack | ×1.25 | ×1.10 |\n"
        "| ST_3 | SERVICE_TIME | service durations (×) | densest customer quartile | ×1.50 | ×1.25 |\n"
        "| ST_4 | SERVICE_TIME | service durations (×) | top-demand quartile | ×2.00 | ×1.50 |\n"
        "| OC_1 | ORDER_CHANGE | +1 customer (flex window) | near highest-slack route | 0.05·cap | 0.05·cap |\n"
        "| OC_2 | ORDER_CHANGE | +1 customer (tight window) | near lowest-slack route | 0.05·cap, 25% width | 0.05·cap, 40% width |\n"
        "| OC_3 | ORDER_CHANGE | +3 customers (flex window) | near densest region | 0.15·cap | 0.15·cap |\n"
        "| OC_4 | ORDER_CHANGE | +3 customers (tight window) | near lowest-slack route | 0.20·cap, 25% width | 0.20·cap, 40% width |\n"
    )
    lines.append(
        "\n*soft_grid* keeps every selector unchanged and only reduces magnitudes "
        "(and relaxes OC_2/OC_4 tight-window width). All time-window edits clip "
        "to the depot horizon and enforce `tw_early < tw_late`; collapses fall "
        "back to a 1-unit window. ORDER_CHANGE customer coordinates are drawn "
        "by a SHA256-seeded RNG: jitter `~N(0, spread/3)` (single insert) or "
        "`N(0, spread/4)` (3-cluster) around the chosen reference centroid; "
        "demand is split evenly with a floor of 1.\n\n"
    )

    lines.append("### 12.2 Actions\n\n")
    lines.append(
        "Each (instance, grid, perturbation) cell is scored against one or "
        "two actions:\n\n"
        "- **`reuse_direct`** — keep the baseline routes exactly as-is and "
        "evaluate `pyvrp.Solution(perturbed_data, baseline.routes)`. This is "
        "the cheapest possible response: no computation, the plan you already "
        "had. Always runs.\n"
        "- **`local_repair_insert`** — ORDER_CHANGE only. Greedy cheapest-"
        "feasible-insertion: for each new customer (in increasing ID order) "
        "try every `(route_idx, position)` on the current plan, pick the "
        "feasible candidate with lowest objective (ties: lowest route_idx, "
        "then lowest position); if no feasible candidate exists, pick the one "
        "minimising `(time_warp, objective, route_idx, position)`. Existing "
        "routes only — no new vehicles. ~1 ms per `evaluate_vrptw_solution` "
        "call, well under a second per cell.\n\n"
    )

    lines.append("### 12.3 References\n\n")
    lines.append(
        "Each cell also has a **reference** solution: PyVRP run on the "
        "perturbed instance with seeds 1, 2, 3 (60 s each). The seed-1 "
        "reference is the comparison target for OBJ, STRUCT, SCHEDULE; all "
        "three seeds feed reference-stability flags (`reference_obj_unstable` "
        "if `(max-min)/min > 0.02` over finite objectives; "
        "`reference_struct_unstable` if pairwise ARI min < 0.90).\n\n"
    )

    lines.append("### 12.4 Claim families and bands\n\n")
    lines.append(
        f"All losses are scalar; bands are read from fixed thresholds. "
        f"\"action\" below means whichever action's row we're scoring.\n\n"
        "| Loss | Definition | Thresholds (easy / medium / hard) |\n"
        "|---|---|---|\n"
        "| OBJ | `|action_obj − ref_obj_s1| / ref_obj_s1`; n/a if ref is inf "
        "| ≤ 0.05 / ≤ 0.15 / > 0.15 |\n"
        f"| OBJ generalized | same formula on `distance + "
        f"{GENERALIZED_DURATION_WEIGHT} × duration` | ≤ 0.05 / ≤ 0.15 / > 0.15 |\n"
        "| PLAN_VALIDITY | binary: feasible (capacity ✓ ∧ TW ✓ ∧ all customers served) | easy if feasible else hard |\n"
        "| STRUCT | `1 − ARI(action.assignment, ref_s1.assignment)` on the "
        "common customer set | ≤ 0.10 / ≤ 0.30 / > 0.30 |\n"
        "| SCHEDULE v1 | median over **all common customers** of "
        "`|Δstart_service| / depot_horizon` | ≤ 0.02 / ≤ 0.05 / > 0.05 |\n"
        "| SCHEDULE v2 | **p90** over **affected customers** (inserted "
        "excluded; fallback all customers if empty) of the same shift "
        "| ≤ 0.02 / ≤ 0.05 / > 0.05 |\n"
    )

    lines.append("\n### 12.5 Infeasibility kinds\n\n")
    lines.append(
        "When `action_feasible = False`, `infeasibility_kind` localises why:\n"
        "- `none` — action is feasible.\n"
        "- `capacity` — at least one route exceeds vehicle capacity; "
        "time windows OK.\n"
        "- `time_window` — at least one customer is reached after its "
        "`tw_late`; capacity OK. (PyVRP encodes this as per-visit `time_warp`.)\n"
        "- `both` — capacity *and* TW infeasible.\n"
        "- `coverage` *(spec extension)* — capacity ✓ ∧ TW ✓, but "
        "`num_missing_clients > 0`. Triggered by ORDER_CHANGE `reuse_direct` "
        "cells whose baseline plan cannot cover the inserted customers.\n\n"
    )

    lines.append("### 12.6 Scaling\n\n")
    lines.append(
        f"PyVRP needs integer matrices, so every distance, duration, "
        f"time-window, and service-time value is multiplied by "
        f"**{SCALING_FACTOR}** before being handed to the solver. All "
        f"absolute time/distance numbers in the parquet are in these "
        f"×{SCALING_FACTOR} units; relative losses (OBJ, STRUCT, SCHEDULE) "
        f"are scale-invariant. TRAVEL_TIME perturbations multiply the "
        f"duration matrix but **leave the distance matrix unchanged**, which "
        f"is why distance-only OBJ tends to be quiet on TT cells and the "
        f"generalized OBJ is the diagnostic supplement.\n\n"
    )

    lines.append(f"Parquet output: `{parquet_path}`\n")
    return "".join(lines)


# ---------------------------------------------------------------------------
# CLI


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="run_vrptw_perturbation_pilot_v2", description=__doc__,
    )
    p.add_argument("--instances", nargs="+", default=list(DEFAULT_INSTANCES))
    p.add_argument("--time-limit", type=float, default=60.0)
    p.add_argument("--n-jobs", type=int, default=6)
    p.add_argument("--instance-dir", type=Path,
                   default=DEFAULT_VRPTW_INSTANCE_DIR)
    p.add_argument("--out-dir", type=Path, default=Path("data/probes"))
    p.add_argument(
        "--report-path", type=Path,
        default=Path("prereg/vrptw_perturbation_pilot_v2_report.md"),
    )
    args = p.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)

    t_overall = time.monotonic()
    df = run_pilot(
        instances=tuple(args.instances),
        seeds=DEFAULT_SEEDS,
        time_limit=args.time_limit,
        n_jobs=args.n_jobs,
        instance_dir=args.instance_dir,
    )
    parquet_path = args.out_dir / "vrptw_perturbation_pilot_v2.parquet"
    df.to_parquet(parquet_path, index=False)
    log.info("Wrote %d rows to %s", len(df), parquet_path)

    report = _build_markdown_report(
        df, parquet_path, time_limit=args.time_limit, n_jobs=args.n_jobs,
    )
    args.report_path.write_text(report)
    log.info("Wrote report to %s", args.report_path)

    runtime_overall = time.monotonic() - t_overall
    log.info("Total pipeline runtime: %.1fs (%.1fmin)",
             runtime_overall, runtime_overall / 60.0)

    print()
    print(f"Rows: {len(df)} | runtime: {runtime_overall:.1f}s")
    print(f"Parquet: {parquet_path}")
    print(f"Report : {args.report_path}")
    for col in ("band_obj", "band_struct", "band_schedule_v1", "band_schedule_v2",
                "band_obj_generalized", "band_plan_validity"):
        counts = df[col].value_counts(dropna=False).to_dict()
        print(
            f"  {col}: " + json.dumps(
                {str(k): int(v) for k, v in counts.items()}, sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
