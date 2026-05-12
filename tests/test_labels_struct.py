"""Tests for ``loss_struct`` (1 - ARI; prereg §9.3).

The structural loss compares an action's customer→route assignment to the
reference's, treating each customer as a data point and its assigned route
as its cluster label. ARI handles the route-id permutation problem natively.

Coverage focus:

- Identity: identical assignments → loss 0.0.
- Disjoint: a clearly different partition → loss close to 1.0.
- Hand-computed: a known {1,2}/{3,4} vs {1,3}/{2,4} → ARI = 0 → loss = 1.0.
- Partial coverage: customers absent from action assignment receive label
  ``-1``, becoming a distinct cluster in the action partition.
- Determinism: same inputs produce the same loss.
- Customer-id ordering: the label arrays follow ``1..n``, not insertion order.
"""
from __future__ import annotations

import math

import pytest
from sklearn.metrics import adjusted_rand_score

from vrp_copilot_bench.actions import ActionResult
from vrp_copilot_bench.labels import _assignment_label_arrays, _compute_loss_struct


def _result(assignment: dict[int, int]) -> ActionResult:
    """Minimal ActionResult — only the assignment dict matters for ARI."""
    return ActionResult(
        action="dummy",
        objective=0.0,
        feasible=True,
        runtime_seconds=0.0,
        n_overload=0,
        max_overload_fraction=0.0,
        assignment=dict(assignment),
        route_costs={},
        customer_costs={},
    )


# ---------------------------------------------------------------------------
# Identity & disjoint partitions


def test_identical_assignments_loss_zero() -> None:
    a = {1: 0, 2: 0, 3: 1, 4: 1, 5: 2, 6: 2}
    assert _compute_loss_struct(_result(a), _result(a)) == pytest.approx(0.0)


def test_loss_struct_handles_route_id_permutation() -> None:
    """ARI is invariant under cluster-label permutation. Two assignments
    that differ only in route-id labelling must produce loss 0.0."""
    reference = {1: 0, 2: 0, 3: 1, 4: 1}
    action = {1: 7, 2: 7, 3: 9, 4: 9}  # same partition, different route ids
    assert _compute_loss_struct(_result(action), _result(reference)) == pytest.approx(0.0)


def test_orthogonal_partition_hand_computed() -> None:
    """Two completely orthogonal binary partitions on 4 customers.

    Reference partition {1,2}/{3,4}; action partition {1,3}/{2,4}. ARI on
    such a small, perfectly anti-correlated input is *negative* (sklearn's
    adjusted-for-chance formulation can drop below 0); the loss therefore
    exceeds 1.0. Lock the exact value to sklearn's output.
    """
    reference = {1: 0, 2: 0, 3: 1, 4: 1}
    action = {1: 0, 2: 1, 3: 0, 4: 1}
    expected_ari = adjusted_rand_score([0, 0, 1, 1], [0, 1, 0, 1])
    loss = _compute_loss_struct(_result(action), _result(reference))
    assert loss == pytest.approx(1.0 - expected_ari, abs=1e-9)
    # Document the regime: anti-correlated partitions have ARI < 0.
    assert expected_ari < 0.0


# ---------------------------------------------------------------------------
# Partial coverage (reuse_direct on INSERTION)


def test_partial_coverage_labels_unassigned_as_minus_one() -> None:
    """Customers absent from action.assignment get label -1, forming a
    distinct cluster in the action partition."""
    reference = {1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2}
    # 5 and 6 unassigned in the action → labelled -1 by the helper.
    action = {1: 0, 2: 0, 3: 1, 4: 1}
    ref_labels, action_labels = _assignment_label_arrays(action, reference)
    assert list(ref_labels) == [0, 0, 1, 1, 1, 2]
    assert list(action_labels) == [0, 0, 1, 1, -1, -1]


def test_partial_coverage_loss_value_locked() -> None:
    """Lock the exact loss value so future refactors don't silently shift it.

    Reference {1:0, 2:0, 3:1, 4:1, 5:1, 6:2} vs action {1:0, 2:0, 3:1, 4:1}
    where 5,6 → -1. The action partition is {1,2}/{3,4}/{5,6}; the reference
    is {1,2}/{3,4,5}/{6}. ARI is computed by sklearn from these two label
    arrays.
    """
    reference = {1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2}
    action = {1: 0, 2: 0, 3: 1, 4: 1}
    expected_ari = adjusted_rand_score(
        [0, 0, 1, 1, 1, 2], [0, 0, 1, 1, -1, -1]
    )
    expected_loss = 1.0 - expected_ari
    assert _compute_loss_struct(_result(action), _result(reference)) == pytest.approx(
        expected_loss, abs=1e-9
    )


def test_full_partial_coverage_all_unassigned() -> None:
    """Pathological extreme: action assigns no customers. All customers
    get -1 → action partition is one big cluster. ARI is well-defined."""
    reference = {1: 0, 2: 0, 3: 1, 4: 1}
    action: dict[int, int] = {}
    loss = _compute_loss_struct(_result(action), _result(reference))
    # All-same labels on one side → ARI is 0 (partitions are independent).
    assert loss == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Customer-id ordering


def test_customer_ids_iterated_in_order_not_dict_order() -> None:
    """The label arrays follow customer-id order 1..n, regardless of dict
    insertion order. Build a reference dict with shuffled keys and verify
    the array reflects ascending IDs."""
    reference = {3: 1, 1: 0, 4: 1, 2: 0}
    action = {1: 0, 2: 0, 3: 1, 4: 1}
    ref_labels, action_labels = _assignment_label_arrays(action, reference)
    assert list(ref_labels) == [0, 0, 1, 1]  # by id 1,2,3,4 — not 3,1,4,2
    assert list(action_labels) == [0, 0, 1, 1]


# ---------------------------------------------------------------------------
# Edge cases


def test_empty_reference_returns_nan() -> None:
    """An empty reference assignment yields NaN — ARI is undefined on
    empty inputs, and the schema validator treats NaN per the standard
    null-loss path."""
    loss = _compute_loss_struct(_result({}), _result({}))
    assert math.isnan(loss)


def test_three_route_partition_against_two_route_action() -> None:
    """Reference has three baseline-style routes; action collapses to two.
    Loss is positive but bounded.
    """
    reference = {1: 0, 2: 0, 3: 1, 4: 1, 5: 2, 6: 2}
    action = {1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 1}
    loss = _compute_loss_struct(_result(action), _result(reference))
    # Hand-check via sklearn directly.
    expected = 1.0 - adjusted_rand_score([0, 0, 1, 1, 2, 2], [0, 0, 0, 1, 1, 1])
    assert loss == pytest.approx(expected, abs=1e-9)
    assert 0.0 < loss < 1.0


# ---------------------------------------------------------------------------
# Determinism


def test_loss_struct_is_deterministic() -> None:
    """Running the same inputs through the loss should yield identical
    floats every time. ARI has no RNG; this is a guard against accidental
    nondeterminism via dict ordering or numpy seed leakage."""
    reference = {c: c % 5 for c in range(1, 30)}
    action = {c: (c * 3) % 7 for c in range(1, 30)}
    losses = [
        _compute_loss_struct(_result(action), _result(reference))
        for _ in range(5)
    ]
    assert all(loss == losses[0] for loss in losses)
