"""Thin PyVRP wrapper.

The wrapper's job:

1. Convert an :class:`~vrp_copilot_bench.instances.Instance` into a PyVRP
   ``ProblemData`` (depot, clients, vehicle type, integer-rounded
   Euclidean distance matrix).
2. Run PyVRP's iterated local search (``pyvrp.solve``) with the configured
   time limit and seed.
3. Extract the best solution and translate it back into a
   :class:`SolveResult`: routes (customer-id sequences, depot excluded),
   per-route costs, per-customer marginal costs (via
   :func:`solvers.marginal_costs.compute_customer_costs`), feasibility,
   overload statistics, runtime.

PyVRP runs single-threaded by construction in this version (0.13.x).
``pyvrp.solve`` exposes no thread-count knob; the iterated local search
is a single C++ thread per call. Every call from this project therefore
honors the project-wide rule that joblib parallelism is the only source
of concurrency. Threading inside a worker stays at one. We document the
constraint here rather than enforce it (there is nothing to set).

Distance convention: rounded Euclidean (``round_func='round'``-equivalent)
matching standard CVRPLIB integer-distance conventions and the result of
:func:`pyvrp.read` on the X-set ``.vrp`` files. The matrix is built via
:func:`vrp_copilot_bench.actions.evaluate.build_perturbed_distance_matrix`
(imported lazily inside :func:`solve` to avoid an import-time cycle with
the actions package). For ``PerturbedInstance`` inputs the matrix
incorporates ``distance_multiplier_mask`` element-wise; for ``Instance``
inputs and ``PerturbedInstance`` with ``mask=None`` the result is bit-equal
to the pre-Phase-C inline ``_build_distance_matrix(coords)`` helper —
verified by a regression test in :mod:`tests.test_pyvrp_wrapper`.

Item 5 Phase C diff:
    - :func:`solve` accepts ``Instance | PerturbedInstance`` (previously
      ``Instance`` only). The two share the same field shape so the
      downstream ``_build_problem_data`` works unchanged.
    - The matrix construction is delegated to the central helper. The
      private ``_build_distance_matrix`` symbol remains as a thin
      compatibility shim so existing test imports keep working — it
      simply forwards to the helper.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Sequence

import numpy as np

from ..instances import Instance
from ..perturbations.types import PerturbedInstance
from .marginal_costs import compute_customer_costs

logger = logging.getLogger(__name__)


# Resolve PyVRP version once at import time so SolveResult can record it.
try:
    _PYVRP_VERSION: str = version("pyvrp")
except PackageNotFoundError:  # pragma: no cover - package always installed in tests
    _PYVRP_VERSION = "unknown"


# ---------------------------------------------------------------------------
# Public dataclasses


@dataclass(frozen=True)
class SolveConfig:
    """Configuration for a single PyVRP solve.

    ``n_threads`` is documented for clarity but PyVRP 0.13.x has no
    thread-count parameter — solves are single-threaded by construction.
    The field exists to allow upstream code to pass a config object
    that names this constraint explicitly.
    """

    time_limit_seconds: float
    seed: int
    n_threads: int = 1

    def __post_init__(self) -> None:
        if self.time_limit_seconds <= 0:
            raise ValueError(
                f"time_limit_seconds must be positive, got {self.time_limit_seconds}"
            )
        if self.n_threads != 1:
            raise ValueError(
                f"n_threads must be 1 (project convention; PyVRP is single-threaded), "
                f"got {self.n_threads}"
            )

    def to_dict(self) -> dict:
        return {
            "time_limit_seconds": self.time_limit_seconds,
            "seed": self.seed,
            "n_threads": self.n_threads,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SolveConfig":
        return cls(
            time_limit_seconds=float(data["time_limit_seconds"]),
            seed=int(data["seed"]),
            n_threads=int(data.get("n_threads", 1)),
        )


@dataclass(frozen=True)
class SolveResult:
    """Output of a single PyVRP solve.

    Common to baseline computation (unperturbed instance) and action runs
    (perturbed instance). Field semantics match the project's
    :class:`~vrp_copilot_bench.actions.ActionResult` for the overlapping
    fields.

    routes
        One list per route, each containing the customer IDs visited in
        order. Depot is not included in the visits list. Customer IDs
        are 1-indexed (matching this project's :class:`Instance`
        convention; the depot is index 0).
    assignment
        ``customer_id → route_index`` map. Route indices match positions
        in ``routes``.
    route_costs
        ``route_index → distance``. Distances are integer-Euclidean in
        the project's distance convention; stored as floats for
        downstream metric computation.
    customer_costs
        ``customer_id → marginal cost`` per the removal-cost rule
        (prereg §9.4). Computed by
        :func:`solvers.marginal_costs.compute_customer_costs`.
    n_overload, max_overload_fraction
        Capacity-violation statistics. ``n_overload`` is the number of
        routes whose load exceeds vehicle capacity. ``max_overload_fraction``
        is ``max(load - capacity, 0) / capacity`` taken over routes;
        zero when all routes are feasible.
    """

    objective: float
    feasible: bool
    routes: list[list[int]]
    assignment: dict[int, int]
    route_costs: dict[int, float]
    customer_costs: dict[int, float]
    n_overload: int
    max_overload_fraction: float
    runtime_seconds: float
    pyvrp_version: str = field(default=_PYVRP_VERSION)


class SolverFailure(RuntimeError):
    """Raised when PyVRP fails to find any solution within the time limit."""


# ---------------------------------------------------------------------------
# Internal helpers


def _build_distance_matrix(coords: np.ndarray) -> np.ndarray:
    """Integer-rounded Euclidean distance matrix from (n, 2) coordinates.

    Output is ``(n, n)`` ``int64``. Diagonal is zero. Symmetric.

    Phase C compatibility shim: forwards to
    :func:`vrp_copilot_bench.actions.evaluate.build_perturbed_distance_matrix`
    via a minimal :class:`Instance` wrapper so test code that imported
    ``_build_distance_matrix(coords)`` keeps working bit-equivalently.
    Lazy import avoids actions↔solvers import-time entanglement.
    """
    from ..actions.evaluate import build_perturbed_distance_matrix

    n = coords.shape[0] - 1
    proxy = Instance(
        instance_id="_proxy",
        n_customers=n,
        capacity=1,
        n_vehicles=1,
        coords=coords,
        demands=np.zeros(n + 1, dtype=np.int64),
        depot_index=0,
    )
    return build_perturbed_distance_matrix(proxy)


def _build_problem_data(
    instance: Instance | PerturbedInstance,
    distance_matrix: np.ndarray,
):
    """Build a ``pyvrp.ProblemData`` from an :class:`Instance` or :class:`PerturbedInstance`.

    Builds one Depot from ``coords[0]``, one Client per remaining row of
    ``coords`` with ``delivery=demands[i]``, and one VehicleType with
    ``num_available=instance.n_vehicles, capacity=[instance.capacity]``.

    Both ``Instance`` and ``PerturbedInstance`` share the same scalar
    and array field shape (``n_customers``, ``coords``, ``demands``,
    ``capacity``, ``n_vehicles``); the same code works for either.

    Imports of PyVRP are lazy so importing this module is cheap.
    """
    from pyvrp import Client, Depot, ProblemData, VehicleType

    n_clients = instance.n_customers
    if distance_matrix.shape != (n_clients + 1, n_clients + 1):
        raise ValueError(
            f"distance_matrix shape {distance_matrix.shape} does not match "
            f"instance with {n_clients} customers"
        )

    depot = Depot(
        x=int(round(instance.coords[0, 0])),
        y=int(round(instance.coords[0, 1])),
    )
    clients = [
        Client(
            x=int(round(instance.coords[i, 0])),
            y=int(round(instance.coords[i, 1])),
            delivery=[int(instance.demands[i])],
        )
        for i in range(1, n_clients + 1)
    ]
    vehicle_type = VehicleType(
        num_available=int(instance.n_vehicles),
        capacity=[int(instance.capacity)],
    )

    duration_matrix = np.zeros_like(distance_matrix)
    return ProblemData(
        clients=clients,
        depots=[depot],
        vehicle_types=[vehicle_type],
        distance_matrices=[distance_matrix],
        duration_matrices=[duration_matrix],
    )


def _route_load(route: Sequence[int], demands: np.ndarray) -> int:
    return int(sum(int(demands[c]) for c in route))


# ---------------------------------------------------------------------------
# Public API


def solve(
    instance: Instance | PerturbedInstance, config: SolveConfig
) -> SolveResult:
    """Run PyVRP on ``instance`` with ``config``; return a populated SolveResult.

    Accepts both :class:`Instance` (unperturbed; baseline computation) and
    :class:`PerturbedInstance` (action-time, with optional
    ``distance_multiplier_mask``). The matrix construction goes through
    :func:`vrp_copilot_bench.actions.evaluate.build_perturbed_distance_matrix`
    so that DISTANCE perturbations propagate into PyVRP's search at the
    same matrix the evaluator will later score with — this is the
    load-bearing correctness guarantee for DISTANCE cells.

    Determinism note: PyVRP under ``MaxRuntime`` is wall-clock-bounded.
    The seed determines the search trajectory, but the *iteration count*
    completed within the time budget varies with system noise (CPU
    scheduling, JIT warm-up, allocator state). Two runs with the same
    seed therefore produce results within a tight noise band (typically
    well under the 2% bound the prereg uses for ``reference_obj_unstable``
    in §8.2), but not bit-equal incumbents. If bit-exact reproducibility
    is required for a downstream task, switch the stopping criterion to
    ``MaxIterations``; that is not the prereg-locked protocol but is a
    valid escape hatch for diagnostic re-runs.

    Raises
    ------
    SolverFailure
        If PyVRP returns no solution within the time limit. Rare for
        unperturbed CVRP at typical time budgets; possible for tightly
        perturbed instances.
    """
    # Lazy import: avoids an actions ↔ solvers cycle at module load.
    from ..actions.evaluate import build_perturbed_distance_matrix
    from pyvrp import solve as pyvrp_solve
    from pyvrp.stop import MaxRuntime

    distance_matrix = build_perturbed_distance_matrix(instance)
    data = _build_problem_data(instance, distance_matrix)

    t0 = time.perf_counter()
    result = pyvrp_solve(
        data,
        stop=MaxRuntime(config.time_limit_seconds),
        seed=config.seed,
        display=False,
        collect_stats=False,
    )
    runtime_seconds = time.perf_counter() - t0

    best = result.best
    if best is None or best.num_routes() == 0:
        raise SolverFailure(
            f"PyVRP returned no routes for instance {instance.instance_id} "
            f"within {config.time_limit_seconds}s (seed={config.seed})"
        )

    routes_list: list[list[int]] = []
    route_costs: dict[int, float] = {}
    assignment: dict[int, int] = {}
    n_overload = 0
    overload_fractions: list[float] = []

    for route_idx, pyvrp_route in enumerate(best.routes()):
        visits = [int(c) for c in pyvrp_route.visits()]
        if not visits:
            continue
        routes_list.append(visits)
        route_costs[route_idx] = float(pyvrp_route.distance())
        for c in visits:
            assignment[c] = route_idx

        load = _route_load(visits, instance.demands)
        if load > instance.capacity:
            n_overload += 1
            overload_fractions.append((load - instance.capacity) / instance.capacity)

    max_overload_fraction = max(overload_fractions, default=0.0)

    # Depot is always node 0 by project convention. ``Instance`` exposes
    # ``depot_index`` (default 0); ``PerturbedInstance`` doesn't carry the
    # field at all, but the depot convention is identical, so we use the
    # literal here rather than reading an attribute that exists on only
    # one of the two input types.
    customer_costs = compute_customer_costs(
        routes=routes_list,
        distance_matrix=distance_matrix,
        depot_id=0,
    )

    feasible = bool(result.is_feasible())
    objective = float(result.cost())

    logger.debug(
        "PyVRP solved %s in %.3fs: obj=%.1f feasible=%s routes=%d",
        instance.instance_id, runtime_seconds, objective, feasible, len(routes_list),
    )

    return SolveResult(
        objective=objective,
        feasible=feasible,
        routes=routes_list,
        assignment=assignment,
        route_costs=route_costs,
        customer_costs=customer_costs,
        n_overload=n_overload,
        max_overload_fraction=max_overload_fraction,
        runtime_seconds=runtime_seconds,
        pyvrp_version=_PYVRP_VERSION,
    )
