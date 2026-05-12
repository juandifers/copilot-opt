"""Tests for ``reference_rank_unstable`` (prereg §8.2).

The flag fires when the minimum pairwise top-3 baseline-group Jaccard
across the three reference seeds is below 0.50. Tested cases:

- All three seeds with identical top-3 → False.
- All three seeds with disjoint top-3 → True.
- Threshold boundary: Jaccard exactly 0.50 → False (strict inequality).
- Determinism.
"""
from __future__ import annotations

from vrp_copilot_bench.actions import ActionResult
from vrp_copilot_bench.baselines import Solution
from vrp_copilot_bench.labels import _compute_reference_rank_unstable
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig


def _action(customer_costs: dict[int, float]) -> ActionResult:
    return ActionResult(
        action="dummy",
        objective=0.0,
        feasible=True,
        runtime_seconds=0.0,
        n_overload=0,
        max_overload_fraction=0.0,
        assignment={c: 0 for c in customer_costs},
        route_costs={},
        customer_costs=dict(customer_costs),
    )


def _baseline(routes: list[list[int]], customer_costs: dict[int, float]) -> Solution:
    assignment: dict[int, int] = {}
    for ri, route in enumerate(routes):
        for c in route:
            assignment[c] = ri
    return Solution(
        instance_id="dummy",
        objective=sum(customer_costs.values()),
        routes=routes,
        assignment=assignment,
        route_costs={ri: 0.0 for ri in range(len(routes))},
        customer_costs=dict(customer_costs),
        runtime_seconds=0.0,
        pyvrp_version="test",
        config=SolveConfig(time_limit_seconds=1.0, seed=1),
    )


def test_three_seeds_identical_top3_not_unstable() -> None:
    baseline_costs = {c: 0.0 for c in range(1, 7)}
    baseline = _baseline(
        routes=[[1], [2], [3], [4], [5], [6]],
        customer_costs=baseline_costs,
    )
    costs = {1: 100.0, 2: 90.0, 3: 80.0, 4: 1.0, 5: 1.0, 6: 1.0}
    a = _action(costs)
    assert _compute_reference_rank_unstable(a, a, a, baseline) is False


def test_three_seeds_disjoint_top3_unstable() -> None:
    baseline_costs = {c: 0.0 for c in range(1, 10)}
    baseline = _baseline(
        routes=[[c] for c in range(1, 10)],  # 9 single-customer routes
        customer_costs=baseline_costs,
    )
    # Three completely disjoint top-3 sets.
    seed1 = _action({1: 100.0, 2: 90.0, 3: 80.0, **{c: 1.0 for c in range(4, 10)}})
    seed2 = _action({4: 100.0, 5: 90.0, 6: 80.0, **{c: 1.0 for c in range(1, 4)}, **{c: 1.0 for c in range(7, 10)}})
    seed3 = _action({7: 100.0, 8: 90.0, 9: 80.0, **{c: 1.0 for c in range(1, 7)}})
    assert _compute_reference_rank_unstable(seed1, seed2, seed3, baseline) is True


def test_threshold_boundary_jaccard_exactly_0_50_is_not_unstable() -> None:
    """Jaccard exactly 0.50 → not unstable. Engineer this by making seeds 2 and 3
    identical but each disagreeing with seed 1 on exactly 1 of 3 groups."""
    baseline_costs = {c: 0.0 for c in range(1, 5)}
    baseline = _baseline(
        routes=[[c] for c in range(1, 5)],  # 4 routes
        customer_costs=baseline_costs,
    )
    # seed1 top-3: {0, 1, 2}; seed2 = seed3 top-3: {0, 1, 3}.
    # Jaccard(seed1, seed2) = |{0,1}| / |{0,1,2,3}| = 2/4 = 0.5.
    # Jaccard(seed2, seed3) = 1.0; min = 0.5.
    seed1 = _action({1: 100.0, 2: 90.0, 3: 80.0, 4: 1.0})
    seed2 = _action({1: 100.0, 2: 90.0, 3: 1.0, 4: 80.0})
    seed3 = _action({1: 100.0, 2: 90.0, 3: 1.0, 4: 80.0})
    # Strict inequality: 0.5 < 0.5 is False → not unstable.
    assert _compute_reference_rank_unstable(seed1, seed2, seed3, baseline) is False


def test_threshold_below_0_50_unstable() -> None:
    baseline_costs = {c: 0.0 for c in range(1, 7)}
    baseline = _baseline(
        routes=[[c] for c in range(1, 7)],
        customer_costs=baseline_costs,
    )
    # seed1 top-3: {0, 1, 2}; seed2 top-3: {0, 3, 4}.
    # Jaccard = |{0}| / |{0,1,2,3,4}| = 1/5 = 0.2.
    seed1 = _action({1: 100.0, 2: 90.0, 3: 80.0, 4: 1.0, 5: 1.0, 6: 1.0})
    seed2 = _action({1: 100.0, 2: 1.0, 3: 1.0, 4: 90.0, 5: 80.0, 6: 1.0})
    seed3 = _action({1: 100.0, 2: 90.0, 3: 80.0, 4: 1.0, 5: 1.0, 6: 1.0})
    assert _compute_reference_rank_unstable(seed1, seed2, seed3, baseline) is True


def test_threshold_parameter_overridable() -> None:
    """Tighten the threshold and the same input flips to unstable."""
    baseline_costs = {c: 0.0 for c in range(1, 5)}
    baseline = _baseline(
        routes=[[c] for c in range(1, 5)],
        customer_costs=baseline_costs,
    )
    seed1 = _action({1: 100.0, 2: 90.0, 3: 80.0, 4: 1.0})
    seed2 = _action({1: 100.0, 2: 90.0, 3: 1.0, 4: 80.0})  # Jaccard 0.5 vs seed1
    seed3 = _action({1: 100.0, 2: 90.0, 3: 1.0, 4: 80.0})
    # Default threshold 0.50: not unstable (0.5 < 0.5 is False).
    assert _compute_reference_rank_unstable(seed1, seed2, seed3, baseline) is False
    # Tighter threshold 0.75: now unstable.
    assert (
        _compute_reference_rank_unstable(seed1, seed2, seed3, baseline, threshold=0.75)
        is True
    )


def test_determinism() -> None:
    baseline_costs = {c: 0.0 for c in range(1, 7)}
    baseline = _baseline(
        routes=[[c] for c in range(1, 7)],
        customer_costs=baseline_costs,
    )
    seed1 = _action({c: float(c) for c in range(1, 7)})
    seed2 = _action({c: float(c) * 2 for c in range(1, 7)})
    seed3 = _action({c: float(7 - c) for c in range(1, 7)})
    runs = [
        _compute_reference_rank_unstable(seed1, seed2, seed3, baseline)
        for _ in range(5)
    ]
    assert all(r == runs[0] for r in runs)
