"""Cleaned-up VRPTW namespace for the scale-check and future benchmark.

This package is the canonical import surface for new VRPTW code:

    from vrp_copilot_bench.vrptw import (
        VRPTWInstance, load_vrptw_instance,
        VRPTWPerturbationSpec, enumerate_vrptw_perturbations,
        solve_vrptw, evaluate_vrptw_solution,
        load_or_compute_baseline,
        ReuseDirect, LocalRepairInsert, cheap_action_for_family,
        evaluate_action,
        extract_features,
        compute_losses,
    )

Existing pilot scripts (v1/v2 perturbation pilots, Phase 1 probe) still
import from the legacy top-level paths (``vrp_copilot_bench.vrptw_instances``,
``vrp_copilot_bench.vrptw_perturbations``,
``vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper``). Those locations are
unchanged — the modules in this package either re-export from those legacy
paths (instances/perturbations/solver) or add new layered logic that uses
them (baselines/actions/evaluation/features/losses).
"""
from __future__ import annotations

from .instances import VRPTWInstance, load_vrptw_instance
from .perturbations import (
    PERTURBATION_FAMILIES,
    PERTURBATION_FAMILY_OF,
    PERTURBATION_IDS,
    PERTURBATION_MAGNITUDES,
    SOFT_PERTURBATION_MAGNITUDES,
    SOFT_TIGHT_WINDOW_WIDTH_FRACTION,
    V1_TIGHT_WINDOW_WIDTH_FRACTION,
    VRPTWPerturbationSpec,
    VRPTWPerturbedInstance,
    apply_vrptw_perturbation,
    enumerate_vrptw_perturbations,
    lookup_vrptw_perturbation,
)
from .solver import (
    SCALING_FACTOR,
    EvaluatedVRPTW,
    RouteSummary,
    SolveConfig,
    VisitSchedule,
    VRPTWSolveResult,
    VRPTWSolverFailure,
    evaluate_vrptw_solution,
    solve_vrptw,
)

__all__ = [
    "VRPTWInstance",
    "load_vrptw_instance",
    "PERTURBATION_FAMILIES",
    "PERTURBATION_FAMILY_OF",
    "PERTURBATION_IDS",
    "PERTURBATION_MAGNITUDES",
    "SOFT_PERTURBATION_MAGNITUDES",
    "SOFT_TIGHT_WINDOW_WIDTH_FRACTION",
    "V1_TIGHT_WINDOW_WIDTH_FRACTION",
    "VRPTWPerturbationSpec",
    "VRPTWPerturbedInstance",
    "apply_vrptw_perturbation",
    "enumerate_vrptw_perturbations",
    "lookup_vrptw_perturbation",
    "SCALING_FACTOR",
    "EvaluatedVRPTW",
    "RouteSummary",
    "SolveConfig",
    "VisitSchedule",
    "VRPTWSolveResult",
    "VRPTWSolverFailure",
    "evaluate_vrptw_solution",
    "solve_vrptw",
]
