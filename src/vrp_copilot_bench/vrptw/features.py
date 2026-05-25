"""Pre-recompute feature extraction for the VRPTW scale-check.

Strict rule
-----------
**No reference-solve outputs may enter features.** Features are the
inputs a future predictor would see; the reference seeds are the labels.
Mixing the two leaks information and would inflate any downstream
predictor score.

Three feature groups
--------------------
1. **Baseline features** (depend only on the unperturbed baseline plan):
   ``baseline_n_routes``, ``baseline_obj``, ``baseline_total_wait``,
   ``baseline_min_route_slack``, ``baseline_mean_route_slack``,
   ``baseline_n_tight_customers``.

2. **Perturbation/affected features** (depend on the perturbation spec
   and the baseline plan, not on the action evaluation):
   ``n_affected_customers``, ``affected_route_share``,
   ``affected_demand_share``, ``affected_service_time_share``,
   ``affected_min_slack``, ``affected_mean_slack``,
   ``affected_total_wait``.

3. **Action features** (depend on the cheap-action evaluation; the
   action is itself a deterministic transformation of baseline +
   perturbation, so this is still leakage-free):
   ``action_obj_delta_pct``, ``action_generalized_delta_pct``,
   ``action_time_warp``, ``action_total_wait``,
   ``action_total_duration``, ``action_n_late_customers``,
   ``action_max_lateness``.

A "tight" customer is one whose window width is strictly less than the
median customer window width — a cheap proxy for time-pressure load.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .evaluation import eval_to_costs, generalized_cost
from .perturbations import VRPTWPerturbedInstance
from .solver import EvaluatedVRPTW, VRPTWSolveResult


@dataclass(frozen=True)
class FeatureBundle:
    """All scale-check features for one (cell, action) row.

    Lives as a dataclass so the scale-check can ``asdict(...)`` it into
    a parquet row with stable column ordering.
    """

    # Baseline-only
    baseline_n_routes: int
    baseline_obj: float
    baseline_generalized_cost: float
    baseline_total_wait: int
    baseline_min_route_slack: int
    baseline_mean_route_slack: float
    baseline_n_tight_customers: int

    # Perturbation / affected scope
    n_affected_customers: int
    affected_route_share: float
    affected_demand_share: float
    affected_service_time_share: float
    affected_min_slack: float          # nan if no affected customer on a route
    affected_mean_slack: float
    affected_total_wait: int

    # Action evaluation
    action_obj_delta_pct: float        # vs baseline (not reference!)
    action_generalized_delta_pct: float
    action_time_warp: int
    action_total_wait: int
    action_total_duration: int
    action_n_late_customers: int
    action_max_lateness: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers


def _customer_window_widths(instance: Any) -> np.ndarray:
    tw = np.asarray(instance.time_windows, dtype=np.int64)
    widths = (tw[1:, 1] - tw[1:, 0]).astype(np.float64)
    return widths


def _baseline_features(
    instance: Any, baseline: VRPTWSolveResult,
) -> dict[str, Any]:
    summaries = baseline.route_summaries
    waits = [int(rs.wait_duration) for rs in summaries] if summaries else [0]
    min_slacks = [int(rs.min_slack_to_tw_late) for rs in summaries] if summaries else [0]
    mean_slacks = (
        [float(rs.mean_slack_to_tw_late) for rs in summaries]
        if summaries else [0.0]
    )

    widths = _customer_window_widths(instance)
    median_width = float(np.median(widths)) if widths.size else 0.0
    n_tight = int(np.sum(widths < median_width)) if widths.size else 0

    gc = generalized_cost(*eval_to_costs(baseline))

    return {
        "baseline_n_routes": int(baseline.n_routes),
        "baseline_obj": float(baseline.objective),
        "baseline_generalized_cost": float(gc),
        "baseline_total_wait": int(sum(waits)),
        "baseline_min_route_slack": int(min(min_slacks)) if min_slacks else 0,
        "baseline_mean_route_slack": float(
            np.mean(mean_slacks) if mean_slacks else 0.0
        ),
        "baseline_n_tight_customers": n_tight,
    }


def _affected_features(
    instance: Any,
    perturbed: VRPTWPerturbedInstance,
    baseline: VRPTWSolveResult,
) -> dict[str, Any]:
    affected = tuple(perturbed.affected_customers)
    aff_routes = set(perturbed.affected_baseline_routes)
    sched = baseline.per_customer_schedule

    # Slack: derived from baseline schedule's per-customer slack_to_tw_late
    # over original customers in the affected set. For inserted (OC) new
    # customers there is no baseline schedule entry, so we skip them.
    slack_vals = [
        float(sched[c].slack_to_tw_late) for c in affected
        if c in sched
    ]
    if slack_vals:
        aff_min_slack = float(min(slack_vals))
        aff_mean_slack = float(np.mean(slack_vals))
    else:
        aff_min_slack = math.nan
        aff_mean_slack = math.nan

    # Total wait on the affected baseline routes (clamped to existing).
    summaries_by_idx = {rs.route_idx: rs for rs in baseline.route_summaries}
    aff_total_wait = int(sum(
        int(summaries_by_idx[ri].wait_duration)
        for ri in aff_routes if ri in summaries_by_idx
    ))

    # Affected service-time share (only meaningful for original customers).
    st = np.asarray(instance.service_times, dtype=np.int64)
    total_st = int(st[1:].sum())
    aff_st = int(sum(int(st[c]) for c in affected if 1 <= c <= instance.n_customers))
    aff_st_share = float(aff_st / total_st) if total_st > 0 else 0.0

    return {
        "n_affected_customers": int(perturbed.n_affected_customers),
        "affected_route_share": float(perturbed.affected_route_share),
        "affected_demand_share": float(perturbed.affected_demand_share),
        "affected_service_time_share": float(aff_st_share),
        "affected_min_slack": aff_min_slack,
        "affected_mean_slack": aff_mean_slack,
        "affected_total_wait": aff_total_wait,
    }


def _action_features(
    baseline: VRPTWSolveResult,
    action_eval: EvaluatedVRPTW,
) -> dict[str, Any]:
    base_obj = float(baseline.objective)
    base_gc = generalized_cost(*eval_to_costs(baseline))
    act_obj = float(action_eval.objective)
    act_dist, act_dur = eval_to_costs(action_eval)
    act_gc = generalized_cost(act_dist, act_dur)

    obj_delta_pct = (
        (act_obj - base_obj) / base_obj if base_obj > 0 else math.nan
    )
    gc_delta_pct = (
        (act_gc - base_gc) / base_gc if base_gc > 0 else math.nan
    )

    return {
        "action_obj_delta_pct": float(obj_delta_pct),
        "action_generalized_delta_pct": float(gc_delta_pct),
        "action_time_warp": int(action_eval.total_time_warp),
        "action_total_wait": int(action_eval.total_wait),
        "action_total_duration": int(action_eval.total_duration),
        "action_n_late_customers": int(action_eval.n_late_customers),
        "action_max_lateness": int(action_eval.max_lateness),
    }


# ---------------------------------------------------------------------------
# Public API


def extract_features(
    *,
    instance: Any,
    perturbed: VRPTWPerturbedInstance,
    baseline: VRPTWSolveResult,
    action_eval: EvaluatedVRPTW,
) -> FeatureBundle:
    """Return the full :class:`FeatureBundle` for one (cell, action) row."""
    d: dict[str, Any] = {}
    d.update(_baseline_features(instance, baseline))
    d.update(_affected_features(instance, perturbed, baseline))
    d.update(_action_features(baseline, action_eval))
    return FeatureBundle(**d)


__all__ = [
    "FeatureBundle",
    "extract_features",
]
