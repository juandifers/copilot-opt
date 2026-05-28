#!/usr/bin/env python3
"""Diagnostic probe: escalated TT/TW magnitudes per Appendix A.1/A.2.

Does the prereg's §12.6 §12.1-clause escalation (one rung) bring the two
failing OBJ blocks (OBJ × TIME_WINDOW = 1.000, OBJ × TRAVEL_TIME = 0.973)
into the [0.10, 0.90] label-distribution bracket — and does it overshoot
PV/STRUCT/SCHEDULE on the same columns?

This is **diagnostic only**. Does not modify Stage A artifacts, does not
apply the §12.6 revision procedure. The probe output is the decision
input for whether to apply it.

Sample
======
- 20 of 56 Stage A instances, stratified across Solomon C / R / RC in
  the same proportion as the 56-instance pool (6 / 8 / 6).
- Selection RNG: ``random.Random(42)`` (reported in the run stats).
- All 4 magnitudes for each affected family: TT_1..TT_4, TW_1..TW_4.
- 20 × 8 = 160 cells × 3 reference seeds = 480 reference solves at 120s.

Pipeline mirrors :mod:`scripts.run_vrptw_scale_check` (expanded ladder),
swapping :data:`SOFT_PERTURBATION_MAGNITUDES` for the canonical
:data:`PERTURBATION_MAGNITUDES`, which equal Appendix A.1/A.2 *escalate*
verbatim. Reference protocol is the v1.1 120 s scaled protocol.

Outputs
=======
- ``data/probes/escalation_probe.parquet`` (wide, one row per
  (cell, action))
- ``data/probes/escalation_probe_claim_rows.parquet`` (long, one row
  per (cell, action, claim_family))
- ``data/probes/escalation_probe_checkpoints/`` (resumable checkpoints)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from vrp_copilot_bench.vrptw import (  # noqa: E402
    PERTURBATION_FAMILY_OF,
    PERTURBATION_MAGNITUDES,
    EvaluatedVRPTW,
    SolveConfig,
    VRPTWPerturbedInstance,
    VRPTWSolveResult,
    apply_vrptw_perturbation,
    load_vrptw_instance,
    lookup_vrptw_perturbation,
    solve_vrptw,
)
from vrp_copilot_bench.vrptw.actions import (  # noqa: E402
    ACTION_TIER,
    ActionResult,
    ConstructFeasible,
    LocalRepairInsert,
    PyvrpSolve,
    ReuseDirect,
    actions_for_family,
    cheap_action_for_family,
    materialize_reference_action,
)
from vrp_copilot_bench.vrptw.baselines import (  # noqa: E402
    CachedBaseline,
    load_or_compute_baseline,
)
from vrp_copilot_bench.vrptw.checkpoint import CheckpointStore  # noqa: E402
from vrp_copilot_bench.vrptw.evaluation import (  # noqa: E402
    ReferenceStability,
    depot_horizon_scaled,
    eval_to_costs,
    generalized_cost,
    infeasibility_kind,
    reference_stability,
    route_end_disruption_max,
)
from vrp_copilot_bench.vrptw.features import FeatureBundle, extract_features  # noqa: E402
from vrp_copilot_bench.vrptw.losses import LossBundle, compute_losses  # noqa: E402
from vrp_copilot_bench.vrptw.solver import evaluate_vrptw_solution  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("escalation_probe")


CLAIM_FAMILIES: tuple[str, ...] = ("OBJ", "PLAN_VALIDITY", "STRUCT", "SCHEDULE")

PROBE_DIR = PROJECT_ROOT / "data" / "probes"
CHECKPOINT_DIR = PROBE_DIR / "escalation_probe_checkpoints"
WIDE_PARQUET = PROBE_DIR / "escalation_probe.parquet"
CLAIM_PARQUET = PROBE_DIR / "escalation_probe_claim_rows.parquet"
RUN_STATS_JSON = CHECKPOINT_DIR / "run_stats.json"

SEEDS = (1, 2, 3)
BASELINE_TIME_LIMIT = 60.0  # reuse Stage A baselines (60s cache)
REFERENCE_TIME_LIMIT = 120.0  # v1.1 scaled reference protocol
PYVRP10S_TIME_LIMIT = 10.0

# Sampling
SAMPLE_SEED = 42
SAMPLE_N_C = 6
SAMPLE_N_R = 8
SAMPLE_N_RC = 6
ESCALATED_PERTURBATIONS = (
    "TT_1", "TT_2", "TT_3", "TT_4",
    "TW_1", "TW_2", "TW_3", "TW_4",
)


def _instance_class(iid: str) -> str:
    if iid.startswith("RC"):
        return "RC"
    if iid.startswith("R"):
        return "R"
    if iid.startswith("C"):
        return "C"
    raise ValueError(f"unrecognized instance id {iid!r}")


def _stratified_sample() -> list[str]:
    df = pd.read_parquet(PROJECT_ROOT / "data" / "stage_a_vrptw.parquet")
    ids = sorted(df["instance_id"].unique())
    by_class: dict[str, list[str]] = {"C": [], "R": [], "RC": []}
    for iid in ids:
        by_class[_instance_class(iid)].append(iid)
    rng = random.Random(SAMPLE_SEED)
    pick = (
        sorted(rng.sample(by_class["C"], SAMPLE_N_C))
        + sorted(rng.sample(by_class["R"], SAMPLE_N_R))
        + sorted(rng.sample(by_class["RC"], SAMPLE_N_RC))
    )
    return pick


# ---------------------------------------------------------------------------
# Worker entry points (module-level for loky pickling)


def _apply_escalated_perturbation(instance, spec, baseline_solve_result):
    """Apply ESCALATED magnitude (Appendix A.1/A.2 'escalate' = the
    canonical ``PERTURBATION_MAGNITUDES`` constants verbatim).

    Only TRAVEL_TIME and TIME_WINDOW are exercised by this probe.
    """
    return apply_vrptw_perturbation(
        instance, spec, baseline_solve_result,
        magnitude_override=PERTURBATION_MAGNITUDES[spec.perturbation_id],
    )


def _esc_reference_solve(
    instance_id: str,
    perturbation_id: str,
    seed: int,
    reference_time_limit: float,
    baseline_time_limit: float,
    instance_dir,
    checkpoint_root: str,
):
    store = CheckpointStore(Path(checkpoint_root))
    if store.has_failure("refs", instance_id, perturbation_id, seed=seed):
        return instance_id, perturbation_id, seed, None, True
    cached = store.load_ref(instance_id, perturbation_id, seed)
    if cached is not None:
        return instance_id, perturbation_id, seed, cached, False
    try:
        instance = load_vrptw_instance(instance_id, instance_dir)
        baseline = load_or_compute_baseline(
            instance_id, seed=1,
            time_limit_seconds=baseline_time_limit,
            instance_dir=instance_dir,
        )
        spec = lookup_vrptw_perturbation(perturbation_id)
        perturbed = _apply_escalated_perturbation(
            instance, spec, baseline.solve_result,
        )
        cfg = SolveConfig(time_limit_seconds=reference_time_limit, seed=seed)
        result = solve_vrptw(perturbed, cfg)
        store.save_ref(instance_id, perturbation_id, seed, result)
        return instance_id, perturbation_id, seed, result, False
    except Exception as exc:
        store.save_failure(
            "refs", instance_id, perturbation_id, seed=seed, exc=exc,
        )
        return instance_id, perturbation_id, seed, None, True


def _esc_pyvrp10s_solve(
    instance_id: str,
    perturbation_id: str,
    pyvrp10s_time_limit: float,
    baseline_time_limit: float,
    instance_dir,
    checkpoint_root: str,
):
    store = CheckpointStore(Path(checkpoint_root))
    if store.has_failure("pyvrp10s", instance_id, perturbation_id):
        return instance_id, perturbation_id, None, True
    cached = store.load_pyvrp10s(instance_id, perturbation_id)
    if cached is not None:
        return instance_id, perturbation_id, cached, False
    try:
        instance = load_vrptw_instance(instance_id, instance_dir)
        baseline = load_or_compute_baseline(
            instance_id, seed=1,
            time_limit_seconds=baseline_time_limit,
            instance_dir=instance_dir,
        )
        spec = lookup_vrptw_perturbation(perturbation_id)
        perturbed = _apply_escalated_perturbation(
            instance, spec, baseline.solve_result,
        )
        cfg = SolveConfig(time_limit_seconds=pyvrp10s_time_limit, seed=1)
        result = solve_vrptw(perturbed, cfg)
        store.save_pyvrp10s(instance_id, perturbation_id, result)
        return instance_id, perturbation_id, result, False
    except Exception as exc:
        store.save_failure("pyvrp10s", instance_id, perturbation_id, exc=exc)
        return instance_id, perturbation_id, None, True


def _ensure_baseline_warm(instance_id: str, baseline_time_limit: float, instance_dir):
    cb = load_or_compute_baseline(
        instance_id, seed=1,
        time_limit_seconds=baseline_time_limit,
        instance_dir=instance_dir,
    )
    return instance_id, cb


# ---------------------------------------------------------------------------
# Row assembly (mirrors run_vrptw_scale_check._build_wide_row)


def _action_for_name(name: str, *, pyvrp10s_time_limit: float = 10.0):
    if name == "reuse_direct":
        return ReuseDirect()
    if name == "local_repair_insert":
        return LocalRepairInsert()
    if name == "construct_feasible":
        return ConstructFeasible()
    if name == "pyvrp_10s":
        return PyvrpSolve(seed=1, time_limit_seconds=pyvrp10s_time_limit)
    raise ValueError(f"non-runnable or unknown action {name!r}")


def _pyvrp10s_result_to_action_result(
    perturbed: VRPTWPerturbedInstance,
    solve_result: VRPTWSolveResult,
    *,
    time_limit_seconds: float,
) -> ActionResult:
    routes = [list(r) for r in solve_result.routes if r]
    ev = evaluate_vrptw_solution(perturbed, routes)
    return ActionResult(
        name="pyvrp_10s",
        routes=routes,
        evaluation=ev,
        runtime_seconds=float(solve_result.runtime_seconds),
        solver_seed=1,
        solver_time_limit_seconds=float(time_limit_seconds),
    )


def _failure_kind_for_row(stab: ReferenceStability, ref_s1: VRPTWSolveResult) -> str:
    if not stab.s1_feasible or not math.isfinite(ref_s1.objective):
        if stab.any_feasible:
            return "s1_infeasible_other_feasible"
        return "all_infeasible"
    if not stab.all_feasible:
        return "any_infeasible"
    return "none"


def _f_or_none(x):
    if x is None:
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    return float(x)


def _build_wide_row(
    *,
    instance,
    spec,
    perturbed: VRPTWPerturbedInstance,
    baseline: CachedBaseline,
    references: dict[int, VRPTWSolveResult],
    action_result: ActionResult,
    runtime_reference_s: float,
) -> dict[str, Any]:
    ref_s1, ref_s2, ref_s3 = references[1], references[2], references[3]
    stab = reference_stability(ref_s1, ref_s2, ref_s3)
    failure_kind = _failure_kind_for_row(stab, ref_s1)

    losses: LossBundle = compute_losses(
        instance=instance, perturbed=perturbed,
        action_eval=action_result.evaluation, ref_s1=ref_s1,
    )
    feats: FeatureBundle = extract_features(
        instance=instance, perturbed=perturbed,
        baseline=baseline.solve_result, action_eval=action_result.evaluation,
    )

    action_eval = action_result.evaluation
    coverage_feasible = bool(action_eval.is_complete)
    n_unserved = int(len(action_eval.unserved_customers))

    repair = action_result.local_repair
    if repair is not None:
        repair_inserted_all = bool(repair.inserted_all)
        repair_total_insertions = int(repair.total_insertions)
        repair_opened_new_route = bool(repair.opened_new_route)
    else:
        repair_inserted_all = None
        repair_total_insertions = None
        repair_opened_new_route = None

    horizon = depot_horizon_scaled(instance)
    route_end_max = route_end_disruption_max(
        action_eval, baseline.solve_result,
        perturbed.affected_baseline_routes, horizon,
    )

    cheap = cheap_action_for_family(perturbed.perturbation_family)
    is_cheap = bool(action_result.name == cheap)

    action_dist, action_dur = eval_to_costs(action_eval)
    action_gc = generalized_cost(action_dist, action_dur)
    tier_idx, tier_label, is_middle, is_reference = ACTION_TIER[action_result.name]
    action_valid = bool(action_eval.feasible)

    row: dict[str, Any] = {
        "instance_id": instance.instance_id,
        "perturbation_id": spec.perturbation_id,
        "perturbation_family": perturbed.perturbation_family,
        "perturbation_magnitude": float(perturbed.perturbation_magnitude),
        "action": action_result.name,
        "action_tier": tier_label,
        "action_tier_index": int(tier_idx),
        "is_middle_action": bool(is_middle),
        "is_reference_action": bool(is_reference),
        "cheap_action_for_cell": cheap,
        "is_cheap_action": is_cheap,
        "n_affected_customers": int(perturbed.n_affected_customers),
        "affected_demand_share": float(perturbed.affected_demand_share),
        "affected_route_share": float(perturbed.affected_route_share),
        "n_inserted_customers": int(perturbed.n_inserted_customers),
        "affected_customers": ",".join(map(str, perturbed.affected_customers)),
        "affected_baseline_routes": ",".join(
            map(str, perturbed.affected_baseline_routes)
        ),
        "baseline_obj": float(baseline.objective),
        "baseline_generalized_cost": float(baseline.generalized_cost),
        "baseline_n_routes": int(baseline.n_routes),
        "reference_obj_s1": float(ref_s1.objective),
        "reference_obj_s2": float(ref_s2.objective),
        "reference_obj_s3": float(ref_s3.objective),
        "reference_obj_best_feasible": (
            float(stab.obj_best_feasible)
            if math.isfinite(stab.obj_best_feasible) else None
        ),
        "reference_s1_feasible": bool(stab.s1_feasible),
        "reference_s2_feasible": bool(stab.s2_feasible),
        "reference_s3_feasible": bool(stab.s3_feasible),
        "reference_any_feasible": bool(stab.any_feasible),
        "reference_all_feasible": bool(stab.all_feasible),
        "reference_n_routes_s1": int(stab.n_routes_s1),
        "reference_n_routes_s2": int(stab.n_routes_s2),
        "reference_n_routes_s3": int(stab.n_routes_s3),
        "reference_ari_s1s2": (
            float(stab.ari_s1s2) if not math.isnan(stab.ari_s1s2) else None
        ),
        "reference_ari_s1s3": (
            float(stab.ari_s1s3) if not math.isnan(stab.ari_s1s3) else None
        ),
        "reference_ari_s2s3": (
            float(stab.ari_s2s3) if not math.isnan(stab.ari_s2s3) else None
        ),
        "reference_ari_min": (
            float(stab.ari_min) if not math.isnan(stab.ari_min) else None
        ),
        "reference_obj_unstable": bool(stab.obj_unstable),
        "reference_struct_unstable": (
            None if stab.struct_unstable is None
            else bool(stab.struct_unstable)
        ),
        "reference_failure_kind": failure_kind,
        "action_obj": float(action_eval.objective),
        "action_generalized_cost": float(action_gc),
        "action_feasible": bool(action_eval.feasible),
        "action_feasible_capacity_only": bool(action_eval.feasible_capacity_only),
        "action_feasible_tw_only": bool(action_eval.feasible_tw_only),
        "coverage_feasible": coverage_feasible,
        "n_unserved_customers": n_unserved,
        "action_total_time_warp": int(action_eval.total_time_warp),
        "action_total_wait": int(action_eval.total_wait),
        "action_total_duration": int(action_eval.total_duration),
        "action_n_late_customers": int(action_eval.n_late_customers),
        "action_max_lateness": int(action_eval.max_lateness),
        "infeasibility_kind": infeasibility_kind(action_eval),
        "loss_obj_distance": _f_or_none(losses.loss_obj_distance),
        "band_obj_distance": losses.band_obj_distance,
        "loss_obj_generalized": _f_or_none(losses.loss_obj_generalized),
        "band_obj_generalized": losses.band_obj_generalized,
        "loss_plan_validity": float(losses.loss_plan_validity),
        "band_plan_validity": losses.band_plan_validity,
        "loss_struct": _f_or_none(losses.loss_struct),
        "band_struct": losses.band_struct,
        "loss_schedule": _f_or_none(losses.loss_schedule),
        "band_schedule": losses.band_schedule,
        "loss_schedule_global_median": _f_or_none(losses.loss_schedule_global_median),
        "loss_schedule_affected_median": _f_or_none(losses.loss_schedule_affected_median),
        "loss_schedule_affected_p90": _f_or_none(losses.loss_schedule_affected_p90),
        "loss_schedule_affected_max": _f_or_none(losses.loss_schedule_affected_max),
        "schedule_eval_n_customers": int(losses.schedule_eval_n_customers),
        "schedule_disruption_route_end_max": _f_or_none(route_end_max),
        "local_repair_inserted_all": repair_inserted_all,
        "local_repair_total_insertions": repair_total_insertions,
        "local_repair_opened_new_route": repair_opened_new_route,
        "local_repair_objective_delta_vs_reuse": None,
        "runtime_baseline_s": float(baseline.runtime_seconds),
        "runtime_reference_s": float(runtime_reference_s),
        "runtime_action_s": float(action_result.runtime_seconds),
        "action_runtime_s": float(action_result.runtime_seconds),
        "action_solver_time_limit": (
            float(action_result.solver_time_limit_seconds)
            if action_result.solver_time_limit_seconds is not None else None
        ),
        "action_seed": (
            int(action_result.solver_seed)
            if action_result.solver_seed is not None else None
        ),
        "action_valid": action_valid,
        "pyvrp_version": baseline.pyvrp_version,
        "reference_time_limit_s": int(REFERENCE_TIME_LIMIT),
        "magnitude_grid": "escalated_appendix_A",
    }
    row.update(feats.as_dict())
    return row


_FEATURE_COLUMNS: tuple[str, ...] = tuple(FeatureBundle.__annotations__.keys())


def _build_claim_rows(wide: dict[str, Any]) -> list[dict[str, Any]]:
    family_to_losses = {
        "OBJ":           (wide["loss_obj_distance"], wide["band_obj_distance"]),
        "PLAN_VALIDITY": (wide["loss_plan_validity"], wide["band_plan_validity"]),
        "STRUCT":        (wide["loss_struct"], wide["band_struct"]),
        "SCHEDULE":      (wide["loss_schedule"], wide["band_schedule"]),
    }
    ref_s1_valid = bool(
        wide["reference_s1_feasible"]
        and wide["reference_obj_s1"] is not None
        and math.isfinite(wide["reference_obj_s1"])
        and wide["reference_obj_s1"] > 0
    )
    out: list[dict[str, Any]] = []
    for family in CLAIM_FAMILIES:
        loss, band = family_to_losses[family]
        if band == "n/a":
            sufficient_binary = None
        elif band == "easy":
            sufficient_binary = 1
        else:
            sufficient_binary = 0
        if family == "OBJ":
            reference_valid = ref_s1_valid and not wide["reference_obj_unstable"]
        elif family == "STRUCT":
            ru = wide["reference_struct_unstable"]
            reference_valid = ref_s1_valid and (ru is False)
        elif family == "PLAN_VALIDITY":
            reference_valid = True
        elif family == "SCHEDULE":
            reference_valid = ref_s1_valid
        else:
            raise ValueError(family)
        row = {
            "instance_id": wide["instance_id"],
            "perturbation_id": wide["perturbation_id"],
            "perturbation_family": wide["perturbation_family"],
            "action": wide["action"],
            "action_tier": wide["action_tier"],
            "action_tier_index": int(wide["action_tier_index"]),
            "is_middle_action": bool(wide["is_middle_action"]),
            "is_reference_action": bool(wide["is_reference_action"]),
            "action_runtime_s": float(wide["action_runtime_s"]),
            "action_solver_time_limit": wide["action_solver_time_limit"],
            "action_seed": wide["action_seed"],
            "action_valid": bool(wide["action_valid"]),
            "cheap_action_for_cell": wide["cheap_action_for_cell"],
            "is_cheap_action": wide["is_cheap_action"],
            "claim_family": family,
            "loss": _f_or_none(loss) if family != "PLAN_VALIDITY" else float(loss),
            "band": band,
            "sufficient_binary": sufficient_binary,
            "reference_valid": bool(reference_valid),
            "reference_struct_unstable": (
                None if wide["reference_struct_unstable"] is None
                else bool(wide["reference_struct_unstable"])
            ),
            "reference_obj_unstable": bool(wide["reference_obj_unstable"]),
            "action_feasible": bool(wide["action_feasible"]),
            "infeasibility_kind": wide["infeasibility_kind"],
            "magnitude_grid": "escalated_appendix_A",
        }
        for col in _FEATURE_COLUMNS:
            row[col] = wide[col]
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Pipeline


def run_probe(
    instances: tuple[str, ...],
    perturbation_ids: tuple[str, ...],
    n_jobs: int,
    instance_dir: Path | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    store = CheckpointStore(CHECKPOINT_DIR)
    store.mkdir()
    store.write_manifest({
        "instances": list(instances),
        "perturbation_ids": list(perturbation_ids),
        "seeds": list(SEEDS),
        "baseline_time_limit": float(BASELINE_TIME_LIMIT),
        "reference_time_limit": float(REFERENCE_TIME_LIMIT),
        "pyvrp10s_time_limit": float(PYVRP10S_TIME_LIMIT),
        "n_jobs": int(n_jobs),
        "sample_seed": int(SAMPLE_SEED),
        "magnitude_grid": "escalated_appendix_A",
    })
    checkpoint_root = str(CHECKPOINT_DIR)

    # Phase 1: warm baselines (60s cache).
    log.info("Phase 1/4: warming %d baselines (60s cache)", len(instances))
    t0 = time.monotonic()
    bl_jobs = [
        delayed(_ensure_baseline_warm)(iid, BASELINE_TIME_LIMIT, instance_dir)
        for iid in instances
    ]
    bl_pairs = Parallel(
        n_jobs=min(n_jobs, len(instances)), backend="loky", verbose=5,
    )(bl_jobs)
    baselines: dict[str, CachedBaseline] = dict(bl_pairs)
    runtime_baseline = time.monotonic() - t0
    log.info(
        "Phase 1/4 done in %.1fs (cache hits=%d)",
        runtime_baseline,
        sum(1 for b in baselines.values() if b.from_cache),
    )

    cells = [(iid, pid) for iid in instances for pid in perturbation_ids]

    # Phase 2: 120s reference solves (parallel).
    n_ref = len(cells) * len(SEEDS)
    log.info("Phase 2/4: %d reference solves at %.0fs each", n_ref, REFERENCE_TIME_LIMIT)
    t1 = time.monotonic()
    ref_jobs = [
        delayed(_esc_reference_solve)(
            iid, pid, seed, REFERENCE_TIME_LIMIT, BASELINE_TIME_LIMIT,
            instance_dir, checkpoint_root,
        )
        for (iid, pid) in cells
        for seed in SEEDS
    ]
    raw_refs = Parallel(n_jobs=n_jobs, backend="loky", verbose=5)(ref_jobs)
    refs_by_cell: dict[tuple[str, str], dict[int, VRPTWSolveResult]] = {}
    failed_ref_keys: list[tuple[str, str, int]] = []
    for iid, pid, seed, res, failed in raw_refs:
        if failed or res is None:
            failed_ref_keys.append((iid, pid, seed))
            continue
        refs_by_cell.setdefault((iid, pid), {})[seed] = res
    runtime_reference = time.monotonic() - t1
    log.info(
        "Phase 2/4 done in %.1fs: %d solves succeeded, %d failed",
        runtime_reference, n_ref - len(failed_ref_keys), len(failed_ref_keys),
    )
    failed_ref_cells = {(iid, pid) for iid, pid, _ in failed_ref_keys}
    for iid, pid in cells:
        if (iid, pid) not in failed_ref_cells and not all(
            s in refs_by_cell.get((iid, pid), {}) for s in SEEDS
        ):
            failed_ref_cells.add((iid, pid))

    # Phase 3: 10s pyvrp solves (parallel).
    py_cells = [c for c in cells if c not in failed_ref_cells]
    log.info("Phase 3/4: %d pyvrp_10s solves", len(py_cells))
    t2 = time.monotonic()
    py_jobs = [
        delayed(_esc_pyvrp10s_solve)(
            iid, pid, PYVRP10S_TIME_LIMIT, BASELINE_TIME_LIMIT,
            instance_dir, checkpoint_root,
        )
        for (iid, pid) in py_cells
    ]
    py_results = Parallel(n_jobs=n_jobs, backend="loky", verbose=5)(py_jobs)
    pyvrp10s_by_cell: dict[tuple[str, str], VRPTWSolveResult] = {}
    failed_pyvrp10s_cells: set[tuple[str, str]] = set()
    for iid, pid, res, failed in py_results:
        if failed or res is None:
            failed_pyvrp10s_cells.add((iid, pid))
            continue
        pyvrp10s_by_cell[(iid, pid)] = res
    runtime_pyvrp10s = time.monotonic() - t2
    log.info(
        "Phase 3/4 done in %.1fs: %d successful, %d failed",
        runtime_pyvrp10s, len(pyvrp10s_by_cell), len(failed_pyvrp10s_cells),
    )

    # Phase 4: assemble rows.
    log.info(
        "Phase 4/4: assembling rows for %d cells (%d skipped)",
        len(py_cells), len(failed_ref_cells),
    )
    t3 = time.monotonic()
    wide_rows: list[dict[str, Any]] = []
    failed_action_keys: list[tuple[str, str, str]] = []
    n_cached_rows = 0
    for iid, pid in cells:
        if (iid, pid) in failed_ref_cells:
            continue
        instance = load_vrptw_instance(iid, instance_dir)
        baseline = baselines[iid]
        spec = lookup_vrptw_perturbation(pid)
        perturbed = _apply_escalated_perturbation(
            instance, spec, baseline.solve_result,
        )
        # Non-OC families only in this probe.
        actions = actions_for_family(
            perturbed.perturbation_family, expanded=True,
        )
        avg_ref_runtime = float(np.mean([
            refs_by_cell[(iid, pid)][s].runtime_seconds for s in SEEDS
        ]))
        for action_name in actions:
            cached_row = store.load_row(iid, pid, action_name)
            if cached_row is not None:
                wide_rows.append(cached_row)
                n_cached_rows += 1
                continue
            if store.has_failure("actions", iid, pid, action=action_name):
                failed_action_keys.append((iid, pid, action_name))
                continue
            if action_name == "pyvrp_10s" and (iid, pid) in failed_pyvrp10s_cells:
                store.save_failure(
                    "actions", iid, pid, action=action_name,
                    exc=RuntimeError("pyvrp_10s skipped — Phase 3 solve failed"),
                )
                failed_action_keys.append((iid, pid, action_name))
                continue
            try:
                if action_name == "pyvrp_60s_reference":
                    res = materialize_reference_action(
                        perturbed, refs_by_cell[(iid, pid)][1],
                        time_limit_seconds=REFERENCE_TIME_LIMIT,
                    )
                elif action_name == "pyvrp_10s":
                    solve = pyvrp10s_by_cell[(iid, pid)]
                    res = _pyvrp10s_result_to_action_result(
                        perturbed, solve, time_limit_seconds=PYVRP10S_TIME_LIMIT,
                    )
                else:
                    action = _action_for_name(
                        action_name, pyvrp10s_time_limit=PYVRP10S_TIME_LIMIT,
                    )
                    res = action.apply(perturbed, baseline.routes)
                row = _build_wide_row(
                    instance=instance, spec=spec, perturbed=perturbed,
                    baseline=baseline, references=refs_by_cell[(iid, pid)],
                    action_result=res, runtime_reference_s=avg_ref_runtime,
                )
            except Exception as exc:
                store.save_failure("actions", iid, pid, action=action_name, exc=exc)
                failed_action_keys.append((iid, pid, action_name))
                log.warning("Action %s failed for %s/%s: %s",
                            action_name, iid, pid, exc)
                continue
            store.save_row(iid, pid, action_name, row)
            wide_rows.append(row)

    wide_df = pd.DataFrame(wide_rows)
    claim_rows: list[dict[str, Any]] = []
    for r in wide_rows:
        claim_rows.extend(_build_claim_rows(r))
    claim_df = pd.DataFrame(claim_rows)
    runtime_assemble = time.monotonic() - t3
    log.info(
        "Phase 4/4 done in %.1fs: wide=%d, long=%d (cached=%d, action_failures=%d)",
        runtime_assemble, len(wide_df), len(claim_df),
        n_cached_rows, len(failed_action_keys),
    )

    stats = {
        "instances": list(instances),
        "perturbation_ids": list(perturbation_ids),
        "seeds": list(SEEDS),
        "sample_seed": int(SAMPLE_SEED),
        "n_cells": len(cells),
        "n_assemble_cells": len(py_cells),
        "n_wide_rows": int(len(wide_df)),
        "n_long_rows": int(len(claim_df)),
        "n_cached_rows": int(n_cached_rows),
        "phase_baselines_seconds": float(runtime_baseline),
        "phase_references_seconds": float(runtime_reference),
        "phase_pyvrp10s_seconds": float(runtime_pyvrp10s),
        "phase_assemble_seconds": float(runtime_assemble),
        "failed_ref_keys": [
            {"instance_id": iid, "perturbation_id": pid, "seed": int(s)}
            for (iid, pid, s) in failed_ref_keys
        ],
        "failed_ref_cells": [
            {"instance_id": iid, "perturbation_id": pid}
            for (iid, pid) in sorted(failed_ref_cells)
        ],
        "failed_pyvrp10s_cells": [
            {"instance_id": iid, "perturbation_id": pid}
            for (iid, pid) in sorted(failed_pyvrp10s_cells)
        ],
        "failed_action_keys": [
            {"instance_id": iid, "perturbation_id": pid, "action": act}
            for (iid, pid, act) in failed_action_keys
        ],
    }
    RUN_STATS_JSON.write_text(json.dumps(stats, indent=2))
    return wide_df, claim_df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-jobs", type=int, default=6)
    ap.add_argument("--instance-dir", type=Path, default=None)
    args = ap.parse_args()

    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    instances = tuple(_stratified_sample())
    log.info(
        "Sample (n=%d, seed=%d): %s",
        len(instances), SAMPLE_SEED, ", ".join(instances),
    )
    perturbation_ids = ESCALATED_PERTURBATIONS

    wide_df, claim_df = run_probe(
        instances=instances,
        perturbation_ids=perturbation_ids,
        n_jobs=args.n_jobs,
        instance_dir=args.instance_dir,
    )
    wide_df.to_parquet(WIDE_PARQUET, index=False)
    claim_df.to_parquet(CLAIM_PARQUET, index=False)
    log.info("Wrote %s (%d rows)", WIDE_PARQUET, len(wide_df))
    log.info("Wrote %s (%d rows)", CLAIM_PARQUET, len(claim_df))


if __name__ == "__main__":
    main()
