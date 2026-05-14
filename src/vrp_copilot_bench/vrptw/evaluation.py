"""Evaluation primitives for VRPTW claim families.

Reusable across the scale-check and any future training pipeline:

- :func:`ari_on_common` — Adjusted Rand Index restricted to the customer
  set that exists in both assignments. We always do this on the
  intersection because ORDER_CHANGE perturbations grow the customer set,
  and a baseline plan has no label for the new customers.
- :func:`infeasibility_kind` — categorical breakdown of why an
  :class:`EvaluatedVRPTW` is infeasible.
- :func:`reference_stability` — pairwise ARI and objective-spread
  summary across the three reference seeds.
- :func:`schedule_shifts` — per-customer normalized start-service deltas.
- :func:`route_end_disruption_max` — max abs end-time shift over affected
  baseline routes.
- :func:`generalized_cost` — diagnostic generalized cost ``distance + 0.1 * duration``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.metrics import adjusted_rand_score

from .solver import (
    SCALING_FACTOR,
    EvaluatedVRPTW,
    VisitSchedule,
    VRPTWSolveResult,
)


#: Stored as a constant so the report can quote it verbatim.
GENERALIZED_DURATION_WEIGHT: float = 0.1


#: ARI threshold below which we treat reference structure as unstable.
ARI_STRUCT_UNSTABLE_THRESHOLD: float = 0.90


#: Relative objective spread above which we treat reference obj as unstable.
OBJ_UNSTABLE_THRESHOLD: float = 0.05


# ---------------------------------------------------------------------------
# ARI / structure


def ari_on_common(a: dict[int, int], b: dict[int, int]) -> float:
    """ARI on customers present in **both** assignments.

    Returns ``nan`` if fewer than two common customers exist.
    """
    common = sorted(set(a) & set(b))
    if len(common) < 2:
        return math.nan
    la = np.fromiter((a[c] for c in common), dtype=np.int64, count=len(common))
    lb = np.fromiter((b[c] for c in common), dtype=np.int64, count=len(common))
    return float(adjusted_rand_score(la, lb))


# ---------------------------------------------------------------------------
# Feasibility breakdown


def infeasibility_kind(ev: EvaluatedVRPTW) -> str:
    """Categorical: ``none / capacity / time_window / both / coverage``.

    ``coverage`` is the VRPTW-specific case where served routes are
    capacity+TW feasible but some instance customer is unserved (e.g.
    ORDER_CHANGE ``reuse_direct``).
    """
    cap_ok = ev.feasible_capacity_only
    tw_ok = ev.feasible_tw_only
    if cap_ok and tw_ok:
        return "none" if ev.is_complete else "coverage"
    if not cap_ok and tw_ok:
        return "capacity"
    if cap_ok and not tw_ok:
        return "time_window"
    return "both"


# ---------------------------------------------------------------------------
# Reference stability


@dataclass(frozen=True)
class ReferenceStability:
    """Pairwise-ARI and objective-spread summary across 3 reference seeds.

    ``failure_kind`` is ``"none"`` when all three solves are feasible
    with finite objectives; otherwise it surfaces what went wrong in a
    coarse-grained way for the report.
    """

    ari_s1s2: float
    ari_s1s3: float
    ari_s2s3: float
    ari_min: float
    obj_unstable: bool
    # struct_unstable is None when no seed is feasible: a cell with no
    # feasible reference on any seed has no well-defined reference
    # partition to compare against, so structural stability is undefined.
    # PREREG_v1.1_vrptw.md amendment to §8.2 / §12.3.
    struct_unstable: bool | None
    s1_feasible: bool
    s2_feasible: bool
    s3_feasible: bool
    any_feasible: bool
    all_feasible: bool
    obj_best_feasible: float  # +inf when nothing feasible
    n_routes_s1: int
    n_routes_s2: int
    n_routes_s3: int
    failure_kind: str  # "none" / "any_infeasible" / "all_infeasible" / ...


def reference_stability(
    s1: VRPTWSolveResult, s2: VRPTWSolveResult, s3: VRPTWSolveResult,
) -> ReferenceStability:
    """Summarize the 3-seed reference set."""
    ari12 = ari_on_common(s1.assignment, s2.assignment)
    ari13 = ari_on_common(s1.assignment, s3.assignment)
    ari23 = ari_on_common(s2.assignment, s3.assignment)
    aris = [a for a in (ari12, ari13, ari23) if not math.isnan(a)]
    ari_min = float(min(aris)) if aris else math.nan

    objs = [float(s1.objective), float(s2.objective), float(s3.objective)]
    finite = [o for o in objs if math.isfinite(o)]
    if len(finite) >= 2 and min(finite) > 0:
        obj_unstable = bool(
            (max(finite) - min(finite)) / min(finite) > OBJ_UNSTABLE_THRESHOLD
        )
    else:
        obj_unstable = False

    feas = [bool(s.feasible) for s in (s1, s2, s3)]
    # PREREG_v1.1_vrptw.md amendment to §8.2 / §12.3: a cell with no
    # feasible reference on any seed has stability-undefined. PyVRP
    # still returns a penalty-bounded "best" assignment for infeasible
    # solves, so ari_min remains computable, but the comparison is
    # against partitions that the §8.3 n/a policy already excludes from
    # STRUCT/SCHEDULE training. Keep struct_unstable None here and the
    # §12.3 rate naturally excludes the cell from both numerator and
    # denominator.
    struct_unstable: bool | None
    if not any(feas):
        struct_unstable = None
    else:
        struct_unstable = bool(
            ari_min < ARI_STRUCT_UNSTABLE_THRESHOLD
            if not math.isnan(ari_min) else False
        )
    obj_best = float(min(finite)) if finite else float("inf")

    if all(feas):
        failure_kind = "none"
    elif not any(feas):
        failure_kind = "all_infeasible"
    else:
        failure_kind = "any_infeasible"

    return ReferenceStability(
        ari_s1s2=float(ari12) if not math.isnan(ari12) else math.nan,
        ari_s1s3=float(ari13) if not math.isnan(ari13) else math.nan,
        ari_s2s3=float(ari23) if not math.isnan(ari23) else math.nan,
        ari_min=ari_min,
        obj_unstable=obj_unstable,
        struct_unstable=struct_unstable,
        s1_feasible=feas[0],
        s2_feasible=feas[1],
        s3_feasible=feas[2],
        any_feasible=any(feas),
        all_feasible=all(feas),
        obj_best_feasible=obj_best,
        n_routes_s1=int(s1.n_routes),
        n_routes_s2=int(s2.n_routes),
        n_routes_s3=int(s3.n_routes),
        failure_kind=failure_kind,
    )


# ---------------------------------------------------------------------------
# Schedule helpers


def depot_horizon_scaled(instance: Any) -> int:
    """``(tw_late[0] - tw_early[0]) * SCALING_FACTOR``. May be 0 for malformed
    instances; callers should guard against divide-by-zero."""
    return (
        (int(instance.time_windows[0, 1]) - int(instance.time_windows[0, 0]))
        * SCALING_FACTOR
    )


def median_arrival_shift_global(
    a_schedule: dict[int, VisitSchedule],
    b_schedule: dict[int, VisitSchedule],
    depot_horizon: int,
) -> tuple[float, int]:
    """Median of normalized abs ``start_service`` shifts over common customers.

    Returns ``(loss, n_common)``. ``loss`` is ``nan`` if there are no
    common customers or the horizon is non-positive.
    """
    common = sorted(set(a_schedule) & set(b_schedule))
    if not common or depot_horizon <= 0:
        return math.nan, 0
    diffs = np.array([
        abs(a_schedule[c].start_service - b_schedule[c].start_service)
        for c in common
    ], dtype=np.float64)
    return float(np.median(diffs) / float(depot_horizon)), len(common)


def schedule_shifts(
    a_schedule: dict[int, VisitSchedule],
    b_schedule: dict[int, VisitSchedule],
    customers: list[int],
    depot_horizon: int,
) -> list[float]:
    """Per-customer normalized abs ``start_service`` shifts over ``customers``."""
    if depot_horizon <= 0:
        return []
    out: list[float] = []
    for c in customers:
        if c in a_schedule and c in b_schedule:
            out.append(
                abs(a_schedule[c].start_service - b_schedule[c].start_service)
                / float(depot_horizon)
            )
    return out


def route_end_disruption_max(
    action_eval: EvaluatedVRPTW,
    baseline: VRPTWSolveResult,
    affected_route_idxs: tuple[int, ...],
    depot_horizon: int,
) -> float:
    """Max abs route-end-time shift (normalized) over affected baseline routes."""
    if depot_horizon <= 0 or not affected_route_idxs:
        return math.nan
    b_by_idx = {rs.route_idx: rs for rs in baseline.route_summaries}
    a_by_idx = {rs.route_idx: rs for rs in action_eval.route_summaries}
    deltas: list[float] = []
    for ri in affected_route_idxs:
        if ri in b_by_idx and ri in a_by_idx:
            deltas.append(
                abs(int(a_by_idx[ri].end_time) - int(b_by_idx[ri].end_time))
                / float(depot_horizon)
            )
    return float(max(deltas)) if deltas else math.nan


# ---------------------------------------------------------------------------
# Generalized cost


def generalized_cost(distance: float, duration: float | None) -> float:
    """``distance + 0.1 * duration``. ``None`` duration → distance only."""
    if duration is None:
        return float(distance)
    return float(distance) + GENERALIZED_DURATION_WEIGHT * float(duration)


def eval_to_costs(ev_or_ref: Any) -> tuple[float, float]:
    """Extract ``(distance, duration)`` from EvaluatedVRPTW or VRPTWSolveResult.

    For :class:`VRPTWSolveResult` the cost equals the distance (PyVRP is
    configured with ``unit_duration_cost=0``).
    """
    if hasattr(ev_or_ref, "total_distance"):
        return float(ev_or_ref.total_distance), float(ev_or_ref.total_duration)
    return (
        float(ev_or_ref.objective),
        float(ev_or_ref.total_duration or 0.0),
    )


__all__ = [
    "ARI_STRUCT_UNSTABLE_THRESHOLD",
    "GENERALIZED_DURATION_WEIGHT",
    "OBJ_UNSTABLE_THRESHOLD",
    "ReferenceStability",
    "ari_on_common",
    "depot_horizon_scaled",
    "eval_to_costs",
    "generalized_cost",
    "infeasibility_kind",
    "median_arrival_shift_global",
    "reference_stability",
    "route_end_disruption_max",
    "schedule_shifts",
]
