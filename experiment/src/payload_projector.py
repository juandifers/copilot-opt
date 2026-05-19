"""Project an executed action's EvaluatedVRPTW into a family-specific payload.

For each prompt in ``experiment/data/prompts.csv`` the runner needs:
1. The perturbed instance for the cell's (instance_id, perturbation_id).
2. The baseline routes (seed=1, time-limit per the cached baseline).
3. The action's executed result (per ``action_taken`` column).
4. The projected payload matching the family schema at
   ``experiment/configs/payload_schemas.json``.

This module re-runs the action on the fly. All actions are deterministic
under (instance, perturbation, baseline_routes, seed=1) so the projection
is reproducible across runs. The expensive case is ``pyvrp_10s`` (10s
per call); ``reuse_direct`` and ``local_repair_insert`` complete in
milliseconds.

Caching: actions are cached in-process by (dataset, instance_id,
perturbation_id, action). Same-process duplicate invocations (e.g.,
several prompts sharing a cell) hit the cache. No on-disk caching —
re-running the script re-derives from instances + perturbations as a
matter of methodological cleanliness.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# Make sure src/ is importable.
import sys
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))

from vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper import (  # noqa: E402
    SCALING_FACTOR,
    EvaluatedVRPTW,
    SolveConfig,
)
from vrp_copilot_bench.vrptw.actions import (  # noqa: E402
    LocalRepairInsert,
    PyvrpSolve,
    ReuseDirect,
)
from vrp_copilot_bench.vrptw.baselines import load_or_compute_baseline  # noqa: E402
from vrp_copilot_bench.vrptw.instances import load_vrptw_instance  # noqa: E402
from vrp_copilot_bench.vrptw_perturbations import (  # noqa: E402
    apply_vrptw_perturbation,
    lookup_vrptw_perturbation,
)

SOLOMON_INSTANCE_DIR = _REPO / "data" / "vrptw_instances"
HOMBERGER_INSTANCE_DIR = _REPO / "data" / "vrptw_instances" / "homberger200"
BASELINE_DIR = _REPO / "data" / "vrptw_baselines"
STAGE_A_PARQUET = _REPO / "data" / "stage_a_vrptw_consolidated.parquet"
HOMBERGER_PARQUET = _REPO / "data" / "homberger_probe_cells_merged.parquet"

PAYLOAD_FAMILY_KEY = {
    "OBJ": "OBJ",
    "PLAN_VALIDITY": "PV",
    "STRUCT": "STRUCT",
    "SCHEDULE": "SCHEDULE",
}


@dataclass(frozen=True)
class ProjectedAction:
    """Cached output of an action execution + its projected metadata."""
    family: str
    evaluation: EvaluatedVRPTW
    baseline_objective: float  # already unscaled (published units)
    routes: list[list[int]]


# In-process cache keyed by (dataset, instance_id, perturbation_id, action_name).
_ACTION_CACHE: dict[tuple[str, str, str, str], ProjectedAction] = {}


def _instance_dir_for(dataset: str) -> Path:
    if dataset == "Solomon":
        return SOLOMON_INSTANCE_DIR
    if dataset == "Homberger":
        return HOMBERGER_INSTANCE_DIR
    raise ValueError(f"unknown dataset {dataset!r}")


def _load_baseline_time_limit(instance_id: str) -> float:
    """Read the cached baseline's time_limit_seconds.

    The baseline cache was populated by Stage A / the Homberger probe at
    instance-specific budgets (60s Solomon, 120s/180s Homberger). We
    re-use whatever was cached, asserting only seed=1.
    """
    path = BASELINE_DIR / f"{instance_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"baseline cache missing: {path}. "
            f"Re-run the baseline solve before the experiment."
        )
    entry = json.loads(path.read_text())
    if int(entry.get("seed", -1)) != 1:
        raise ValueError(
            f"baseline {path} has seed={entry.get('seed')}; expected 1"
        )
    return float(entry["time_limit_seconds"])


def _baseline_obj_from_parquet(dataset: str, instance_id: str,
                               perturbation_id: str) -> float:
    """Look up Stage A's published-unit baseline_obj for this cell."""
    path = STAGE_A_PARQUET if dataset == "Solomon" else HOMBERGER_PARQUET
    df = pd.read_parquet(path)
    sub = df[(df.instance_id == instance_id) &
             (df.perturbation_id == perturbation_id)]
    if len(sub) == 0:
        raise KeyError(
            f"no parquet row for ({instance_id!r}, {perturbation_id!r}) in {path}"
        )
    # baseline_obj is in the solver's scaled units (×10); the schema
    # demands the unscaled / published unit. Divide.
    return float(sub.iloc[0]["baseline_obj"]) / SCALING_FACTOR


def run_action(dataset: str, instance_id: str, perturbation_id: str,
               action_name: str) -> ProjectedAction:
    """Execute the action on a fresh perturbed instance; return its evaluation.

    Cached in-process. The action is deterministic under (instance,
    perturbation, baseline, seed=1).
    """
    key = (dataset, instance_id, perturbation_id, action_name)
    if key in _ACTION_CACHE:
        return _ACTION_CACHE[key]

    instance_dir = _instance_dir_for(dataset)
    instance = load_vrptw_instance(instance_id, instance_dir)

    baseline_tl = _load_baseline_time_limit(instance_id)
    baseline = load_or_compute_baseline(
        instance_id,
        seed=1,
        time_limit_seconds=baseline_tl,
        baseline_dir=BASELINE_DIR,
        instance_dir=instance_dir,
    )

    spec = lookup_vrptw_perturbation(perturbation_id)
    perturbed = apply_vrptw_perturbation(instance, spec, baseline.solve_result)

    if action_name == "reuse_direct":
        result = ReuseDirect().apply(perturbed, baseline.routes)
    elif action_name == "local_repair_insert":
        result = LocalRepairInsert().apply(perturbed, baseline.routes)
    elif action_name == "pyvrp_10s":
        result = PyvrpSolve(seed=1, time_limit_seconds=10.0).apply(
            perturbed, baseline.routes,
        )
    else:
        raise ValueError(f"unsupported action_taken {action_name!r}")

    baseline_obj_published = float(baseline.objective) / SCALING_FACTOR

    projected = ProjectedAction(
        family="",  # set per-prompt by the projector
        evaluation=result.evaluation,
        baseline_objective=baseline_obj_published,
        routes=[list(r) for r in result.routes if r],
    )
    _ACTION_CACHE[key] = projected
    return projected


# ---------------------------------------------------------------------------
# Family-specific payload projections


def _project_obj(ev: EvaluatedVRPTW, baseline_obj_published: float) -> dict:
    action_obj = round(float(ev.objective) / SCALING_FACTOR, 2)
    baseline_obj = round(baseline_obj_published, 2)
    delta_abs = round(action_obj - baseline_obj, 2)
    delta_pct = round(
        100.0 * (action_obj - baseline_obj) / baseline_obj, 2,
    ) if baseline_obj != 0 else 0.0
    return {
        "units": {"objective": "solomon_distance"},
        "action_objective": action_obj,
        "baseline_objective": baseline_obj,
        "objective_delta_absolute": delta_abs,
        "objective_delta_percent": delta_pct,
    }


def _project_pv(ev: EvaluatedVRPTW) -> dict:
    is_complete = bool(ev.is_complete)
    capacity_ok = bool(ev.feasible_capacity_only)
    tw_ok = bool(ev.feasible_tw_only)
    if is_complete and capacity_ok and tw_ok:
        kind = "none"
    elif not is_complete:
        kind = "coverage"
    elif not capacity_ok and not tw_ok:
        kind = "both"
    elif not capacity_ok:
        kind = "capacity"
    elif not tw_ok:
        kind = "time_window"
    else:
        kind = "none"
    return {
        "feasible": bool(ev.feasible),
        "feasibility_breakdown": {
            "capacity_ok": capacity_ok,
            "time_windows_ok": tw_ok,
            "coverage_ok": is_complete,
        },
        "infeasibility_kind": kind,
        "n_unserved_customers": int(len(ev.unserved_customers)),
        "unserved_customer_ids": [int(c) for c in ev.unserved_customers],
    }


def _project_struct(ev: EvaluatedVRPTW) -> dict:
    # ev.route_summaries carries route_idx; ev.routes is a parallel list
    # in solver enumeration order. Filter out empty routes.
    routes = []
    for rs in ev.route_summaries:
        if rs.n_customers == 0:
            continue
        ridx = int(rs.route_idx)
        # find the matching route in ev.routes by index alignment.
        # ev.route_summaries is one-to-one with ev.routes (post-filter).
        # Re-derive customer_ids directly from per_customer_schedule for
        # safety against assumption drift.
        cids = [int(c) for c, vs in ev.per_customer_schedule.items()
                if int(vs.route_idx) == ridx]
        # Preserve solver-order. Each VisitSchedule has start_service,
        # so order customers by start_service ascending.
        cids = sorted(cids, key=lambda c: int(ev.per_customer_schedule[c].start_service))
        if cids:
            routes.append({"route_idx": ridx, "customer_ids": cids})
    return {
        "n_routes": len(routes),
        "routes": routes,
    }


def _project_schedule(ev: EvaluatedVRPTW) -> dict:
    late_ids = sorted(
        int(c) for c, vs in ev.per_customer_schedule.items()
        if int(vs.time_warp) > 0
    )
    route_end_times = []
    for rs in ev.route_summaries:
        if rs.n_customers == 0:
            continue
        route_end_times.append({
            "route_idx": int(rs.route_idx),
            "end_time": round(float(rs.end_time) / SCALING_FACTOR, 1),
            "has_time_warp": bool(rs.has_time_warp),
        })
    customer_schedule = []
    for cid, vs in sorted(ev.per_customer_schedule.items()):
        customer_schedule.append({
            "customer_id": int(cid),
            "route_idx": int(vs.route_idx),
            "arrival": round(float(vs.arrival) / SCALING_FACTOR, 1),
            "start_service": round(float(vs.start_service) / SCALING_FACTOR, 1),
            "end_service": round(float(vs.end_service) / SCALING_FACTOR, 1),
            "tw_early": round(float(vs.tw_early) / SCALING_FACTOR, 1),
            "tw_late": round(float(vs.tw_late) / SCALING_FACTOR, 1),
            "is_late": bool(int(vs.time_warp) > 0),
            "lateness_minutes": round(float(vs.time_warp) / SCALING_FACTOR, 1),
        })
    return {
        "units": {"time": "solomon_minutes"},
        "n_late_customers": int(len(late_ids)),
        "late_customer_ids": late_ids,
        "route_end_times": route_end_times,
        "customer_schedule": customer_schedule,
    }


def project_payload(family: str, projected: ProjectedAction) -> dict:
    """Map a ProjectedAction → family-specific payload dict.

    family is prompts.csv's family column ('OBJ', 'PLAN_VALIDITY',
    'STRUCT', 'SCHEDULE'). The returned dict matches one of the four
    sub-schemas at experiment/configs/payload_schemas.json.
    """
    ev = projected.evaluation
    if family == "OBJ":
        return _project_obj(ev, projected.baseline_objective)
    if family == "PLAN_VALIDITY":
        return _project_pv(ev)
    if family == "STRUCT":
        return _project_struct(ev)
    if family == "SCHEDULE":
        return _project_schedule(ev)
    raise ValueError(f"unknown family {family!r}")


def build_payload(dataset: str, instance_id: str, perturbation_id: str,
                  action_name: str, family: str) -> dict:
    """Convenience: run the action and project to the family payload."""
    projected = run_action(dataset, instance_id, perturbation_id, action_name)
    return project_payload(family, projected)
