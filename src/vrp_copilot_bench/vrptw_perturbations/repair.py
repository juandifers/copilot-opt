"""Local cheapest-feasible-insertion repair for the v2 VRPTW pilot.

For ORDER_CHANGE perturbations the baseline route plan cannot cover the
newly-inserted customers (``reuse_direct`` reports coverage failure).
This module supplies a *local repair* action that keeps the existing
route structure intact and inserts each new customer into the best
position on an existing route using a cheap deterministic heuristic.

Algorithm
---------
For each inserted customer (in increasing customer-ID order):

1. Enumerate every (route_idx, pos) candidate insertion on the *current*
   route plan.
2. Evaluate the candidate plan under the perturbed instance via
   :func:`vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper.evaluate_vrptw_solution`.
3. Among **feasible** candidates (capacity OK *and* TW OK), choose the
   one with the lowest objective. Tie-break by lowest route_idx, then
   lowest insertion position.
4. If no candidate is feasible, choose by lexicographic key
   ``(total_time_warp, objective, route_idx, position)``.
5. Commit the chosen insertion to the current plan and move on to the
   next inserted customer.

Returns
-------
:class:`LocalRepairResult` — the patched routes + diagnostics
(``inserted_all``, ``total_insertions``, per-customer success flags,
``opened_new_route``).

The implementation does *not* open a new vehicle in v2 by default — it
operates strictly on the baseline's existing route slots. If
``allow_new_route=True`` is passed, an empty route slot is appended once
all existing routes are infeasibility-dominated for a given insertion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..solvers.pyvrp_vrptw_wrapper import evaluate_vrptw_solution


@dataclass(frozen=True)
class LocalRepairResult:
    """Outcome of :func:`local_repair_insert`."""

    routes: list[list[int]]
    inserted_all: bool
    total_insertions: int
    opened_new_route: bool
    per_customer_feasible: dict[int, bool]
    per_customer_route_idx: dict[int, int]
    per_customer_position: dict[int, int]


def _copy_routes(routes: list[list[int]]) -> list[list[int]]:
    return [list(r) for r in routes]


def local_repair_insert(
    perturbed_instance: Any,
    baseline_routes: list[list[int]],
    inserted_customer_ids: tuple[int, ...] | list[int],
    *,
    allow_new_route: bool = False,
) -> LocalRepairResult:
    """Greedy cheapest-feasible-insertion of inserted customers.

    See module docstring for full semantics.
    """
    current = _copy_routes(baseline_routes)
    inserted_sorted = sorted(int(c) for c in inserted_customer_ids)

    per_customer_feasible: dict[int, bool] = {}
    per_customer_route_idx: dict[int, int] = {}
    per_customer_position: dict[int, int] = {}
    opened_new_route = False
    total_insertions = 0

    for new_c in inserted_sorted:
        best_feasible: tuple[float, int, int, list[list[int]]] | None = None
        # (obj, route_idx, pos, candidate_routes) lexicographic min

        best_infeasible: tuple[int, float, int, int, list[list[int]]] | None = None
        # (time_warp, obj, route_idx, pos, candidate_routes) lexicographic min

        # Try every existing-route position.
        for ri, route in enumerate(current):
            for pos in range(len(route) + 1):
                cand = _copy_routes(current)
                cand[ri] = list(route[:pos]) + [new_c] + list(route[pos:])
                ev = evaluate_vrptw_solution(perturbed_instance, cand)

                # ``is_complete`` requires every instance customer to be in
                # the plan, but later-inserted customers are still missing
                # during intermediate steps. So we only check cap + TW.
                cap_ok = ev.feasible_capacity_only
                tw_ok = ev.feasible_tw_only
                feasible_here = cap_ok and tw_ok

                if feasible_here:
                    key = (float(ev.objective), int(ri), int(pos))
                    if best_feasible is None or key < (
                        best_feasible[0], best_feasible[1], best_feasible[2],
                    ):
                        best_feasible = (
                            float(ev.objective), int(ri), int(pos), cand,
                        )
                else:
                    key = (
                        int(ev.total_time_warp), float(ev.objective),
                        int(ri), int(pos),
                    )
                    if best_infeasible is None or key < (
                        best_infeasible[0], best_infeasible[1],
                        best_infeasible[2], best_infeasible[3],
                    ):
                        best_infeasible = (
                            int(ev.total_time_warp), float(ev.objective),
                            int(ri), int(pos), cand,
                        )

        # Optionally try opening a new (empty) route.
        if (
            allow_new_route and best_feasible is None
            and len(current) < perturbed_instance.n_vehicles
        ):
            new_route_idx = len(current)
            cand = _copy_routes(current) + [[new_c]]
            ev = evaluate_vrptw_solution(perturbed_instance, cand)
            cap_ok = ev.feasible_capacity_only
            tw_ok = ev.feasible_tw_only
            if cap_ok and tw_ok:
                best_feasible = (
                    float(ev.objective), int(new_route_idx), 0, cand,
                )
                opened_new_route = True

        # Commit the best choice.
        if best_feasible is not None:
            _, ri, pos, cand = best_feasible
            per_customer_feasible[new_c] = True
        else:
            assert best_infeasible is not None, "no candidates at all?"
            _, _, ri, pos, cand = best_infeasible
            per_customer_feasible[new_c] = False
        per_customer_route_idx[new_c] = ri
        per_customer_position[new_c] = pos
        current = cand
        total_insertions += 1

    inserted_all = all(per_customer_feasible.values())

    return LocalRepairResult(
        routes=current,
        inserted_all=inserted_all,
        total_insertions=total_insertions,
        opened_new_route=opened_new_route,
        per_customer_feasible=per_customer_feasible,
        per_customer_route_idx=per_customer_route_idx,
        per_customer_position=per_customer_position,
    )
