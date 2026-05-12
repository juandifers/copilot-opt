"""``reuse_direct`` — re-evaluate the baseline solution under a perturbation.

Per prereg §7: "no solving. Take the baseline solution S, computed once
per instance before any perturbation. Re-evaluate its objective under the
perturbed distance and demand matrices. Re-check feasibility under
perturbed capacity."

Phase A's first real action. The implementation is a thin wrapper over
:func:`vrp_copilot_bench.actions.evaluate.evaluate_route_plan`: pass the
baseline's routes through, set ``allow_partial_coverage=True`` for
INSERTION (where the new customers don't appear in the baseline plan),
record partial-coverage diagnostics in ``meta``.
"""
from __future__ import annotations

import time

from ..baselines import Solution
from ..perturbations.types import PerturbedInstance
from . import ActionResult
from .evaluate import evaluate_route_plan


def reuse_direct(
    perturbed: PerturbedInstance,
    baseline: Solution,
) -> ActionResult:
    """Re-evaluate the baseline routes under the perturbed instance.

    No solving — just scoring. The baseline's exact route partitioning is
    preserved verbatim; only the cost function and the feasibility check
    change because of the perturbation.

    Coverage rules:

    - Non-INSERTION perturbations (CAPACITY, DEMAND, DISTANCE) leave
      ``perturbed.n_customers`` equal to the baseline's customer count, so
      the baseline routes cover every customer. ``allow_partial_coverage``
      is False; the partition check enforces that.

    - INSERTION perturbations grow the customer set
      (``perturbed.n_customers > len(baseline)``). The reuse semantics here
      are "keep the existing plan; ignore the new customers" — the new
      customers are unserved under reuse. They appear in
      ``ActionResult.assignment`` with ``route_id == -1`` (the explicit
      unassignment convention from Item 5 §3) and do **not** appear in
      ``customer_costs``. ``meta`` records ``partial_coverage: True`` and
      the count of unassigned customers.

    Detection of INSERTION uses ``perturbed.perturbation_family``, which
    is authoritative.

    The implementation does not mutate either input.
    """
    is_insertion = perturbed.perturbation_family == "INSERTION"

    start = time.perf_counter()
    evaluation = evaluate_route_plan(
        baseline.routes,
        perturbed,
        allow_partial_coverage=is_insertion,
        unassigned_label=-1,
    )
    runtime = time.perf_counter() - start

    n_unassigned = sum(1 for v in evaluation.assignment.values() if v == -1)

    meta: dict[str, object] = {}
    if is_insertion:
        meta["partial_coverage"] = True
        meta["n_unassigned_customers"] = n_unassigned

    return ActionResult(
        action="reuse_direct",
        objective=evaluation.objective,
        feasible=evaluation.feasible,
        runtime_seconds=runtime,
        n_overload=evaluation.n_overload,
        max_overload_fraction=evaluation.max_overload_fraction,
        assignment=dict(evaluation.assignment),
        route_costs=dict(evaluation.route_costs),
        customer_costs=dict(evaluation.customer_costs),
        routes=[list(r) for r in baseline.routes],
        meta=meta,
    )
