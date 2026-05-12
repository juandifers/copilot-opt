"""Greedy nearest-neighbor route construction.

Algorithm (per Item 5 Phase B):

1. Start every new route at the depot with an empty truck (load 0).
2. Among unvisited customers whose demand fits in the truck's remaining
   capacity, pick the one nearest the *current node* (depot at start of a
   route, last visited customer otherwise). Ties: lowest customer ID.
3. Append the chosen customer; advance current node; subtract demand;
   repeat until no customer fits.
4. Close the route (return-to-depot is implicit) and start a new one.
5. Stop when no unvisited customers remain.

Oversized customers: if a fresh empty truck cannot accept *any* remaining
customer (every remaining demand > capacity), each such customer is
placed on its own single-customer route. The evaluator marks them
infeasible (``feasible=False``, ``n_overload > 0``). Raising here would
leave the group without a base action in the parquet.

Empty-routes invariant: the algorithm never produces empty routes. A
route is appended to ``routes`` only after at least one customer has been
added to it; if the inner loop exits before adding any customer (which
can only happen on a fresh empty truck), the algorithm raises rather
than appending. Action wrappers and the evaluator may rely on this.

Customer / node ID convention: customer IDs are 1-indexed in
``[1, n_customers]``; the depot is ID 0. Routes are ``list[int]`` of
customer IDs in visit order; the depot is implicit at both ends.

Distance matrix contract: ``distance_matrix`` must be the same matrix
that the evaluator will use to score the result. Pass the output of
:func:`vrp_copilot_bench.actions.evaluate.build_perturbed_distance_matrix`.
This is the only correct call site; bypassing the helper produces silent
DISTANCE-perturbation corruption.
"""
from __future__ import annotations

import numpy as np

from ...perturbations.types import PerturbedInstance


def construct(
    perturbed: PerturbedInstance,
    distance_matrix: np.ndarray,
) -> list[list[int]]:
    """Build a CVRP route plan via greedy nearest-neighbor.

    See module docstring for the algorithm and contract.
    """
    n = perturbed.n_customers
    capacity = int(perturbed.capacity)
    demands = perturbed.demands

    unvisited: set[int] = set(range(1, n + 1))
    routes: list[list[int]] = []

    while unvisited:
        current_route: list[int] = []
        current_load = 0
        current_node = 0  # depot

        while True:
            # Filter to capacity-feasible candidates from a fresh truck.
            best_dist: int | None = None
            best_c: int | None = None
            for c in unvisited:
                if current_load + int(demands[c]) > capacity:
                    continue
                d = int(distance_matrix[current_node, c])
                # Tie: lowest customer ID wins.
                if best_dist is None or d < best_dist or (d == best_dist and c < best_c):
                    best_dist = d
                    best_c = c

            if best_c is None:
                break

            current_route.append(best_c)
            current_load += int(demands[best_c])
            unvisited.remove(best_c)
            current_node = best_c

        if not current_route:
            # Every remaining customer has demand > capacity on a fresh
            # truck. Place each on its own singleton route; the evaluator
            # will mark the plan infeasible with n_overload > 0.
            for c in sorted(unvisited):
                routes.append([c])
            break
        routes.append(current_route)

    return routes
