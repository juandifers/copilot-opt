"""Tests for the DEMAND perturbation family (prereg §6.3)."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from vrp_copilot_bench.baselines import Solution, load_baseline_solution
from vrp_copilot_bench.instances import Instance, load_instance
from vrp_copilot_bench.perturbations import (
    PerturbationSpec,
    PerturbedInstance,
    lookup_perturbation,
)
from vrp_copilot_bench.perturbations.families.demand import apply_demand
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig


def _instance_present(instance_id: str) -> bool:
    return (Path("data/instances") / f"{instance_id}.vrp").exists()


def _baseline_present(instance_id: str) -> bool:
    return (Path("data/baselines") / f"{instance_id}.json").exists()


def _toy_instance(*, demands: list[int]) -> Instance:
    """Synthetic instance with caller-controlled demand vector.

    ``demands`` lists customer demands (depot demand = 0 prepended).
    """
    n = len(demands)
    rng = np.random.default_rng(7)
    coords = rng.uniform(0.0, 100.0, size=(n + 1, 2))
    demand_arr = np.zeros(n + 1, dtype=np.int64)
    demand_arr[1:] = np.array(demands, dtype=np.int64)
    return Instance(
        instance_id="toy",
        n_customers=n,
        capacity=200,
        n_vehicles=n,
        coords=coords,
        demands=demand_arr,
        depot_index=0,
    )


def _toy_baseline(
    instance: Instance,
    routes: list[list[int]],
    costs: list[float] | None = None,
) -> Solution:
    if costs is None:
        costs = [float(i + 1) for i in range(len(routes))]
    assert len(costs) == len(routes)
    assignment: dict[int, int] = {}
    route_costs: dict[int, float] = {}
    for ri, r in enumerate(routes):
        route_costs[ri] = costs[ri]
        for c in r:
            assignment[c] = ri
    return Solution(
        instance_id=instance.instance_id,
        objective=sum(route_costs.values()),
        routes=[list(r) for r in routes],
        assignment=assignment,
        route_costs=route_costs,
        customer_costs={c: 1.0 for c in assignment},
        runtime_seconds=0.0,
        pyvrp_version="test",
        config=SolveConfig(time_limit_seconds=1.0, seed=1),
    )


def _dem(perturbation_id: str) -> PerturbationSpec:
    return lookup_perturbation("X-n101-k25", perturbation_id)


# ---------------------------------------------------------------------------
# Subset selection by id


def test_dem_1_selects_smallest_cluster() -> None:
    """Routes of sizes 5, 2, 3 → smallest is route_index 1."""
    inst = _toy_instance(demands=[10] * 10)
    baseline = _toy_baseline(
        inst,
        [[1, 2, 3, 4, 5], [6, 7], [8, 9, 10]],
    )
    perturbed = apply_demand(inst, _dem("DEM_1"), baseline)
    # Subset = customers in route 1 = [6, 7]; their demands inflated by 1.10.
    assert perturbed.n_affected_customers == 2
    assert perturbed.demands[6] == int(round(10 * 1.10))
    assert perturbed.demands[7] == int(round(10 * 1.10))


def test_dem_2_uses_smallest_cluster_with_higher_delta() -> None:
    inst = _toy_instance(demands=[20, 20, 20, 20])
    baseline = _toy_baseline(inst, [[1, 2, 3], [4]])  # smallest = route 1
    perturbed = apply_demand(inst, _dem("DEM_2"), baseline)
    # δ=0.50 → 20 * 1.5 = 30
    assert perturbed.demands[4] == 30
    # Untouched customers
    for c in (1, 2, 3):
        assert perturbed.demands[c] == 20


def test_dem_3_selects_median_cost_route() -> None:
    """5 routes with distinct costs → sorted ascending, median = sorted[5//2] = sorted[2].

    Costs in order: [10, 30, 20, 50, 40]. Sorted (with index tiebreak):
    [(10,0),(20,2),(30,1),(40,4),(50,3)]. sorted[2] = (30,1) → route_index 1.
    """
    inst = _toy_instance(demands=[10] * 10)
    baseline = _toy_baseline(
        inst,
        [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]],
        costs=[10.0, 30.0, 20.0, 50.0, 40.0],
    )
    perturbed = apply_demand(inst, _dem("DEM_3"), baseline)
    # δ=0.50 → 10 * 1.5 = 15. Route 1 customers = [3, 4].
    assert perturbed.demands[3] == 15
    assert perturbed.demands[4] == 15
    assert perturbed.demands[1] == 10
    assert perturbed.demands[5] == 10


def test_dem_4_selects_highest_cost_route() -> None:
    inst = _toy_instance(demands=[10] * 6)
    baseline = _toy_baseline(
        inst,
        [[1, 2], [3, 4], [5, 6]],
        costs=[10.0, 50.0, 30.0],
    )
    perturbed = apply_demand(inst, _dem("DEM_4"), baseline)
    # Highest cost = route 1, customers [3, 4]. δ=1.00 → 10 * 2.0 = 20.
    assert perturbed.demands[3] == 20
    assert perturbed.demands[4] == 20


# ---------------------------------------------------------------------------
# Tie-breaking


def test_dem_4_tiebreak_lowest_route_index() -> None:
    """Two equal-cost routes: lower index wins."""
    inst = _toy_instance(demands=[10] * 6)
    baseline = _toy_baseline(
        inst,
        [[1, 2], [3, 4], [5, 6]],
        costs=[50.0, 50.0, 30.0],  # routes 0 and 1 both at max
    )
    perturbed = apply_demand(inst, _dem("DEM_4"), baseline)
    # Route 0 wins; customers [1, 2] inflated.
    assert perturbed.demands[1] == 20
    assert perturbed.demands[2] == 20
    assert perturbed.demands[3] == 10
    assert perturbed.demands[4] == 10


def test_dem_1_tiebreak_lowest_route_index() -> None:
    """Equal-size smallest clusters: lower index wins."""
    inst = _toy_instance(demands=[10] * 6)
    baseline = _toy_baseline(
        inst,
        [[1, 2], [3, 4], [5, 6]],  # all size 2
    )
    perturbed = apply_demand(inst, _dem("DEM_1"), baseline)
    assert perturbed.demands[1] == int(round(10 * 1.10))
    assert perturbed.demands[2] == int(round(10 * 1.10))
    # Other routes untouched.
    assert perturbed.demands[3] == 10


# ---------------------------------------------------------------------------
# Inflation arithmetic


def test_per_customer_inflation_uniform_within_subset() -> None:
    """Each customer in the subset has its individual demand multiplied by (1+δ)."""
    inst = _toy_instance(demands=[10, 30, 50])
    baseline = _toy_baseline(inst, [[1, 2, 3]])  # only route, contains all
    perturbed = apply_demand(inst, _dem("DEM_2"), baseline)
    # δ=0.50; 10→15, 30→45, 50→75
    assert perturbed.demands[1] == 15
    assert perturbed.demands[2] == 45
    assert perturbed.demands[3] == 75


def test_customers_outside_subset_unchanged() -> None:
    inst = _toy_instance(demands=[10, 20, 30, 40])
    baseline = _toy_baseline(inst, [[1, 2], [3, 4]])
    perturbed = apply_demand(inst, _dem("DEM_4"), baseline)
    # Highest cost = route 1 (cost 2.0 > 1.0); customers [3, 4] inflated, [1, 2] not.
    assert perturbed.demands[1] == 10
    assert perturbed.demands[2] == 20
    assert perturbed.demands[3] == 60   # 30 * 2.0
    assert perturbed.demands[4] == 80   # 40 * 2.0


# ---------------------------------------------------------------------------
# Diagnostic metadata


def test_n_affected_customers_equals_subset_size() -> None:
    inst = _toy_instance(demands=[10] * 5)
    baseline = _toy_baseline(inst, [[1, 2], [3, 4, 5]])
    perturbed = apply_demand(inst, _dem("DEM_4"), baseline)
    # Route 1 (cost=2.0, size=3) wins; n_affected = 3
    assert perturbed.n_affected_customers == 3


def test_affected_demand_share() -> None:
    inst = _toy_instance(demands=[10, 20, 30, 40])
    # subset = route 1 = [3, 4]; subset_demand = 70; total = 100.
    baseline = _toy_baseline(inst, [[1, 2], [3, 4]])
    perturbed = apply_demand(inst, _dem("DEM_4"), baseline)
    assert perturbed.affected_demand_share == pytest.approx(70 / 100)


def test_affected_route_share_is_one_over_n_routes() -> None:
    inst = _toy_instance(demands=[10] * 6)
    baseline = _toy_baseline(inst, [[1, 2], [3, 4], [5, 6]])
    perturbed = apply_demand(inst, _dem("DEM_4"), baseline)
    assert perturbed.affected_route_share == pytest.approx(1.0 / 3.0)


# ---------------------------------------------------------------------------
# Errors


def test_raises_when_baseline_is_none() -> None:
    inst = _toy_instance(demands=[10, 20])
    with pytest.raises(ValueError, match="baseline"):
        apply_demand(inst, _dem("DEM_1"), None)


def test_rejects_non_demand_spec() -> None:
    inst = _toy_instance(demands=[10, 20])
    baseline = _toy_baseline(inst, [[1, 2]])
    bad = lookup_perturbation("X-n101-k25", "CAP_1")
    with pytest.raises(ValueError, match="DEMAND"):
        apply_demand(inst, bad, baseline)


# ---------------------------------------------------------------------------
# Determinism / no mutation


def test_determinism() -> None:
    inst = _toy_instance(demands=[10, 20, 30, 40])
    baseline = _toy_baseline(inst, [[1, 2], [3, 4]])
    a = apply_demand(inst, _dem("DEM_4"), baseline)
    b = apply_demand(inst, _dem("DEM_4"), baseline)
    assert np.array_equal(a.demands, b.demands)
    assert a.n_affected_customers == b.n_affected_customers


def test_no_mutation_of_input() -> None:
    inst = _toy_instance(demands=[10, 20, 30, 40])
    baseline = _toy_baseline(inst, [[1, 2], [3, 4]])
    demands_before = inst.demands.copy()
    apply_demand(inst, _dem("DEM_4"), baseline)
    assert np.array_equal(inst.demands, demands_before)


def test_preserves_capacity_and_coords() -> None:
    inst = _toy_instance(demands=[10, 20, 30])
    baseline = _toy_baseline(inst, [[1, 2, 3]])
    perturbed = apply_demand(inst, _dem("DEM_1"), baseline)
    assert perturbed.capacity == inst.capacity
    assert np.array_equal(perturbed.coords, inst.coords)
    assert perturbed.distance_multiplier_mask is None


# ---------------------------------------------------------------------------
# Real instance hand-check


@pytest.mark.skipif(
    not (_instance_present("X-n101-k25") and _baseline_present("X-n101-k25")),
    reason="X-n101-k25 instance file or cached baseline missing",
)
def test_x_n101_k25_dem_4_hand_check() -> None:
    """Highest-cost baseline route on X-n101-k25 is route 0 (cost=1951).

    Customer set = [7, 2, 45, 43, 29, 36, 72, 57], route demand = 206,
    total customer demand = 5147. δ=1.00 doubles each member's demand.
    """
    inst = load_instance("X-n101-k25")
    baseline = load_baseline_solution("X-n101-k25")
    perturbed = apply_demand(inst, _dem("DEM_4"), baseline)
    affected = baseline.routes[0]
    assert sorted(affected) == sorted([7, 2, 45, 43, 29, 36, 72, 57])
    for c in affected:
        assert perturbed.demands[c] == 2 * int(inst.demands[c])
    assert perturbed.n_affected_customers == 8
    assert perturbed.affected_demand_share == pytest.approx(206 / 5147)
    assert perturbed.affected_route_share == pytest.approx(1 / 26)


@pytest.mark.skipif(
    not (_instance_present("X-n101-k25") and _baseline_present("X-n101-k25")),
    reason="X-n101-k25 instance file or cached baseline missing",
)
def test_x_n101_k25_dem_1_hand_check() -> None:
    """Smallest baseline route on X-n101-k25: route 4, customers [8, 17]."""
    inst = load_instance("X-n101-k25")
    baseline = load_baseline_solution("X-n101-k25")
    perturbed = apply_demand(inst, _dem("DEM_1"), baseline)
    assert perturbed.n_affected_customers == 2
    # δ=0.10; old demands = 98 and 74; round(98*1.10)=108, round(74*1.10)=81
    assert perturbed.demands[8] == int(round(98 * 1.10))
    assert perturbed.demands[17] == int(round(74 * 1.10))


@pytest.mark.skipif(
    not (_instance_present("X-n101-k25") and _baseline_present("X-n101-k25")),
    reason="X-n101-k25 instance file or cached baseline missing",
)
def test_x_n101_k25_dem_3_hand_check() -> None:
    """Median-cost route on X-n101-k25 is route 21 (cost=987, customers [82,60,59])."""
    inst = load_instance("X-n101-k25")
    baseline = load_baseline_solution("X-n101-k25")
    perturbed = apply_demand(inst, _dem("DEM_3"), baseline)
    assert perturbed.n_affected_customers == 3
    for c in [82, 60, 59]:
        assert perturbed.demands[c] == int(round(int(inst.demands[c]) * 1.50))
