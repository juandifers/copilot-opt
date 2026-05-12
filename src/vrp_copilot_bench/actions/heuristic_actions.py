"""Action wrappers for the two construction heuristics.

Each wrapper:

1. Builds the perturbed-and-masked distance matrix via
   :func:`vrp_copilot_bench.actions.evaluate.build_perturbed_distance_matrix`.
2. Calls the heuristic's ``construct(perturbed, distance_matrix)`` to get
   route plan.
3. Scores the plan via :func:`evaluate_route_plan` (which independently
   re-builds the same matrix from the same perturbed instance — a small
   redundant cost that buys a strict single-source-of-truth boundary).
4. Packages the result as an :class:`ActionResult`.

The ``baseline`` parameter is unused by both heuristics (they construct
from scratch) but accepted for signature uniformity with
:func:`reuse_direct` and the PyVRP actions; the runner dispatches all
seven actions through the same shape.

Both wrappers raise :class:`ActionFailure` (via the underlying
construction routine) if a single customer's demand exceeds capacity.
:func:`run_action` does **not** catch this — the runner does.
"""
from __future__ import annotations

import time

from ..baselines import Solution
from ..perturbations.types import PerturbedInstance
from ..solvers.heuristics import clarke_wright as cw
from ..solvers.heuristics import nearest_neighbor as nn
from . import ActionResult
from .evaluate import build_perturbed_distance_matrix, evaluate_route_plan


def nearest_neighbor_action(
    perturbed: PerturbedInstance,
    baseline: Solution,  # noqa: ARG001 — accepted for signature uniformity
) -> ActionResult:
    """Build a plan via greedy NN and return its :class:`ActionResult`."""
    start = time.perf_counter()
    distance_matrix = build_perturbed_distance_matrix(perturbed)
    routes = nn.construct(perturbed, distance_matrix)
    evaluation = evaluate_route_plan(
        routes, perturbed, allow_partial_coverage=False
    )
    runtime = time.perf_counter() - start
    return ActionResult(
        action="nearest_neighbor",
        objective=evaluation.objective,
        feasible=evaluation.feasible,
        runtime_seconds=runtime,
        n_overload=evaluation.n_overload,
        max_overload_fraction=evaluation.max_overload_fraction,
        assignment=dict(evaluation.assignment),
        route_costs=dict(evaluation.route_costs),
        customer_costs=dict(evaluation.customer_costs),
        routes=[list(r) for r in routes],
        meta={},
    )


def clarke_wright_action(
    perturbed: PerturbedInstance,
    baseline: Solution,  # noqa: ARG001 — accepted for signature uniformity
) -> ActionResult:
    """Build a plan via Clarke-Wright and return its :class:`ActionResult`."""
    start = time.perf_counter()
    distance_matrix = build_perturbed_distance_matrix(perturbed)
    routes = cw.construct(perturbed, distance_matrix)
    evaluation = evaluate_route_plan(
        routes, perturbed, allow_partial_coverage=False
    )
    runtime = time.perf_counter() - start
    return ActionResult(
        action="clarke_wright",
        objective=evaluation.objective,
        feasible=evaluation.feasible,
        runtime_seconds=runtime,
        n_overload=evaluation.n_overload,
        max_overload_fraction=evaluation.max_overload_fraction,
        assignment=dict(evaluation.assignment),
        route_costs=dict(evaluation.route_costs),
        customer_costs=dict(evaluation.customer_costs),
        routes=[list(r) for r in routes],
        meta={},
    )
