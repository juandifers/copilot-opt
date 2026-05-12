"""Tests for the Clarke-Wright parallel-savings heuristic.

Two layers:

1. The ``construct`` primitive — algorithmic correctness on hand-checked
   instances (a fully traced 4-customer merge sequence, tie-breaking,
   boundary-only merging, capacity respect, the ActionFailure path).
2. The ``clarke_wright_action`` wrapper — produces a valid
   :class:`ActionResult` with the cost-invariant
   ``objective == sum(route_costs)``.

The DISTANCE-mask integration test is the load-bearing test: it proves
CW consumed the perturbed matrix during construction, not just the
unperturbed coords.

# Hand-traced 4-customer merge sequence (chain on x-axis)

    depot=0, c1=10, c2=20, c3=30, c4=40   (all on x-axis at integer
                                           positions)
    demands all 10, capacity 30

Distances (rounded euclidean):
    d(0,1)=10  d(0,2)=20  d(0,3)=30  d(0,4)=40
    d(1,2)=10  d(1,3)=20  d(1,4)=30
    d(2,3)=10  d(2,4)=20
    d(3,4)=10

Savings s_ij = d(0,i) + d(0,j) - d(i,j):
    s_12 = 10+20-10 = 20
    s_13 = 10+30-20 = 20
    s_14 = 10+40-30 = 20
    s_23 = 20+30-10 = 40
    s_24 = 20+40-20 = 40
    s_34 = 30+40-10 = 60

Sorted descending (ties by (i,j) ascending):
    (60, (3,4)), (40, (2,3)), (40, (2,4)),
    (20, (1,2)), (20, (1,3)), (20, (1,4))

Initial routes: [[1], [2], [3], [4]], each load 10.

Process (60, 3,4): different routes; load 10+10=20≤30; both at boundary;
    canonicalize (singletons, no reversal); merge → [3,4] (load 20).
    Routes: [[1], [2], [3,4], None]

Process (40, 2,3): 2 in [2], 3 in [3,4]; combined load 10+20=30 ≤ 30;
    both at boundary; canonicalize (i=2 at end of [2]; j=3 at start of
    [3,4]); merge → [2,3,4] (load 30).
    Routes: [[1], [2,3,4], None, None]

Process (40, 2,4): 2 in [2,3,4], 4 in [2,3,4]; same route → SKIP.

Process (20, 1,2): 1 in [1] (boundary); 2 in [2,3,4] at start (boundary);
    combined load 10+30=40 > 30 → SKIP (capacity).

Process (20, 1,3): 1 in [1] (boundary); 3 in [2,3,4] interior (index 1)
    → SKIP (boundary).

Process (20, 1,4): 1 in [1] (boundary); 4 in [2,3,4] at end (boundary);
    combined load 40 > 30 → SKIP (capacity).

Final: [[1], [2,3,4]].

This trace exercises every CW skip path: same-route, capacity, interior.
"""
from __future__ import annotations

import numpy as np
import pytest

from vrp_copilot_bench.actions import ActionFailure, ActionResult
from vrp_copilot_bench.actions.evaluate import build_perturbed_distance_matrix
from vrp_copilot_bench.actions.heuristic_actions import clarke_wright_action
from vrp_copilot_bench.baselines import Solution
from vrp_copilot_bench.instances import Instance
from vrp_copilot_bench.perturbations.types import PerturbedInstance
from vrp_copilot_bench.solvers.heuristics.clarke_wright import construct
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig


# ---------------------------------------------------------------------------
# Fixture helpers (same shape as test_nearest_neighbor.py)


def _instance(
    *,
    coords: list[tuple[float, float]],
    demands: list[int],
    capacity: int,
    instance_id: str = "toy_cw",
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
# Hand-traced 4-customer merge sequence


@pytest.fixture
def chain_instance() -> Instance:
    """4 customers + depot on the x-axis, see module docstring for trace."""
    return _instance(
        coords=[(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0), (40.0, 0.0)],
        demands=[0, 10, 10, 10, 10],
        capacity=30,
    )


def test_cw_hand_traced_chain(chain_instance: Instance) -> None:
    """Module-docstring trace: expected output [[1], [2,3,4]]."""
    perturbed = _to_perturbed(chain_instance)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    assert routes == [[1], [2, 3, 4]]


def test_cw_chain_loads_within_capacity(chain_instance: Instance) -> None:
    perturbed = _to_perturbed(chain_instance)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    for r in routes:
        load = sum(int(perturbed.demands[c]) for c in r)
        assert load <= perturbed.capacity


# ---------------------------------------------------------------------------
# Tie-breaking on equal savings


def test_cw_tie_breaking_lower_pair_first() -> None:
    """Ties on equal savings are broken by (i, j) ascending.

    Symmetric square of 4 customers around a depot. By symmetry, all
    diagonal-pair savings (i.e. opposite corners) are equal.

    Coords:
        depot(50, 50)
        c1(0,0), c2(100,0), c3(100,100), c4(0,100)

    Distances:
        d(0,c) = 71 for all c (rounded sqrt(5000))
        d(1,2) = d(2,3) = d(3,4) = d(1,4) = 100  (sides)
        d(1,3) = d(2,4) = 141                    (diagonals)

    Savings:
        s_12 = s_23 = s_34 = s_14 = 71+71-100 = 42  (sides)
        s_13 = s_24 = 71+71-141 = 1                  (diagonals)

    Sorted descending: ties on the four side-savings, broken by (i,j)
    ascending: (1,2), (1,4), (2,3), (3,4).

    With capacity = 30 and demand = 15 each, only one merge fits per
    route (15 + 15 = 30, but a 3-customer route would be 45 > 30).

    Expected merges: (1,2) first → [1,2]; (1,4): 1 in [1,2] interior?
    no, 1 is at start of [1,2] (boundary). 4 singleton. But combined
    load 15+15+15 = 45 > 30 → skip. (2,3): 2 interior. skip. (3,4): both
    boundary; load 30; merge → [3,4].

    Final: [[1,2], [3,4]].
    """
    inst = _instance(
        coords=[(50.0, 50.0), (0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)],
        demands=[0, 15, 15, 15, 15],
        capacity=30,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    assert routes == [[1, 2], [3, 4]], (
        f"expected tie-break to merge (1,2) first then (3,4); got {routes}"
    )


# ---------------------------------------------------------------------------
# Boundary-only merging


def test_cw_skips_interior_customer_merge() -> None:
    """A merge candidate whose endpoint is interior to its route is skipped,
    even at the highest savings.

    Build an instance where (after one prior merge) the next-best
    candidate has an interior endpoint.

    Coords on x-axis: depot(0,0), c1(10,0), c2(20,0), c3(30,0), c4(40,0).
    Demands all 10, capacity 30 (so 3-customer routes are at capacity).

    From the chain trace: routes after early merges → [[1], [2,3,4]].
    Then (1,3) attempts to merge 1 (boundary) with 3 (interior of
    [2,3,4]). Even with capacity room (20+10=30) it must SKIP because
    of the boundary check; instead the lower-savings (1,4) is also
    blocked by capacity, so 1 stays singleton.

    The test simply confirms 1 is in its own route in the final plan.
    """
    inst = _instance(
        coords=[(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0), (40.0, 0.0)],
        demands=[0, 10, 10, 10, 10],
        capacity=30,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    # Customer 1 ends up alone — interior 3 blocked the (1,3) merge and
    # capacity blocked (1,2) and (1,4). [[1], [2,3,4]] is the final.
    assert [1] in routes


# ---------------------------------------------------------------------------
# Capacity, coverage, empty-routes invariant


def test_cw_capacity_respected_random_instance() -> None:
    rng = np.random.default_rng(123)
    n = 12
    coords = np.zeros((n + 1, 2), dtype=np.float64)
    coords[0] = (50.0, 50.0)
    coords[1:] = rng.uniform(0, 100, size=(n, 2))
    demands_arr = np.zeros(n + 1, dtype=np.int64)
    demands_arr[1:] = rng.integers(5, 25, size=n)
    inst = _instance(
        coords=[tuple(c) for c in coords],
        demands=demands_arr.tolist(),
        capacity=50,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    for r in routes:
        load = sum(int(perturbed.demands[c]) for c in r)
        assert load <= perturbed.capacity


def test_cw_coverage_complete() -> None:
    rng = np.random.default_rng(7)
    n = 10
    coords = np.zeros((n + 1, 2), dtype=np.float64)
    coords[0] = (50.0, 50.0)
    coords[1:] = rng.uniform(0, 100, size=(n, 2))
    demands_arr = np.zeros(n + 1, dtype=np.int64)
    demands_arr[1:] = 10
    inst = _instance(
        coords=[tuple(c) for c in coords],
        demands=demands_arr.tolist(),
        capacity=50,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    flat = [c for r in routes for c in r]
    assert sorted(flat) == list(range(1, n + 1))


def test_cw_never_produces_empty_routes() -> None:
    """No route in the output is empty (project invariant)."""
    rng = np.random.default_rng(99)
    n = 8
    coords = np.zeros((n + 1, 2), dtype=np.float64)
    coords[0] = (50.0, 50.0)
    coords[1:] = rng.uniform(0, 100, size=(n, 2))
    demands_arr = np.zeros(n + 1, dtype=np.int64)
    demands_arr[1:] = rng.integers(5, 25, size=n)
    inst = _instance(
        coords=[tuple(c) for c in coords],
        demands=demands_arr.tolist(),
        capacity=40,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    assert all(len(r) > 0 for r in routes)


def test_cw_oversized_customer_becomes_singleton_route() -> None:
    """Customer with demand > capacity survives as a singleton route.

    The heuristic no longer raises — it returns an infeasible plan so the
    consolidator gets a full (instance, perturbation) group rather than a
    missing base action.  The evaluator marks the plan feasible=False with
    n_overload > 0.  CW's singleton seed already handles this naturally:
    the oversized singleton just fails every capacity-feasibility merge
    check and remains as-is.
    """
    inst = _instance(
        coords=[(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)],
        demands=[0, 50, 30],
        capacity=40,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    routes = construct(perturbed, dm)
    all_customers = sorted(c for route in routes for c in route)
    assert all_customers == [1, 2]
    assert [1] in routes  # oversized singleton survives


# ---------------------------------------------------------------------------
# Determinism


def test_cw_determinism() -> None:
    rng = np.random.default_rng(42)
    n = 15
    coords = np.zeros((n + 1, 2), dtype=np.float64)
    coords[0] = (50.0, 50.0)
    coords[1:] = rng.uniform(0, 100, size=(n, 2))
    demands_arr = np.zeros(n + 1, dtype=np.int64)
    demands_arr[1:] = rng.integers(5, 20, size=n)
    inst = _instance(
        coords=[tuple(c) for c in coords],
        demands=demands_arr.tolist(),
        capacity=50,
    )
    perturbed = _to_perturbed(inst)
    dm = build_perturbed_distance_matrix(perturbed)
    a = construct(perturbed, dm)
    b = construct(perturbed, dm)
    assert a == b


# ---------------------------------------------------------------------------
# DISTANCE-mask integration test (load-bearing)


def test_cw_uses_perturbed_distance_matrix() -> None:
    """A 2× mask on customer 5's edges must change CW's output.

    Geometry:
        depot(0,0)
        c1(10,0), c2(20,0), c3(30,0), c4(40,0)   on x-axis
        c5(0,10)                                 on y-axis (orthogonal)

    Distances (rounded):
        d(0,5) = 10
        d(5,1)=14, d(5,2)=22, d(5,3)=32, d(5,4)=41
        d(0,1..4) = 10, 20, 30, 40
        d(i,j) for i,j in {1..4}: see chain trace.

    Unmasked savings (descending, with ties):
        s_34=60, s_23=40, s_24=40,
        s_12=20, s_13=20, s_14=20,
        s_45=9, s_25=8, s_35=8, s_15=6.

    Masked savings (2× on every C5 edge): C5's contribution drops a lot.
        Recompute s_5j for each j with d(0,5)→20 and d(5,j)→2*d(5,j):
            s_15 = 20+10-28 = 2
            s_25 = 20+20-44 = -4
            s_35 = 20+30-64 = -14
            s_45 = 20+40-82 = -22.
        The non-C5 savings are unchanged.

    With capacity=50 and demand 10 each, the unmasked plan has C5 merged
    after the chain forms [1,2,3,4]: best C5-pair is (4,5) at savings 9,
    fitting the route to capacity 50. Final: [[1,2,3,4,5]].

    The masked plan instead merges C5 last via (1,5) (savings 2) — by
    that point [1,2,3,4] has 1 at the *start*, so canonicalizing reverses
    the route → [4,3,2,1,5].

    Two assertions:
      a) routes_unmasked != routes_masked (the mask was used)
      b) the route containing C5 has a different sequence in each plan
         (sequence-level signal, not just set membership)
    """
    inst = _instance(
        coords=[
            (0.0, 0.0),
            (10.0, 0.0),
            (20.0, 0.0),
            (30.0, 0.0),
            (40.0, 0.0),
            (0.0, 10.0),
        ],
        demands=[0, 10, 10, 10, 10, 10],
        capacity=50,
    )
    p_unmasked = _to_perturbed(inst)
    dm_unmasked = build_perturbed_distance_matrix(p_unmasked)
    routes_unmasked = construct(p_unmasked, dm_unmasked)

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

    assert routes_unmasked != routes_masked, (
        f"CW must consume the masked matrix; routes identical: {routes_unmasked}"
    )
    # Sequence-level signal: the route containing customer 5 differs.
    route_unm = next(r for r in routes_unmasked if 5 in r)
    route_mas = next(r for r in routes_masked if 5 in r)
    assert route_unm != route_mas, (
        f"customer 5's route sequence unchanged under mask: {route_unm} == {route_mas}"
    )


# ---------------------------------------------------------------------------
# Action wrapper


def test_cw_action_returns_action_result() -> None:
    inst = _instance(
        coords=[(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)],
        demands=[0, 10, 10, 10],
        capacity=30,
    )
    perturbed = _to_perturbed(inst)
    out = clarke_wright_action(perturbed, _baseline_for(inst))
    assert isinstance(out, ActionResult)
    assert out.action == "clarke_wright"


def test_cw_action_objective_equals_sum_of_route_costs() -> None:
    inst = _instance(
        coords=[(0.0, 0.0)] + [(i * 7.0, i * 3.0) for i in range(1, 9)],
        demands=[0] + [8] * 8,
        capacity=30,
    )
    perturbed = _to_perturbed(inst)
    out = clarke_wright_action(perturbed, _baseline_for(inst))
    assert out.objective == pytest.approx(
        sum(out.route_costs.values()), abs=1e-6
    )


def test_cw_action_assignment_covers_all() -> None:
    inst = _instance(
        coords=[(0.0, 0.0)] + [(i * 7.0, i * 3.0) for i in range(1, 9)],
        demands=[0] + [8] * 8,
        capacity=30,
    )
    perturbed = _to_perturbed(inst)
    out = clarke_wright_action(perturbed, _baseline_for(inst))
    assert set(out.assignment) == set(range(1, 9))
    assert all(v >= 0 for v in out.assignment.values())
