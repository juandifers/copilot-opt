"""Tests for ``loss_rank`` (1 - top-3 baseline-group Jaccard; prereg §9.4).

The ranking metric is the most subtle of the four loss families:

- It is grounded in the *baseline* route partitioning (identity-stable across
  all actions), not in action-side route IDs.
- The per-baseline-group impact is computed as a *delta* from the baseline:
  ``impact(g) = sum_action_costs(g) - sum_baseline_costs(g)``. This is what
  surfaces "which groups the perturbation actually changed", as opposed to
  "which groups are absolutely expensive" (which the raw-sum form would
  return).

Coverage focus:

- Identical top-3 sets → loss 0.0.
- Disjoint top-3 sets → loss 1.0.
- Two of three matching → Jaccard 0.5 → loss 0.5.
- Hand-computed: known impact vectors with known top-3 ordering.
- Tie-breaking: equal impacts → lowest group ID first.
- Partial coverage: customers absent from action.customer_costs contribute
  0.0 on the action side.
- Determinism.
- Fewer than 3 baseline groups: top-k reduces to top-min(3, n_groups).
- Empty action.customer_costs returns NaN.
"""
from __future__ import annotations

import math

import pytest

from vrp_copilot_bench.actions import ActionResult
from vrp_copilot_bench.baselines import Solution
from vrp_copilot_bench.labels import (
    _compute_baseline_group_impacts,
    _compute_loss_rank,
    _top_n_groups,
    _top_n_jaccard,
)
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig


def _action(customer_costs: dict[int, float]) -> ActionResult:
    """Minimal ActionResult — only customer_costs is used by loss_rank."""
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


def _baseline(
    routes: list[list[int]],
    customer_costs: dict[int, float],
) -> Solution:
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


# ---------------------------------------------------------------------------
# Helper: _compute_baseline_group_impacts (delta form)


def test_impact_aggregates_per_group_in_delta_form() -> None:
    """impact(g) = sum_plan(g) - sum_baseline(g). For two routes with two
    customers each, with action costs [10, 5, 20, 15] and baseline costs
    [8, 4, 18, 12] across customers 1..4:

    - g=0 (customers 1,2): action=10+5=15, baseline=8+4=12, delta=+3.
    - g=1 (customers 3,4): action=20+15=35, baseline=18+12=30, delta=+5.
    """
    baseline_assignment = {1: 0, 2: 0, 3: 1, 4: 1}
    baseline_costs = {1: 8.0, 2: 4.0, 3: 18.0, 4: 12.0}
    action_costs = {1: 10.0, 2: 5.0, 3: 20.0, 4: 15.0}
    impacts = _compute_baseline_group_impacts(
        action_costs, baseline_assignment, baseline_costs
    )
    assert impacts == {0: 3.0, 1: 5.0}


def test_impact_excludes_customers_with_negative_baseline_group() -> None:
    """Customers with baseline_assignment[c] = -1 (e.g., new INSERTION
    customers) are not aggregated into any group."""
    baseline_assignment = {1: 0, 2: 0, 3: -1, 4: 1}
    baseline_costs = {1: 0.0, 2: 0.0, 4: 0.0}  # 3 absent — INSERTION customer
    action_costs = {1: 1.0, 2: 1.0, 3: 5.0, 4: 1.0}
    impacts = _compute_baseline_group_impacts(
        action_costs, baseline_assignment, baseline_costs
    )
    # Group 0: customer 1+2 → 1+1-0-0 = 2. Group 1: customer 4 → 1-0 = 1.
    # Customer 3 (group=-1) is skipped.
    assert impacts == {0: 2.0, 1: 1.0}


def test_impact_partial_coverage_action_costs_default_to_zero() -> None:
    """Customers absent from plan_customer_costs contribute 0 on the action
    side — appropriate for ``reuse_direct`` on INSERTION where the new
    customers don't appear in the action's plan."""
    baseline_assignment = {1: 0, 2: 0, 3: 1, 4: 1}
    baseline_costs = {1: 5.0, 2: 5.0, 3: 5.0, 4: 5.0}
    # action covers only customers 1 and 3.
    action_costs = {1: 8.0, 3: 8.0}
    impacts = _compute_baseline_group_impacts(
        action_costs, baseline_assignment, baseline_costs
    )
    # g=0: action 8+0 - baseline 5+5 = -2. g=1: action 8+0 - baseline 5+5 = -2.
    assert impacts == {0: -2.0, 1: -2.0}


# ---------------------------------------------------------------------------
# Helper: _top_n_groups


def test_top_n_descending_by_impact() -> None:
    impacts = {0: 5.0, 1: 20.0, 2: 10.0, 3: 15.0}
    assert _top_n_groups(impacts, n=3) == [1, 3, 2]


def test_top_n_tiebreak_lowest_group_id_first() -> None:
    """Two groups with identical impact: the lower group ID wins."""
    impacts = {3: 10.0, 1: 10.0, 5: 10.0, 2: 5.0}
    assert _top_n_groups(impacts, n=3) == [1, 3, 5]


def test_top_n_reduced_when_fewer_than_n_groups() -> None:
    impacts = {0: 5.0, 1: 10.0}
    assert _top_n_groups(impacts, n=3) == [1, 0]


def test_top_n_empty_returns_empty_list() -> None:
    assert _top_n_groups({}, n=3) == []


# ---------------------------------------------------------------------------
# Helper: _top_n_jaccard


def test_jaccard_identical_sets_is_one() -> None:
    assert _top_n_jaccard([0, 1, 2], [0, 1, 2]) == pytest.approx(1.0)


def test_jaccard_disjoint_sets_is_zero() -> None:
    assert _top_n_jaccard([0, 1, 2], [3, 4, 5]) == pytest.approx(0.0)


def test_jaccard_two_of_three_matching() -> None:
    """|∩|=2, |∪|=4 → Jaccard 0.5."""
    assert _top_n_jaccard([0, 1, 2], [0, 1, 3]) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# loss_rank end-to-end


def test_loss_rank_identical_rankings_zero() -> None:
    """Action and reference produce the same top-3 → loss 0.0."""
    baseline_costs = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0}
    baseline = _baseline(
        routes=[[1, 2], [3, 4], [5, 6]],
        customer_costs=baseline_costs,
    )
    # Same per-customer cost increase on every route → top-3 is all three.
    action_costs = {1: 5.0, 2: 5.0, 3: 5.0, 4: 5.0, 5: 5.0, 6: 5.0}
    reference_costs = action_costs
    assert _compute_loss_rank(_action(action_costs), _action(reference_costs), baseline) == pytest.approx(0.0)


def test_loss_rank_disjoint_top3_one() -> None:
    """4 baseline routes; action's top-3 is {0,1,2}, reference's is {3} —
    only 1 group exists in reference's top-1 because reference only
    perturbed group 3.

    Reduce to top-min(3, 4) = top-3 each side → action top-3 = {0,1,2},
    reference top-3 = {3, low-impact-group, low-impact-group}. Jaccard
    depends on the low-impact tie-break.

    Cleaner construction: two completely separate impact vectors where
    top-3 sets share no element. Engineer with 6 baseline routes.
    """
    baseline_costs = {c: 0.0 for c in range(1, 7)}  # zero baseline → action_cost = delta
    baseline = _baseline(
        routes=[[1], [2], [3], [4], [5], [6]],  # 6 single-customer routes
        customer_costs=baseline_costs,
    )
    # Action: top-3 groups {0, 1, 2} (highest cost on customers 1,2,3)
    action_costs = {1: 100.0, 2: 90.0, 3: 80.0, 4: 1.0, 5: 1.0, 6: 1.0}
    # Reference: top-3 groups {3, 4, 5}
    reference_costs = {1: 1.0, 2: 1.0, 3: 1.0, 4: 100.0, 5: 90.0, 6: 80.0}
    loss = _compute_loss_rank(_action(action_costs), _action(reference_costs), baseline)
    assert loss == pytest.approx(1.0)


def test_loss_rank_two_of_three_matching() -> None:
    """Top-3 action = {0, 1, 2}; top-3 reference = {0, 1, 3}. |∩|=2,
    |∪|=4, jaccard=0.5, loss=0.5."""
    baseline_costs = {c: 0.0 for c in range(1, 7)}
    baseline = _baseline(
        routes=[[1], [2], [3], [4], [5], [6]],
        customer_costs=baseline_costs,
    )
    action_costs = {1: 100.0, 2: 90.0, 3: 80.0, 4: 1.0, 5: 1.0, 6: 1.0}
    reference_costs = {1: 100.0, 2: 90.0, 3: 1.0, 4: 80.0, 5: 1.0, 6: 1.0}
    loss = _compute_loss_rank(_action(action_costs), _action(reference_costs), baseline)
    assert loss == pytest.approx(0.5)


def test_loss_rank_hand_computed_identical_ranking() -> None:
    """4 baseline groups, impacts under action [10, 5, 20, 15], under
    reference [12, 4, 18, 16]. Top-3 action = [2, 3, 0]; top-3 reference =
    [2, 3, 0]. Identical → loss 0.0.
    """
    baseline_costs = {c: 0.0 for c in range(1, 5)}
    baseline = _baseline(
        routes=[[1], [2], [3], [4]],  # 4 single-customer routes, group ids 0..3
        customer_costs=baseline_costs,
    )
    action_costs = {1: 10.0, 2: 5.0, 3: 20.0, 4: 15.0}
    reference_costs = {1: 12.0, 2: 4.0, 3: 18.0, 4: 16.0}
    loss = _compute_loss_rank(_action(action_costs), _action(reference_costs), baseline)
    assert loss == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Edge cases: small baselines and partial coverage


def test_loss_rank_with_two_baseline_routes_uses_top2() -> None:
    """When the baseline has only 2 routes, top-k reduces to 2 on each side
    per §9.4."""
    baseline_costs = {1: 0.0, 2: 0.0}
    baseline = _baseline(
        routes=[[1], [2]],
        customer_costs=baseline_costs,
    )
    action_costs = {1: 5.0, 2: 10.0}
    reference_costs = {1: 5.0, 2: 10.0}
    loss = _compute_loss_rank(_action(action_costs), _action(reference_costs), baseline)
    assert loss == pytest.approx(0.0)


def test_loss_rank_partial_coverage_zeros_action_side_for_unassigned() -> None:
    """``reuse_direct`` on INSERTION leaves the inserted customers absent
    from action.customer_costs. The aggregator treats them as 0.0 on the
    action side, contributing only the baseline subtraction. Affected
    groups still appear in the impact dict.
    """
    baseline_costs = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}
    baseline = _baseline(
        routes=[[1, 2], [3, 4]],
        customer_costs=baseline_costs,
    )
    # Action covers customers 1 and 3 only (2 and 4 unassigned).
    action_costs = {1: 5.0, 3: 5.0}
    impacts = _compute_baseline_group_impacts(
        action_costs, baseline.assignment, baseline.customer_costs
    )
    # g=0: 5 + 0 - 1 - 1 = 3. g=1: 5 + 0 - 1 - 1 = 3.
    assert impacts == {0: 3.0, 1: 3.0}


def test_loss_rank_returns_nan_on_empty_action_customer_costs() -> None:
    """An action result with no customer_costs is degenerate; the labels
    module logs a warning and returns NaN rather than silently returning 1.0."""
    baseline = _baseline(
        routes=[[1, 2]], customer_costs={1: 0.0, 2: 0.0}
    )
    reference_costs = {1: 5.0, 2: 5.0}
    loss = _compute_loss_rank(_action({}), _action(reference_costs), baseline)
    assert math.isnan(loss)


def test_loss_rank_is_deterministic() -> None:
    baseline_costs = {c: float(c) for c in range(1, 21)}
    baseline = _baseline(
        routes=[[c for c in range(i, i + 5)] for i in range(1, 21, 5)],
        customer_costs=baseline_costs,
    )
    action_costs = {c: float(c) * 2 for c in range(1, 21)}
    reference_costs = {c: float(c) * 1.5 for c in range(1, 21)}
    runs = [
        _compute_loss_rank(_action(action_costs), _action(reference_costs), baseline)
        for _ in range(5)
    ]
    assert all(r == runs[0] for r in runs)
