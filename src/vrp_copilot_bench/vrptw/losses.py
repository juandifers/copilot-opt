"""Loss + band logic for the four VRPTW claim families.

Pure functions; given an :class:`EvaluatedVRPTW` for the action and a
:class:`VRPTWSolveResult` for reference seed 1 (plus a few diagnostics),
return ``LossBundle`` which the scale-check serializes into the wide and
long output tables.

Claim families and their primary losses
---------------------------------------
``OBJ``           — ``abs(action_obj - ref_obj_s1) / ref_obj_s1``
                    Distance-only. Generalized cost is a parallel
                    diagnostic (:attr:`LossBundle.loss_obj_generalized`).
``PLAN_VALIDITY`` — ``0`` feasible / ``1`` infeasible.
``STRUCT``        — ``1 - ARI(action_assignment, ref_s1.assignment)`` on
                    the common customer set.
``SCHEDULE``      — v2: p90 of per-customer normalized abs start-service
                    shift, computed over **affected original customers**
                    (inserted customers excluded). Falls back to all
                    originals when the affected-original set is empty.

Banding
-------
=============  ========  ========  ===========================
Family         easy ≤    medium ≤   hard
=============  ========  ========  ===========================
OBJ            0.05      0.15      > 0.15  (or n/a if ref s1 bad)
PLAN_VALIDITY  feasible  —         infeasible
STRUCT         0.10      0.30      > 0.30  (or n/a if ref s1 bad)
SCHEDULE       0.02      0.05      > 0.05  (or n/a if ref s1 bad)
=============  ========  ========  ===========================
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from .evaluation import (
    ari_on_common,
    depot_horizon_scaled,
    eval_to_costs,
    generalized_cost,
    median_arrival_shift_global,
    schedule_shifts,
)
from .solver import EvaluatedVRPTW, VRPTWSolveResult


# --- Band thresholds --------------------------------------------------------


OBJ_EASY: float = 0.05
OBJ_MEDIUM: float = 0.15

STRUCT_EASY: float = 0.10
STRUCT_MEDIUM: float = 0.30

SCHEDULE_EASY: float = 0.02
SCHEDULE_MEDIUM: float = 0.05


def _band_continuous(x: float, easy: float, medium: float) -> str:
    """``easy / medium / hard / n/a`` from a continuous loss + thresholds."""
    if math.isnan(x):
        return "n/a"
    if x <= easy:
        return "easy"
    if x <= medium:
        return "medium"
    return "hard"


def _band_plan_validity(feasible: bool) -> str:
    return "easy" if feasible else "hard"


# --- Loss bundle ------------------------------------------------------------


@dataclass(frozen=True)
class LossBundle:
    """All losses + bands + auxiliary schedule fields for one (cell, action).

    ``ref_s1_valid`` is True when reference seed 1 returned a feasible
    plan with a finite, positive objective — the rows where OBJ / STRUCT
    / SCHEDULE primaries can be computed. When False, primaries are NaN
    and bands are ``"n/a"``.
    """

    # OBJ distance (primary)
    loss_obj_distance: float
    band_obj_distance: str
    # OBJ generalized (diagnostic)
    loss_obj_generalized: float
    band_obj_generalized: str
    # PLAN_VALIDITY
    loss_plan_validity: float
    band_plan_validity: str
    # STRUCT
    loss_struct: float
    band_struct: str
    # SCHEDULE (primary = v2 affected-p90)
    loss_schedule: float
    band_schedule: str
    # SCHEDULE diagnostic fields (v1 global + the three local stats)
    loss_schedule_global_median: float
    loss_schedule_affected_median: float
    loss_schedule_affected_p90: float
    loss_schedule_affected_max: float
    schedule_eval_n_customers: int
    # Provenance
    ref_s1_valid: bool


def _ref_s1_valid(ref_s1: VRPTWSolveResult) -> bool:
    return (
        bool(ref_s1.feasible)
        and math.isfinite(float(ref_s1.objective))
        and float(ref_s1.objective) > 0.0
    )


def compute_losses(
    *,
    instance: Any,
    perturbed: Any,
    action_eval: EvaluatedVRPTW,
    ref_s1: VRPTWSolveResult,
) -> LossBundle:
    """Compute OBJ/PV/STRUCT/SCHEDULE for one (instance, perturbation, action).

    ``perturbed`` carries the affected customer list; for ORDER_CHANGE
    those are the inserted customers, which we **exclude** from the
    primary SCHEDULE computation per v2's recommendation. If the
    resulting customer set is empty, we fall back to all original
    customers that appear in both schedules.
    """
    ref_valid = _ref_s1_valid(ref_s1)

    # --- OBJ (distance-only) -----------------------------------------------
    action_obj = float(action_eval.objective)
    ref_obj_s1 = float(ref_s1.objective)
    if ref_valid:
        loss_obj = abs(action_obj - ref_obj_s1) / ref_obj_s1
    else:
        loss_obj = math.nan

    # --- OBJ generalized ---------------------------------------------------
    action_dist, action_dur = eval_to_costs(action_eval)
    ref_dist, ref_dur = eval_to_costs(ref_s1)
    action_gc = generalized_cost(action_dist, action_dur)
    ref_gc = generalized_cost(ref_dist, ref_dur)
    if ref_valid and ref_gc > 0 and math.isfinite(ref_gc):
        loss_obj_gen = abs(action_gc - ref_gc) / ref_gc
    else:
        loss_obj_gen = math.nan

    # --- PLAN_VALIDITY -----------------------------------------------------
    loss_pv = 0.0 if action_eval.feasible else 1.0

    # --- STRUCT ------------------------------------------------------------
    ari_av = ari_on_common(action_eval.assignment, ref_s1.assignment)
    if ref_valid and not math.isnan(ari_av):
        loss_struct = 1.0 - ari_av
    else:
        loss_struct = math.nan

    # --- SCHEDULE ----------------------------------------------------------
    horizon = depot_horizon_scaled(instance)

    # Diagnostic global median (v1 SCHEDULE)
    loss_sched_global, _ = median_arrival_shift_global(
        action_eval.per_customer_schedule, ref_s1.per_customer_schedule, horizon,
    )

    # Primary v2: affected originals, p90.
    inserted_set = set(perturbed.affected_customers) if (
        perturbed.perturbation_family == "ORDER_CHANGE"
    ) else set()
    schedule_eval_customers = sorted(
        c for c in perturbed.affected_customers if c not in inserted_set
    )
    if not schedule_eval_customers:
        schedule_eval_customers = sorted(
            c for c in range(1, instance.n_customers + 1)
            if c in action_eval.per_customer_schedule
            and c in ref_s1.per_customer_schedule
        )
    shifts = schedule_shifts(
        action_eval.per_customer_schedule, ref_s1.per_customer_schedule,
        schedule_eval_customers, horizon,
    )
    if shifts and ref_valid:
        arr = np.array(shifts, dtype=np.float64)
        loss_sched_aff_median = float(np.median(arr))
        loss_sched_aff_p90 = float(np.quantile(arr, 0.90))
        loss_sched_aff_max = float(np.max(arr))
    else:
        loss_sched_aff_median = math.nan
        loss_sched_aff_p90 = math.nan
        loss_sched_aff_max = math.nan
    loss_sched_primary = loss_sched_aff_p90

    return LossBundle(
        loss_obj_distance=loss_obj,
        band_obj_distance=_band_continuous(loss_obj, OBJ_EASY, OBJ_MEDIUM),
        loss_obj_generalized=loss_obj_gen,
        band_obj_generalized=_band_continuous(loss_obj_gen, OBJ_EASY, OBJ_MEDIUM),
        loss_plan_validity=loss_pv,
        band_plan_validity=_band_plan_validity(bool(action_eval.feasible)),
        loss_struct=loss_struct,
        band_struct=_band_continuous(loss_struct, STRUCT_EASY, STRUCT_MEDIUM),
        loss_schedule=loss_sched_primary,
        band_schedule=_band_continuous(
            loss_sched_primary, SCHEDULE_EASY, SCHEDULE_MEDIUM,
        ),
        loss_schedule_global_median=loss_sched_global,
        loss_schedule_affected_median=loss_sched_aff_median,
        loss_schedule_affected_p90=loss_sched_aff_p90,
        loss_schedule_affected_max=loss_sched_aff_max,
        schedule_eval_n_customers=len(schedule_eval_customers),
        ref_s1_valid=ref_valid,
    )


__all__ = [
    "LossBundle",
    "OBJ_EASY",
    "OBJ_MEDIUM",
    "SCHEDULE_EASY",
    "SCHEDULE_MEDIUM",
    "STRUCT_EASY",
    "STRUCT_MEDIUM",
    "compute_losses",
]
