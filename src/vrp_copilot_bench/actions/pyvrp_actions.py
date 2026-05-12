"""PyVRP action wrappers — five solves, two time budgets, three seeds.

Per prereg §7 (action set) and §8.2 (audit subset):

- :func:`pyvrp_10s` — 10-second time limit, seed=1.
- :func:`pyvrp_60s` — 60-second time limit, seed=1. This is also the
  reference protocol on every cell (§8.1).
- :func:`pyvrp_60s_seed2`, :func:`pyvrp_60s_seed3` — 60-second audit
  variants (run only on the audit subset, scheduled by the work plan).

All four wrappers share the same skeleton:

1. Build a :class:`SolveConfig` for the (time_limit, seed) pair.
2. Call :func:`solve` on the perturbed instance — the solver internally
   uses :func:`build_perturbed_distance_matrix` so DISTANCE masks
   propagate into search.
3. Convert via :func:`solve_result_to_action_result`.

The ``baseline`` argument is unused (PyVRP solves from scratch) but
accepted for signature uniformity across the seven dispatchable actions.

Determinism: PyVRP under ``MaxRuntime`` is wall-clock-bounded; same seed
produces a result within a tight noise band rather than bit-equal output.
The audit (§8.2) measures this noise via the ``reference_obj_unstable``
flag on each audited cell.
"""
from __future__ import annotations

from ..baselines import Solution
from ..perturbations.types import PerturbedInstance
from ..solvers.pyvrp_wrapper import SolveConfig, solve
from . import ActionResult
from ._conversion import solve_result_to_action_result


def _run_pyvrp(
    perturbed: PerturbedInstance,
    *,
    time_limit_seconds: float,
    seed: int,
    action_name: str,
) -> ActionResult:
    """Shared body: solve, then convert to ActionResult."""
    config = SolveConfig(time_limit_seconds=time_limit_seconds, seed=seed)
    solve_result = solve(perturbed, config)
    return solve_result_to_action_result(
        solve_result, perturbed, action_name=action_name
    )


def pyvrp_10s(
    perturbed: PerturbedInstance,
    baseline: Solution,  # noqa: ARG001 — accepted for signature uniformity
) -> ActionResult:
    return _run_pyvrp(
        perturbed, time_limit_seconds=10.0, seed=1, action_name="pyvrp_10s"
    )


def pyvrp_60s(
    perturbed: PerturbedInstance,
    baseline: Solution,  # noqa: ARG001
) -> ActionResult:
    return _run_pyvrp(
        perturbed, time_limit_seconds=60.0, seed=1, action_name="pyvrp_60s"
    )


def pyvrp_60s_seed2(
    perturbed: PerturbedInstance,
    baseline: Solution,  # noqa: ARG001
) -> ActionResult:
    return _run_pyvrp(
        perturbed, time_limit_seconds=60.0, seed=2, action_name="pyvrp_60s_seed2"
    )


def pyvrp_60s_seed3(
    perturbed: PerturbedInstance,
    baseline: Solution,  # noqa: ARG001
) -> ActionResult:
    return _run_pyvrp(
        perturbed, time_limit_seconds=60.0, seed=3, action_name="pyvrp_60s_seed3"
    )
