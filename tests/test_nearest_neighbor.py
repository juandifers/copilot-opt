"""Tests for the greedy nearest-neighbor heuristic.

Two layers:

1. The ``construct`` primitive — algorithmic correctness on hand-checked
   instances (visit order, tie-breaking, capacity, the ActionFailure path).
2. The ``nearest_neighbor_action`` wrapper — produces a valid
   :class:`ActionResult` with the cost-invariant
   ``objective == sum(route_costs)`` and matches the evaluator's view.

The DISTANCE-mask integration test (visiting customer 5 later under a
2× mask) is the load-bearing test: it proves NN consumed the perturbed
matrix during construction, not just the unperturbed coords.
"""
from __future__ import annotations

import numpy as np
import pytest

from vrp_copilot_bench.actions import ActionFailure, ActionResult
from vrp_copilot_bench.actions.evaluate import build_perturbed_distance_matrix
from vrp_copilot_bench.actions.heuristic_actions import nearest_neighbor_action
from vrp_copilot_bench.baselines import Solution
from vrp_copilot_bench.instances import Instance
from vrp_copilot_bench.perturbations.types import PerturbedInstance
from vrp_copilot_bench.solvers.heuristics.nearest_neighbor import construct
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig


# ---------------------------------------------------------------------------
# Fixture helpers


def _instance(
    *,
    coords: list[tuple[float, float]],
    demands: list[int],
    capacity: int,
    instance_id: str = "toy_nn",
    n_vehicles: int | None = None,
) -> Instance:
    coords_arr = np.array(coords, dtype=np.float64)
    demands_arr = np.array(demands, dtype=np.int64)
    n = len(coords) - 1
    return Instance(
        instance_id=instance_id,
        n_customers=n,
        capacity=capacity,
        n_vehicles=n_vehicles if n_vehicles is not None else n,
        coords=coords_arr,
        demands=demands_arr,
        depot_index=0,
    )


def _to_perturbed(
    inst: Instance,
    *,
    family: str = "CAPACITY",
    perturbation_id: str = "CAP_1",
    magnitude: float = 0.02,
    capacity: int | None = None,
    demands: np.ndarray | None = None,
    coords: np.ndarray | None = None,
    n_customers: int | None = None,
    mask: np.ndarray | None = None,
) -> PerturbedInstance:
    return PerturbedInstance(
        instance_id=inst.instance_id,
        perturbation_id=perturbation_id,
        perturbation_family=family,
        perturbation_magnitude=magnitude,
        n_customers=n_customers if n_customers is not None else inst.n_customers,
        coords=coords if coords is not None else inst.coords,
        demands=demands if demands is not None else inst.demands,
        capacity=capacity if capacity is not None else inst.capacity,
        n_vehicles=inst.n_vehicles,
        distance_multiplier_mask=mask,
        n_affected_customers=0,
        affected_demand_share=0.0,
        affected_route_share=0.0,
    )


def _baseline_for(inst: Instance) -> Solution:
    """Synthetic baseline. NN/CW wrappers ignore it; provided for signature."""
    return Solution(
        instance_id=inst.instance_id,
        objective=0.0,
        routes=[[c] for c in range(1, inst.n_customers + 1)],
        assignment={c: c - 1 for c in range(1, inst.n_customers + 1)},
        route_costs={c - 1: 0.0 for c in range(1, inst.n_customers + 1)},
        customer_costs={c: 0.0 for c in range(1, inst.n_customers + 1)},
        runtime_seconds=0.0,
        pyvrp_version="test",
        config=SolveConfig(time_limit_seconds=1.0, seed=1),
    )


# ---------------------------------------------------------------------------
# Hand-traced 3-customer NN run


def test_nn_three_customer_visit_order() -> None:
    """3 customers on the x-axis. Capacity holds all three; one route.

    Coords: depot(0,0), c1(1,0), c2(3,0), c3(2,0).

    From depot: nearest is c1 (d=1), then c2 (d=2 from c1)? Wait —
    after c1, c3 is at distance |3-1.5|=... no, from c1(1,0): c2 is at
    distance 2 (3-1), c3 at distance 1 (2-1). c3 wins.
    From c3(2,0): c2 (d=1). Done.

    Expected route: [1, 3, 2].
    """
    inst = _instance(
        coords=[(0.0, 0.0), (1.0, 0.0), (3.0, 0.0), (2.0, 0.0)],
        demands=[0, 10, 10, 10],
        capacity=100,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    assert routes == [[1, 3, 2]]


def test_nn_tie_breaking_lowest_id() -> None:
    """Equidistant candidates: lowest customer ID wins.

    Coords: depot(0,0), c1(10,0), c2(0,10).
    d(0,1) = 10, d(0,2) = 10. Tie → c1 first."""
    inst = _instance(
        coords=[(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)],
        demands=[0, 5, 5],
        capacity=100,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    assert routes == [[1, 2]]


def test_nn_determinism() -> None:
    """Same inputs produce the same routes."""
    rng = np.random.default_rng(42)
    n = 15
    coords = np.zeros((n + 1, 2), dtype=np.float64)
    coords[0] = (50.0, 50.0)
    coords[1:] = rng.uniform(0, 100, size=(n, 2))
    demands = np.zeros(n + 1, dtype=np.int64)
    demands[1:] = rng.integers(5, 20, size=n)
    inst = _instance(
        coords=[tuple(c) for c in coords],
        demands=demands.tolist(),
        capacity=50,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    a = construct(perturbed, dm)
    b = construct(perturbed, dm)
    assert a == b


def test_nn_capacity_respected() -> None:
    """Every route's load ≤ capacity."""
    inst = _instance(
        coords=[(0.0, 0.0)] + [(i * 5.0, 0.0) for i in range(1, 11)],
        demands=[0] + [10] * 10,
        capacity=30,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    for r in routes:
        load = sum(int(perturbed.demands[c]) for c in r)
        assert load <= perturbed.capacity, (
            f"route {r} load {load} > capacity {perturbed.capacity}"
        )


def test_nn_coverage_complete() -> None:
    """Every customer appears in exactly one route."""
    inst = _instance(
        coords=[(0.0, 0.0)] + [(i * 5.0, 0.0) for i in range(1, 11)],
        demands=[0] + [10] * 10,
        capacity=30,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    flat = [c for r in routes for c in r]
    assert sorted(flat) == list(range(1, 11))


def test_nn_never_produces_empty_routes() -> None:
    """No route in the output is empty (project invariant)."""
    inst = _instance(
        coords=[(0.0, 0.0)] + [(i * 5.0, 0.0) for i in range(1, 11)],
        demands=[0] + [7] * 10,
        capacity=20,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    assert all(len(r) > 0 for r in routes)


def test_nn_oversized_customer_becomes_singleton_route() -> None:
    """Customer with demand > capacity gets its own singleton route.

    The heuristic no longer raises — it returns an infeasible plan so the
    consolidator gets a full (instance, perturbation) group rather than a
    missing base action.  The evaluator marks the plan feasible=False with
    n_overload > 0.
    """
    inst = _instance(
        coords=[(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)],
        demands=[0, 50, 30],  # c1 demand 50 > capacity 40
        capacity=40,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    # c2 (demand 30 ≤ 40) forms a normal route; c1 (demand 50 > 40) is a singleton.
    all_customers = sorted(c for route in routes for c in route)
    assert all_customers == [1, 2]
    singleton_routes = [r for r in routes if len(r) == 1]
    assert [1] in singleton_routes  # oversized customer on its own


# ---------------------------------------------------------------------------
# DISTANCE-mask integration test (load-bearing)


def test_nn_uses_perturbed_distance_matrix() -> None:
    """Customer 5's edges doubled → C5 visited later than under unmasked.

    Geometry (5 customers + depot, all on x-axis at integer positions):

        depot=0, c1=10, c2=20, c3=30, c4=40, c5=5

    Without mask: from depot, c5 (d=5) is closest → visited first.
    Routes (capacity 100, demands all 10): [[5, 1, 2, 3, 4]].

    With 2× mask on every edge touching c5:
        d(0,5) = round(2*5)=10, equals d(0,1)=10 → tie-break to c1.
        From c1(10,0): d(1,5)=10 (mask), d(1,2)=10 (no mask) → tie → c2.
        From c2: d(2,5)=30, d(2,3)=10 → c3.
        From c3: d(3,5)=50, d(3,4)=10 → c4.
        From c4: only c5 left → c5.
    Routes: [[1, 2, 3, 4, 5]].

    Assertion: in the unmasked plan customer 5's position in its route
    is strictly less than in the masked plan.
    """
    inst = _instance(
        coords=[
            (0.0, 0.0),
            (10.0, 0.0),
            (20.0, 0.0),
            (30.0, 0.0),
            (40.0, 0.0),
            (5.0, 0.0),
        ],
        demands=[0, 10, 10, 10, 10, 10],
        capacity=100,
    )
    # Unmasked
    p_unmasked = _to_perturbed(inst)
    dm_unmasked = build_perturbed_distance_matrix(p_unmasked)
    routes_unmasked = construct(p_unmasked, dm_unmasked)

    # Masked: 2× on every edge touching customer 5.
    n = inst.n_customers
    mask = np.ones((n + 1, n + 1), dtype=np.float64)
    mask[5, :] = 2.0
    mask[:, 5] = 2.0
    np.fill_diagonal(mask, 1.0)
    p_masked = _to_perturbed(
        inst, family="DISTANCE", perturbation_id="DIST_3", magnitude=2.0, mask=mask
    )
    dm_masked = build_perturbed_distance_matrix(p_masked)
    routes_masked = construct(p_masked, dm_masked)

    # Find C5's route + position in each plan.
    def _find_pos(routes: list[list[int]], c: int) -> tuple[int, int]:
        for ri, r in enumerate(routes):
            if c in r:
                return ri, r.index(c)
        raise AssertionError(f"customer {c} not in any route")

    ru, pu = _find_pos(routes_unmasked, 5)
    rm, pm = _find_pos(routes_masked, 5)
    # When the plan is a single route, ri is the same, so position alone
    # is the comparator. When plans split into multiple routes, prefer
    # comparing the *order in which customer 5 is visited overall* — the
    # cumulative position over preceding routes plus index.
    cum_pos_unmasked = sum(len(r) for r in routes_unmasked[:ru]) + pu
    cum_pos_masked = sum(len(r) for r in routes_masked[:rm]) + pm
    assert cum_pos_masked > cum_pos_unmasked, (
        f"expected customer 5 to be visited later under 2× mask: "
        f"unmasked pos {cum_pos_unmasked} (routes={routes_unmasked}), "
        f"masked pos {cum_pos_masked} (routes={routes_masked})"
    )


# ---------------------------------------------------------------------------
# Action wrapper


def test_nn_action_returns_action_result() -> None:
    inst = _instance(
        coords=[(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)],
        demands=[0, 10, 10, 10],
        capacity=30,
    )
    perturbed = _to_perturbed(inst)
    out = nearest_neighbor_action(perturbed, _baseline_for(inst))
    assert isinstance(out, ActionResult)
    assert out.action == "nearest_neighbor"


def test_nn_action_objective_equals_sum_of_route_costs() -> None:
    inst = _instance(
        coords=[(0.0, 0.0)] + [(i * 7.0, i * 3.0) for i in range(1, 9)],
        demands=[0] + [8] * 8,
        capacity=30,
    )
    perturbed = _to_perturbed(inst)
    out = nearest_neighbor_action(perturbed, _baseline_for(inst))
    assert out.objective == pytest.approx(
        sum(out.route_costs.values()), abs=1e-6
    )


def test_nn_action_assignment_covers_all() -> None:
    inst = _instance(
        coords=[(0.0, 0.0)] + [(i * 7.0, i * 3.0) for i in range(1, 9)],
        demands=[0] + [8] * 8,
        capacity=30,
    )
    perturbed = _to_perturbed(inst)
    out = nearest_neighbor_action(perturbed, _baseline_for(inst))
    assert set(out.assignment) == set(range(1, 9))
    assert all(v >= 0 for v in out.assignment.values())
