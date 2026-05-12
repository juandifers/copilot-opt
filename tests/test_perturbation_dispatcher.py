"""Tests for the perturbation dispatcher.

The dispatcher (:func:`vrp_copilot_bench.perturbations.apply_perturbation`)
routes a :class:`PerturbationSpec` to the right family-specific
implementation. This test file checks the routing contract end-to-end
plus the all-16 happy path on a synthetic instance.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from vrp_copilot_bench.baselines import Solution
from vrp_copilot_bench.instances import Instance
from vrp_copilot_bench.perturbations import (
    PERTURBATION_IDS,
    PerturbationSpec,
    PerturbedInstance,
    apply_perturbation,
    enumerate_perturbations,
    lookup_perturbation,
)
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig


# ---------------------------------------------------------------------------
# Fixtures


@pytest.fixture
def toy_instance() -> Instance:
    rng = np.random.default_rng(123)
    n = 30
    coords = np.zeros((n + 1, 2), dtype=np.float64)
    coords[0] = (500.0, 500.0)
    coords[1:] = rng.uniform(0.0, 1000.0, size=(n, 2))
    demands = np.zeros(n + 1, dtype=np.int64)
    demands[1:] = rng.integers(10, 30, size=n)
    return Instance(
        instance_id="toy_disp",
        n_customers=n,
        capacity=200,
        n_vehicles=n,
        coords=coords,
        demands=demands,
        depot_index=0,
    )


@pytest.fixture
def toy_baseline(toy_instance: Instance) -> Solution:
    """Round-robin partition into 5 routes."""
    routes: list[list[int]] = [[] for _ in range(5)]
    for c in range(1, toy_instance.n_customers + 1):
        routes[(c - 1) % 5].append(c)
    assignment: dict[int, int] = {}
    route_costs: dict[int, float] = {}
    for ri, r in enumerate(routes):
        route_costs[ri] = 100.0 * (ri + 1)  # distinct
        for c in r:
            assignment[c] = ri
    return Solution(
        instance_id=toy_instance.instance_id,
        objective=sum(route_costs.values()),
        routes=routes,
        assignment=assignment,
        route_costs=route_costs,
        customer_costs={c: 1.0 for c in assignment},
        runtime_seconds=0.0,
        pyvrp_version="test",
        config=SolveConfig(time_limit_seconds=1.0, seed=1),
    )


# ---------------------------------------------------------------------------
# All 16 perturbations succeed and produce valid output


def test_all_16_perturbations_succeed(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    seen_pids: list[str] = []
    for spec in enumerate_perturbations(toy_instance.instance_id):
        out = apply_perturbation(toy_instance, spec, toy_baseline)
        assert isinstance(out, PerturbedInstance)
        assert out.perturbation_id == spec.perturbation_id
        assert out.perturbation_family == spec.family
        assert out.perturbation_magnitude == pytest.approx(spec.magnitude)
        seen_pids.append(spec.perturbation_id)
    assert sorted(seen_pids) == sorted(PERTURBATION_IDS)


def test_per_family_invariants(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    """Each family's signature: which fields change, which don't."""
    for spec in enumerate_perturbations(toy_instance.instance_id):
        out = apply_perturbation(toy_instance, spec, toy_baseline)
        if spec.family == "CAPACITY":
            assert out.capacity != toy_instance.capacity
            assert out.n_customers == toy_instance.n_customers
            assert out.distance_multiplier_mask is None
            np.testing.assert_array_equal(out.coords, toy_instance.coords)
            np.testing.assert_array_equal(out.demands, toy_instance.demands)
        elif spec.family == "DISTANCE":
            assert out.capacity == toy_instance.capacity
            assert out.n_customers == toy_instance.n_customers
            assert out.distance_multiplier_mask is not None
            np.testing.assert_array_equal(out.coords, toy_instance.coords)
            np.testing.assert_array_equal(out.demands, toy_instance.demands)
        elif spec.family == "DEMAND":
            assert out.capacity == toy_instance.capacity
            assert out.n_customers == toy_instance.n_customers
            assert out.distance_multiplier_mask is None
            np.testing.assert_array_equal(out.coords, toy_instance.coords)
            assert not np.array_equal(out.demands, toy_instance.demands)
        elif spec.family == "INSERTION":
            assert out.capacity == toy_instance.capacity
            assert out.n_customers > toy_instance.n_customers
            assert out.distance_multiplier_mask is None


# ---------------------------------------------------------------------------
# Family routing


def test_routes_to_capacity(toy_instance: Instance) -> None:
    spec = lookup_perturbation(toy_instance.instance_id, "CAP_2")
    out = apply_perturbation(toy_instance, spec)
    assert out.perturbation_family == "CAPACITY"
    assert out.distance_multiplier_mask is None


def test_routes_to_distance(toy_instance: Instance) -> None:
    spec = lookup_perturbation(toy_instance.instance_id, "DIST_3")
    out = apply_perturbation(toy_instance, spec)
    assert out.perturbation_family == "DISTANCE"
    assert out.distance_multiplier_mask is not None


def test_routes_to_demand(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    spec = lookup_perturbation(toy_instance.instance_id, "DEM_4")
    out = apply_perturbation(toy_instance, spec, toy_baseline)
    assert out.perturbation_family == "DEMAND"


def test_routes_to_insertion(
    toy_instance: Instance, toy_baseline: Solution
) -> None:
    spec = lookup_perturbation(toy_instance.instance_id, "INS_2")
    out = apply_perturbation(toy_instance, spec, toy_baseline)
    assert out.perturbation_family == "INSERTION"
    assert out.n_customers == toy_instance.n_customers + 3


# ---------------------------------------------------------------------------
# Baseline=None contract by family


def test_capacity_succeeds_without_baseline(toy_instance: Instance) -> None:
    out = apply_perturbation(
        toy_instance, lookup_perturbation(toy_instance.instance_id, "CAP_3")
    )
    assert out.affected_route_share == 0.0


def test_distance_1_2_3_succeed_without_baseline(toy_instance: Instance) -> None:
    for pid in ("DIST_1", "DIST_2", "DIST_3"):
        out = apply_perturbation(
            toy_instance, lookup_perturbation(toy_instance.instance_id, pid)
        )
        assert out.perturbation_family == "DISTANCE"


def test_distance_4_requires_baseline(toy_instance: Instance) -> None:
    spec = lookup_perturbation(toy_instance.instance_id, "DIST_4")
    with pytest.raises(ValueError, match="baseline"):
        apply_perturbation(toy_instance, spec)


def test_demand_requires_baseline(toy_instance: Instance) -> None:
    for pid in ("DEM_1", "DEM_2", "DEM_3", "DEM_4"):
        spec = lookup_perturbation(toy_instance.instance_id, pid)
        with pytest.raises(ValueError, match="baseline"):
            apply_perturbation(toy_instance, spec)


def test_insertion_requires_baseline(toy_instance: Instance) -> None:
    for pid in ("INS_1", "INS_2", "INS_3", "INS_4"):
        spec = lookup_perturbation(toy_instance.instance_id, pid)
        with pytest.raises(ValueError, match="baseline"):
            apply_perturbation(toy_instance, spec)


# ---------------------------------------------------------------------------
# Unknown family rejection


@dataclass(frozen=True)
class _FakeSpec:
    perturbation_id: str
    family: str
    magnitude: float

    @property
    def short_family(self) -> str:
        return self.perturbation_id.split("_", 1)[0]


def test_unknown_family_raises(toy_instance: Instance) -> None:
    bad = _FakeSpec(perturbation_id="X_1", family="WIBBLE", magnitude=1.0)
    with pytest.raises(ValueError, match="unknown perturbation family"):
        apply_perturbation(toy_instance, bad)


# ---------------------------------------------------------------------------
# Backwards-compatibility with the runner's 2-arg call


def test_two_arg_call_still_works_for_capacity(toy_instance: Instance) -> None:
    """The runner currently calls apply_perturbation(instance, spec) — no
    baseline. CAPACITY (and DIST_1/2/3) should still work."""
    spec = lookup_perturbation(toy_instance.instance_id, "CAP_4")
    out = apply_perturbation(toy_instance, spec)  # 2-arg
    assert out.perturbation_family == "CAPACITY"
