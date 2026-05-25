"""Shim re-exporting the PyVRP VRPTW wrapper and CVRP-shared ``SolveConfig``.

Lives so that all new VRPTW code can import the solver from
``vrp_copilot_bench.vrptw.solver`` (or the top-level
``vrp_copilot_bench.vrptw``) without reaching into the shared
``solvers/`` package. The underlying wrapper file is left where it is so
the v1/v2 pilots keep working.
"""
from __future__ import annotations

from ..solvers.pyvrp_vrptw_wrapper import (
    SCALING_FACTOR,
    EvaluatedVRPTW,
    RouteSummary,
    VisitSchedule,
    VRPTWSolveResult,
    VRPTWSolverFailure,
    evaluate_vrptw_solution,
    solve_vrptw,
)
from ..solvers.pyvrp_wrapper import SolveConfig

__all__ = [
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
