"""SolveResult → ActionResult conversion (Phase C).

The PyVRP wrapper returns :class:`SolveResult` — the canonical "what
PyVRP found" record. The action layer needs :class:`ActionResult`, which
is the canonical "what an action contributed to a benchmark cell" record.
The two have largely overlapping fields; this module is the one place
that maps between them.

Sibling helper note (do not confuse the two):

- :meth:`vrp_copilot_bench.baselines.Solution.from_solve_result` maps
  ``SolveResult → Solution``. Solution is the *cached unperturbed*
  baseline artifact (no perturbation context, no ``feasible``/``n_overload``
  fields because PyVRP 60s seed=1 on an unperturbed CVRP is feasible by
  construction).
- :func:`solve_result_to_action_result` (this module) maps
  ``SolveResult → ActionResult``. ActionResult is the *per-cell action
  output* (carries the perturbation's ``feasible``/``n_overload`` flags,
  the action name, and meta-diagnostics).

Both are real, parallel, and intentionally separate; one cannot be
expressed in terms of the other without losing field semantics. The
two files coexist by design.
"""
from __future__ import annotations

from ..perturbations.types import PerturbedInstance
from ..solvers.pyvrp_wrapper import SolveResult
from . import ActionResult


def solve_result_to_action_result(
    solve_result: SolveResult,
    perturbed: PerturbedInstance,
    action_name: str,
) -> ActionResult:
    """Convert a :class:`SolveResult` into an :class:`ActionResult`.

    Field mapping:

    +-------------------------------+----------------------------------------+
    | ActionResult field            | source                                 |
    +===============================+========================================+
    | action                        | ``action_name`` (passed in)            |
    | objective                     | ``solve_result.objective``             |
    | feasible                      | ``solve_result.feasible``              |
    | runtime_seconds               | ``solve_result.runtime_seconds``       |
    | n_overload                    | ``solve_result.n_overload``            |
    | max_overload_fraction         | ``solve_result.max_overload_fraction`` |
    | assignment                    | ``solve_result.assignment``            |
    | route_costs                   | ``solve_result.route_costs``           |
    | customer_costs                | ``solve_result.customer_costs``        |
    | routes                        | ``solve_result.routes``                |
    | meta                          | ``{"pyvrp_version": ...,               |
    |                               |    "perturbation_id": ...}``           |
    +-------------------------------+----------------------------------------+

    ``meta`` carries the PyVRP version (recorded once per action invocation
    so audit cells can detect a silent solver bump) and the perturbation
    id (echoed for human-readable diagnostics). Both are short strings;
    the meta payload remains well under the 500-byte budget from §3 of
    the prompt.

    The returned :class:`ActionResult` is independent of ``solve_result``:
    routes/dicts are shallow-copied so mutations on either side don't
    leak. (``ActionResult`` is frozen, so any mutation would have to come
    from outside this function.)

    The ``perturbed`` argument is currently used only for ``meta``; it is
    accepted to keep the signature future-proof if downstream cells later
    need perturbation context (e.g. mapping route-cost shifts to mask
    regions).
    """
    return ActionResult(
        action=action_name,
        objective=solve_result.objective,
        feasible=solve_result.feasible,
        runtime_seconds=solve_result.runtime_seconds,
        n_overload=solve_result.n_overload,
        max_overload_fraction=solve_result.max_overload_fraction,
        assignment=dict(solve_result.assignment),
        route_costs=dict(solve_result.route_costs),
        customer_costs=dict(solve_result.customer_costs),
        routes=[list(r) for r in solve_result.routes],
        meta={
            "pyvrp_version": solve_result.pyvrp_version,
            "perturbation_id": perturbed.perturbation_id,
        },
    )
