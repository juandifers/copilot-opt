"""Shared evaluator and the single source of truth for the perturbed
distance matrix.

This module centralizes two operations every action implementation needs:

1. :func:`build_perturbed_distance_matrix` — build the integer-rounded
   Euclidean distance matrix from coordinates and apply the optional
   ``distance_multiplier_mask`` element-wise. Every caller in Item 5
   (evaluator, NN, CW, PyVRP wrapper) must use this helper. If any caller
   computes its own matrix, DISTANCE perturbations silently corrupt and
   Stage A produces wrong data.

2. :func:`evaluate_route_plan` — score a route plan under a (perturbed)
   instance: total objective, per-route cost, per-customer marginal cost,
   feasibility, and capacity-overload statistics. Returns
   :class:`EvaluatedRoutePlan`.

Customer / node ID convention (used everywhere in this package):
    - Customer IDs are 1-indexed integers in ``[1, n_customers]``.
    - The depot has ID 0.
    - ``coords`` and ``demands`` are indexed by node ID; ``demands[0] == 0``.
    - Route representation: ``list[int]`` of customer IDs in visit order.
      Depot is implicit at both ends — never include 0 in a route.

Vehicle count is elastic in this benchmark (the published Kmin in
``X-nN-kK`` is a minimum, not a hard cap). Feasibility means
**capacity-only**: every route's load ≤ vehicle capacity. The number of
routes is not constrained; ``len(routes) > n_vehicles`` is permitted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..instances import Instance
from ..perturbations.types import PerturbedInstance
from ..solvers.marginal_costs import compute_customer_costs


# ---------------------------------------------------------------------------
# Distance matrix construction


def build_perturbed_distance_matrix(
    obj: PerturbedInstance | Instance,
) -> np.ndarray:
    """Integer-rounded Euclidean distance matrix, with optional mask applied.

    Output is ``(n+1, n+1)`` ``int64``, where ``n = obj.n_customers``.
    Diagonal is zero. Symmetric.

    Behavior by input type:

    - :class:`Instance`: identical to
      ``solvers.pyvrp_wrapper._build_distance_matrix(obj.coords)``. No mask.
    - :class:`PerturbedInstance` with ``distance_multiplier_mask is None``:
      same as the unmasked case (CAPACITY, DEMAND, INSERTION outputs).
    - :class:`PerturbedInstance` with a ``(n+1, n+1)`` float mask
      (DISTANCE outputs): the mask is multiplied element-wise into the
      distance matrix and the result is rounded back to int64 once.

    This is the single source of truth for distance matrices in Item 5.
    Every caller — evaluator, NN, CW, PyVRP wrapper — must use this helper.
    Centralization is the load-bearing correctness guarantee for DISTANCE
    perturbations.
    """
    coords = obj.coords
    diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
    sq = (diff ** 2).sum(axis=-1)
    dist = np.sqrt(sq)

    mask = getattr(obj, "distance_multiplier_mask", None)
    if mask is not None:
        if mask.shape != dist.shape:
            raise ValueError(
                f"distance_multiplier_mask shape {mask.shape} does not match "
                f"coords-derived distance matrix shape {dist.shape}"
            )
        dist = dist * mask

    return np.round(dist).astype(np.int64)


# ---------------------------------------------------------------------------
# Route plan evaluation


@dataclass(frozen=True)
class EvaluatedRoutePlan:
    """Result of evaluating a route plan under a (possibly perturbed) instance.

    Field semantics match :class:`vrp_copilot_bench.actions.ActionResult`:
    every field except ``routes`` and the action-name metadata is populated
    here, and an action wrapper composes its ``ActionResult`` from this.
    """

    objective: float
    feasible: bool
    n_overload: int
    max_overload_fraction: float
    assignment: dict[int, int]
    route_costs: dict[int, float]
    customer_costs: dict[int, float]


def _route_load(route: Sequence[int], demands: np.ndarray) -> int:
    return int(sum(int(demands[c]) for c in route))


def _route_cost(route: Sequence[int], distance_matrix: np.ndarray, depot: int) -> float:
    """Total distance: depot → first ... last → depot."""
    if not route:
        return 0.0
    cost = float(distance_matrix[depot, route[0]])
    for i in range(len(route) - 1):
        cost += float(distance_matrix[route[i], route[i + 1]])
    cost += float(distance_matrix[route[-1], depot])
    return cost


def evaluate_route_plan(
    routes: list[list[int]],
    perturbed: PerturbedInstance | Instance,
    *,
    allow_partial_coverage: bool = False,
    unassigned_label: int = -1,
) -> EvaluatedRoutePlan:
    """Score a route plan under a (perturbed) instance.

    Parameters
    ----------
    routes
        One list per route, customer IDs in visit order. Customer IDs lie in
        ``[1, n_customers]``; the depot (0) is implicit at both ends and must
        not appear inside a route.
    perturbed
        :class:`PerturbedInstance` (Item 5 default) or :class:`Instance`
        (round-trip / convenience use). The distance matrix is built via
        :func:`build_perturbed_distance_matrix`, so DISTANCE masks are
        applied here in this single location.
    allow_partial_coverage
        When ``False`` (default): the union of routes must equal
        ``{1, ..., n_customers}`` exactly — no duplicates, no missing.
        When ``True``: the union may be a strict subset; missing customers
        appear in the returned ``assignment`` with value ``unassigned_label``.
    unassigned_label
        Sentinel route id for missing customers (default ``-1``). Only used
        when ``allow_partial_coverage=True``.

    Returns
    -------
    :class:`EvaluatedRoutePlan` with:

    - ``objective`` — sum of route costs under the (masked) distance matrix.
    - ``feasible`` — True iff every route's load ≤ ``perturbed.capacity``.
    - ``n_overload`` — count of routes with load > capacity.
    - ``max_overload_fraction`` — ``max((load - capacity) / capacity, 0)``
      taken over routes; 0 if feasible.
    - ``assignment`` — ``customer_id → route_index`` (plus
      ``unassigned_label`` entries when partial).
    - ``route_costs`` — ``route_index → cost``.
    - ``customer_costs`` — ``customer_id → marginal cost`` via
      :func:`solvers.marginal_costs.compute_customer_costs`. Unassigned
      customers do not appear in this dict.

    Vehicle-count is elastic — the route count is not validated.

    Raises
    ------
    ValueError
        If a customer ID lies outside ``[1, n_customers]``, if a customer
        appears in more than one route, if depot (0) appears inside a
        route, or if ``allow_partial_coverage=False`` and the partition
        is incomplete.
    """
    n = perturbed.n_customers
    capacity = perturbed.capacity
    demands = perturbed.demands

    # ---------- partition validation ----------
    seen: set[int] = set()
    for ri, route in enumerate(routes):
        for c in route:
            if c == 0:
                raise ValueError(
                    f"route {ri} contains the depot (0); depot is implicit "
                    f"and must not appear inside a route"
                )
            if c < 1 or c > n:
                raise ValueError(
                    f"route {ri} contains customer id {c}, outside [1, {n}]"
                )
            if c in seen:
                raise ValueError(
                    f"customer {c} appears in more than one route"
                )
            seen.add(c)

    expected = set(range(1, n + 1))
    if not allow_partial_coverage and seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise ValueError(
            f"route plan does not cover {{1..{n}}} exactly: "
            f"missing={missing[:10]}{'...' if len(missing) > 10 else ''}, "
            f"extra={extra[:10]}{'...' if len(extra) > 10 else ''}"
        )

    # ---------- distance matrix and per-route metrics ----------
    distance_matrix = build_perturbed_distance_matrix(perturbed)
    depot = 0

    assignment: dict[int, int] = {}
    route_costs: dict[int, float] = {}
    n_overload = 0
    overload_fractions: list[float] = []
    objective = 0.0

    for ri, route in enumerate(routes):
        if not route:
            # Empty routes contribute nothing; skip without index allocation.
            continue
        cost = _route_cost(route, distance_matrix, depot)
        route_costs[ri] = cost
        objective += cost
        for c in route:
            assignment[c] = ri
        load = _route_load(route, demands)
        if load > capacity:
            n_overload += 1
            overload_fractions.append((load - capacity) / capacity)

    if allow_partial_coverage:
        for c in expected - seen:
            assignment[c] = unassigned_label

    customer_costs = compute_customer_costs(
        routes=routes,
        distance_matrix=distance_matrix,
        depot_id=depot,
    )

    return EvaluatedRoutePlan(
        objective=objective,
        feasible=(n_overload == 0),
        n_overload=n_overload,
        max_overload_fraction=max(overload_fractions, default=0.0),
        assignment=assignment,
        route_costs=route_costs,
        customer_costs=customer_costs,
    )
