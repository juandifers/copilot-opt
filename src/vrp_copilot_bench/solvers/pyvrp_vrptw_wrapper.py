"""PyVRP wrapper for the VRPTW probes (Phase 1 + perturbation pilot).

Sibling to :mod:`vrp_copilot_bench.solvers.pyvrp_wrapper` and intentionally
separate — the CVRP wrapper is preregistered and must not be altered.

Scaling convention (×10)
------------------------
PyVRP expects integer distance/duration/time values. Solomon time
windows and service times are already integers, but Euclidean distances
between Solomon coordinates are reals with one decimal of useful
precision. To keep travel times, service times, and time windows on a
common integer scale, every quantity is multiplied by 10 before being
handed to PyVRP::

    distance_matrix[i, j] = round(10 * euclidean(coords[i], coords[j]))
    duration_matrix       = distance_matrix * travel_time_mask (default 1.0)
    time_windows          = round(10 * raw_time_windows)
    service_times         = round(10 * raw_service_times)

The reported ``objective`` is therefore in "×10 distance units" and is
**not** comparable to published Solomon BKS values without dividing by
10. Stability metrics (pairwise ARI, relative objective drift) are
scale-invariant. No BKS comparison is performed here.

Perturbation pilot additions
----------------------------
- :func:`solve_vrptw` and :func:`evaluate_vrptw_solution` accept either
  :class:`VRPTWInstance` (unperturbed) or
  :class:`vrp_copilot_bench.vrptw_perturbations.types.VRPTWPerturbedInstance`
  (perturbed). The two share the same field shape (``coords``, ``demands``,
  ``service_times``, ``time_windows``, ``capacity``, ``n_vehicles``) so the
  same ``_build_problem_data`` path works for both.
- If the input carries a non-None ``travel_time_multiplier_mask`` of shape
  ``(n+1, n+1)``, the duration matrix is scaled element-wise by it.
  Distances are unchanged.
- :class:`VRPTWSolveResult` now also carries ``route_summaries`` and
  ``per_customer_schedule`` (optional; populated by default).
- :func:`evaluate_vrptw_solution` constructs ``pyvrp.Solution(data, fixed_routes)``
  under the perturbed ProblemData and returns the same kind of schedule
  payload as ``solve_vrptw`` plus capacity/TW-split feasibility flags.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import numpy as np

from ..vrptw_instances import VRPTWInstance
from .pyvrp_wrapper import SolveConfig  # reuse the CVRP config dataclass

logger = logging.getLogger(__name__)


try:
    _PYVRP_VERSION: str = version("pyvrp")
except PackageNotFoundError:  # pragma: no cover
    _PYVRP_VERSION = "unknown"


#: Integer rescaling factor applied to distances, durations, time windows,
#: and service times. See module docstring.
SCALING_FACTOR: int = 10


# ---------------------------------------------------------------------------
# Schedule dataclasses


@dataclass(frozen=True)
class VisitSchedule:
    """Per-customer schedule entry derived from PyVRP's ``ScheduledVisit``.

    All time fields are in the ×10-scaled unit system the solver saw.
    ``arrival = start_service - wait_duration`` by definition of PyVRP's
    schedule semantics.
    """

    customer_id: int
    route_idx: int
    arrival: int
    start_service: int
    end_service: int
    wait_duration: int
    service_duration: int
    time_warp: int
    tw_early: int
    tw_late: int
    slack_to_tw_late: int  # tw_late - start_service (negative if late)


@dataclass(frozen=True)
class RouteSummary:
    """Per-route aggregates from PyVRP's ``Route``."""

    route_idx: int
    n_customers: int
    start_time: int
    end_time: int
    distance: int
    duration: int
    wait_duration: int
    service_duration: int
    travel_duration: int
    time_warp: int
    slack: int  # depot return slack from PyVRP
    is_feasible: bool
    has_time_warp: bool
    has_excess_load: bool
    min_slack_to_tw_late: int  # min over customers in this route
    mean_slack_to_tw_late: float
    n_late_customers: int


@dataclass(frozen=True)
class EvaluatedVRPTW:
    """Output of :func:`evaluate_vrptw_solution` — fixed-route reuse evaluation."""

    objective: float
    feasible: bool
    feasible_capacity_only: bool
    feasible_tw_only: bool
    is_complete: bool
    has_time_warp: bool
    total_time_warp: int
    total_duration: int
    total_wait: int
    total_distance: int
    n_late_customers: int
    max_lateness: int
    routes: list[list[int]]
    assignment: dict[int, int]
    route_summaries: list[RouteSummary]
    per_customer_schedule: dict[int, VisitSchedule]
    unserved_customers: list[int]


@dataclass(frozen=True)
class VRPTWSolveResult:
    """Output of a single VRPTW PyVRP solve.

    All scalar costs/durations are in the ×10-scaled unit system the solver
    saw (see module docstring). Divide by :data:`SCALING_FACTOR` to recover
    the published Solomon distance unit.

    ``route_summaries`` and ``per_customer_schedule`` were added for the
    perturbation pilot (additive; Phase 1 callers do not need them).
    """

    objective: float
    feasible: bool
    routes: list[list[int]]
    assignment: dict[int, int]
    route_costs: dict[int, float]
    runtime_seconds: float
    pyvrp_version: str
    n_routes: int
    total_duration: float | None = field(default=None)
    route_summaries: list[RouteSummary] = field(default_factory=list)
    per_customer_schedule: dict[int, VisitSchedule] = field(default_factory=dict)


class VRPTWSolverFailure(RuntimeError):
    """Raised when PyVRP fails to produce a usable VRPTW solution.

    Carries ``instance_id``, ``seed``, ``time_limit_seconds`` and the
    triggering exception's message so callers can attribute the failure
    without re-running.
    """

    def __init__(
        self,
        instance_id: str,
        seed: int,
        time_limit_seconds: float,
        message: str,
    ) -> None:
        super().__init__(
            f"VRPTW solve failed for instance={instance_id!r} "
            f"seed={seed} time_limit={time_limit_seconds}s: {message}"
        )
        self.instance_id = instance_id
        self.seed = seed
        self.time_limit_seconds = time_limit_seconds
        self.message = message


# ---------------------------------------------------------------------------
# Internal helpers


def _build_distance_matrix(coords: np.ndarray, factor: int) -> np.ndarray:
    """``round(factor * euclidean(coords))`` as an int64 ``(n, n)`` matrix."""
    diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
    sq = (diff ** 2).sum(axis=-1)
    dist = np.sqrt(sq) * factor
    return np.round(dist).astype(np.int64)


def _build_duration_matrix(
    coords: np.ndarray,
    factor: int,
    travel_time_mask: np.ndarray | None,
) -> np.ndarray:
    """Duration matrix; equal to distance matrix when ``mask is None``.

    When a mask is provided the scaling-then-rounding is done **once** on
    ``factor * raw_distance * mask`` to avoid the double-round drift you
    get from rounding distance first and then multiplying.
    """
    diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
    raw = np.sqrt((diff ** 2).sum(axis=-1))
    if travel_time_mask is None:
        scaled = factor * raw
    else:
        if travel_time_mask.shape != raw.shape:
            raise ValueError(
                f"travel_time_multiplier_mask shape {travel_time_mask.shape} "
                f"does not match coords-derived shape {raw.shape}"
            )
        scaled = factor * raw * travel_time_mask
    return np.round(scaled).astype(np.int64)


def _problem_input_fields(instance: Any) -> tuple[np.ndarray, np.ndarray | None]:
    """Return ``(coords, travel_time_multiplier_mask)`` from any input.

    Accepts either :class:`VRPTWInstance` (no mask) or
    :class:`VRPTWPerturbedInstance` (mask may be present or None).
    """
    mask = getattr(instance, "travel_time_multiplier_mask", None)
    return instance.coords, mask


def _build_problem_data(instance: Any, distance_matrix: np.ndarray):
    """Build a ``pyvrp.ProblemData`` from a VRPTW(Perturbed)Instance.

    Time windows and service times are rescaled by :data:`SCALING_FACTOR`
    to match the distance/duration scale. Duration matrix is constructed
    here (so it can pick up an optional ``travel_time_multiplier_mask``).
    """
    from pyvrp import Client, Depot, ProblemData, VehicleType

    n_clients = instance.n_customers
    if distance_matrix.shape != (n_clients + 1, n_clients + 1):
        raise ValueError(
            f"distance_matrix shape {distance_matrix.shape} does not match "
            f"instance with {n_clients} customers"
        )

    tw = instance.time_windows * SCALING_FACTOR
    st = instance.service_times * SCALING_FACTOR

    depot = Depot(
        x=float(instance.coords[0, 0]),
        y=float(instance.coords[0, 1]),
        tw_early=int(tw[0, 0]),
        tw_late=int(tw[0, 1]),
        service_duration=int(st[0]),
    )
    clients = [
        Client(
            x=float(instance.coords[i, 0]),
            y=float(instance.coords[i, 1]),
            delivery=[int(instance.demands[i])],
            service_duration=int(st[i]),
            tw_early=int(tw[i, 0]),
            tw_late=int(tw[i, 1]),
        )
        for i in range(1, n_clients + 1)
    ]
    # Vehicle's own working horizon is the depot's [tw_early, tw_late]
    # window: every vehicle must depart no earlier than depot open and
    # return no later than depot close.
    vehicle_type = VehicleType(
        num_available=int(instance.n_vehicles),
        capacity=[int(instance.capacity)],
        tw_early=int(tw[0, 0]),
        tw_late=int(tw[0, 1]),
    )

    _, mask = _problem_input_fields(instance)
    duration_matrix = _build_duration_matrix(
        instance.coords, SCALING_FACTOR, mask,
    )
    return ProblemData(
        clients=clients,
        depots=[depot],
        vehicle_types=[vehicle_type],
        distance_matrices=[distance_matrix],
        duration_matrices=[duration_matrix],
    )


def _extract_schedule(
    solution, instance: Any,
) -> tuple[list[RouteSummary], dict[int, VisitSchedule], dict[int, int]]:
    """Walk ``solution.routes()`` and pull per-route + per-customer schedule.

    Per-customer ``slack_to_tw_late`` is computed externally as
    ``tw_late_scaled - start_service`` (PyVRP doesn't surface it directly).
    The depot entries in each route's schedule (``location == 0``) are
    filtered out — only customer visits land in ``per_customer_schedule``.
    """
    tw = instance.time_windows * SCALING_FACTOR
    summaries: list[RouteSummary] = []
    per_customer: dict[int, VisitSchedule] = {}
    assignment: dict[int, int] = {}

    for route_idx, pyvrp_route in enumerate(solution.routes()):
        visits = [int(c) for c in pyvrp_route.visits()]
        if not visits:
            continue

        route_per_cust_slack: list[int] = []
        n_late = 0
        for sv in pyvrp_route.schedule():
            loc = int(sv.location)
            if loc == 0:  # depot endpoints — skip
                continue
            tw_early_c = int(tw[loc, 0])
            tw_late_c = int(tw[loc, 1])
            start = int(sv.start_service)
            slack = tw_late_c - start
            route_per_cust_slack.append(slack)
            # PyVRP encodes lateness via per-visit ``time_warp`` (a visit's
            # start_service is always clamped to ``<= tw_late``; any "would
            # have been late" amount is folded into ``time_warp``). So we
            # count *late customers* by ``time_warp > 0`` rather than by
            # comparing start_service to tw_late.
            tw_violation = int(sv.time_warp)
            if tw_violation > 0:
                n_late += 1
            per_customer[loc] = VisitSchedule(
                customer_id=loc,
                route_idx=route_idx,
                arrival=start - int(sv.wait_duration),
                start_service=start,
                end_service=int(sv.end_service),
                wait_duration=int(sv.wait_duration),
                service_duration=int(sv.service_duration),
                time_warp=tw_violation,
                tw_early=tw_early_c,
                tw_late=tw_late_c,
                slack_to_tw_late=slack,
            )
            assignment[loc] = route_idx

        min_slack = min(route_per_cust_slack) if route_per_cust_slack else 0
        mean_slack = (
            float(np.mean(route_per_cust_slack))
            if route_per_cust_slack else 0.0
        )
        summaries.append(RouteSummary(
            route_idx=route_idx,
            n_customers=len(visits),
            start_time=int(pyvrp_route.start_time()),
            end_time=int(pyvrp_route.end_time()),
            distance=int(pyvrp_route.distance()),
            duration=int(pyvrp_route.duration()),
            wait_duration=int(pyvrp_route.wait_duration()),
            service_duration=int(pyvrp_route.service_duration()),
            travel_duration=int(pyvrp_route.travel_duration()),
            time_warp=int(pyvrp_route.time_warp()),
            slack=int(pyvrp_route.slack()),
            is_feasible=bool(pyvrp_route.is_feasible()),
            has_time_warp=bool(pyvrp_route.has_time_warp()),
            has_excess_load=bool(pyvrp_route.has_excess_load()),
            min_slack_to_tw_late=min_slack,
            mean_slack_to_tw_late=mean_slack,
            n_late_customers=n_late,
        ))

    return summaries, per_customer, assignment


# ---------------------------------------------------------------------------
# Public API


def solve_vrptw(
    instance: Any, config: SolveConfig
) -> VRPTWSolveResult:
    """Run PyVRP on a VRPTW(Perturbed)Instance and return a populated result.

    Accepts :class:`VRPTWInstance` (Phase 1 path) and
    :class:`vrp_copilot_bench.vrptw_perturbations.types.VRPTWPerturbedInstance`
    (pilot path). Both share the same shape; the latter may carry a
    ``travel_time_multiplier_mask`` that scales the duration matrix.

    Raises
    ------
    VRPTWSolverFailure
        If PyVRP raises or returns no solution within the time limit.
    """
    from pyvrp import solve as pyvrp_solve
    from pyvrp.stop import MaxRuntime

    distance_matrix = _build_distance_matrix(instance.coords, SCALING_FACTOR)
    data = _build_problem_data(instance, distance_matrix)

    t0 = time.perf_counter()
    try:
        result = pyvrp_solve(
            data,
            stop=MaxRuntime(config.time_limit_seconds),
            seed=config.seed,
            display=False,
            collect_stats=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise VRPTWSolverFailure(
            instance.instance_id, config.seed, config.time_limit_seconds,
            f"{type(exc).__name__}: {exc}",
        ) from exc
    runtime_seconds = time.perf_counter() - t0

    best = result.best
    if best is None or best.num_routes() == 0:
        raise VRPTWSolverFailure(
            instance.instance_id, config.seed, config.time_limit_seconds,
            "PyVRP returned no routes within the time limit",
        )

    route_summaries, per_customer, assignment = _extract_schedule(best, instance)

    routes_list: list[list[int]] = []
    route_costs: dict[int, float] = {}
    total_duration: float = 0.0

    for route_idx, pyvrp_route in enumerate(best.routes()):
        visits = [int(c) for c in pyvrp_route.visits()]
        if not visits:
            continue
        routes_list.append(visits)
        route_costs[route_idx] = float(pyvrp_route.distance())
        total_duration += float(pyvrp_route.duration())

    n_routes = len(routes_list)
    feasible = bool(result.is_feasible())
    objective = float(result.cost())

    logger.debug(
        "VRPTW PyVRP solved %s seed=%d in %.3fs: obj=%.1f feasible=%s routes=%d",
        instance.instance_id, config.seed, runtime_seconds,
        objective, feasible, n_routes,
    )

    return VRPTWSolveResult(
        objective=objective,
        feasible=feasible,
        routes=routes_list,
        assignment=assignment,
        route_costs=route_costs,
        runtime_seconds=runtime_seconds,
        pyvrp_version=_PYVRP_VERSION,
        n_routes=n_routes,
        total_duration=total_duration if total_duration > 0.0 else None,
        route_summaries=route_summaries,
        per_customer_schedule=per_customer,
    )


def evaluate_vrptw_solution(
    instance: Any, fixed_routes: list[list[int]],
) -> EvaluatedVRPTW:
    """Score a fixed route plan under a (possibly perturbed) VRPTW instance.

    Constructs ``pyvrp.Solution(data, fixed_routes)`` under the perturbed
    ``ProblemData`` and reads off distance, schedule, time-warp, and
    coverage. No solving — PyVRP just computes the deterministic schedule
    for the supplied routes.

    For ORDER_CHANGE perturbations the baseline routes do not cover the
    newly-inserted customers; PyVRP reports ``num_missing_clients > 0`` and
    ``is_complete=False``. Those customers are surfaced in
    ``unserved_customers`` and the overall ``feasible`` flag is ``False``.
    The ``feasible_capacity_only`` / ``feasible_tw_only`` flags reflect the
    state of the *served* routes — useful for diagnosing what kind of
    infeasibility a cell exhibits.
    """
    from pyvrp import Solution

    distance_matrix = _build_distance_matrix(instance.coords, SCALING_FACTOR)
    data = _build_problem_data(instance, distance_matrix)

    sol = Solution(data, [list(map(int, r)) for r in fixed_routes if r])

    route_summaries, per_customer, assignment = _extract_schedule(sol, instance)

    # Total time-warp (PyVRP-reported, scaled units): one number for the
    # whole solution. Per-customer time_warp summed gives the same total
    # when routes feed through to the depot return; we trust the global one.
    total_time_warp = int(sol.time_warp())
    total_duration = int(sol.duration())
    total_distance = int(sol.distance())
    total_wait = sum(int(rs.wait_duration) for rs in route_summaries)
    has_time_warp = bool(sol.has_time_warp())
    has_excess_load = bool(sol.has_excess_load())
    is_complete = bool(sol.is_complete())

    # Capacity-only feasibility: would the existing routes be capacity-OK
    # ignoring TW? PyVRP's per-route ``has_excess_load`` gives us this.
    feasible_capacity_only = not has_excess_load
    feasible_tw_only = not has_time_warp
    feasible_overall = feasible_capacity_only and feasible_tw_only and is_complete

    # Per-customer lateness from schedule (PyVRP encodes lateness via
    # ``time_warp``; see ``_extract_schedule``).
    n_late = sum(rs.n_late_customers for rs in route_summaries)
    max_lateness = max(
        (vs.time_warp for vs in per_customer.values()), default=0,
    )

    # Determine which clients (if any) are missing.
    served = set(assignment.keys())
    all_customers = set(range(1, instance.n_customers + 1))
    unserved = sorted(all_customers - served)

    routes_clean = [list(map(int, r)) for r in fixed_routes if r]
    objective = float(total_distance)  # cost == distance (unit_duration_cost=0)

    return EvaluatedVRPTW(
        objective=objective,
        feasible=feasible_overall,
        feasible_capacity_only=feasible_capacity_only,
        feasible_tw_only=feasible_tw_only,
        is_complete=is_complete,
        has_time_warp=has_time_warp,
        total_time_warp=total_time_warp,
        total_duration=total_duration,
        total_wait=total_wait,
        total_distance=total_distance,
        n_late_customers=n_late,
        max_lateness=max_lateness,
        routes=routes_clean,
        assignment=assignment,
        route_summaries=route_summaries,
        per_customer_schedule=per_customer,
        unserved_customers=unserved,
    )
