"""Activation-screen tests - required by Phase 1 protocol.

Validates:
  - objective change detection (nonzero response)
  - route count change
  - ARI threshold behavior (structural response)

ARI invariants used below:
  - Identical partitions -> ARI == 1
  - A permutation of cluster labels -> ARI == 1 (ARI is label-invariant)
  - A fully random reshuffle -> ARI near 0
"""
from __future__ import annotations

import math

import pytest

from vrpbench.artifacts.solution import SolutionArtifact
from vrpbench.evaluation.activation import (
    DEFAULT_THRESHOLDS,
    screen_perturbation,
    screen_backend_disagreement,
)
from vrpbench.evaluation.metrics import adjusted_rand_index


def _artifact(
    *,
    instance_id="inst",
    backend="pyvrp",
    objective=1000.0,
    routes=None,
    n_routes=None,
    status="ok",
):
    routes = routes or [[1, 2, 3], [4, 5, 6]]
    return SolutionArtifact(
        instance_id=instance_id,
        backend_name=backend,
        status=status,
        objective=objective,
        runtime_sec=0.01,
        n_routes=n_routes if n_routes is not None else len(routes),
        routes=routes,
        route_loads=[0.0] * len(routes),
        route_distances=[1.0] * len(routes),
        random_seed=1,
        time_limit_sec=1.0,
        solver_params={},
        solver_version="test",
        run_id="test",
        metadata={},
    )


# ------------------------------ ARI invariants -------------------------------


def test_ari_identical_is_one():
    assert adjusted_rand_index([0, 0, 1, 1, 2], [0, 0, 1, 1, 2]) == pytest.approx(1.0)


def test_ari_label_permutation_is_one():
    # relabel 0->7, 1->3, 2->9 — same partition, ARI must still be 1.
    assert adjusted_rand_index([0, 0, 1, 1, 2], [7, 7, 3, 3, 9]) == pytest.approx(1.0)


def test_ari_full_split_is_low():
    # Same singletons on both sides -> max_index == expected -> returns 1.0
    # That is the correct special case. Use a partition vs singletons instead.
    # A strong 2-cluster vs singletons has low but nonzero ARI.
    a = [0, 0, 0, 1, 1, 1]
    b = [0, 1, 2, 3, 4, 5]
    ari = adjusted_rand_index(a, b)
    assert ari < 0.2


def test_ari_disjoint_groups_is_low_or_zero():
    a = [0, 0, 1, 1, 2, 2]
    b = [0, 1, 2, 0, 1, 2]  # permutes membership; no co-clustering preserved
    ari = adjusted_rand_index(a, b)
    assert ari < 0.1


# ------------------------ Perturbation-gate behavior -------------------------


def test_objective_change_below_threshold_does_not_trigger():
    # 0.5% relative change is below the 1% nonzero-response threshold.
    baseline = _artifact(objective=1000.0)
    perturbed = _artifact(objective=1005.0, routes=[[1, 2, 3], [4, 5, 6]])
    row = screen_perturbation(baseline, perturbed, n_customers=6, tag="test")
    assert row.objective_rel_change < DEFAULT_THRESHOLDS["nonzero_response"]["objective_rel_change"]
    assert row.nonzero_response is False


def test_objective_change_above_threshold_triggers():
    # 5% relative change is well above 1%.
    baseline = _artifact(objective=1000.0)
    perturbed = _artifact(objective=1050.0)
    row = screen_perturbation(baseline, perturbed, n_customers=6, tag="test")
    assert row.nonzero_response is True


def test_route_count_change_triggers_nonzero_and_structural():
    baseline = _artifact(objective=1000.0, routes=[[1, 2, 3], [4, 5, 6]])
    perturbed = _artifact(objective=1001.0, routes=[[1, 2], [3, 4], [5, 6]])
    row = screen_perturbation(baseline, perturbed, n_customers=6, tag="test")
    assert row.route_count_change is True
    assert row.nonzero_response is True
    assert row.structural_response is True


def test_ari_below_threshold_triggers_structural():
    # Same route count but complete reshuffle of assignment.
    baseline = _artifact(objective=1000.0, routes=[[1, 2, 3], [4, 5, 6]])
    perturbed = _artifact(objective=1001.0, routes=[[1, 4, 5], [2, 3, 6]])
    row = screen_perturbation(baseline, perturbed, n_customers=6, tag="test")
    assert row.route_count_change is False
    assert row.adjusted_rand is not None
    assert row.adjusted_rand < DEFAULT_THRESHOLDS["structural_response"]["adjusted_rand_below"]
    assert row.structural_response is True


def test_identical_solutions_do_not_trigger_structural():
    baseline = _artifact(objective=1000.0, routes=[[1, 2, 3], [4, 5, 6]])
    perturbed = _artifact(objective=1000.0, routes=[[1, 2, 3], [4, 5, 6]])
    row = screen_perturbation(baseline, perturbed, n_customers=6, tag="test")
    assert row.structural_response is False
    assert row.nonzero_response is False
    assert row.adjusted_rand == pytest.approx(1.0)


# ------------------------ Backend-disagreement gate -------------------------


def test_backend_disagreement_requires_both_criteria():
    # Objective gap 10%, structural ARI very low — should flip disagreement on.
    cheap = _artifact(backend="nearest_neighbor", objective=1100.0,
                      routes=[[1, 2, 3], [4, 5, 6]])
    strong = _artifact(backend="pyvrp", objective=1000.0,
                       routes=[[1, 4, 5], [2, 3, 6]])
    row = screen_backend_disagreement(cheap, strong, n_customers=6)
    assert row.objective_rel_change is not None
    assert row.adjusted_rand is not None
    assert row.backend_disagreement is True


def test_backend_disagreement_objective_only_is_insufficient():
    # Large objective gap but identical structure.
    cheap = _artifact(backend="nearest_neighbor", objective=1100.0,
                      routes=[[1, 2, 3], [4, 5, 6]])
    strong = _artifact(backend="pyvrp", objective=1000.0,
                       routes=[[1, 2, 3], [4, 5, 6]])
    row = screen_backend_disagreement(cheap, strong, n_customers=6)
    assert row.nonzero_response is True  # objective gap exists
    assert row.structural_response is False
    assert row.backend_disagreement is False


def test_backend_disagreement_structural_only_is_insufficient():
    cheap = _artifact(backend="nearest_neighbor", objective=1000.0,
                      routes=[[1, 2, 3], [4, 5, 6]])
    strong = _artifact(backend="pyvrp", objective=1005.0,  # <3% gap
                       routes=[[1, 4, 5], [2, 3, 6]])
    row = screen_backend_disagreement(cheap, strong, n_customers=6)
    assert row.nonzero_response is False
    assert row.backend_disagreement is False
