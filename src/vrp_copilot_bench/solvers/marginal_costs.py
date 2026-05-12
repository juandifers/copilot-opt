"""Per-customer marginal-cost computation.

Implements the classical removal-cost formulation: for a customer ``c``
sitting between ``prev`` and ``next`` in a route,

::

    customer_cost[c] = d[prev, c] + d[c, next] − d[prev, next]

i.e. the extra distance ``c`` adds to the route compared to the
(prev, next) shortcut. The depot is treated as ``prev`` for the first
customer and as ``next`` for the last customer in each route.

This is the cost-attribution rule the prereg locks for the RANK metric
(prereg §9.4: ``cost_contribution(c, plan, instance)``). Action wrappers
and the baseline pipeline both call this to populate the
``customer_costs`` field of :class:`vrp_copilot_bench.actions.ActionResult`
and :class:`vrp_copilot_bench.baselines.Solution`.

The module is intentionally PyVRP-free: it operates on a routes list
and a distance matrix, both NumPy/Python-native. That keeps it testable
in isolation and reusable on perturbed-instance distance matrices that
action wrappers will produce later.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np


def compute_customer_costs(
    routes: Sequence[Sequence[int]],
    distance_matrix: np.ndarray,
    depot_id: int = 0,
) -> dict[int, float]:
    """Compute per-customer marginal-cost contributions.

    For each customer ``c_i`` in each route ``[c_1, c_2, ..., c_k]`` (the
    depot is *not* part of the visits list — it's appended/prepended
    implicitly via ``depot_id``), the marginal cost is

    ::

        d[prev, c_i] + d[c_i, next] − d[prev, next]

    where ``prev`` and ``next`` are the depot at the route boundaries and
    the adjacent customers in the interior.

    Parameters
    ----------
    routes
        Sequence of routes. Each route is itself a sequence of customer
        IDs (depot excluded). IDs are indices into ``distance_matrix``.
        Empty routes are silently skipped.
    distance_matrix
        2-D array of distances. ``distance_matrix[i, j]`` is the cost of
        traveling from node ``i`` to node ``j``. Customer IDs in
        ``routes`` and ``depot_id`` are valid row/column indices.
    depot_id
        Node ID of the depot (default 0, matching this project's
        :class:`Instance` convention).

    Returns
    -------
    dict mapping customer_id → marginal cost (Python float).

    Notes
    -----
    The sum of returned values equals the total route cost minus the
    depot-to-depot direct edge ``d[depot, depot] = 0`` for each route —
    i.e. ``sum(customer_costs) ≈ sum(route_costs)`` for routes that
    return to the same depot. The approximation is exact under the
    removal-cost decomposition because every internal edge is shared
    by two adjacent customers' contributions and the boundary edges are
    accounted for once each.
    """
    customer_costs: dict[int, float] = {}
    for route in routes:
        n = len(route)
        if n == 0:
            continue
        for i, c in enumerate(route):
            prev = depot_id if i == 0 else route[i - 1]
            nxt = depot_id if i == n - 1 else route[i + 1]
            cost = (
                float(distance_matrix[prev, c])
                + float(distance_matrix[c, nxt])
                - float(distance_matrix[prev, nxt])
            )
            customer_costs[int(c)] = cost
    return customer_costs
