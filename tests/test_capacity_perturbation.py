"""Tests for the CAPACITY perturbation family (prereg §6.1)."""
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
from vrp_copilot_bench.perturbations.families.capacity import apply_capacity
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig


# ---------------------------------------------------------------------------
# Fixtures


def _instance_present(instance_id: str) -> bool:
    return (Path("data/instances") / f"{instance_id}.vrp").exists()


def _baseline_present(instance_id: str) -> bool:
    return (Path("data/baselines") / f"{instance_id}.json").exists()


def _toy_instance(*, capacity: int = 100, n: int = 5) -> Instance:
    """A small synthetic instance for tests that don't need real data."""
    rng = np.random.default_rng(42)
    coords = rng.uniform(0.0, 100.0, size=(n + 1, 2))
    demands = np.zeros(n + 1, dtype=np.int64)
    demands[1:] = rng.integers(10, 30, size=n)
    return Instance(
        instance_id="toy",
        n_customers=n,
        capacity=capacity,
        n_vehicles=n,
        coords=coords,
        demands=demands,
        depot_index=0,
    )


def _toy_baseline(instance: Instance, route_loads: list[list[int]]) -> Solution:
    """Build a baseline whose routes / loads / costs are caller-controlled.

    Each entry of ``route_loads`` is a list of customer indices.
    """
    routes = [list(r) for r in route_loads]
    assignment: dict[int, int] = {}
    route_costs: dict[int, float] = {}
    for ri, r in enumerate(routes):
        route_costs[ri] = float(ri + 1)  # arbitrary distinct costs
        for c in r:
            assignment[c] = ri
    return Solution(
        instance_id=instance.instance_id,
        objective=sum(route_costs.values()),
        routes=routes,
        assignment=assignment,
        route_costs=route_costs,
        customer_costs={c: 1.0 for c in assignment},
        runtime_seconds=0.0,
        pyvrp_version="test",
        config=SolveConfig(time_limit_seconds=1.0, seed=1),
    )


def _cap_spec(perturbation_id: str) -> PerturbationSpec:
    return lookup_perturbation("X-n101-k25", perturbation_id)


# ---------------------------------------------------------------------------
# Capacity arithmetic


def test_new_capacity_for_each_rho() -> None:
    """All four ρ values produce ``round(capacity * (1 - ρ))``."""
    inst = _toy_instance(capacity=200)
    expected = {
        "CAP_1": round(200 * 0.98),
        "CAP_2": round(200 * 0.95),
        "CAP_3": round(200 * 0.90),
        "CAP_4": round(200 * 0.80),
    }
    for pid, want in expected.items():
        got = apply_capacity(inst, _cap_spec(pid)).capacity
        assert got == want, f"{pid}: expected capacity {want}, got {got}"


def test_capacity_uses_round_not_floor() -> None:
    """Banker's rounding via int(round(...)) — verified on a non-integer product."""
    # 207 * 0.98 = 202.86 → round → 203
    inst = _toy_instance(capacity=207)
    perturbed = apply_capacity(inst, _cap_spec("CAP_1"))
    assert perturbed.capacity == 203


# ---------------------------------------------------------------------------
# Coords / demands / customer count untouched


def test_coords_and_demands_unchanged() -> None:
    inst = _toy_instance()
    perturbed = apply_capacity(inst, _cap_spec("CAP_4"))
    assert np.array_equal(perturbed.coords, inst.coords)
    assert np.array_equal(perturbed.demands, inst.demands)
    assert perturbed.n_customers == inst.n_customers
    assert perturbed.n_vehicles == inst.n_vehicles


def test_distance_mask_is_none() -> None:
    inst = _toy_instance()
    perturbed = apply_capacity(inst, _cap_spec("CAP_2"))
    assert perturbed.distance_multiplier_mask is None


# ---------------------------------------------------------------------------
# No mutation of input


def test_no_mutation_of_input_instance() -> None:
    inst = _toy_instance(capacity=100)
    capacity_before = inst.capacity
    coords_before = inst.coords.copy()
    demands_before = inst.demands.copy()
    apply_capacity(inst, _cap_spec("CAP_4"))
    assert inst.capacity == capacity_before
    assert np.array_equal(inst.coords, coords_before)
    assert np.array_equal(inst.demands, demands_before)


def test_returned_arrays_independent_of_input() -> None:
    """Mutating the returned arrays does not propagate back to the source."""
    inst = _toy_instance()
    perturbed = apply_capacity(inst, _cap_spec("CAP_1"))
    perturbed.coords[0] = (-999, -999)
    perturbed.demands[1] = -42
    assert inst.coords[0, 0] != -999
    assert inst.demands[1] != -42


# ---------------------------------------------------------------------------
# Determinism


def test_determinism_same_inputs_same_output() -> None:
    inst = _toy_instance()
    a = apply_capacity(inst, _cap_spec("CAP_3"))
    b = apply_capacity(inst, _cap_spec("CAP_3"))
    assert a.capacity == b.capacity
    assert np.array_equal(a.coords, b.coords)
    assert np.array_equal(a.demands, b.demands)
    assert a.affected_route_share == b.affected_route_share


# ---------------------------------------------------------------------------
# Diagnostic metadata


def test_n_affected_customers_zero() -> None:
    inst = _toy_instance()
    perturbed = apply_capacity(inst, _cap_spec("CAP_4"))
    assert perturbed.n_affected_customers == 0
    assert perturbed.affected_demand_share == 0.0


def test_affected_route_share_no_baseline_is_zero() -> None:
    inst = _toy_instance()
    perturbed = apply_capacity(inst, _cap_spec("CAP_4"))  # baseline=None default
    assert perturbed.affected_route_share == 0.0


def test_affected_route_share_with_synthetic_baseline() -> None:
    """3 routes with loads 50, 80, 95; capacity=100, ρ=0.20 → new=80.

    Routes with load > 80: only the third. Expected share = 1/3.
    """
    inst = _toy_instance(capacity=100, n=6)
    # Override demands to give clean route loads.
    inst = replace(
        inst, demands=np.array([0, 25, 25, 40, 40, 50, 45], dtype=np.int64)
    )
    # Routes: [1,2] load=50; [3,4] load=80; [5,6] load=95.
    baseline = _toy_baseline(inst, [[1, 2], [3, 4], [5, 6]])
    perturbed = apply_capacity(inst, _cap_spec("CAP_4"), baseline)
    assert perturbed.capacity == 80
    assert perturbed.affected_route_share == pytest.approx(1.0 / 3.0)


def test_affected_route_share_uses_strict_inequality() -> None:
    """A route exactly at the new capacity is *not* counted as overloaded."""
    inst = _toy_instance(capacity=100, n=2)
    inst = replace(inst, demands=np.array([0, 80, 80], dtype=np.int64))
    baseline = _toy_baseline(inst, [[1], [2]])  # both routes load=80
    # ρ=0.20 → new_capacity=80; load==80 is feasible → 0/2 overloaded.
    perturbed = apply_capacity(inst, _cap_spec("CAP_4"), baseline)
    assert perturbed.capacity == 80
    assert perturbed.affected_route_share == 0.0


# ---------------------------------------------------------------------------
# Wrong-family rejection


def test_rejects_non_capacity_spec() -> None:
    inst = _toy_instance()
    bad = lookup_perturbation("X-n101-k25", "DEM_1")
    with pytest.raises(ValueError, match="CAPACITY"):
        apply_capacity(inst, bad)


# ---------------------------------------------------------------------------
# Instance-data sanity check (gated on data presence)


@pytest.mark.skipif(
    not (_instance_present("X-n101-k25") and _baseline_present("X-n101-k25")),
    reason="X-n101-k25 instance file or cached baseline missing",
)
def test_x_n101_k25_cap_4_hand_check() -> None:
    """Hand-checked numbers for the project's reference instance.

    capacity=206; ρ=0.20 → new_capacity = round(206 * 0.80) = 165.
    All 26 baseline routes have loads ≥ 172, so every route is overloaded.
    """
    inst = load_instance("X-n101-k25")
    baseline = load_baseline_solution("X-n101-k25")
    perturbed = apply_capacity(inst, _cap_spec("CAP_4"), baseline)
    assert perturbed.capacity == 165
    assert perturbed.affected_route_share == pytest.approx(26 / 26)
    assert perturbed.n_affected_customers == 0
    assert perturbed.affected_demand_share == 0.0
    assert perturbed.perturbation_family == "CAPACITY"
    assert perturbed.perturbation_magnitude == pytest.approx(0.20)


@pytest.mark.skipif(
    not (_instance_present("X-n101-k25") and _baseline_present("X-n101-k25")),
    reason="X-n101-k25 instance file or cached baseline missing",
)
def test_x_n101_k25_cap_1_hand_check() -> None:
    """ρ=0.02 → new_capacity = round(206 * 0.98) = 202; 11/26 routes overloaded."""
    inst = load_instance("X-n101-k25")
    baseline = load_baseline_solution("X-n101-k25")
    perturbed = apply_capacity(inst, _cap_spec("CAP_1"), baseline)
    assert perturbed.capacity == 202
    assert perturbed.affected_route_share == pytest.approx(11 / 26)
