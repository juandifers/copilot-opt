"""Tests for the DISTANCE perturbation family (prereg §6.2)."""
from __future__ import annotations

import math
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
from vrp_copilot_bench.perturbations.families._common import compute_k_nn_spread
from vrp_copilot_bench.perturbations.families.distance import (
    _build_distance_mask,
    _select_closest_quartile,
    _select_density_partition,
    _select_farthest_quartile,
    apply_distance,
)
# Local alias preserves the existing test names that referenced the moved helper.
_compute_k_nn_spread = compute_k_nn_spread
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig


def _instance_present(instance_id: str) -> bool:
    return (Path("data/instances") / f"{instance_id}.vrp").exists()


def _baseline_present(instance_id: str) -> bool:
    return (Path("data/baselines") / f"{instance_id}.json").exists()


def _instance_from_coords(
    coords: np.ndarray, *, demands: np.ndarray | None = None
) -> Instance:
    """Build a synthetic instance from a coords array (depot at row 0)."""
    n = coords.shape[0] - 1
    if demands is None:
        demands = np.concatenate(
            [np.array([0]), np.full(n, 10, dtype=np.int64)]
        ).astype(np.int64)
    return Instance(
        instance_id="toy",
        n_customers=n,
        capacity=200,
        n_vehicles=n,
        coords=coords.astype(np.float64),
        demands=demands,
        depot_index=0,
    )


def _toy_baseline(
    instance: Instance,
    routes: list[list[int]],
    costs: list[float] | None = None,
) -> Solution:
    if costs is None:
        costs = [float(i + 1) for i in range(len(routes))]
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


def _dist(perturbation_id: str) -> PerturbationSpec:
    return lookup_perturbation("X-n101-k25", perturbation_id)


# ---------------------------------------------------------------------------
# Region-size invariants


def test_dist_3_size_for_n_100() -> None:
    """ceil(100 / 4) = 25."""
    coords = np.zeros((101, 2), dtype=np.float64)
    coords[1:] = np.random.default_rng(0).uniform(0, 100, size=(100, 2))
    region = _select_closest_quartile(coords)
    assert len(region) == 25


def test_farthest_quartile_size_rounds_up_for_n_109() -> None:
    """ceil(109 / 4) = 28 (verifies the round-up convention on a non-clean n)."""
    coords = np.zeros((110, 2), dtype=np.float64)
    coords[1:] = np.random.default_rng(1).uniform(0, 100, size=(109, 2))
    region = _select_farthest_quartile(coords)
    assert len(region) == 28


def test_dist_1_dist_2_partition_farthest_25() -> None:
    """DIST_1 ∪ DIST_2 = farthest 25%, and DIST_1 ∩ DIST_2 = ∅."""
    coords = np.zeros((101, 2), dtype=np.float64)
    coords[1:] = np.random.default_rng(2).uniform(0, 100, size=(100, 2))
    farthest = set(_select_farthest_quartile(coords))
    low = set(_select_density_partition(coords, want_low_density=True))
    high = set(_select_density_partition(coords, want_low_density=False))
    assert low.isdisjoint(high)
    assert low | high == farthest


# ---------------------------------------------------------------------------
# Tie-breaking on equidistant boundary customers


def test_farthest_quartile_tiebreak_lowest_index_wins() -> None:
    """Customers 5 and 6 equidistant at the boundary; only customer 5 fits."""
    # n=12, ceil(12/4)=3. We want the 3 farthest. Distances:
    #   1..4: very close;   7..9: small;   12: small;
    #   10: 100 (farthest), 11: 50 (2nd), 5: 30 (tied 3rd), 6: 30 (tied 3rd).
    n = 12
    dist_targets = {
        1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0,
        5: 30.0, 6: 30.0,
        7: 7.0, 8: 8.0, 9: 9.0,
        10: 100.0, 11: 50.0, 12: 12.0,
    }
    coords = np.zeros((n + 1, 2), dtype=np.float64)
    for c, r in dist_targets.items():
        coords[c] = (r, 0.0)
    region = _select_farthest_quartile(coords)
    assert region == [5, 10, 11], (
        f"expected farthest-3 = [5, 10, 11] (5 wins tiebreak over 6); got {region}"
    )
    assert 6 not in region


def test_closest_quartile_tiebreak_lowest_index_wins() -> None:
    """Customers 5 and 6 tied at the boundary of the closest-25%; only 5 fits."""
    n = 12
    dist_targets = {
        1: 100.0, 2: 50.0, 3: 80.0, 4: 90.0,    # all far
        5: 5.0,  6: 5.0,                         # tied at boundary
        7: 1.0,  8: 2.0,                         # clearly closest
        9: 60.0, 10: 70.0, 11: 40.0, 12: 30.0,  # far
    }
    coords = np.zeros((n + 1, 2), dtype=np.float64)
    for c, r in dist_targets.items():
        coords[c] = (r, 0.0)
    region = _select_closest_quartile(coords)
    # ceil(12/4)=3; closest are 7 (1), 8 (2), then tied 5/6 at 5 → 5 wins.
    assert region == [5, 7, 8]
    assert 6 not in region


# ---------------------------------------------------------------------------
# k-NN spread metric


def test_k_nn_spread_uses_customer_neighbors_only() -> None:
    """Depot is not in the neighbor pool — verified by placing the depot
    very far from all customers and checking spreads are unaffected."""
    rng = np.random.default_rng(3)
    customer_coords = rng.uniform(0, 100, size=(20, 2))
    coords_a = np.concatenate([np.array([[50.0, 50.0]]), customer_coords])
    coords_b = np.concatenate([np.array([[1e6, 1e6]]), customer_coords])
    spread_a = _compute_k_nn_spread(coords_a, k=5)
    spread_b = _compute_k_nn_spread(coords_b, k=5)
    np.testing.assert_allclose(spread_a, spread_b)


def test_k_nn_spread_known_geometry() -> None:
    """Two clusters, k=2: the spread of a tight-cluster customer equals
    the mean of the two nearest within-cluster distances."""
    # Cluster A: 3 customers around (0, 0).
    # Cluster B: 3 customers around (100, 0).
    coords = np.array([
        [50.0, 50.0],   # depot (irrelevant)
        [0.0, 0.0],     # c1
        [1.0, 0.0],     # c2
        [2.0, 0.0],     # c3
        [100.0, 0.0],   # c4
        [101.0, 0.0],   # c5
        [102.0, 0.0],   # c6
    ])
    spread = _compute_k_nn_spread(coords, k=2)
    # c1 nearest customers: c2 (d=1), c3 (d=2). Mean = 1.5.
    assert spread[0] == pytest.approx(1.5)
    # c2 nearest: c1 (1), c3 (1). Mean = 1.0.
    assert spread[1] == pytest.approx(1.0)
    # Symmetric for cluster B.
    assert spread[3] == pytest.approx(1.5)
    assert spread[4] == pytest.approx(1.0)


def test_k_nn_spread_rejects_too_small_n() -> None:
    coords = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])  # only 2 customers
    with pytest.raises(ValueError):
        _compute_k_nn_spread(coords, k=5)


# ---------------------------------------------------------------------------
# Mask construction


def test_mask_shape_dtype_and_default() -> None:
    coords = np.zeros((11, 2))
    coords[1:] = np.random.default_rng(4).uniform(0, 100, size=(10, 2))
    inst = _instance_from_coords(coords)
    perturbed = apply_distance(inst, _dist("DIST_3"))
    mask = perturbed.distance_multiplier_mask
    assert mask is not None
    assert mask.shape == (11, 11)
    assert mask.dtype == np.float64


def test_mask_only_affects_region_edges() -> None:
    """Synthetic 6-customer instance; affected region = {1, 2}."""
    region = [1, 2]
    mask = _build_distance_mask(n_customers=6, region=region)
    # Depot ↔ region edges
    assert mask[0, 1] == 2.0
    assert mask[1, 0] == 2.0
    assert mask[0, 2] == 2.0
    assert mask[2, 0] == 2.0
    # Region ↔ region edges
    assert mask[1, 2] == 2.0
    assert mask[2, 1] == 2.0
    # Cross edges (one in, one out): unscaled
    assert mask[1, 3] == 1.0
    assert mask[3, 1] == 1.0
    # Out-of-region pairs: unscaled
    assert mask[3, 4] == 1.0
    assert mask[4, 3] == 1.0
    # Depot ↔ non-region: unscaled
    assert mask[0, 3] == 1.0
    assert mask[3, 0] == 1.0
    # Diagonal: 1.0
    for i in range(7):
        assert mask[i, i] == 1.0


def test_mask_is_symmetric() -> None:
    coords = np.zeros((26, 2))
    coords[1:] = np.random.default_rng(5).uniform(0, 100, size=(25, 2))
    inst = _instance_from_coords(coords)
    perturbed = apply_distance(inst, _dist("DIST_1"))
    mask = perturbed.distance_multiplier_mask
    assert mask is not None
    np.testing.assert_array_equal(mask, mask.T)


def test_mask_empty_region_is_all_ones() -> None:
    mask = _build_distance_mask(n_customers=4, region=[])
    assert np.all(mask == 1.0)


# ---------------------------------------------------------------------------
# DIST_4: highest-cost baseline route


def test_dist_4_uses_highest_cost_route() -> None:
    coords = np.zeros((7, 2))
    coords[1:] = np.random.default_rng(6).uniform(0, 100, size=(6, 2))
    inst = _instance_from_coords(coords)
    baseline = _toy_baseline(
        inst,
        [[1, 2], [3, 4], [5, 6]],
        costs=[10.0, 50.0, 30.0],
    )  # route 1 wins
    perturbed = apply_distance(inst, _dist("DIST_4"), baseline)
    mask = perturbed.distance_multiplier_mask
    assert mask is not None
    # Region = {3, 4}. mask[0,3]=mask[0,4]=mask[3,4]=mask[4,3]=2.0; others=1.0.
    assert mask[0, 3] == 2.0
    assert mask[0, 4] == 2.0
    assert mask[3, 4] == 2.0
    assert mask[4, 3] == 2.0
    # Routes 0 and 2 untouched.
    assert mask[0, 1] == 1.0
    assert mask[1, 2] == 1.0
    assert mask[5, 6] == 1.0


def test_dist_4_tiebreak_lowest_route_index() -> None:
    coords = np.zeros((7, 2))
    coords[1:] = np.random.default_rng(7).uniform(0, 100, size=(6, 2))
    inst = _instance_from_coords(coords)
    baseline = _toy_baseline(
        inst,
        [[1, 2], [3, 4], [5, 6]],
        costs=[50.0, 50.0, 30.0],  # routes 0 and 1 tied at max
    )
    perturbed = apply_distance(inst, _dist("DIST_4"), baseline)
    mask = perturbed.distance_multiplier_mask
    # Route 0 wins → region = {1, 2}.
    assert mask is not None
    assert mask[0, 1] == 2.0
    assert mask[0, 2] == 2.0
    assert mask[1, 2] == 2.0
    # Route 1 untouched.
    assert mask[3, 4] == 1.0


def test_dist_4_raises_without_baseline() -> None:
    coords = np.zeros((11, 2))
    coords[1:] = np.random.default_rng(8).uniform(0, 100, size=(10, 2))
    inst = _instance_from_coords(coords)
    with pytest.raises(ValueError, match="baseline"):
        apply_distance(inst, _dist("DIST_4"), None)


def test_dist_1_dist_2_dist_3_succeed_without_baseline() -> None:
    coords = np.zeros((11, 2))
    coords[1:] = np.random.default_rng(9).uniform(0, 100, size=(10, 2))
    inst = _instance_from_coords(coords)
    for pid in ("DIST_1", "DIST_2", "DIST_3"):
        out = apply_distance(inst, _dist(pid), None)
        assert out.affected_route_share == 0.0


# ---------------------------------------------------------------------------
# Coords / demands / capacity unchanged


def test_coords_and_demands_unchanged() -> None:
    coords = np.zeros((11, 2))
    coords[1:] = np.random.default_rng(10).uniform(0, 100, size=(10, 2))
    inst = _instance_from_coords(coords)
    perturbed = apply_distance(inst, _dist("DIST_3"))
    assert np.array_equal(perturbed.coords, inst.coords)
    assert np.array_equal(perturbed.demands, inst.demands)
    assert perturbed.capacity == inst.capacity
    assert perturbed.n_customers == inst.n_customers


def test_no_mutation_of_input() -> None:
    coords = np.zeros((11, 2))
    coords[1:] = np.random.default_rng(11).uniform(0, 100, size=(10, 2))
    inst = _instance_from_coords(coords)
    coords_before = inst.coords.copy()
    apply_distance(inst, _dist("DIST_3"))
    assert np.array_equal(inst.coords, coords_before)


# ---------------------------------------------------------------------------
# Determinism


def test_determinism() -> None:
    coords = np.zeros((11, 2))
    coords[1:] = np.random.default_rng(12).uniform(0, 100, size=(10, 2))
    inst = _instance_from_coords(coords)
    a = apply_distance(inst, _dist("DIST_1"))
    b = apply_distance(inst, _dist("DIST_1"))
    np.testing.assert_array_equal(a.distance_multiplier_mask, b.distance_multiplier_mask)
    assert a.n_affected_customers == b.n_affected_customers


# ---------------------------------------------------------------------------
# Diagnostics


def test_diagnostic_metadata_consistency() -> None:
    """n_affected_customers = number of distinct mask entries set to 2.0
    in the depot row (excluding the diagonal)."""
    coords = np.zeros((11, 2))
    coords[1:] = np.random.default_rng(13).uniform(0, 100, size=(10, 2))
    inst = _instance_from_coords(coords)
    out = apply_distance(inst, _dist("DIST_3"))
    n_from_mask = int((out.distance_multiplier_mask[0, 1:] == 2.0).sum())
    assert out.n_affected_customers == n_from_mask


def test_affected_route_share_with_baseline() -> None:
    """3 routes; region = customers in route 1 only → share = 1/3."""
    coords = np.zeros((7, 2))
    coords[1:] = np.random.default_rng(14).uniform(0, 100, size=(6, 2))
    inst = _instance_from_coords(coords)
    baseline = _toy_baseline(
        inst,
        [[1, 2], [3, 4], [5, 6]],
        costs=[10.0, 50.0, 30.0],
    )
    out = apply_distance(inst, _dist("DIST_4"), baseline)
    assert out.affected_route_share == pytest.approx(1.0 / 3.0)


# ---------------------------------------------------------------------------
# Wrong-family rejection


def test_rejects_non_distance_spec() -> None:
    coords = np.zeros((11, 2))
    coords[1:] = np.random.default_rng(15).uniform(0, 100, size=(10, 2))
    inst = _instance_from_coords(coords)
    bad = lookup_perturbation("X-n101-k25", "DEM_1")
    with pytest.raises(ValueError, match="DISTANCE"):
        apply_distance(inst, bad)


# ---------------------------------------------------------------------------
# Real instance hand-check


@pytest.mark.skipif(
    not (_instance_present("X-n101-k25") and _baseline_present("X-n101-k25")),
    reason="X-n101-k25 instance file or cached baseline missing",
)
def test_x_n101_k25_dist_3_hand_check() -> None:
    """The 25 closest customers to the X-n101-k25 depot, hand-computed."""
    inst = load_instance("X-n101-k25")
    out = apply_distance(inst, _dist("DIST_3"))
    expected_closest = [
        5, 8, 11, 12, 15, 17, 19, 21, 23, 24, 30, 31, 32, 34, 35,
        46, 50, 58, 61, 75, 79, 80, 85, 95, 100,
    ]
    assert out.n_affected_customers == 25
    affected = sorted(
        c for c in range(1, inst.n_customers + 1)
        if out.distance_multiplier_mask[0, c] == 2.0
    )
    assert affected == expected_closest


@pytest.mark.skipif(
    not (_instance_present("X-n101-k25") and _baseline_present("X-n101-k25")),
    reason="X-n101-k25 instance file or cached baseline missing",
)
def test_x_n101_k25_dist_1_dist_2_partition() -> None:
    """For X-n101-k25: DIST_1 has 13 customers, DIST_2 has 12, sum = 25."""
    inst = load_instance("X-n101-k25")
    out_1 = apply_distance(inst, _dist("DIST_1"))
    out_2 = apply_distance(inst, _dist("DIST_2"))
    set_1 = {c for c in range(1, 101) if out_1.distance_multiplier_mask[0, c] == 2.0}
    set_2 = {c for c in range(1, 101) if out_2.distance_multiplier_mask[0, c] == 2.0}
    assert len(set_1) == 13
    assert len(set_2) == 12
    assert set_1.isdisjoint(set_2)
    assert len(set_1 | set_2) == 25


@pytest.mark.skipif(
    not (_instance_present("X-n101-k25") and _baseline_present("X-n101-k25")),
    reason="X-n101-k25 instance file or cached baseline missing",
)
def test_x_n101_k25_dist_4_hand_check() -> None:
    """DIST_4 region = customers of route 0 (cost=1951) on X-n101-k25."""
    inst = load_instance("X-n101-k25")
    baseline = load_baseline_solution("X-n101-k25")
    out = apply_distance(inst, _dist("DIST_4"), baseline)
    expected = sorted([2, 7, 29, 36, 43, 45, 57, 72])
    affected = sorted(
        c for c in range(1, 101) if out.distance_multiplier_mask[0, c] == 2.0
    )
    assert affected == expected
    assert out.n_affected_customers == 8
    # Route 0 is the only baseline route fully in the region; other routes
    # may also overlap if they share a customer (they don't, since
    # baseline routes partition customers). So affected_route_share = 1/26.
    assert out.affected_route_share == pytest.approx(1 / 26)
