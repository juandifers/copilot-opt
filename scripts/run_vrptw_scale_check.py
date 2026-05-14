#!/usr/bin/env python3
"""VRPTW 18-instance scale-check runner.

Stage 3 of the VRPTW pre-thesis push. Builds on the perturbation pilot v2
findings — uses the soft_grid only, the local-repair action for OC, and
the v2 SCHEDULE-affected-p90 metric.

Pipeline
========
1. **Baselines** (parallel, one per instance). Loaded from
   :func:`vrp_copilot_bench.vrptw.baselines.load_or_compute_baseline`
   (JSON cache at ``data/vrptw_baselines/{instance_id}.json``).
2. **References** (parallel, one per (instance, perturbation, seed)).
   Three PyVRP seeds at ``time_limit`` on the perturbed instance.
3. **Wide rows** (per (instance, perturbation, action)):
   non-OC families → ``reuse_direct`` only;
   OC family       → ``reuse_direct`` **and** ``local_repair_insert``.
4. **Long claim rows** (per (wide row, claim family)) — 4 claim families
   per action row: OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE.
5. Persist both tables as parquet + write the Stage 3 markdown report.

CLI
===
::

    python scripts/run_vrptw_scale_check.py \\
        --roster instances/vrptw_scale_check_18.txt \\
        --time-limit 60 --n-jobs 6 \\
        --out-dir data/probes \\
        --report-path prereg/vrptw_scale_check_18_report.md

    python scripts/run_vrptw_scale_check.py \\
        --instances C101 --perturbations TT_1 OC_1 \\
        --time-limit 60 --n-jobs 6 --out-stem vrptw_scale_check_smoke

The defaults match the prompt's recommended scale-check; the smoke
variant above is the Checkpoint-3 sanity run.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from collections import Counter
from dataclasses import asdict
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
    PERTURBATION_IDS,
    SCALING_FACTOR,
    SOFT_PERTURBATION_MAGNITUDES,
    SOFT_TIGHT_WINDOW_WIDTH_FRACTION,
    EvaluatedVRPTW,
    SolveConfig,
    VRPTWPerturbedInstance,
    VRPTWSolveResult,
    apply_vrptw_perturbation,
    enumerate_vrptw_perturbations,
    load_vrptw_instance,
    lookup_vrptw_perturbation,
    solve_vrptw,
)
from vrp_copilot_bench.vrptw.actions import (  # noqa: E402
    ACTION_TIER,
    ActionResult,
    CHEAP_ACTION_FOR_FAMILY,
    ConstructFeasible,
    LocalRepairInsert,
    PyvrpSolve,
    ReuseDirect,
    actions_for_family,
    cheap_action_for_family,
    materialize_reference_action,
)
from vrp_copilot_bench.vrptw.checkpoint import CheckpointStore  # noqa: E402
from vrp_copilot_bench.vrptw.solver import evaluate_vrptw_solution  # noqa: E402
from vrp_copilot_bench.vrptw.baselines import (  # noqa: E402
    CachedBaseline,
    load_or_compute_baseline,
)
from vrp_copilot_bench.vrptw.evaluation import (  # noqa: E402
    GENERALIZED_DURATION_WEIGHT,
    ReferenceStability,
    depot_horizon_scaled,
    eval_to_costs,
    generalized_cost,
    infeasibility_kind,
    median_arrival_shift_global,
    reference_stability,
    route_end_disruption_max,
)
from vrp_copilot_bench.vrptw.features import FeatureBundle, extract_features  # noqa: E402
from vrp_copilot_bench.vrptw.losses import LossBundle, compute_losses  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("vrptw_scale_check")


CLAIM_FAMILIES: tuple[str, ...] = ("OBJ", "PLAN_VALIDITY", "STRUCT", "SCHEDULE")


# ---------------------------------------------------------------------------
# Worker entry points (module-level so loky can pickle them)


def _worker_reference_solve(
    instance_id: str,
    perturbation_id: str,
    seed: int,
    time_limit: float,
    instance_dir: Path | None,
    checkpoint_root: str | None = None,
) -> tuple[str, str, int, VRPTWSolveResult | None, bool]:
    """Solve a perturbed instance with one PyVRP seed.

    Re-applies the perturbation inside the worker so the perturbed instance
    doesn't have to cross the loky boundary. With ``checkpoint_root`` set,
    the worker consults the store before computing, persists on success,
    and writes a failure record on exception.

    Returns ``(iid, pid, seed, result_or_none, failed)``. ``result_or_none``
    is the solver result on success/cache-hit and ``None`` on failure;
    ``failed`` is ``True`` only when an exception was caught (cache hits
    return ``failed=False`` even when the cached result is infeasible).
    """
    if checkpoint_root is not None:
        store = CheckpointStore(Path(checkpoint_root))
        if store.has_failure("refs", instance_id, perturbation_id, seed=seed):
            return instance_id, perturbation_id, seed, None, True
        cached = store.load_ref(instance_id, perturbation_id, seed)
        if cached is not None:
            return instance_id, perturbation_id, seed, cached, False
    else:
        store = None
    try:
        instance = load_vrptw_instance(instance_id, instance_dir)
        baseline = load_or_compute_baseline(
            instance_id, seed=1, time_limit_seconds=time_limit,
            instance_dir=instance_dir,
        )
        spec = lookup_vrptw_perturbation(perturbation_id)
        if spec.family == "ORDER_CHANGE":
            perturbed = apply_vrptw_perturbation(
                instance, spec, baseline.solve_result,
                magnitude_override=SOFT_PERTURBATION_MAGNITUDES[perturbation_id],
                tight_width_fraction=SOFT_TIGHT_WINDOW_WIDTH_FRACTION,
            )
        else:
            perturbed = apply_vrptw_perturbation(
                instance, spec, baseline.solve_result,
                magnitude_override=SOFT_PERTURBATION_MAGNITUDES[perturbation_id],
            )
        cfg = SolveConfig(time_limit_seconds=time_limit, seed=seed)
        result = solve_vrptw(perturbed, cfg)
        if store is not None:
            store.save_ref(instance_id, perturbation_id, seed, result)
        return instance_id, perturbation_id, seed, result, False
    except Exception as exc:
        if store is not None:
            store.save_failure(
                "refs", instance_id, perturbation_id, seed=seed, exc=exc,
            )
            return instance_id, perturbation_id, seed, None, True
        raise


def _ensure_baseline_warm(
    instance_id: str, time_limit: float, instance_dir: Path | None,
) -> tuple[str, CachedBaseline]:
    cb = load_or_compute_baseline(
        instance_id, seed=1, time_limit_seconds=time_limit,
        instance_dir=instance_dir,
    )
    return instance_id, cb


def _worker_pyvrp10s_solve(
    instance_id: str,
    perturbation_id: str,
    pyvrp10s_time_limit: float,
    reference_time_limit: float,
    instance_dir: Path | None,
    checkpoint_root: str | None = None,
) -> tuple[str, str, VRPTWSolveResult | None, bool]:
    """Solve the perturbed instance with PyVRP at the 10 s budget (seed 1).

    Same cache+failure semantics as :func:`_worker_reference_solve`.
    Returns ``(iid, pid, result_or_none, failed)``.
    """
    if checkpoint_root is not None:
        store = CheckpointStore(Path(checkpoint_root))
        if store.has_failure("pyvrp10s", instance_id, perturbation_id):
            return instance_id, perturbation_id, None, True
        cached = store.load_pyvrp10s(instance_id, perturbation_id)
        if cached is not None:
            return instance_id, perturbation_id, cached, False
    else:
        store = None
    try:
        instance = load_vrptw_instance(instance_id, instance_dir)
        baseline = load_or_compute_baseline(
            instance_id, seed=1, time_limit_seconds=reference_time_limit,
            instance_dir=instance_dir,
        )
        spec = lookup_vrptw_perturbation(perturbation_id)
        if spec.family == "ORDER_CHANGE":
            perturbed = apply_vrptw_perturbation(
                instance, spec, baseline.solve_result,
                magnitude_override=SOFT_PERTURBATION_MAGNITUDES[perturbation_id],
                tight_width_fraction=SOFT_TIGHT_WINDOW_WIDTH_FRACTION,
            )
        else:
            perturbed = apply_vrptw_perturbation(
                instance, spec, baseline.solve_result,
                magnitude_override=SOFT_PERTURBATION_MAGNITUDES[perturbation_id],
            )
        cfg = SolveConfig(time_limit_seconds=pyvrp10s_time_limit, seed=1)
        result = solve_vrptw(perturbed, cfg)
        if store is not None:
            store.save_pyvrp10s(instance_id, perturbation_id, result)
        return instance_id, perturbation_id, result, False
    except Exception as exc:
        if store is not None:
            store.save_failure("pyvrp10s", instance_id, perturbation_id, exc=exc)
            return instance_id, perturbation_id, None, True
        raise


# ---------------------------------------------------------------------------
# Row assembly


def _apply_soft_perturbation(
    instance, spec, baseline_solve_result,
):
    """Apply soft_grid magnitude with the soft tight-window fraction for OC."""
    if spec.family == "ORDER_CHANGE":
        return apply_vrptw_perturbation(
            instance, spec, baseline_solve_result,
            magnitude_override=SOFT_PERTURBATION_MAGNITUDES[spec.perturbation_id],
            tight_width_fraction=SOFT_TIGHT_WINDOW_WIDTH_FRACTION,
        )
    return apply_vrptw_perturbation(
        instance, spec, baseline_solve_result,
        magnitude_override=SOFT_PERTURBATION_MAGNITUDES[spec.perturbation_id],
    )


def _action_for_name(name: str, *, pyvrp10s_time_limit: float = 10.0):
    """Construct a runnable :class:`VRPTWAction` from its name.

    ``pyvrp_60s_reference`` is *not* runnable — the runner materializes it
    from reference seed 1 via :func:`materialize_reference_action`. Asking
    for it here is a programmer error.
    """
    if name == "reuse_direct":
        return ReuseDirect()
    if name == "local_repair_insert":
        return LocalRepairInsert()
    if name == "construct_feasible":
        return ConstructFeasible()
    if name == "pyvrp_10s":
        return PyvrpSolve(seed=1, time_limit_seconds=pyvrp10s_time_limit)
    raise ValueError(f"non-runnable or unknown action {name!r}")


def _actions_for_cell(family: str, *, expanded: bool) -> tuple[str, ...]:
    """Which actions get evaluated for this cell — legacy or expanded ladder."""
    return actions_for_family(family, expanded=expanded)


def _pyvrp10s_result_to_action_result(
    perturbed: VRPTWPerturbedInstance,
    solve_result: VRPTWSolveResult,
    *,
    time_limit_seconds: float,
) -> ActionResult:
    """Wrap a pre-computed pyvrp_10s solve into an :class:`ActionResult`.

    Same shape Phase 3 would produce if we ran the action serially.
    """
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
    """Reference failure label used in the wide table.

    Differs from :attr:`ReferenceStability.failure_kind` only by surfacing
    seed-1 infeasibility distinctly (it gates the primary losses).
    """
    if not stab.s1_feasible or not math.isfinite(ref_s1.objective):
        if stab.any_feasible:
            return "s1_infeasible_other_feasible"
        return "all_infeasible"
    if not stab.all_feasible:
        return "any_infeasible"
    return "none"


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

    # Coverage / repair diagnostics (only meaningful for OC, but keep
    # the columns present everywhere for a uniform schema).
    action_eval = action_result.evaluation
    coverage_feasible: bool | None
    n_unserved: int | None
    if perturbed.perturbation_family == "ORDER_CHANGE":
        coverage_feasible = bool(action_eval.is_complete)
        n_unserved = int(len(action_eval.unserved_customers))
    else:
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

    # action-vs-reuse delta is populated only on the local-repair row;
    # reuse_direct rows leave it null.
    repair_obj_delta_vs_reuse: float | None = None
    # We don't always have the reuse evaluation here — populated later
    # at write-time by pairing rows. Default to None.

    cheap = cheap_action_for_family(perturbed.perturbation_family)
    is_cheap = bool(action_result.name == cheap)

    action_dist, action_dur = eval_to_costs(action_eval)
    action_gc = generalized_cost(action_dist, action_dur)

    tier_idx, tier_label, is_middle, is_reference = ACTION_TIER[action_result.name]

    # action_valid mirrors action_feasible for ordinary actions. For the
    # materialized reference row we still use action_feasible — i.e.
    # whether reference seed 1's routes are feasible under the perturbed
    # instance. (When ref_s1 itself was infeasible, its routes carry
    # time_warp under the perturbed data, so this is True/False correctly.)
    action_valid = bool(action_eval.feasible)

    row: dict[str, Any] = {
        # identifiers
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

        # baseline / reference
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
        # struct_unstable is None on cells with no feasible reference on
        # any seed (§8.2/§12.3 amendment in PREREG_v1.1_vrptw.md).
        "reference_struct_unstable": (
            None if stab.struct_unstable is None
            else bool(stab.struct_unstable)
        ),
        "reference_failure_kind": failure_kind,

        # action evaluation
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

        # losses + bands
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

        # local repair diagnostics
        "local_repair_inserted_all": repair_inserted_all,
        "local_repair_total_insertions": repair_total_insertions,
        "local_repair_opened_new_route": repair_opened_new_route,
        "local_repair_objective_delta_vs_reuse": repair_obj_delta_vs_reuse,

        # timing/version
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
    }
    # Append features (FeatureBundle is leak-free by construction).
    row.update(feats.as_dict())
    return row


def _f_or_none(x: float | None) -> float | None:
    if x is None:
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    return float(x)


def _pair_local_repair_delta(rows: list[dict[str, Any]]) -> None:
    """Populate ``local_repair_objective_delta_vs_reuse`` on local-repair rows.

    The action layer can't compute this on its own (each row only knows
    its own action). We resolve it here by pairing the OC reuse_direct
    row with the OC local_repair_insert row in the same cell.
    """
    by_cell: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for r in rows:
        if r["perturbation_family"] != "ORDER_CHANGE":
            continue
        key = (r["instance_id"], r["perturbation_id"])
        by_cell.setdefault(key, {})[r["action"]] = r
    for key, by_action in by_cell.items():
        reuse_row = by_action.get("reuse_direct")
        repair_row = by_action.get("local_repair_insert")
        if reuse_row is None or repair_row is None:
            continue
        repair_row["local_repair_objective_delta_vs_reuse"] = float(
            repair_row["action_obj"] - reuse_row["action_obj"]
        )


# ---------------------------------------------------------------------------
# Claim long table


_FEATURE_COLUMNS: tuple[str, ...] = tuple(FeatureBundle.__annotations__.keys())


def _build_claim_rows(wide: dict[str, Any]) -> list[dict[str, Any]]:
    """One long row per claim family for a given wide row."""
    family_to_losses: dict[str, tuple[Any, str]] = {
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
        sufficient_binary: int | None
        if band == "n/a":
            sufficient_binary = None
        elif band == "easy":
            sufficient_binary = 1
        else:
            sufficient_binary = 0

        # Per-family reference_valid rules (see prompt).
        if family == "OBJ":
            reference_valid = ref_s1_valid and not wide["reference_obj_unstable"]
        elif family == "STRUCT":
            reference_valid = ref_s1_valid and not wide["reference_struct_unstable"]
        elif family == "PLAN_VALIDITY":
            reference_valid = True  # action-feasibility check
        elif family == "SCHEDULE":
            # SCHEDULE only needs seed 1 valid; STRUCT instability is a
            # diagnostic that's carried separately.
            reference_valid = ref_s1_valid
        else:  # pragma: no cover
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
        }
        for col in _FEATURE_COLUMNS:
            row[col] = wide[col]
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Pipeline


def run_scale_check(
    instances: tuple[str, ...],
    perturbation_ids: tuple[str, ...],
    seeds: tuple[int, ...],
    time_limit: float,
    n_jobs: int,
    instance_dir: Path | None,
    force_baselines: bool,
    expanded_actions: bool = False,
    pyvrp10s_time_limit: float = 10.0,
    checkpoint_dir: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the pipeline. Returns ``(wide_df, claim_long_df)``.

    When ``expanded_actions`` is False the legacy 2-action ladder runs
    (reuse + repair). When True the 5-action ladder runs: reuse, repair
    (OC only), construct_feasible, pyvrp_10s, pyvrp_60s_reference
    (materialized from reference seed 1).

    With ``checkpoint_dir`` set, every expensive solve and every wide row
    is cached on disk under that directory. On a re-run, cached results
    are loaded instead of recomputed; failed (instance, perturbation,
    seed/action) keys are skipped (their failure records live in
    ``checkpoint_dir/_failures/``).
    """
    phase_count = 4 if expanded_actions else 3
    store: CheckpointStore | None
    if checkpoint_dir is not None:
        store = CheckpointStore(Path(checkpoint_dir))
        store.mkdir()
        store.write_manifest({
            "instances": list(instances),
            "perturbation_ids": list(perturbation_ids),
            "seeds": list(seeds),
            "time_limit": float(time_limit),
            "n_jobs": int(n_jobs),
            "expanded_actions": bool(expanded_actions),
            "pyvrp10s_time_limit": float(pyvrp10s_time_limit),
        })
        checkpoint_root_str: str | None = str(Path(checkpoint_dir))
    else:
        store = None
        checkpoint_root_str = None

    # ---------- Phase 1: baselines (parallel) ----------
    log.info(
        "Phase 1/%d: baselines for %d instances (n_jobs=%d)",
        phase_count, len(instances), n_jobs,
    )
    t0 = time.monotonic()
    if force_baselines:
        for iid in instances:
            cache_path = (
                Path("data/vrptw_baselines") / f"{iid}.json"
            )
            if cache_path.exists():
                cache_path.unlink()
                log.info("Removed stale baseline cache %s", cache_path)
    baseline_jobs = [
        delayed(_ensure_baseline_warm)(iid, time_limit, instance_dir)
        for iid in instances
    ]
    baselines_list = Parallel(
        n_jobs=min(n_jobs, len(instances)), backend="loky", verbose=5,
    )(baseline_jobs)
    baselines: dict[str, CachedBaseline] = dict(baselines_list)
    runtime_baseline_total = time.monotonic() - t0
    cache_hits = sum(1 for b in baselines.values() if b.from_cache)
    log.info(
        "Phase 1/%d done: %d baselines (%d cache hits) in %.1fs",
        phase_count, len(baselines), cache_hits, runtime_baseline_total,
    )

    # ---------- Phase 2: references (parallel) ----------
    cells = [(iid, pid) for iid in instances for pid in perturbation_ids]
    n_solves = len(cells) * len(seeds)
    log.info("Phase 2/%d: %d reference solves (%d cells × %d seeds)",
             phase_count, n_solves, len(cells), len(seeds))
    t1 = time.monotonic()
    ref_jobs = [
        delayed(_worker_reference_solve)(
            iid, pid, seed, time_limit, instance_dir, checkpoint_root_str,
        )
        for (iid, pid) in cells
        for seed in seeds
    ]
    raw_refs = Parallel(n_jobs=n_jobs, backend="loky", verbose=5)(ref_jobs)
    refs_by_cell: dict[tuple[str, str], dict[int, VRPTWSolveResult]] = {}
    failed_ref_keys: list[tuple[str, str, int]] = []
    for iid, pid, seed, res, failed in raw_refs:
        if failed or res is None:
            failed_ref_keys.append((iid, pid, seed))
            continue
        refs_by_cell.setdefault((iid, pid), {})[seed] = res
    runtime_reference_total = time.monotonic() - t1
    log.info(
        "Phase 2/%d done in %.1fs: %d successful, %d failed",
        phase_count, runtime_reference_total,
        n_solves - len(failed_ref_keys), len(failed_ref_keys),
    )

    failed_ref_cells = {(iid, pid) for iid, pid, _ in failed_ref_keys}
    # Any cell missing a seed (covered by failed_ref_keys list) is dropped.
    for iid, pid in cells:
        if (iid, pid) not in failed_ref_cells and not all(
            s in refs_by_cell.get((iid, pid), {}) for s in seeds
        ):
            failed_ref_cells.add((iid, pid))

    # ---------- Phase 2b: pyvrp_10s solves (parallel) — expanded only ----------
    pyvrp10s_by_cell: dict[tuple[str, str], VRPTWSolveResult] = {}
    failed_pyvrp10s_cells: set[tuple[str, str]] = set()
    runtime_pyvrp10s_total = 0.0
    if expanded_actions:
        # Only schedule pyvrp_10s for cells whose references all succeeded —
        # the assembly loop would skip the cell anyway.
        py_cells = [c for c in cells if c not in failed_ref_cells]
        log.info(
            "Phase 3/%d: %d pyvrp_10s solves (%d cells × 1 seed, %.1fs each)",
            phase_count, len(py_cells), len(py_cells), pyvrp10s_time_limit,
        )
        t1b = time.monotonic()
        py_jobs = [
            delayed(_worker_pyvrp10s_solve)(
                iid, pid, pyvrp10s_time_limit, time_limit, instance_dir,
                checkpoint_root_str,
            )
            for (iid, pid) in py_cells
        ]
        py_results = Parallel(n_jobs=n_jobs, backend="loky", verbose=5)(py_jobs)
        for iid, pid, res, failed in py_results:
            if failed or res is None:
                failed_pyvrp10s_cells.add((iid, pid))
                continue
            pyvrp10s_by_cell[(iid, pid)] = res
        runtime_pyvrp10s_total = time.monotonic() - t1b
        log.info(
            "Phase 3/%d done in %.1fs: %d successful, %d failed",
            phase_count, runtime_pyvrp10s_total,
            len(pyvrp10s_by_cell), len(failed_pyvrp10s_cells),
        )

    # ---------- Phase 3 (legacy) / Phase 4 (expanded): assemble rows ----------
    assemble_phase = 4 if expanded_actions else 3
    n_assemble_cells = sum(1 for c in cells if c not in failed_ref_cells)
    log.info(
        "Phase %d/%d: assembling rows for %d cells (%d skipped due to ref failure)",
        assemble_phase, phase_count, n_assemble_cells, len(failed_ref_cells),
    )
    t2 = time.monotonic()
    wide_rows: list[dict[str, Any]] = []
    failed_action_keys: list[tuple[str, str, str]] = []
    n_cached_rows = 0
    for iid, pid in cells:
        if (iid, pid) in failed_ref_cells:
            continue
        instance = load_vrptw_instance(iid, instance_dir)
        baseline = baselines[iid]
        spec = lookup_vrptw_perturbation(pid)
        perturbed = _apply_soft_perturbation(instance, spec, baseline.solve_result)
        actions = _actions_for_cell(
            perturbed.perturbation_family, expanded=expanded_actions,
        )

        avg_ref_runtime = float(np.mean([
            refs_by_cell[(iid, pid)][s].runtime_seconds for s in seeds
        ]))
        for action_name in actions:
            # Row-level checkpoint.
            if store is not None:
                cached_row = store.load_row(iid, pid, action_name)
                if cached_row is not None:
                    wide_rows.append(cached_row)
                    n_cached_rows += 1
                    continue
                if store.has_failure(
                    "actions", iid, pid, action=action_name,
                ):
                    failed_action_keys.append((iid, pid, action_name))
                    continue
            # pyvrp_10s requires Phase 2b success for this cell.
            if action_name == "pyvrp_10s" and (iid, pid) in failed_pyvrp10s_cells:
                if store is not None:
                    store.save_failure(
                        "actions", iid, pid, action=action_name,
                        exc=RuntimeError(
                            "pyvrp_10s skipped — Phase 2b solve failed for this cell"
                        ),
                    )
                failed_action_keys.append((iid, pid, action_name))
                continue
            try:
                if action_name == "pyvrp_60s_reference":
                    res = materialize_reference_action(
                        perturbed, refs_by_cell[(iid, pid)][1],
                        time_limit_seconds=time_limit,
                    )
                elif action_name == "pyvrp_10s":
                    solve = pyvrp10s_by_cell[(iid, pid)]
                    res = _pyvrp10s_result_to_action_result(
                        perturbed, solve, time_limit_seconds=pyvrp10s_time_limit,
                    )
                else:
                    action = _action_for_name(
                        action_name, pyvrp10s_time_limit=pyvrp10s_time_limit,
                    )
                    res = action.apply(perturbed, baseline.routes)
                row = _build_wide_row(
                    instance=instance, spec=spec, perturbed=perturbed,
                    baseline=baseline, references=refs_by_cell[(iid, pid)],
                    action_result=res,
                    runtime_reference_s=avg_ref_runtime,
                )
            except Exception as exc:
                if store is not None:
                    store.save_failure(
                        "actions", iid, pid, action=action_name, exc=exc,
                    )
                failed_action_keys.append((iid, pid, action_name))
                log.warning(
                    "Action %s failed for %s/%s: %s",
                    action_name, iid, pid, exc,
                )
                continue
            if store is not None:
                store.save_row(iid, pid, action_name, row)
            wide_rows.append(row)

    _pair_local_repair_delta(wide_rows)
    wide_df = pd.DataFrame(wide_rows)
    claim_rows: list[dict[str, Any]] = []
    for r in wide_rows:
        claim_rows.extend(_build_claim_rows(r))
    claim_df = pd.DataFrame(claim_rows)
    runtime_assemble = time.monotonic() - t2
    log.info(
        "Phase %d/%d done in %.1fs: wide=%d rows, long=%d rows "
        "(cached_rows=%d, action_failures=%d)",
        assemble_phase, phase_count, runtime_assemble,
        len(wide_df), len(claim_df), n_cached_rows, len(failed_action_keys),
    )

    if store is not None:
        stats = {
            "phase_baselines_seconds": float(runtime_baseline_total),
            "phase_references_seconds": float(runtime_reference_total),
            "phase_pyvrp10s_seconds": float(runtime_pyvrp10s_total),
            "phase_assemble_seconds": float(runtime_assemble),
            "n_wide_rows": int(len(wide_df)),
            "n_long_rows": int(len(claim_df)),
            "n_cells": int(len(cells)),
            "n_assemble_cells": int(n_assemble_cells),
            "n_cached_rows": int(n_cached_rows),
            "baseline_cache_hits": int(cache_hits),
            "failed_ref_keys": [
                {"instance_id": iid, "perturbation_id": pid, "seed": int(seed)}
                for (iid, pid, seed) in failed_ref_keys
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
        store.write_stats(stats)

    return wide_df, claim_df


# ---------------------------------------------------------------------------
# Markdown report


def _display_path(p: Path) -> str:
    """Make a path display-friendly relative to the project root when possible."""
    try:
        return str(p.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def _band_counts(series: pd.Series) -> dict[str, int]:
    return {k: int(v) for k, v in series.value_counts(dropna=False).to_dict().items()}


_TIER_ORDER = (
    "reuse_direct",
    "local_repair_insert",
    "construct_feasible",
    "pyvrp_10s",
    "pyvrp_60s_reference",
)


def _runtime_stats(s: pd.Series) -> dict[str, float]:
    s = s.dropna()
    if not len(s):
        return {"n": 0, "mean": 0.0, "median": 0.0, "p90": 0.0, "max": 0.0}
    return {
        "n": int(len(s)),
        "mean": float(s.mean()),
        "median": float(s.median()),
        "p90": float(s.quantile(0.9)),
        "max": float(s.max()),
    }


def _build_expanded_report(
    wide_df: pd.DataFrame,
    claim_df: pd.DataFrame,
    *,
    instances: tuple[str, ...],
    perturbation_ids: tuple[str, ...],
    seeds: tuple[int, ...],
    time_limit: float,
    n_jobs: int,
    parquet_wide: Path,
    parquet_long: Path,
    runtime_total: float,
    pyvrp10s_time_limit: float,
) -> str:
    """11-section report for the expanded-action ladder run."""
    lines: list[str] = []
    push = lines.append

    push("# VRPTW 18-instance expanded-action scale-check report")
    push("")

    # ---- 1. Purpose ------------------------------------------------------
    push("## 1. Purpose")
    push("")
    push(
        "This phase tests an expanded action ladder before any 56-instance "
        "full benchmark. The previous 18-instance scale-check survived but "
        "the action set (reuse / local repair) was too thin for a strong "
        "compute-aware benchmark. Here we add three middle/reference rungs "
        "so the benchmark can answer: *given a disruption and a claim "
        "family, which level of computational response is sufficient?*"
    )
    push("")

    # ---- 2. Action ladder ------------------------------------------------
    push("## 2. Action ladder")
    push("")
    push(
        "| tier | action | role |"
    )
    push("|---|---|---|")
    push(
        "| 0 | `reuse_direct` | score baseline routes unchanged under the "
        "perturbed instance |"
    )
    push(
        "| 1 | `local_repair_insert` | OC-only — cheapest-feasible-insertion "
        "of new customers into the existing routes |"
    )
    push(
        "| 2 | `construct_feasible` | deterministic build-from-scratch "
        "insertion heuristic; ignores baseline; prebuilt-ProblemData fast "
        "path preserves the heuristic |"
    )
    push(
        f"| 3 | `pyvrp_10s` | PyVRP metaheuristic, seed=1, "
        f"{pyvrp10s_time_limit:.0f} s budget |"
    )
    push(
        f"| 4 | `pyvrp_60s_reference` | materialized from reference seed 1 "
        f"({time_limit:.0f} s budget) — no extra solve |"
    )
    push("")
    push(
        "The cheap-action rule is unchanged: non-OC families use "
        "`reuse_direct` (tier 0); ORDER_CHANGE uses `local_repair_insert` "
        "(tier 1)."
    )
    push("")

    # ---- 3. Dataset and setup --------------------------------------------
    push("## 3. Dataset and setup")
    push("")
    push(f"- **Instances** ({len(instances)}): {', '.join(instances)}")
    push(
        f"- **Perturbations** ({len(perturbation_ids)}): "
        f"{', '.join(perturbation_ids)} (soft_grid magnitudes)"
    )
    push(f"- **Seeds**: {', '.join(map(str, seeds))} (per perturbation cell)")
    push(f"- **Reference time limit per solve**: {time_limit:.0f}s")
    push(f"- **pyvrp_10s time limit**: {pyvrp10s_time_limit:.0f}s")
    push(f"- **n_jobs**: {n_jobs}")
    push(f"- **Total wall-clock**: {runtime_total:.1f}s")
    push(f"- **Wide rows**: {len(wide_df)}")
    push(f"- **Long claim rows**: {len(claim_df)}")
    n_non_oc = sum(
        1 for pid in perturbation_ids
        if PERTURBATION_FAMILY_OF[pid] != "ORDER_CHANGE"
    )
    n_oc = len(perturbation_ids) - n_non_oc
    expected_wide = len(instances) * (n_non_oc * 4 + n_oc * 5)
    expected_long = expected_wide * len(CLAIM_FAMILIES)
    push(
        f"- **Expected wide rows**: {expected_wide} "
        f"(non-OC × 4 actions + OC × 5 actions) — "
        f"{'OK' if expected_wide == len(wide_df) else 'MISMATCH'}"
    )
    push(
        f"- **Expected long rows**: {expected_long} — "
        f"{'OK' if expected_long == len(claim_df) else 'MISMATCH'}"
    )
    push("")

    # ---- 4. Data-quality checks ------------------------------------------
    push("## 4. Data-quality checks")
    push("")
    push(
        f"- Cells where all 3 reference seeds feasible: "
        f"{int(wide_df['reference_all_feasible'].sum())} / {len(wide_df)}"
    )
    push(
        f"- Cells with any reference infeasible: "
        f"{int((~wide_df['reference_all_feasible']).sum())} / {len(wide_df)}"
    )
    na_obj = int((wide_df['band_obj_distance'] == 'n/a').sum())
    na_struct = int((wide_df['band_struct'] == 'n/a').sum())
    na_sched = int((wide_df['band_schedule'] == 'n/a').sum())
    push(f"- Wide rows with `band_obj_distance=n/a`: {na_obj}")
    push(f"- Wide rows with `band_struct=n/a`:        {na_struct}")
    push(f"- Wide rows with `band_schedule=n/a`:      {na_sched}")
    push("- Action failures (action_valid=False) by action:")
    for action in _TIER_ORDER:
        sub = wide_df[wide_df["action"] == action]
        if not len(sub):
            continue
        fail = int((~sub["action_valid"]).sum())
        push(f"    - `{action}`: {fail} / {len(sub)}")
    push("")

    # ---- 5. Reference stability ------------------------------------------
    push("## 5. Reference stability")
    push("")
    push(f"- `reference_obj_unstable` rate: {wide_df['reference_obj_unstable'].mean():.3f}")
    push(f"- `reference_struct_unstable` rate: {wide_df['reference_struct_unstable'].mean():.3f}")
    ari_min = wide_df['reference_ari_min'].dropna()
    push(
        f"- median `reference_ari_min`: "
        f"{float(ari_min.median()) if len(ari_min) else float('nan'):.3f}"
    )
    by_family = wide_df.groupby("perturbation_family")[
        ["reference_obj_unstable", "reference_struct_unstable"]
    ].mean().round(3).to_dict("index")
    push("- By perturbation family (obj_unstable, struct_unstable):")
    for fam, d in by_family.items():
        push(
            f"    - {fam}: obj={d['reference_obj_unstable']:.3f}  "
            f"struct={d['reference_struct_unstable']:.3f}"
        )
    push("")

    # ---- 6. Action quality by claim family -------------------------------
    push("## 6. Action quality by claim family")
    push("")
    push("Band counts in the long claim table, by action × claim family:")
    push("")
    for fam in CLAIM_FAMILIES:
        push(f"### {fam}")
        push("")
        push("| action | easy | medium | hard | n/a |")
        push("|---|---:|---:|---:|---:|")
        sub_fam = claim_df[claim_df["claim_family"] == fam]
        for action in _TIER_ORDER:
            sub = sub_fam[sub_fam["action"] == action]
            if not len(sub):
                continue
            counts = sub["band"].value_counts().to_dict()
            push(
                f"| `{action}` | {int(counts.get('easy', 0))} | "
                f"{int(counts.get('medium', 0))} | "
                f"{int(counts.get('hard', 0))} | "
                f"{int(counts.get('n/a', 0))} |"
            )
        push("")

    # ---- 7. Runtime by action --------------------------------------------
    push("## 7. Runtime by action")
    push("")
    push("`action_runtime_s` distribution per action:")
    push("")
    push("| action | n | mean (s) | median (s) | p90 (s) | max (s) |")
    push("|---|---:|---:|---:|---:|---:|")
    for action in _TIER_ORDER:
        sub = wide_df[wide_df["action"] == action]
        if not len(sub):
            continue
        rs = _runtime_stats(sub["action_runtime_s"])
        push(
            f"| `{action}` | {rs['n']} | "
            f"{rs['mean']:.3f} | {rs['median']:.3f} | "
            f"{rs['p90']:.3f} | {rs['max']:.3f} |"
        )
    push("")

    # ---- 8. Cost/quality ladder ------------------------------------------
    push("## 8. Cost/quality ladder")
    push("")
    push(
        "For each claim family, the table shows the mean primary loss and "
        "the `sufficient_binary` rate (band ∈ {easy} ⇒ 1; medium/hard ⇒ 0; "
        "n/a ⇒ null and excluded from the rate) per action. A meaningful "
        "ladder shows monotonically decreasing loss and rising sufficiency "
        "as the tier rises."
    )
    push("")
    for fam in CLAIM_FAMILIES:
        push(f"### {fam}")
        push("")
        push("| action | n | mean loss | easy_rate (sufficient) |")
        push("|---|---:|---:|---:|")
        sub_fam = claim_df[claim_df["claim_family"] == fam]
        for action in _TIER_ORDER:
            sub = sub_fam[sub_fam["action"] == action]
            if not len(sub):
                continue
            loss_s = sub["loss"].dropna()
            mean_loss = float(loss_s.mean()) if len(loss_s) else float("nan")
            suff = sub["sufficient_binary"].dropna()
            suff_rate = float(suff.mean()) if len(suff) else float("nan")
            mean_s = "n/a" if math.isnan(mean_loss) else f"{mean_loss:.4f}"
            suff_s = "n/a" if math.isnan(suff_rate) else f"{suff_rate:.3f}"
            push(f"| `{action}` | {len(sub)} | {mean_s} | {suff_s} |")
        push("")

    # ---- 9. ORDER_CHANGE analysis ----------------------------------------
    push("## 9. ORDER_CHANGE analysis")
    push("")
    oc = wide_df[wide_df["perturbation_family"] == "ORDER_CHANGE"]
    push(
        f"Total OC wide rows: **{len(oc)}** "
        f"({n_oc} OC perturbations × {len(instances)} instances × 5 actions "
        f"= {n_oc * len(instances) * 5})"
    )
    push("")
    push(
        "| action | rows | coverage_feasible | action_feasible | "
        "infeasibility_kind (non-`none`) |"
    )
    push("|---|---:|---:|---:|---|")
    for action in _TIER_ORDER:
        sub = oc[oc["action"] == action]
        if not len(sub):
            continue
        cov = float(sub["coverage_feasible"].mean())
        feas = float(sub["action_feasible"].mean())
        kinds = sub.loc[sub["infeasibility_kind"] != "none", "infeasibility_kind"]
        kinds_str = json.dumps(
            {k: int(v) for k, v in kinds.value_counts().to_dict().items()}
        ) if len(kinds) else "{}"
        push(
            f"| `{action}` | {len(sub)} | {cov:.3f} | {feas:.3f} | "
            f"{kinds_str} |"
        )
    push("")
    push("OC bands by action (cheap-action `local_repair_insert` first):")
    push("")
    push("| action | OBJ easy | STRUCT easy | SCHEDULE easy | PV easy |")
    push("|---|---:|---:|---:|---:|")
    for action in _TIER_ORDER:
        sub = oc[oc["action"] == action]
        if not len(sub):
            continue
        push(
            f"| `{action}` | "
            f"{int((sub['band_obj_distance'] == 'easy').sum())} | "
            f"{int((sub['band_struct'] == 'easy').sum())} | "
            f"{int((sub['band_schedule'] == 'easy').sum())} | "
            f"{int((sub['band_plan_validity'] == 'easy').sum())} |"
        )
    push("")

    # ---- 10. Middle-action value -----------------------------------------
    push("## 10. Middle-action value")
    push("")
    push(
        "Comparisons between adjacent ladder rungs across all 4 claim "
        "families (long-table band-easy rates):"
    )
    push("")
    push(
        "| comparison | OBJ Δeasy% | PV Δeasy% | STRUCT Δeasy% | SCHEDULE Δeasy% |"
    )
    push("|---|---:|---:|---:|---:|")
    pairs = [
        ("reuse_direct → construct_feasible",
         "reuse_direct", "construct_feasible"),
        ("construct_feasible → pyvrp_10s",
         "construct_feasible", "pyvrp_10s"),
        ("pyvrp_10s → pyvrp_60s_reference",
         "pyvrp_10s", "pyvrp_60s_reference"),
    ]

    def _easy_rate(action: str, fam: str) -> float:
        sub = claim_df[(claim_df["action"] == action) &
                       (claim_df["claim_family"] == fam)]
        if not len(sub):
            return float("nan")
        return float((sub["band"] == "easy").mean())

    for label, a, b in pairs:
        cells = []
        for fam in CLAIM_FAMILIES:
            ra = _easy_rate(a, fam)
            rb = _easy_rate(b, fam)
            if math.isnan(ra) or math.isnan(rb):
                cells.append("n/a")
            else:
                cells.append(f"{(rb - ra) * 100:+.1f}")
        push(f"| {label} | " + " | ".join(cells) + " |")
    push("")
    # Cases where pyvrp_10s rescues a cheap-action failure.
    cheap_rows = wide_df[wide_df["is_cheap_action"]]
    if len(cheap_rows):
        py10s = wide_df[wide_df["action"] == "pyvrp_10s"]
        cheap_keys = cheap_rows.set_index(["instance_id", "perturbation_id"])
        py10s_keys = py10s.set_index(["instance_id", "perturbation_id"])
        common = cheap_keys.index.intersection(py10s_keys.index)
        if len(common):
            cheap_pv_hard = cheap_keys.loc[
                common, "band_plan_validity"
            ].eq("hard")
            py10s_pv_easy = py10s_keys.loc[
                common, "band_plan_validity"
            ].eq("easy")
            rescued = int((cheap_pv_hard & py10s_pv_easy).sum())
            push(
                f"- Cells where cheap action gave PV=hard but pyvrp_10s "
                f"recovered PV=easy: **{rescued} / {len(common)}** "
                f"({100 * rescued / len(common):.1f}%)"
            )
            ref = wide_df[wide_df["action"] == "pyvrp_60s_reference"]
            ref_keys = ref.set_index(["instance_id", "perturbation_id"])
            common2 = py10s_keys.index.intersection(ref_keys.index)
            if len(common2):
                py10s_pv_hard = py10s_keys.loc[
                    common2, "band_plan_validity"
                ].eq("hard")
                ref_pv_easy = ref_keys.loc[
                    common2, "band_plan_validity"
                ].eq("easy")
                still_short = int(py10s_pv_hard.sum())
                push(
                    f"- Cells where even pyvrp_10s gave PV=hard: "
                    f"**{still_short} / {len(common2)}** — of which "
                    f"pyvrp_60s_reference recovered: "
                    f"{int((py10s_pv_hard & ref_pv_easy).sum())}"
                )
    push("")

    # ---- 11. Recommendation ----------------------------------------------
    push("## 11. Recommendation")
    push("")
    push(
        "Programmatic answers to the prompt's recommendation questions. "
        "Use these numbers; final prose is for the user."
    )
    push("")
    push("Headline aggregates:")
    push("")
    push("| metric | value |")
    push("|---|---:|")
    push(f"| wide rows | {len(wide_df)} |")
    push(f"| long claim rows | {len(claim_df)} |")
    push(f"| reference_struct_unstable rate | {wide_df['reference_struct_unstable'].mean():.3f} |")
    push(f"| reference_obj_unstable rate | {wide_df['reference_obj_unstable'].mean():.3f} |")
    push(f"| wall-clock | {runtime_total:.0f}s |")
    push("")
    push(f"- Wide parquet: `{_display_path(parquet_wide)}`")
    push(f"- Long parquet: `{_display_path(parquet_long)}`")
    push("")
    return "\n".join(lines)


def _build_report(
    wide_df: pd.DataFrame,
    claim_df: pd.DataFrame,
    *,
    instances: tuple[str, ...],
    perturbation_ids: tuple[str, ...],
    seeds: tuple[int, ...],
    time_limit: float,
    n_jobs: int,
    parquet_wide: Path,
    parquet_long: Path,
    runtime_total: float,
    expanded_actions: bool = False,
    pyvrp10s_time_limit: float = 10.0,
) -> str:
    """Build the markdown report (11 sections per the prompt).

    Branches on ``expanded_actions``: legacy mode keeps the original
    sections, expanded mode reorganizes into the ladder/runtime/cost-
    quality view requested for the expanded-actions run.
    """
    if expanded_actions:
        return _build_expanded_report(
            wide_df, claim_df,
            instances=instances, perturbation_ids=perturbation_ids,
            seeds=seeds, time_limit=time_limit, n_jobs=n_jobs,
            parquet_wide=parquet_wide, parquet_long=parquet_long,
            runtime_total=runtime_total,
            pyvrp10s_time_limit=pyvrp10s_time_limit,
        )

    lines: list[str] = []
    push = lines.append

    push(f"# VRPTW 18-instance scale-check report")
    push("")
    push("## 1. Purpose")
    push("")
    push(
        "This is an 18-instance scale-check before committing to a full "
        "VRPTW thesis benchmark. It uses the soft_grid from perturbation "
        "pilot v2 and exercises both cheap actions (`reuse_direct` for "
        "TRAVEL_TIME/TIME_WINDOW/SERVICE_TIME, `local_repair_insert` for "
        "ORDER_CHANGE)."
    )
    push("")
    push("## 2. Architecture changes")
    push("")
    push(
        "- New `src/vrp_copilot_bench/vrptw/` package — canonical import "
        "surface for new VRPTW code. Legacy paths "
        "(`vrp_copilot_bench.vrptw_instances`, `.vrptw_perturbations`, "
        "`.solvers.pyvrp_vrptw_wrapper`) untouched and still imported by the "
        "v1/v2 pilots."
    )
    push(
        "- `vrptw/baselines.py`: JSON cache at "
        "`data/vrptw_baselines/{id}.json`; cache key is "
        "`(instance_id, seed, time_limit_seconds, pyvrp_version)`."
    )
    push(
        "- `vrptw/actions.py`: `VRPTWAction` protocol + `ReuseDirect`, "
        "`LocalRepairInsert`. `cheap_action_for_family` is the canonical "
        "rule: ORDER_CHANGE → `local_repair_insert`, else `reuse_direct`."
    )
    push(
        "- `vrptw/evaluation.py`: ARI, infeasibility-kind, reference-stability, "
        "schedule shifts, route-end-disruption, generalized cost."
    )
    push(
        "- `vrptw/features.py`: leak-free feature extraction "
        "(baseline + perturbation + action only — no reference outputs)."
    )
    push(
        "- `vrptw/losses.py`: OBJ/PV/STRUCT/SCHEDULE primary losses "
        "and bands per spec."
    )
    push(
        "- Wide table = one row per (instance, perturbation, action); "
        "long claim table = 4 rows per wide row (one per claim family)."
    )
    push("")
    push("## 3. Dataset and setup")
    push("")
    push(f"- **Instances** ({len(instances)}): {', '.join(instances)}")
    push(
        f"- **Perturbations** ({len(perturbation_ids)}): "
        f"{', '.join(perturbation_ids)} (soft_grid magnitudes)"
    )
    push(f"- **Seeds**: {', '.join(map(str, seeds))} (per perturbation cell)")
    push(f"- **Time limit per solve**: {time_limit:.0f}s")
    push(f"- **n_jobs**: {n_jobs}")
    push(f"- **Total wall-clock**: {runtime_total:.1f}s")
    push(f"- **Wide rows**: {len(wide_df)}")
    push(f"- **Long claim rows**: {len(claim_df)}")
    n_non_oc = sum(
        1 for pid in perturbation_ids
        if PERTURBATION_FAMILY_OF[pid] != "ORDER_CHANGE"
    )
    n_oc = len(perturbation_ids) - n_non_oc
    expected_wide = len(instances) * (n_non_oc * 1 + n_oc * 2)
    expected_long = expected_wide * len(CLAIM_FAMILIES)
    push(
        f"- **Expected wide rows**: {expected_wide} "
        f"(non-OC × 1 action + OC × 2 actions) — "
        f"{'OK' if expected_wide == len(wide_df) else 'MISMATCH'}"
    )
    push(
        f"- **Expected long rows**: {expected_long} — "
        f"{'OK' if expected_long == len(claim_df) else 'MISMATCH'}"
    )
    push("")
    push("## 4. Data-quality checks")
    push("")
    null_obj = int(wide_df["loss_obj_distance"].isna().sum())
    null_struct = int(wide_df["loss_struct"].isna().sum())
    null_sched = int(wide_df["loss_schedule"].isna().sum())
    push(f"- Wide rows with null `loss_obj_distance`: {null_obj}")
    push(f"- Wide rows with null `loss_struct`: {null_struct}")
    push(f"- Wide rows with null `loss_schedule`: {null_sched}")
    refs_all_feas = int(wide_df["reference_all_feasible"].sum())
    refs_any_infeas = int((~wide_df["reference_all_feasible"]).sum())
    push(
        f"- Cells where all 3 reference seeds feasible: {refs_all_feas} / "
        f"{len(wide_df)}"
    )
    push(
        f"- Cells with any reference infeasible: {refs_any_infeas} / "
        f"{len(wide_df)}"
    )
    push(
        "- Band-n/a counts by family: "
        + "; ".join(
            f"{c}: " + json.dumps({k: v for k, v in _band_counts(wide_df[c]).items() if k == 'n/a'})
            for c in ("band_obj_distance", "band_obj_generalized", "band_struct", "band_schedule")
        )
    )
    push(f"- Baseline cache files: `data/vrptw_baselines/*.json` (one per instance)")
    push("")
    push("## 5. Reference stability")
    push("")
    push(f"- `reference_obj_unstable` rate: {wide_df['reference_obj_unstable'].mean():.3f}")
    push(f"- `reference_struct_unstable` rate: {wide_df['reference_struct_unstable'].mean():.3f}")
    ari_min = wide_df["reference_ari_min"].dropna()
    push(
        f"- median `reference_ari_min`: "
        f"{float(ari_min.median()) if len(ari_min) else float('nan'):.3f}"
    )
    by_family = wide_df.groupby("perturbation_family")[
        ["reference_obj_unstable", "reference_struct_unstable"]
    ].mean().round(3).to_dict("index")
    push("- By perturbation family (obj_unstable, struct_unstable):")
    for fam, d in by_family.items():
        push(
            f"    - {fam}: "
            f"obj={d['reference_obj_unstable']:.3f}  "
            f"struct={d['reference_struct_unstable']:.3f}"
        )
    push("")
    push("## 6. Wide-table action results")
    push("")
    for action_name, sub in wide_df.groupby("action"):
        push(f"### {action_name} ({len(sub)} rows)")
        for col, label in (
            ("band_plan_validity", "PLAN_VALIDITY"),
            ("band_struct", "STRUCT"),
            ("band_schedule", "SCHEDULE"),
            ("band_obj_distance", "OBJ (distance)"),
            ("band_obj_generalized", "OBJ (generalized)"),
        ):
            push(f"- {label}: {json.dumps(_band_counts(sub[col]))}")
        push("")
    push("## 7. Cheap-action results")
    push("")
    cheap = claim_df[claim_df["is_cheap_action"]].copy()
    push(f"Long-table rows where `is_cheap_action=True`: **{len(cheap)}**")
    push("")
    push("Bands by claim_family × perturbation_family:")
    for claim in CLAIM_FAMILIES:
        push(f"- **{claim}**")
        sub = cheap[cheap["claim_family"] == claim]
        for fam, fsub in sub.groupby("perturbation_family"):
            push(f"    - {fam}: {json.dumps(_band_counts(fsub['band']))}")
    push("")
    push("## 8. ORDER_CHANGE and local repair")
    push("")
    oc_rows = wide_df[wide_df["perturbation_family"] == "ORDER_CHANGE"]
    reuse_rows = oc_rows[oc_rows["action"] == "reuse_direct"]
    repair_rows = oc_rows[oc_rows["action"] == "local_repair_insert"]
    if len(reuse_rows):
        push(
            f"- OC × reuse_direct rows with coverage failure: "
            f"{int((reuse_rows['infeasibility_kind'] == 'coverage').sum())} / "
            f"{len(reuse_rows)}"
        )
    if len(repair_rows):
        push(
            f"- OC × local_repair_insert `coverage_feasible=True` rate: "
            f"{float(repair_rows['coverage_feasible'].mean()):.3f}"
        )
        push(
            f"- OC × local_repair_insert `action_feasible=True` rate: "
            f"{float(repair_rows['action_feasible'].mean()):.3f}"
        )
        push(
            f"- OC × local_repair_insert infeasibility kinds: "
            f"{json.dumps(_band_counts(repair_rows['infeasibility_kind']))}"
        )
        delta = repair_rows["local_repair_objective_delta_vs_reuse"].dropna()
        if len(delta):
            push(
                f"- Mean `local_repair_objective_delta_vs_reuse` "
                f"(vs OC reuse_direct on same cell): "
                f"{float(delta.mean()):.1f}"
            )
    push("")
    push("## 9. SCHEDULE v2 analysis")
    push("")
    sched = wide_df["loss_schedule"].dropna()
    if len(sched):
        push(
            f"- `loss_schedule` (affected-p90) distribution: "
            f"min={sched.min():.4f}, median={sched.median():.4f}, "
            f"p90={sched.quantile(0.9):.4f}, max={sched.max():.4f}"
        )
    tw_feas = wide_df[wide_df["action_feasible"]]
    if len(tw_feas):
        non_easy = (tw_feas["band_schedule"].isin({"medium", "hard"})).mean()
        push(
            f"- Time-feasible rows where SCHEDULE is medium/hard: "
            f"{float(non_easy):.3f} ({int((tw_feas['band_schedule'].isin({'medium','hard'})).sum())} / {len(tw_feas)})"
        )
    push("")
    push("## 10. Feature sanity")
    push("")
    for col in (
        "affected_min_slack", "affected_total_wait",
        "action_time_warp",
        "action_obj_delta_pct", "action_generalized_delta_pct",
    ):
        s = wide_df[col].dropna()
        if not len(s):
            push(f"- `{col}`: n=0 (all NaN)")
            continue
        push(
            f"- `{col}`: n={len(s)}, "
            f"min={float(s.min()):.4g}, "
            f"median={float(s.median()):.4g}, "
            f"mean={float(s.mean()):.4g}, "
            f"max={float(s.max()):.4g}"
        )
    push("")
    push("## 11. Recommendation")
    push("")
    push(
        "Programmatic answers to the prompt's recommendation questions. "
        "Use these numbers; the prose interpretation is for the user to write."
    )
    pv_easy = float(wide_df["band_plan_validity"].eq("easy").mean())
    struct_dist = {k: int(v) for k, v in
                   wide_df["band_struct"].value_counts(dropna=False).items()}
    sched_dist = {k: int(v) for k, v in
                  wide_df["band_schedule"].value_counts(dropna=False).items()}
    push(f"- Overall `band_plan_validity=easy` rate: {pv_easy:.3f}")
    push(f"- `band_struct` distribution: {json.dumps(struct_dist)}")
    push(f"- `band_schedule` (affected-p90, primary) distribution: {json.dumps(sched_dist)}")
    push(
        f"- Reference structural instability rate: "
        f"{float(wide_df['reference_struct_unstable'].mean()):.3f}"
    )
    push("")
    push(f"- Wide parquet: `{_display_path(parquet_wide)}`")
    push(f"- Long parquet: `{_display_path(parquet_long)}`")
    push("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI


def _read_roster(roster_path: Path) -> tuple[str, ...]:
    lines = []
    for raw in roster_path.read_text().splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return tuple(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_vrptw_scale_check",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--roster", type=Path, default=Path("instances/vrptw_scale_check_18.txt"),
        help="Roster file (one instance per line). Ignored if --instances given.",
    )
    p.add_argument(
        "--instances", nargs="+", default=None, metavar="ID",
        help="Override the roster with explicit instance IDs.",
    )
    p.add_argument(
        "--perturbations", nargs="+", default=None, metavar="PID",
        help="Subset of perturbations to run (default: all 16 soft_grid IDs).",
    )
    p.add_argument(
        "--seeds", nargs="+", type=int, default=[1, 2, 3],
        help="PyVRP seeds for reference solves (default: 1 2 3).",
    )
    p.add_argument("--time-limit", type=float, default=60.0)
    p.add_argument("--n-jobs", type=int, default=6)
    p.add_argument(
        "--instance-dir", type=Path, default=None,
        help="Override VRPTW instance directory.",
    )
    p.add_argument(
        "--out-dir", type=Path, default=Path("data/probes"),
        help="Where the two parquet outputs are written.",
    )
    p.add_argument(
        "--out-stem", default="vrptw_scale_check_18",
        help="Filename stem; produces <stem>.parquet and <stem>_claim_rows.parquet.",
    )
    p.add_argument(
        "--report-path", type=Path,
        default=Path("prereg/vrptw_scale_check_18_report.md"),
    )
    p.add_argument(
        "--force-baselines", action="store_true",
        help="Recompute baselines even if a matching cache file exists.",
    )
    p.add_argument(
        "--expanded-actions", action="store_true",
        help=(
            "Run the expanded action ladder (reuse_direct, "
            "local_repair_insert, construct_feasible, pyvrp_10s, "
            "pyvrp_60s_reference). Default: legacy 2-action set."
        ),
    )
    p.add_argument(
        "--pyvrp10s-time-limit", type=float, default=10.0,
        help="Time budget (seconds) for the pyvrp_10s action (default 10.0).",
    )
    p.add_argument(
        "--checkpoint-dir", type=Path, default=None,
        help=(
            "Optional directory for per-key resumability. When set, "
            "expensive solves and wide rows are cached on disk and "
            "failures are recorded under _failures/."
        ),
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    instances = (
        tuple(args.instances) if args.instances else _read_roster(args.roster)
    )
    if not instances:
        log.error("No instances to run.")
        return 2
    pids = (
        tuple(args.perturbations) if args.perturbations else tuple(PERTURBATION_IDS)
    )
    for pid in pids:
        if pid not in PERTURBATION_FAMILY_OF:
            log.error("Unknown perturbation id %r", pid)
            return 2
    seeds = tuple(int(s) for s in args.seeds)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_wide = args.out_dir / f"{args.out_stem}.parquet"
    parquet_long = args.out_dir / f"{args.out_stem}_claim_rows.parquet"

    log.info(
        "Scale-check: instances=%d perturbations=%d seeds=%d time_limit=%.1fs n_jobs=%d",
        len(instances), len(pids), len(seeds), args.time_limit, args.n_jobs,
    )
    t0 = time.monotonic()
    wide_df, claim_df = run_scale_check(
        instances=instances,
        perturbation_ids=pids,
        seeds=seeds,
        time_limit=args.time_limit,
        n_jobs=args.n_jobs,
        instance_dir=args.instance_dir,
        force_baselines=args.force_baselines,
        expanded_actions=args.expanded_actions,
        pyvrp10s_time_limit=args.pyvrp10s_time_limit,
        checkpoint_dir=args.checkpoint_dir,
    )
    runtime_total = time.monotonic() - t0

    wide_df.to_parquet(parquet_wide, index=False)
    claim_df.to_parquet(parquet_long, index=False)
    log.info("Wrote %s (%d rows)", parquet_wide, len(wide_df))
    log.info("Wrote %s (%d rows)", parquet_long, len(claim_df))

    report = _build_report(
        wide_df, claim_df,
        instances=instances, perturbation_ids=pids, seeds=seeds,
        time_limit=args.time_limit, n_jobs=args.n_jobs,
        parquet_wide=parquet_wide, parquet_long=parquet_long,
        runtime_total=runtime_total,
        expanded_actions=args.expanded_actions,
        pyvrp10s_time_limit=args.pyvrp10s_time_limit,
    )
    args.report_path.write_text(report)
    log.info("Wrote report %s (%d chars)", args.report_path, len(report))

    print(f"\nRows wide:  {len(wide_df)}")
    print(f"Rows long:  {len(claim_df)}")
    print(f"Wall-clock: {runtime_total:.1f}s")
    print(f"Wide parquet: {parquet_wide}")
    print(f"Long parquet: {parquet_long}")
    print(f"Report:       {args.report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
