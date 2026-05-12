"""Tests for the shared evaluator.

Exercises both public helpers in :mod:`vrp_copilot_bench.actions.evaluate`:

- :func:`build_perturbed_distance_matrix` — including the critical mask
  application path (DISTANCE perturbations).
- :func:`evaluate_route_plan` — round-trip on hand-computed plans,
  feasibility/overload accounting, partition strictness, partial-coverage
  semantics, vehicle-count elasticity, and the
  ``objective == sum(route_costs)`` invariant.

Note on hand-computed expectations: the project rounds Euclidean distances
to ``int64`` per CVRPLIB convention. Hand-computed integers below match
the same rule.
"""
from __future__ import annotations

import numpy as np
import pytest

from vrp_copilot_bench.actions.evaluate import (
    EvaluatedRoutePlan,
    build_perturbed_distance_matrix,
    evaluate_route_plan,
)
from vrp_copilot_bench.instances import Instance
from vrp_copilot_bench.perturbations.types import PerturbedInstance
from vrp_copilot_bench.solvers.marginal_costs import compute_customer_costs


# ---------------------------------------------------------------------------
# Fixtures


def _toy_instance(
    *,
    coords: list[tuple[float, float]],
    demands: list[int],
    capacity: int = 100,
    n_vehicles: int = 5,
    instance_id: str = "toy",
) -> Instance:
    coords_arr = np.array(coords, dtype=np.float64)
    demands_arr = np.array(demands, dtype=np.int64)
    n = len(coords) - 1
    assert demands_arr[0] == 0
    return Instance(
        instance_id=instance_id,
        n_customers=n,
        capacity=capacity,
        n_vehicles=n_vehicles,
        coords=coords_arr,
        demands=demands_arr,
        depot_index=0,
    )


def _to_perturbed(
    inst: Instance,
    *,
    family: str = "CAPACITY",
    perturbation_id: str = "CAP_1",
    magnitude: float = 0.05,
    capacity: int | None = None,
    demands: np.ndarray | None = None,
    coords: np.ndarray | None = None,
    n_customers: int | None = None,
    mask: np.ndarray | None = None,
) -> PerturbedInstance:
    """Build a PerturbedInstance from an Instance with selective overrides."""
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


@pytest.fixture
def square_instance() -> Instance:
    """4 customers on a 100-unit square, depot at center.

    Layout:
            c4 (0,100)        c3 (100,100)
                       depot (50, 50)
            c1 (0,0)          c2 (100,0)

    Distances are rounded Euclidean (int64); the chosen scale (100s of units)
    keeps integer rounding stable under the 2.0× DISTANCE mask.

    Demands are all 30, capacity 100, so each route can carry at most 3
    customers.
    """
    return _toy_instance(
        coords=[(50.0, 50.0), (0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)],
        demands=[0, 30, 30, 30, 30],
        capacity=100,
        n_vehicles=4,
        instance_id="square",
    )


# ---------------------------------------------------------------------------
# build_perturbed_distance_matrix


def test_build_distance_matrix_accepts_instance(square_instance: Instance) -> None:
    """Plain Instance: identical to the wrapper's pre-existing behavior."""
    from vrp_copilot_bench.solvers.pyvrp_wrapper import _build_distance_matrix

    expected = _build_distance_matrix(square_instance.coords)
    actual = build_perturbed_distance_matrix(square_instance)
    np.testing.assert_array_equal(actual, expected)


def test_build_distance_matrix_no_mask_matches_unmasked(
    square_instance: Instance,
) -> None:
    """PerturbedInstance with mask=None matches the Instance result."""
    perturbed = _to_perturbed(square_instance)  # mask defaults to None
    np.testing.assert_array_equal(
        build_perturbed_distance_matrix(perturbed),
        build_perturbed_distance_matrix(square_instance),
    )


def test_build_distance_matrix_2x_mask_doubles_objective(
    square_instance: Instance,
) -> None:
    """The single most important Phase A test: a 2.0× mask everywhere
    makes the objective on any plan exactly 2× the unmasked version.

    If a caller bypasses build_perturbed_distance_matrix, this test fails.
    """
    n = square_instance.n_customers
    full_mask = np.full((n + 1, n + 1), 2.0, dtype=np.float64)
    np.fill_diagonal(full_mask, 1.0)  # diagonal unused but tidy
    perturbed = _to_perturbed(
        square_instance,
        family="DISTANCE",
        perturbation_id="DIST_3",
        magnitude=2.0,
        mask=full_mask,
    )

    # A trivial plan: visit all four corners on a single route. Use a
    # capacity-relaxed perturbation so feasibility doesn't muddy the test.
    routes = [[1, 2, 3, 4]]

    plain_perturbed = _to_perturbed(square_instance, capacity=200)
    perturbed_masked = _to_perturbed(
        square_instance,
        family="DISTANCE",
        perturbation_id="DIST_3",
        magnitude=2.0,
        capacity=200,
        mask=full_mask,
    )

    plain = evaluate_route_plan(routes, plain_perturbed)
    masked = evaluate_route_plan(routes, perturbed_masked)

    # Objective scales by exactly 2 within rounding noise. With distances on
    # the order of 70-100 units, doubling and re-rounding stays within ±1
    # per edge, so the relative error is well under 1e-2.
    assert masked.objective == pytest.approx(2.0 * plain.objective, rel=1e-2)


def test_build_distance_matrix_partial_mask(square_instance: Instance) -> None:
    """A mask with 2.0 only on edges to/from customer 1 inflates only
    those distances. Edges between other customers are unaffected."""
    n = square_instance.n_customers
    mask = np.ones((n + 1, n + 1), dtype=np.float64)
    mask[0, 1] = mask[1, 0] = 2.0
    mask[1, 2] = mask[2, 1] = 2.0
    mask[1, 3] = mask[3, 1] = 2.0
    mask[1, 4] = mask[4, 1] = 2.0

    perturbed = _to_perturbed(square_instance, family="DISTANCE", mask=mask)
    dm_unmasked = build_perturbed_distance_matrix(square_instance)
    dm_masked = build_perturbed_distance_matrix(perturbed)

    # Customer-1 edges doubled (with one rounding step):
    for j in (0, 2, 3, 4):
        expected = round(2.0 * np.sqrt(
            (square_instance.coords[1] - square_instance.coords[j]) ** 2
        ).sum() ** 0.5 * 0)  # unused
        # Direct check: dm_masked[1, j] should equal round(2 * raw[1, j]).
        raw = float(np.linalg.norm(square_instance.coords[1] - square_instance.coords[j]))
        assert dm_masked[1, j] == int(round(2.0 * raw))
        assert dm_masked[j, 1] == int(round(2.0 * raw))

    # Edges not touching customer 1 unchanged:
    for i, j in [(2, 3), (3, 4), (2, 4), (0, 2), (0, 3), (0, 4)]:
        assert dm_masked[i, j] == dm_unmasked[i, j], f"({i},{j}) changed unexpectedly"


def test_build_distance_matrix_mask_shape_mismatch_raises(
    square_instance: Instance,
) -> None:
    bad_mask = np.ones((3, 3), dtype=np.float64)
    perturbed = _to_perturbed(square_instance, family="DISTANCE", mask=bad_mask)
    with pytest.raises(ValueError, match="distance_multiplier_mask shape"):
        build_perturbed_distance_matrix(perturbed)


# ---------------------------------------------------------------------------
# evaluate_route_plan: round-trip


def test_evaluate_round_trip_known_objective(square_instance: Instance) -> None:
    """Hand-compute a route's objective and check the evaluator agrees."""
    # Capacity raised so the all-on-one-route plan is feasible — this test
    # checks the cost arithmetic, not feasibility (covered separately).
    perturbed = _to_perturbed(square_instance, capacity=200)
    # Coords: depot(50,50), c1(0,0), c2(100,0), c3(100,100), c4(0,100).
    # Route: depot -> c1 -> c2 -> c3 -> c4 -> depot
    # Edge lengths (rounded euclidean):
    #   d(0,1) = round(sqrt(2500+2500)) = round(70.71) = 71
    #   d(1,2) = 100
    #   d(2,3) = 100
    #   d(3,4) = 100
    #   d(4,0) = round(70.71) = 71
    # Total = 71 + 100 + 100 + 100 + 71 = 442
    out = evaluate_route_plan([[1, 2, 3, 4]], perturbed)
    assert out.objective == pytest.approx(442.0)
    assert out.feasible is True
    assert out.n_overload == 0
    assert out.max_overload_fraction == 0.0


def test_evaluate_objective_equals_sum_of_route_costs(
    square_instance: Instance,
) -> None:
    """Invariant: total objective is the sum of per-route costs."""
    perturbed = _to_perturbed(square_instance)
    out = evaluate_route_plan([[1, 2], [3, 4]], perturbed)
    assert out.objective == pytest.approx(sum(out.route_costs.values()), abs=1e-6)


def test_evaluate_assignment_complete(square_instance: Instance) -> None:
    """All customers map to exactly one route under strict partition."""
    perturbed = _to_perturbed(square_instance)
    out = evaluate_route_plan([[1, 2], [3, 4]], perturbed)
    assert out.assignment == {1: 0, 2: 0, 3: 1, 4: 1}


def test_evaluate_customer_costs_match_helper(square_instance: Instance) -> None:
    """customer_costs is computed via compute_customer_costs."""
    perturbed = _to_perturbed(square_instance)
    routes = [[1, 2, 3], [4]]
    out = evaluate_route_plan(routes, perturbed)
    expected = compute_customer_costs(
        routes=routes,
        distance_matrix=build_perturbed_distance_matrix(perturbed),
        depot_id=0,
    )
    assert out.customer_costs == expected


# ---------------------------------------------------------------------------
# Feasibility


def test_evaluate_load_at_capacity_is_feasible(square_instance: Instance) -> None:
    # 3 customers × 30 = 90 ≤ 100
    perturbed = _to_perturbed(square_instance)
    out = evaluate_route_plan([[1, 2, 3], [4]], perturbed)
    assert out.feasible is True
    assert out.n_overload == 0


def test_evaluate_load_one_over_capacity_is_infeasible(square_instance: Instance) -> None:
    # Set capacity so that 3 customers (load=90) just barely exceed it.
    perturbed = _to_perturbed(square_instance, capacity=89)
    out = evaluate_route_plan([[1, 2, 3], [4]], perturbed)
    assert out.feasible is False
    assert out.n_overload == 1
    # max_overload_fraction = (90 - 89) / 89
    assert out.max_overload_fraction == pytest.approx(1.0 / 89.0)


def test_evaluate_overload_counts_multiple(square_instance: Instance) -> None:
    """3-route plan with 2 overloaded routes returns n_overload=2 and
    max_overload_fraction = max(load - capacity) / capacity."""
    # Two routes exceed capacity 50 (load=60 each), one is fine (load=30).
    perturbed = _to_perturbed(square_instance, capacity=50)
    out = evaluate_route_plan([[1, 2], [3, 4], []], perturbed)
    # routes[2] is empty so it doesn't count toward overload (no load).
    # Customer 4 needs to be placed somewhere; let's adjust.
    # Better: two routes, both overloaded.
    out = evaluate_route_plan([[1, 2], [3, 4]], perturbed)
    assert out.n_overload == 2
    # (60 - 50) / 50 = 0.2
    assert out.max_overload_fraction == pytest.approx(0.2)


def test_evaluate_vehicle_count_not_enforced(square_instance: Instance) -> None:
    """A plan with more routes than n_vehicles is feasible if capacities hold."""
    # square_instance has n_vehicles=4. Use 4 routes (one per customer) — this
    # already equals n_vehicles. To stress test, build an instance with very
    # few vehicles and many routes.
    inst = _toy_instance(
        coords=[(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0), (4.0, 0.0)],
        demands=[0, 10, 10, 10, 10],
        capacity=50,
        n_vehicles=1,  # claim 1 vehicle
    )
    perturbed = _to_perturbed(inst)
    # 4 routes, one per customer — far more than 1 vehicle.
    out = evaluate_route_plan([[1], [2], [3], [4]], perturbed)
    assert out.feasible is True


# ---------------------------------------------------------------------------
# Partition rules


def test_evaluate_strict_partition_missing_customer_raises(
    square_instance: Instance,
) -> None:
    perturbed = _to_perturbed(square_instance)
    with pytest.raises(ValueError, match="does not cover"):
        evaluate_route_plan([[1, 2, 3]], perturbed)  # missing 4


def test_evaluate_duplicate_customer_raises(square_instance: Instance) -> None:
    perturbed = _to_perturbed(square_instance)
    with pytest.raises(ValueError, match="appears in more than one"):
        evaluate_route_plan([[1, 2], [2, 3, 4]], perturbed)


def test_evaluate_depot_in_route_raises(square_instance: Instance) -> None:
    perturbed = _to_perturbed(square_instance)
    with pytest.raises(ValueError, match="depot"):
        evaluate_route_plan([[1, 0, 2], [3, 4]], perturbed)


def test_evaluate_out_of_range_customer_raises(square_instance: Instance) -> None:
    perturbed = _to_perturbed(square_instance)
    with pytest.raises(ValueError, match=r"outside \[1, 4\]"):
        evaluate_route_plan([[1, 2, 99], [3, 4]], perturbed)


# ---------------------------------------------------------------------------
# Partial coverage


def test_evaluate_partial_coverage_marks_missing_minus_one(
    square_instance: Instance,
) -> None:
    """allow_partial_coverage=True: missing customers get -1 in assignment;
    customer_costs has no entry for them."""
    perturbed = _to_perturbed(square_instance)
    routes = [[1, 2, 3]]  # missing customer 4
    out = evaluate_route_plan(
        routes, perturbed, allow_partial_coverage=True
    )
    assert out.assignment[1] == 0
    assert out.assignment[2] == 0
    assert out.assignment[3] == 0
    assert out.assignment[4] == -1
    assert 4 not in out.customer_costs


def test_evaluate_partial_coverage_custom_label(square_instance: Instance) -> None:
    perturbed = _to_perturbed(square_instance)
    out = evaluate_route_plan(
        [[1, 2, 3]],
        perturbed,
        allow_partial_coverage=True,
        unassigned_label=-99,
    )
    assert out.assignment[4] == -99


def test_evaluate_partial_coverage_all_present_no_minus_one(
    square_instance: Instance,
) -> None:
    """When the partition is complete, no -1 entries appear even with
    allow_partial_coverage=True."""
    perturbed = _to_perturbed(square_instance)
    out = evaluate_route_plan(
        [[1, 2], [3, 4]], perturbed, allow_partial_coverage=True
    )
    assert -1 not in out.assignment.values()


# ---------------------------------------------------------------------------
# Type sanity


def test_evaluated_route_plan_is_frozen() -> None:
    """EvaluatedRoutePlan is immutable; helps reason about the cache later."""
    plan = EvaluatedRoutePlan(
        objective=0.0,
        feasible=True,
        n_overload=0,
        max_overload_fraction=0.0,
        assignment={},
        route_costs={},
        customer_costs={},
    )
    with pytest.raises((AttributeError, TypeError)):
        plan.objective = 1.0  # type: ignore[misc]
