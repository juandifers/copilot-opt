"""Clarke-Wright parallel savings algorithm.

Algorithm (per Item 5 Phase B):

1. Seed: one route per customer, ``[c]``. Initial route load = ``demands[c]``.
2. Compute every customer-pair savings
   ``s_ij = d[0,i] + d[0,j] - d[i,j]`` for ``i < j``.
3. Process pairs in descending savings order; ties broken by ``(i, j)``
   ascending. **Stop as soon as the saving is non-positive** — at that
   point every remaining pair would lengthen the total tour rather than
   shorten it, so processing them only risks producing a plan worse
   than the all-singletons seed (this matches the canonical CW variant
   in standard textbooks and reference implementations).

4. For each surviving ``(i, j)``:

   - skip if ``i`` and ``j`` are already in the same route;
   - skip if combining the two routes would exceed vehicle capacity;
   - skip unless **both** ``i`` and ``j`` are at a *boundary* (first or
     last position) of their respective current routes — interior
     customers cannot merge or the route's depot-flanked path topology
     breaks.

5. Merge orientation: canonicalize so that ``i`` is at the *end* of
   ``route_i`` and ``j`` is at the *start* of ``route_j``; the merged
   route is then ``route_i + route_j``. Reverse one or both segments if
   needed. (For a singleton ``[c]``, ``c`` is at both ends — either
   orientation is valid; the canonical form is "no reversal needed".)

6. Stop after every (positive-savings) pair has been considered. The
   result is a list of routes, one per surviving non-empty equivalence
   class.

Oversized customers (individual demand > capacity): the singleton route
``[c]`` survives to the output. The evaluator marks such routes
infeasible (``feasible=False``, ``n_overload > 0``). CW always produces
a plan (worst case: every singleton route survives).

Empty-routes invariant: the algorithm never produces empty routes. The
seeding step creates ``n`` non-empty singletons; each merge replaces two
non-empty routes with one non-empty route; routes that are merged
*into* are removed from the active set rather than emptied. The final
output list contains only the surviving non-empty routes.

Customer / node ID convention: customer IDs are 1-indexed in
``[1, n_customers]``; the depot is ID 0.

Distance matrix contract: ``distance_matrix`` must be the perturbed-and
masked matrix from
:func:`vrp_copilot_bench.actions.evaluate.build_perturbed_distance_matrix`.
Construction and evaluation must use the same matrix.
"""
from __future__ import annotations

import numpy as np

from ...perturbations.types import PerturbedInstance


def construct(
    perturbed: PerturbedInstance,
    distance_matrix: np.ndarray,
) -> list[list[int]]:
    """Build a CVRP route plan via Clarke-Wright parallel savings.

    See module docstring for the algorithm and contract.
    """
    n = perturbed.n_customers
    capacity = int(perturbed.capacity)
    demands = perturbed.demands

    # ---------- Seed: one singleton route per customer ----------
    # Customers whose individual demand exceeds capacity survive as
    # singleton routes; the evaluator will mark them feasible=False with
    # n_overload > 0. Raising here would leave the group without a base
    # action in the parquet, which is worse than an infeasible result.
    # routes[idx] is the current state of route idx; we mutate by
    # replacing entries (the route absorbed in a merge becomes None).
    routes: list[list[int] | None] = [[c] for c in range(1, n + 1)]
    # Map customer id → current route slot. Routes are 0-indexed; customer c
    # starts in slot c-1.
    customer_to_slot: dict[int, int] = {c: c - 1 for c in range(1, n + 1)}
    # Per-slot accumulated load (only meaningful for non-None slots).
    route_load: list[int] = [int(demands[c]) for c in range(1, n + 1)]

    # ---------- Savings list ----------
    # Build (savings, i, j) triples for i < j; sort descending by savings,
    # ties ascending by (i, j).
    triples: list[tuple[float, int, int]] = []
    for i in range(1, n + 1):
        for j in range(i + 1, n + 1):
            s = (
                float(distance_matrix[0, i])
                + float(distance_matrix[0, j])
                - float(distance_matrix[i, j])
            )
            triples.append((s, i, j))
    # Negative second/third component flips: sort by (-s, i, j) ascending
    # is equivalent to "savings descending, then i ascending, then j ascending".
    triples.sort(key=lambda t: (-t[0], t[1], t[2]))

    # ---------- Process merges ----------
    for saving, i, j in triples:
        # Classical CW: stop once savings turn non-positive — every
        # subsequent merge would lengthen the total tour.
        if saving <= 0.0:
            break
        si = customer_to_slot[i]
        sj = customer_to_slot[j]
        if si == sj:
            continue
        ri = routes[si]
        rj = routes[sj]
        # routes[si] / routes[sj] cannot be None because customer_to_slot
        # always points to the *current* slot for any customer.
        assert ri is not None and rj is not None

        # Capacity check
        if route_load[si] + route_load[sj] > capacity:
            continue

        # Boundary check: i must be at start or end of ri; same for j in rj.
        i_at_start = ri[0] == i
        i_at_end = ri[-1] == i
        if not (i_at_start or i_at_end):
            continue
        j_at_start = rj[0] == j
        j_at_end = rj[-1] == j
        if not (j_at_start or j_at_end):
            continue

        # Canonicalize: i at end of seg_i, j at start of seg_j.
        # (For singletons, both ends evaluate True → no reversal.)
        seg_i = ri if i_at_end else list(reversed(ri))
        seg_j = rj if j_at_start else list(reversed(rj))
        merged = seg_i + seg_j

        # Replace si with the merged route; mark sj as absorbed.
        routes[si] = merged
        route_load[si] = route_load[si] + route_load[sj]
        routes[sj] = None
        route_load[sj] = 0
        for c in merged:
            customer_to_slot[c] = si

    # Collect the survivors in slot order (stable).
    return [r for r in routes if r is not None]
