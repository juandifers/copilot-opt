"""Tests for the INSERTION perturbation family (prereg §6.4, v0.4 seeding)."""
from __future__ import annotations

import math
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
from vrp_copilot_bench.perturbations.families.insertion import (
    _convex_hull_ccw,
    _point_in_convex_polygon,
    _seed_rng,
    apply_insertion,
)
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig


def _instance_present(instance_id: str) -> bool:
    return (Path("data/instances") / f"{instance_id}.vrp").exists()


def _baseline_present(instance_id: str) -> bool:
    return (Path("data/baselines") / f"{instance_id}.json").exists()


def _toy_instance(*, n: int = 30, seed: int = 0, capacity: int = 200) -> Instance:
    rng = np.random.default_rng(seed)
    coords = np.zeros((n + 1, 2), dtype=np.float64)
    coords[0] = (500.0, 500.0)  # depot in the middle
    coords[1:] = rng.uniform(0.0, 1000.0, size=(n, 2))
    demands = np.zeros(n + 1, dtype=np.int64)
    demands[1:] = rng.integers(10, 30, size=n)
    return Instance(
        instance_id="toy_ins",
        n_customers=n,
        capacity=capacity,
        n_vehicles=n,
        coords=coords,
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


def _ins(perturbation_id: str) -> PerturbationSpec:
    return lookup_perturbation("X-n101-k25", perturbation_id)


def _toy_partition(instance: Instance, k: int) -> list[list[int]]:
    """Partition the instance's customers into ``k`` round-robin routes."""
    routes: list[list[int]] = [[] for _ in range(k)]
    for c in range(1, instance.n_customers + 1):
        routes[(c - 1) % k].append(c)
    return routes


# ---------------------------------------------------------------------------
# Seeding contract (v0.4 amendment)


def test_seed_rng_per_instance_perturbation_pair() -> None:
    """sha256(f'{instance}_{pid}') → 64 hex; first 16 → int → mod 2^32."""
    rng_a = _seed_rng("X-n101-k25", "INS_1")
    rng_b = _seed_rng("X-n101-k25", "INS_1")
    rng_c = _seed_rng("X-n101-k25", "INS_2")
    rng_d = _seed_rng("X-n200-k36", "INS_1")
    # Same input → same draws.
    np.testing.assert_array_equal(rng_a.uniform(size=10), rng_b.uniform(size=10))
    # Different perturbation_id → different draws (the v0.4 fix).
    assert not np.allclose(
        _seed_rng("X-n101-k25", "INS_1").uniform(size=5),
        _seed_rng("X-n101-k25", "INS_2").uniform(size=5),
    )
    # Different instance → different draws.
    assert not np.allclose(
        _seed_rng("X-n101-k25", "INS_1").uniform(size=5),
        _seed_rng("X-n200-k36", "INS_1").uniform(size=5),
    )


# ---------------------------------------------------------------------------
# Customer-count expansion


@pytest.mark.parametrize(
    "perturbation_id, n_new", [("INS_1", 1), ("INS_2", 3), ("INS_3", 5), ("INS_4", 10)]
)
def test_n_new_customers(perturbation_id: str, n_new: int) -> None:
    inst = _toy_instance()
    baseline = _toy_baseline(inst, _toy_partition(inst, k=3))
    out = apply_insertion(inst, _ins(perturbation_id), baseline)
    assert out.n_customers == inst.n_customers + n_new
    assert out.coords.shape == (inst.n_customers + n_new + 1, 2)
    assert out.demands.shape == (inst.n_customers + n_new + 1,)
    assert out.n_affected_customers == n_new


def test_original_customers_preserved() -> None:
    """The first n+1 rows of coords/demands match the source instance."""
    inst = _toy_instance()
    baseline = _toy_baseline(inst, _toy_partition(inst, k=3))
    out = apply_insertion(inst, _ins("INS_4"), baseline)
    np.testing.assert_array_equal(
        out.coords[: inst.n_customers + 1], inst.coords
    )
    np.testing.assert_array_equal(
        out.demands[: inst.n_customers + 1], inst.demands
    )


def test_capacity_and_n_vehicles_unchanged() -> None:
    inst = _toy_instance(capacity=250)
    baseline = _toy_baseline(inst, _toy_partition(inst, k=3))
    out = apply_insertion(inst, _ins("INS_2"), baseline)
    assert out.capacity == 250
    assert out.n_vehicles == inst.n_vehicles
    assert out.distance_multiplier_mask is None


# ---------------------------------------------------------------------------
# Demand


@pytest.mark.parametrize(
    "perturbation_id, gamma, n_new",
    [
        ("INS_1", 0.30, 1),
        ("INS_2", 0.70, 3),
        ("INS_3", 1.20, 5),
        ("INS_4", 2.00, 10),
    ],
)
def test_inserted_demand_within_rounding(
    perturbation_id: str, gamma: float, n_new: int
) -> None:
    """Total inserted demand ≈ round(γ × capacity) within n_new // 2 + 1."""
    inst = _toy_instance(capacity=206)
    baseline = _toy_baseline(inst, _toy_partition(inst, k=3))
    out = apply_insertion(inst, _ins(perturbation_id), baseline)
    target = round(gamma * 206)
    inserted = out.demands[-n_new:].sum()
    assert abs(int(inserted) - target) <= n_new // 2 + 1


def test_per_customer_demand_uniform() -> None:
    inst = _toy_instance(capacity=206)
    baseline = _toy_baseline(inst, _toy_partition(inst, k=3))
    out = apply_insertion(inst, _ins("INS_4"), baseline)
    inserted = out.demands[-10:]
    assert len(set(int(d) for d in inserted)) == 1


def test_per_customer_demand_at_least_one() -> None:
    """Even tiny γ × small capacity rounds to a positive demand."""
    inst = _toy_instance(capacity=2)  # γ=0.30 × 2 = 0.6 → round → 1
    baseline = _toy_baseline(inst, _toy_partition(inst, k=3))
    out = apply_insertion(inst, _ins("INS_1"), baseline)
    assert int(out.demands[-1]) >= 1


# ---------------------------------------------------------------------------
# Determinism


@pytest.mark.parametrize("perturbation_id", ["INS_1", "INS_2", "INS_3", "INS_4"])
def test_determinism(perturbation_id: str) -> None:
    inst = _toy_instance()
    baseline = _toy_baseline(inst, _toy_partition(inst, k=3))
    a = apply_insertion(inst, _ins(perturbation_id), baseline)
    b = apply_insertion(inst, _ins(perturbation_id), baseline)
    np.testing.assert_array_equal(a.coords, b.coords)
    np.testing.assert_array_equal(a.demands, b.demands)


def test_distinct_placements_across_ins_variants() -> None:
    """The v0.4 seeding fix: INS_1, INS_2, INS_3, INS_4 must produce
    coordinate sets that don't trivially coincide (the v0.3 bug)."""
    inst = _toy_instance()
    baseline = _toy_baseline(inst, _toy_partition(inst, k=3))
    out_1 = apply_insertion(inst, _ins("INS_1"), baseline)
    out_2 = apply_insertion(inst, _ins("INS_2"), baseline)
    # INS_1 has 1 new customer; INS_2 has 3. Under v0.3 seeding INS_1's
    # only sample would equal INS_2's first sample. Under v0.4 they
    # draw distinct streams, so the integer-rounded coords also differ.
    assert not np.array_equal(
        out_1.coords[-1], out_2.coords[inst.n_customers + 1]
    )


# ---------------------------------------------------------------------------
# Coordinate rounding


def test_coords_are_integer_valued() -> None:
    """All inserted coords round to integer floats per Uchoa-X convention."""
    inst = _toy_instance()
    baseline = _toy_baseline(inst, _toy_partition(inst, k=3))
    for pid in ("INS_1", "INS_2", "INS_3", "INS_4"):
        out = apply_insertion(inst, _ins(pid), baseline)
        new = out.coords[inst.n_customers + 1 :]
        np.testing.assert_array_equal(new, np.round(new))


# ---------------------------------------------------------------------------
# Spatial-pattern sanity checks


def test_ins_1_within_three_std_dev_of_depot() -> None:
    """Uniform within 1 std-dev of depot — a single sample stays within
    1*std = customer_std radius. Allow 1 unit slack for integer rounding."""
    inst = _toy_instance(seed=1)
    baseline = _toy_baseline(inst, _toy_partition(inst, k=3))
    out = apply_insertion(inst, _ins("INS_1"), baseline)
    new_xy = out.coords[-1]
    depot = inst.coords[0]
    dist = float(np.sqrt(((new_xy - depot) ** 2).sum()))
    radial = np.sqrt(((inst.coords[1:] - depot) ** 2).sum(axis=1))
    radius = float(np.sqrt((radial ** 2).mean()))
    assert dist <= radius + math.sqrt(2)


def test_ins_3_inside_customer_bounding_box() -> None:
    """INS_3 samples inside the convex hull, which is itself inside the
    customer bounding box. After integer rounding, give 1 unit slack."""
    inst = _toy_instance(seed=2, n=50)
    baseline = _toy_baseline(inst, _toy_partition(inst, k=4))
    out = apply_insertion(inst, _ins("INS_3"), baseline)
    new_xy = out.coords[inst.n_customers + 1 :]
    customer_xy = inst.coords[1:]
    min_xy = customer_xy.min(axis=0) - 1.0
    max_xy = customer_xy.max(axis=0) + 1.0
    assert (new_xy >= min_xy).all() and (new_xy <= max_xy).all()


# ---------------------------------------------------------------------------
# Convex hull primitives


def test_convex_hull_square_returns_4_corners() -> None:
    """A 4-corner square plus interior points → hull is the 4 corners."""
    pts = np.array(
        [
            [0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0],
            [5.0, 5.0], [3.0, 7.0], [7.0, 3.0],
        ]
    )
    hull = _convex_hull_ccw(pts)
    assert hull.shape == (4, 2)
    # CCW order starting from lowest-x lowest-y corner: (0,0), (10,0), (10,10), (0,10)
    assert np.allclose(hull[0], [0.0, 0.0])
    # Verify CCW orientation by signed area > 0.
    area = 0.0
    n = len(hull)
    for i in range(n):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    assert area > 0


def test_point_in_convex_polygon_inside_outside() -> None:
    square = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
    assert _point_in_convex_polygon(np.array([5.0, 5.0]), square)
    assert _point_in_convex_polygon(np.array([0.0, 0.0]), square)  # vertex
    assert _point_in_convex_polygon(np.array([5.0, 0.0]), square)  # edge
    assert not _point_in_convex_polygon(np.array([11.0, 5.0]), square)
    assert not _point_in_convex_polygon(np.array([-0.1, 5.0]), square)


# ---------------------------------------------------------------------------
# Errors


def test_raises_when_baseline_is_none() -> None:
    inst = _toy_instance()
    for pid in ("INS_1", "INS_2", "INS_3", "INS_4"):
        with pytest.raises(ValueError, match="baseline"):
            apply_insertion(inst, _ins(pid), None)


def test_rejects_non_insertion_spec() -> None:
    inst = _toy_instance()
    baseline = _toy_baseline(inst, _toy_partition(inst, k=3))
    bad = lookup_perturbation("X-n101-k25", "CAP_1")
    with pytest.raises(ValueError, match="INSERTION"):
        apply_insertion(inst, bad, baseline)


# ---------------------------------------------------------------------------
# Real instance hand-check


@pytest.mark.skipif(
    not (_instance_present("X-n101-k25") and _baseline_present("X-n101-k25")),
    reason="X-n101-k25 instance file or cached baseline missing",
)
def test_x_n101_k25_all_four_succeed() -> None:
    """All four INS variants run on real X-n101-k25 and produce
    distinct, well-shaped PerturbedInstances."""
    inst = load_instance("X-n101-k25")
    baseline = load_baseline_solution("X-n101-k25")
    seen_coords: list[np.ndarray] = []
    for pid, n_new in [("INS_1", 1), ("INS_2", 3), ("INS_3", 5), ("INS_4", 10)]:
        out = apply_insertion(inst, _ins(pid), baseline)
        assert out.n_customers == 100 + n_new
        assert out.coords.shape == (100 + n_new + 1, 2)
        # Inserted coords must be distinct from any other variant's set.
        new = out.coords[101:]
        for prev in seen_coords:
            assert not _coord_sets_overlap(new, prev)
        seen_coords.append(new)


def _coord_sets_overlap(a: np.ndarray, b: np.ndarray) -> bool:
    set_a = {tuple(row) for row in a}
    set_b = {tuple(row) for row in b}
    return not set_a.isdisjoint(set_b)


@pytest.mark.skipif(
    not (_instance_present("X-n101-k25") and _baseline_present("X-n101-k25")),
    reason="X-n101-k25 instance file or cached baseline missing",
)
def test_x_n101_k25_ins_1_demand_target() -> None:
    """INS_1 on X-n101-k25 (capacity=206, γ=0.30): inserted demand =
    round(0.30 × 206) = 62 (n_new=1, so per-customer = total)."""
    inst = load_instance("X-n101-k25")
    baseline = load_baseline_solution("X-n101-k25")
    out = apply_insertion(inst, _ins("INS_1"), baseline)
    assert int(out.demands[-1]) == 62
    assert out.n_affected_customers == 1
    expected_share = 62 / (5147 + 62)
    assert out.affected_demand_share == pytest.approx(expected_share)
    assert out.affected_route_share == 1.0
