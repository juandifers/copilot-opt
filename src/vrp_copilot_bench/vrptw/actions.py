"""VRPTW action layer for the scale-check.

Action ladder
-------------
The benchmark question — *given a disruption and a claim family, which level
of computational response is sufficient?* — only makes sense if we have a
range of responses with monotonically increasing cost.

==========================  ====  ====================================
action                      tier  what it does
==========================  ====  ====================================
``reuse_direct``            0     score baseline routes unchanged
``local_repair_insert``     1     OC-only: greedy cheapest-feasible
                                  insertion of new customers into
                                  existing routes
``construct_feasible``   2     deterministic build-from-scratch
                                  insertion heuristic (ignores
                                  baseline); fast-path eval
``pyvrp_10s``               3     PyVRP metaheuristic, 10 s budget,
                                  seed 1
``pyvrp_60s_reference``     4     materialized from reference seed 1
                                  (no extra solve)
==========================  ====  ====================================

The cheap-action mapping (``cheap_action_for_family``) is unchanged: it
is the *lowest-tier feasible response* per family. OC is the only family
where tier 0 (``reuse_direct``) fails coverage, so its cheap action is
tier 1 (``local_repair_insert``). Everything else stays at tier 0.

construct_feasible fast path
-------------------------------
The naive spec is "evaluate each candidate via ``evaluate_vrptw_solution``";
under O(N²) candidates per cell that's projected at ~40 h for the full
18-instance run because each call rebuilds the PyVRP ``ProblemData``.

The fast path here prebuilds ``ProblemData`` once per perturbed instance
and constructs ``pyvrp.Solution(data, routes)`` directly inside the inner
loop. The decision rule (feasibility predicate + lexicographic tie-break)
is *bit-identical* to the spec — only the per-candidate evaluation cost
changes. The final committed plan is re-scored with
``evaluate_vrptw_solution`` so the :class:`ActionResult` it returns
matches what any other action would produce.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from ..vrptw_perturbations.repair import (
    LocalRepairResult,
    local_repair_insert,
)
from .perturbations import VRPTWPerturbedInstance
from .solver import (
    EvaluatedVRPTW,
    SolveConfig,
    VRPTWSolveResult,
    evaluate_vrptw_solution,
    solve_vrptw,
)

logger = logging.getLogger(__name__)


CHEAP_ACTION_FOR_FAMILY: dict[str, str] = {
    "TRAVEL_TIME": "reuse_direct",
    "TIME_WINDOW": "reuse_direct",
    "SERVICE_TIME": "reuse_direct",
    "ORDER_CHANGE": "local_repair_insert",
}


#: Map from action name to (tier_index, tier_label, is_middle, is_reference).
#: Stable ordering: 0 < 1 < 2 < 3 < 4.
ACTION_TIER: dict[str, tuple[int, str, bool, bool]] = {
    "reuse_direct":           (0, "0_reuse",               False, False),
    "local_repair_insert":    (1, "1_repair",              False, False),
    "construct_feasible":  (2, "2_construct",           True,  False),
    "pyvrp_10s":              (3, "3_pyvrp_10s",           True,  False),
    "pyvrp_60s_reference":    (4, "4_pyvrp_60s_reference", False, True),
}


def cheap_action_for_family(family: str) -> str:
    """Return the cheap action name to use for a given perturbation family."""
    try:
        return CHEAP_ACTION_FOR_FAMILY[family]
    except KeyError as exc:  # pragma: no cover — guarded upstream
        raise ValueError(f"unknown perturbation family {family!r}") from exc


def actions_for_family(family: str, *, expanded: bool) -> tuple[str, ...]:
    """Action set for a given perturbation family.

    ``expanded=False`` reproduces the original scale-check (reuse / repair).
    ``expanded=True`` returns the full ladder; OC adds ``local_repair_insert``
    as the only family-specific entry. ``pyvrp_60s_reference`` is *included*
    here so the runner enumerates it uniformly — the runner materializes
    that row from reference seed 1 rather than running another solve.
    """
    if not expanded:
        if family == "ORDER_CHANGE":
            return ("reuse_direct", "local_repair_insert")
        return ("reuse_direct",)
    if family == "ORDER_CHANGE":
        return (
            "reuse_direct",
            "local_repair_insert",
            "construct_feasible",
            "pyvrp_10s",
            "pyvrp_60s_reference",
        )
    return (
        "reuse_direct",
        "construct_feasible",
        "pyvrp_10s",
        "pyvrp_60s_reference",
    )


@dataclass(frozen=True)
class ActionResult:
    """Uniform return type for :class:`VRPTWAction`.

    ``routes`` is the route plan the action wants scored. ``evaluation``
    is :func:`evaluate_vrptw_solution` applied to those routes under the
    perturbed instance. ``runtime_seconds`` is wall-clock action time
    (excluding the evaluation call for actions that score outside the
    inner loop). ``local_repair`` is non-None only for
    :class:`LocalRepairInsert`. ``solver_seed`` and
    ``solver_time_limit_seconds`` are populated only for solver-tier
    actions (``pyvrp_10s``, ``pyvrp_60s_reference``).
    """

    name: str
    routes: list[list[int]]
    evaluation: EvaluatedVRPTW
    runtime_seconds: float
    local_repair: LocalRepairResult | None = None
    solver_seed: int | None = None
    solver_time_limit_seconds: float | None = None


class VRPTWAction(Protocol):
    """Anything that turns a perturbed instance + baseline routes into a
    scored route plan. Implementations live below."""

    name: str

    def apply(
        self,
        perturbed: VRPTWPerturbedInstance,
        baseline_routes: list[list[int]],
    ) -> ActionResult:  # pragma: no cover — protocol
        ...


# ---------------------------------------------------------------------------
# reuse_direct


@dataclass(frozen=True)
class ReuseDirect:
    """Score the baseline route plan as-is under the perturbed instance.

    Always-applicable. For ORDER_CHANGE this reports coverage failure;
    that's intentional — the scale-check evaluates both ``reuse_direct``
    and ``local_repair_insert`` on OC cells to show *why* reuse fails.
    """

    name: str = "reuse_direct"

    def apply(
        self,
        perturbed: VRPTWPerturbedInstance,
        baseline_routes: list[list[int]],
    ) -> ActionResult:
        t0 = time.perf_counter()
        routes = [list(map(int, r)) for r in baseline_routes if r]
        ev = evaluate_vrptw_solution(perturbed, routes)
        elapsed = time.perf_counter() - t0
        return ActionResult(
            name=self.name,
            routes=routes,
            evaluation=ev,
            runtime_seconds=elapsed,
            local_repair=None,
        )


# ---------------------------------------------------------------------------
# local_repair_insert


@dataclass(frozen=True)
class LocalRepairInsert:
    """Cheapest-feasible-insertion repair for ORDER_CHANGE cells.

    Inserts each new customer (in increasing ID order) into the best
    feasible position on the *existing* baseline routes. Never opens a
    new vehicle in the scale-check (``allow_new_route=False``). Falls
    back to the lex-min infeasible candidate when no feasible insertion
    exists.

    Calling this on a non-ORDER_CHANGE cell is harmless but pointless —
    ``inserted_customer_ids`` will be empty and the result equals
    :class:`ReuseDirect`.
    """

    name: str = "local_repair_insert"
    allow_new_route: bool = False

    def apply(
        self,
        perturbed: VRPTWPerturbedInstance,
        baseline_routes: list[list[int]],
    ) -> ActionResult:
        t0 = time.perf_counter()
        inserted = tuple(int(c) for c in perturbed.affected_customers) if (
            perturbed.perturbation_family == "ORDER_CHANGE"
        ) else ()
        repair = local_repair_insert(
            perturbed,
            [list(map(int, r)) for r in baseline_routes if r],
            inserted,
            allow_new_route=self.allow_new_route,
        )
        ev = evaluate_vrptw_solution(perturbed, repair.routes)
        elapsed = time.perf_counter() - t0
        return ActionResult(
            name=self.name,
            routes=repair.routes,
            evaluation=ev,
            runtime_seconds=elapsed,
            local_repair=repair,
        )


# ---------------------------------------------------------------------------
# construct_feasible


def _build_problem_data_for(perturbed: VRPTWPerturbedInstance):
    """Build a PyVRP ``ProblemData`` once for a given perturbed instance.

    Wraps the existing wrapper helpers. The result is reusable across many
    ``Solution(data, routes)`` constructions inside the inner loop.
    """
    from ..solvers.pyvrp_vrptw_wrapper import (
        SCALING_FACTOR,
        _build_distance_matrix,
        _build_problem_data,
    )

    distance_matrix = _build_distance_matrix(perturbed.coords, SCALING_FACTOR)
    return _build_problem_data(perturbed, distance_matrix)


def _quick_score(data: Any, routes: list[list[int]]) -> tuple[bool, bool, float, int]:
    """Score a candidate route plan with prebuilt ``ProblemData``.

    Returns ``(cap_ok, tw_ok, distance, time_warp)``. ``distance`` and
    ``time_warp`` are PyVRP's scaled-unit values. ``cap_ok`` and
    ``tw_ok`` mirror :func:`evaluate_vrptw_solution`'s split feasibility
    semantics. Excludes ``is_complete`` because intermediate construction
    plans don't cover every customer yet.
    """
    from pyvrp import Solution

    cleaned = [list(map(int, r)) for r in routes if r]
    sol = Solution(data, cleaned)
    return (
        not bool(sol.has_excess_load()),
        not bool(sol.has_time_warp()),
        float(sol.distance()),
        int(sol.time_warp()),
    )


def _customer_construction_order(perturbed: VRPTWPerturbedInstance) -> list[int]:
    """Sort customers by ``(tw_late asc, tw_early asc, id asc)``.

    Deterministic. Customer indices are 1..n_customers (depot excluded).
    Time windows here are the raw Solomon values (not scaled); ordering
    is scale-invariant.
    """
    tw = perturbed.time_windows
    customers = list(range(1, int(perturbed.n_customers) + 1))
    customers.sort(key=lambda c: (int(tw[c, 1]), int(tw[c, 0]), int(c)))
    return customers


@dataclass(frozen=True)
class ConstructFeasible:
    """Deterministic build-from-scratch insertion heuristic.

    Construction loop
    -----------------
    1. Customers are visited in ``(tw_late asc, tw_early asc, id asc)``
       order.
    2. For each customer, every (existing-route, position) candidate is
       scored, plus a single ``open a new route`` candidate when
       ``len(routes) < n_vehicles``.
    3. Feasible candidates win over infeasible. Among feasible, the key
       is ``(distance, n_routes, route_idx, position)``. Among infeasible
       only, the key is ``(time_warp, distance, n_routes, route_idx,
       position)``.
    4. The chosen candidate is committed and we move on.

    Performance note
    ----------------
    A naive implementation that called :func:`evaluate_vrptw_solution`
    once per candidate would scale to ~40 h for the 18-instance run
    because each call rebuilds the PyVRP ``ProblemData``. This
    implementation prebuilds the ``ProblemData`` once per perturbed
    instance and constructs ``pyvrp.Solution(data, routes)`` directly
    inside the inner loop. The heuristic, the feasibility predicate,
    and the lexicographic acceptance rule are *bit-identical* to the
    spec; only the per-candidate eval cost changes. The committed plan
    is re-scored via :func:`evaluate_vrptw_solution` so the returned
    :class:`ActionResult` carries a normal :class:`EvaluatedVRPTW`.
    """

    name: str = "construct_feasible"

    def apply(
        self,
        perturbed: VRPTWPerturbedInstance,
        baseline_routes: list[list[int]],
    ) -> ActionResult:
        t0 = time.perf_counter()

        data = _build_problem_data_for(perturbed)
        n_vehicles = int(perturbed.n_vehicles)
        order = _customer_construction_order(perturbed)
        current: list[list[int]] = []

        for new_c in order:
            best_feasible: tuple[float, int, int, int, list[list[int]]] | None = None
            # (obj, n_routes, ri, pos, candidate)
            best_infeasible: tuple[int, float, int, int, int, list[list[int]]] | None = None
            # (time_warp, obj, n_routes, ri, pos, candidate)

            # Existing-route candidates.
            for ri, route in enumerate(current):
                for pos in range(len(route) + 1):
                    cand = [list(r) for r in current]
                    cand[ri] = route[:pos] + [new_c] + route[pos:]
                    cap_ok, tw_ok, obj, tw_total = _quick_score(data, cand)
                    n_routes = sum(1 for r in cand if r)
                    if cap_ok and tw_ok:
                        key = (obj, n_routes, ri, pos)
                        if best_feasible is None or key < best_feasible[:4]:
                            best_feasible = (obj, n_routes, ri, pos, cand)
                    else:
                        key = (tw_total, obj, n_routes, ri, pos)
                        if best_infeasible is None or key < best_infeasible[:5]:
                            best_infeasible = (
                                tw_total, obj, n_routes, ri, pos, cand,
                            )

            # New-route candidate (single slot opened with this customer).
            if len(current) < n_vehicles:
                new_ri = len(current)
                cand = [list(r) for r in current] + [[new_c]]
                cap_ok, tw_ok, obj, tw_total = _quick_score(data, cand)
                n_routes = len(current) + 1
                if cap_ok and tw_ok:
                    key = (obj, n_routes, new_ri, 0)
                    if best_feasible is None or key < best_feasible[:4]:
                        best_feasible = (obj, n_routes, new_ri, 0, cand)
                else:
                    key = (tw_total, obj, n_routes, new_ri, 0)
                    if best_infeasible is None or key < best_infeasible[:5]:
                        best_infeasible = (
                            tw_total, obj, n_routes, new_ri, 0, cand,
                        )

            if best_feasible is not None:
                current = best_feasible[4]
            elif best_infeasible is not None:
                current = best_infeasible[5]
            else:
                raise RuntimeError(
                    f"construct_feasible: no candidates for customer {new_c} "
                    f"under {perturbed.perturbation_id}"
                )

        ev = evaluate_vrptw_solution(perturbed, current)
        elapsed = time.perf_counter() - t0
        return ActionResult(
            name=self.name,
            routes=[list(r) for r in current if r],
            evaluation=ev,
            runtime_seconds=elapsed,
        )


# ---------------------------------------------------------------------------
# pyvrp_10s


@dataclass(frozen=True)
class PyvrpSolve:
    """Run a fresh PyVRP solve on the perturbed instance.

    Used as the ``pyvrp_10s`` action (``time_limit_seconds=10``,
    ``seed=1``). The 60-second reference rows are materialized from
    reference seed 1 rather than re-solving; see
    :func:`materialize_reference_action`.
    """

    name: str = "pyvrp_10s"
    seed: int = 1
    time_limit_seconds: float = 10.0

    def apply(
        self,
        perturbed: VRPTWPerturbedInstance,
        baseline_routes: list[list[int]],
    ) -> ActionResult:
        t0 = time.perf_counter()
        cfg = SolveConfig(time_limit_seconds=self.time_limit_seconds, seed=self.seed)
        result = solve_vrptw(perturbed, cfg)
        ev = evaluate_vrptw_solution(perturbed, result.routes)
        elapsed = time.perf_counter() - t0
        return ActionResult(
            name=self.name,
            routes=[list(r) for r in result.routes if r],
            evaluation=ev,
            runtime_seconds=elapsed,
            solver_seed=int(self.seed),
            solver_time_limit_seconds=float(self.time_limit_seconds),
        )


# ---------------------------------------------------------------------------
# Materialized pyvrp_60s_reference (not a runnable Action — built from refs)


def materialize_reference_action(
    perturbed: VRPTWPerturbedInstance,
    ref_s1: VRPTWSolveResult,
    *,
    time_limit_seconds: float,
) -> ActionResult:
    """Build the ``pyvrp_60s_reference`` :class:`ActionResult` from ref seed 1.

    No extra solve. Routes come from ``ref_s1``; the evaluation is the
    fixed-route score under the perturbed instance (so the action shares
    the same :class:`EvaluatedVRPTW` shape as every other action and the
    feasibility/coverage fields are consistent).
    """
    if ref_s1.routes:
        ev = evaluate_vrptw_solution(
            perturbed, [list(r) for r in ref_s1.routes if r],
        )
        routes = [list(r) for r in ref_s1.routes if r]
    else:
        # No-routes reference (failure case): score the empty plan so the
        # evaluation reports coverage failure cleanly.
        ev = evaluate_vrptw_solution(perturbed, [])
        routes = []
    return ActionResult(
        name="pyvrp_60s_reference",
        routes=routes,
        evaluation=ev,
        runtime_seconds=float(ref_s1.runtime_seconds),
        solver_seed=1,
        solver_time_limit_seconds=float(time_limit_seconds),
    )


__all__ = [
    "ACTION_TIER",
    "ActionResult",
    "CHEAP_ACTION_FOR_FAMILY",
    "ConstructFeasible",
    "LocalRepairInsert",
    "LocalRepairResult",
    "PyvrpSolve",
    "ReuseDirect",
    "VRPTWAction",
    "actions_for_family",
    "cheap_action_for_family",
    "materialize_reference_action",
]
