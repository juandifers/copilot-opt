"""Tests for the ``reuse_direct`` action.

Two layers:

1. Synthetic-instance tests for the contract: signature, partial-coverage
   semantics, ``-1`` placeholder, meta diagnostics, determinism, runtime
   bound, ``objective == sum(route_costs)`` invariant.
2. Real-data tests on the cached X-n101-k25 baseline + Phase A's three
   sanity perturbations (CAP_2, CAP_4, DIST_3, INS_2). These verify the
   action against the actual solver outputs the rest of the system will
   feed it.

The Phase 3 dataset showed CAP_4 (ρ=0.20) produces 100 % infeasibility on
reuse_direct; we use that as the expected qualitative behavior on the
"capacity reduction breaks the plan" path.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from vrp_copilot_bench.actions import ActionResult, reuse_direct
from vrp_copilot_bench.baselines import Solution, load_baseline_solution
from vrp_copilot_bench.instances import Instance, load_instance
from vrp_copilot_bench.perturbations import apply_perturbation, lookup_perturbation
from vrp_copilot_bench.perturbations.types import PerturbedInstance
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig


# ---------------------------------------------------------------------------
# Real-data fixtures (require the X-n101-k25 baseline cache)


_REAL_INSTANCE_ID = "X-n101-k25"


def _have_real_baseline() -> bool:
    return (
        Path("data/baselines") / f"{_REAL_INSTANCE_ID}.json"
    ).exists() and (
        Path("data/instances") / f"{_REAL_INSTANCE_ID}.vrp"
    ).exists()


requires_real_baseline = pytest.mark.skipif(
    not _have_real_baseline(),
    reason=f"requires cached baseline for {_REAL_INSTANCE_ID}",
)


@pytest.fixture(scope="module")
def real_instance() -> Instance:
    return load_instance(_REAL_INSTANCE_ID)


@pytest.fixture(scope="module")
def real_baseline() -> Solution:
    return load_baseline_solution(_REAL_INSTANCE_ID)


def _perturb(
    instance: Instance, baseline: Solution, perturbation_id: str
) -> PerturbedInstance:
    spec = lookup_perturbation(instance.instance_id, perturbation_id)
    return apply_perturbation(instance, spec, baseline)


# ---------------------------------------------------------------------------
# Synthetic-instance contract tests


@pytest.fixture
def toy_instance() -> Instance:
    rng = np.random.default_rng(7)
    n = 12
    coords = np.zeros((n + 1, 2), dtype=np.float64)
    coords[0] = (500.0, 500.0)
    coords[1:] = rng.uniform(0.0, 1000.0, size=(n, 2))
    demands = np.zeros(n + 1, dtype=np.int64)
    demands[1:] = rng.integers(10, 30, size=n)
    return Instance(
        instance_id="toy_reuse",
        n_customers=n,
        capacity=100,
        n_vehicles=n,
        coords=coords,
        demands=demands,
        depot_index=0,
    )


@pytest.fixture
def toy_baseline(toy_instance: Instance) -> Solution:
    """3 routes covering all 12 customers, demands ≤ capacity each."""
    routes = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]
    assignment = {c: ri for ri, r in enumerate(routes) for c in r}
    return Solution(
        instance_id=toy_instance.instance_id,
        objective=0.0,
        routes=routes,
        assignment=assignment,
        route_costs={ri: 0.0 for ri in range(len(routes))},
        customer_costs={c: 0.0 for c in assignment},
        runtime_seconds=0.0,
        pyvrp_version="test",
        config=SolveConfig(time_limit_seconds=1.0, seed=1),
    )


def _perturbed_from_overrides(
    inst: Instance,
    *,
    family: str,
    perturbation_id: str,
    magnitude: float,
    capacity: int | None = None,
    coords: np.ndarray | None = None,
    demands: np.ndarray | None = None,
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


def test_reuse_direct_returns_action_result(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    perturbed = _perturbed_from_overrides(
        toy_instance,
        family="CAPACITY",
        perturbation_id="CAP_1",
        magnitude=0.02,
    )
    out = reuse_direct(perturbed, toy_baseline)
    assert isinstance(out, ActionResult)
    assert out.action == "reuse_direct"


def test_reuse_direct_objective_equals_sum_of_route_costs(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    perturbed = _perturbed_from_overrides(
        toy_instance,
        family="CAPACITY",
        perturbation_id="CAP_1",
        magnitude=0.02,
    )
    out = reuse_direct(perturbed, toy_baseline)
    assert out.objective == pytest.approx(
        sum(out.route_costs.values()), abs=1e-6
    )


def test_reuse_direct_preserves_baseline_routes(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    """No re-routing — output routes match baseline.routes verbatim."""
    perturbed = _perturbed_from_overrides(
        toy_instance,
        family="DEMAND",
        perturbation_id="DEM_1",
        magnitude=0.10,
    )
    out = reuse_direct(perturbed, toy_baseline)
    assert out.routes == toy_baseline.routes


def test_reuse_direct_capacity_reduction_can_break_feasibility(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    """Cut capacity hard so the baseline plan must be infeasible."""
    perturbed = _perturbed_from_overrides(
        toy_instance,
        family="CAPACITY",
        perturbation_id="CAP_4",
        magnitude=0.20,
        capacity=10,  # tiny capacity → every route overloaded
    )
    out = reuse_direct(perturbed, toy_baseline)
    assert out.feasible is False
    assert out.n_overload > 0
    assert out.max_overload_fraction > 0.0


def test_reuse_direct_determinism(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    perturbed = _perturbed_from_overrides(
        toy_instance,
        family="DISTANCE",
        perturbation_id="DIST_3",
        magnitude=2.0,
    )
    a = reuse_direct(perturbed, toy_baseline)
    b = reuse_direct(perturbed, toy_baseline)
    assert a.objective == b.objective
    assert a.assignment == b.assignment
    assert a.route_costs == b.route_costs
    assert a.customer_costs == b.customer_costs
    assert a.feasible == b.feasible
    assert a.n_overload == b.n_overload
    # runtime_seconds may differ between calls.


def test_reuse_direct_does_not_mutate_inputs(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    perturbed = _perturbed_from_overrides(
        toy_instance,
        family="CAPACITY",
        perturbation_id="CAP_1",
        magnitude=0.02,
    )
    routes_before = [list(r) for r in toy_baseline.routes]
    coords_before = perturbed.coords.copy()
    demands_before = perturbed.demands.copy()
    _ = reuse_direct(perturbed, toy_baseline)
    assert toy_baseline.routes == routes_before
    np.testing.assert_array_equal(perturbed.coords, coords_before)
    np.testing.assert_array_equal(perturbed.demands, demands_before)


def test_reuse_direct_meta_empty_for_non_insertion(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    """Non-INSERTION perturbations: meta has no partial_coverage flag."""
    for family, pid, magnitude in [
        ("CAPACITY", "CAP_1", 0.02),
        ("DEMAND", "DEM_1", 0.10),
        ("DISTANCE", "DIST_3", 2.0),
    ]:
        perturbed = _perturbed_from_overrides(
            toy_instance,
            family=family,
            perturbation_id=pid,
            magnitude=magnitude,
        )
        out = reuse_direct(perturbed, toy_baseline)
        assert "partial_coverage" not in out.meta
        assert "n_unassigned_customers" not in out.meta


# --- INSERTION semantics ---------------------------------------------------


def _insertion_perturbed(
    inst: Instance, *, n_new: int = 3
) -> PerturbedInstance:
    """Build a synthetic INSERTION-style PerturbedInstance with n_new
    extra customers appended to the trailing indices."""
    n_old = inst.n_customers
    n_total = n_old + n_new
    new_coords = np.zeros((n_total + 1, 2), dtype=np.float64)
    new_coords[: n_old + 1] = inst.coords
    new_coords[n_old + 1 :] = np.array(
        [[100.0 + i, 100.0 + i] for i in range(n_new)], dtype=np.float64
    )
    new_demands = np.zeros(n_total + 1, dtype=np.int64)
    new_demands[: n_old + 1] = inst.demands
    new_demands[n_old + 1 :] = 5
    return PerturbedInstance(
        instance_id=inst.instance_id,
        perturbation_id="INS_2",
        perturbation_family="INSERTION",
        perturbation_magnitude=0.70,
        n_customers=n_total,
        coords=new_coords,
        demands=new_demands,
        capacity=inst.capacity,
        n_vehicles=inst.n_vehicles,
        distance_multiplier_mask=None,
        n_affected_customers=n_new,
        affected_demand_share=0.0,
        affected_route_share=1.0,
    )


def test_reuse_direct_insertion_unassigns_new_customers(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    n_new = 3
    perturbed = _insertion_perturbed(toy_instance, n_new=n_new)
    out = reuse_direct(perturbed, toy_baseline)
    # New customer IDs are toy_instance.n_customers+1 ... +n_new
    new_ids = list(range(toy_instance.n_customers + 1, toy_instance.n_customers + 1 + n_new))
    for c in new_ids:
        assert out.assignment[c] == -1, (
            f"customer {c} should be unassigned; got {out.assignment[c]}"
        )
    # Original customers still mapped to real route indices
    for c in range(1, toy_instance.n_customers + 1):
        assert out.assignment[c] >= 0


def test_reuse_direct_insertion_meta(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    n_new = 3
    perturbed = _insertion_perturbed(toy_instance, n_new=n_new)
    out = reuse_direct(perturbed, toy_baseline)
    assert out.meta.get("partial_coverage") is True
    assert out.meta.get("n_unassigned_customers") == n_new


def test_reuse_direct_insertion_customer_costs_exclude_new(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    n_new = 3
    perturbed = _insertion_perturbed(toy_instance, n_new=n_new)
    out = reuse_direct(perturbed, toy_baseline)
    for c in range(toy_instance.n_customers + 1, toy_instance.n_customers + 1 + n_new):
        assert c not in out.customer_costs


def test_reuse_direct_runtime_under_100ms_on_small_instance(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    perturbed = _perturbed_from_overrides(
        toy_instance,
        family="CAPACITY",
        perturbation_id="CAP_1",
        magnitude=0.02,
    )
    t0 = time.perf_counter()
    out = reuse_direct(perturbed, toy_baseline)
    elapsed = time.perf_counter() - t0
    # Generous bound — the toy is 12 customers; real instances scale linearly.
    assert elapsed < 0.1
    # The action's reported runtime must be non-negative and ≤ outer elapsed.
    assert 0.0 <= out.runtime_seconds <= elapsed + 1e-6


# ---------------------------------------------------------------------------
# Real-data tests (require the X-n101-k25 baseline cache)


@requires_real_baseline
def test_reuse_direct_real_cap_4_infeasible(
    real_instance: Instance, real_baseline: Solution
) -> None:
    """On X-n101-k25 + CAP_4 (ρ=0.20), reuse_direct produces an infeasible
    plan with at least one overloaded route. Phase 3 data showed 100 %
    infeasibility on this magnitude; one overload is sufficient evidence."""
    perturbed = _perturb(real_instance, real_baseline, "CAP_4")
    out = reuse_direct(perturbed, real_baseline)
    assert out.feasible is False
    assert out.n_overload >= 1
    assert out.max_overload_fraction > 0.0


@requires_real_baseline
def test_reuse_direct_real_dist_3_feasible_changed_objective(
    real_instance: Instance, real_baseline: Solution
) -> None:
    """DIST_3 inflates a regional subset of edges. The baseline plan stays
    capacity-feasible (capacity unchanged) but the objective shifts because
    some routes pass through inflated edges."""
    perturbed = _perturb(real_instance, real_baseline, "DIST_3")
    out = reuse_direct(perturbed, real_baseline)
    assert out.feasible is True
    # Objective different from baseline (some edges inflated).
    assert out.objective != pytest.approx(real_baseline.objective, rel=1e-6)
    # The mask only inflates, so reuse objective is ≥ baseline.
    assert out.objective >= real_baseline.objective


@requires_real_baseline
def test_reuse_direct_real_ins_2_partial_coverage(
    real_instance: Instance, real_baseline: Solution
) -> None:
    """INS_2 inserts γ=0.70 worth of new demand. New customer IDs receive
    -1 in assignment; meta records the partial-coverage flags."""
    perturbed = _perturb(real_instance, real_baseline, "INS_2")
    n_new = perturbed.n_customers - real_instance.n_customers
    assert n_new > 0
    out = reuse_direct(perturbed, real_baseline)
    # n_new customers unassigned:
    n_unassigned = sum(1 for v in out.assignment.values() if v == -1)
    assert n_unassigned == n_new
    assert out.meta["partial_coverage"] is True
    assert out.meta["n_unassigned_customers"] == n_new
    # Original customers still have non-negative route ids:
    for c in range(1, real_instance.n_customers + 1):
        assert out.assignment[c] >= 0


@requires_real_baseline
def test_reuse_direct_real_runtime_under_100ms(
    real_instance: Instance, real_baseline: Solution
) -> None:
    """Even on the largest Stage A instance the action should be well
    under 100 ms; X-n101-k25 is on the small end of Stage A."""
    perturbed = _perturb(real_instance, real_baseline, "CAP_2")
    t0 = time.perf_counter()
    _ = reuse_direct(perturbed, real_baseline)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.1


@requires_real_baseline
def test_reuse_direct_real_objective_equals_sum_of_route_costs(
    real_instance: Instance, real_baseline: Solution
) -> None:
    """Invariant on real data."""
    perturbed = _perturb(real_instance, real_baseline, "DIST_4")
    out = reuse_direct(perturbed, real_baseline)
    assert out.objective == pytest.approx(
        sum(out.route_costs.values()), abs=1e-6
    )
