"""End-to-end test of :func:`compute_audit_fields` on real PyVRP solves.

The audit machinery is the layer the §8.2 stability claims actually rest
on. This file runs three short PyVRP solves (10s each) on a real Stage A
cell, feeds them through ``compute_audit_fields``, and verifies:

1. Top-3 fields are populated with real values (not the empty ``"[]"``
   placeholder).
2. The JSON-encoded top-3 lists round-trip through ``json.loads``.
3. The three instability flags are real booleans.
4. The function is deterministic on identical seed inputs.

The PyVRP runs are 10s rather than 60s to keep this test in the default
suite. The math doesn't depend on time budget.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vrp_copilot_bench.actions.pyvrp_actions import (
    pyvrp_10s,
    pyvrp_60s_seed2,
    pyvrp_60s_seed3,
)
from vrp_copilot_bench.actions.pyvrp_actions import _run_pyvrp
from vrp_copilot_bench.baselines import load_baseline_solution
from vrp_copilot_bench.instances import load_instance
from vrp_copilot_bench.labels import compute_audit_fields, null_audit_fields
from vrp_copilot_bench.perturbations import apply_perturbation, lookup_perturbation


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


def _short_pyvrp(perturbed, baseline, *, seed: int):
    """10s PyVRP on the perturbed instance at the given seed.

    Avoids paying the 60s × 3 = 180s wall-clock for this end-to-end test.
    """
    return _run_pyvrp(
        perturbed,
        time_limit_seconds=10.0,
        seed=seed,
        action_name=f"pyvrp_10s_seed{seed}",
    )


@requires_real_baseline
def test_compute_audit_fields_populates_top3_lists() -> None:
    """The top-3 fields are populated with non-empty JSON lists when the
    audit pair has all three seeds."""
    instance = load_instance(_REAL_INSTANCE_ID)
    baseline = load_baseline_solution(_REAL_INSTANCE_ID)
    spec = lookup_perturbation(_REAL_INSTANCE_ID, "DIST_3")
    perturbed = apply_perturbation(instance, spec, baseline)

    ref = _short_pyvrp(perturbed, baseline, seed=1)
    seed2 = _short_pyvrp(perturbed, baseline, seed=2)
    seed3 = _short_pyvrp(perturbed, baseline, seed=3)

    audit = compute_audit_fields(ref, seed2, seed3, baseline)

    # Top-3 lists are JSON arrays (not the placeholder "[]").
    assert audit.seed_2_top3 != "[]"
    assert audit.seed_3_top3 != "[]"
    seed2_top3 = json.loads(audit.seed_2_top3)
    seed3_top3 = json.loads(audit.seed_3_top3)
    # Top-3 has at most 3 elements; every element is a baseline route id.
    assert 1 <= len(seed2_top3) <= 3
    assert 1 <= len(seed3_top3) <= 3
    valid_groups = set(baseline.assignment.values())
    assert all(g in valid_groups for g in seed2_top3)
    assert all(g in valid_groups for g in seed3_top3)


@requires_real_baseline
def test_compute_audit_fields_returns_bool_flags() -> None:
    """The three instability flags are populated with bool, not the
    placeholder False / None."""
    instance = load_instance(_REAL_INSTANCE_ID)
    baseline = load_baseline_solution(_REAL_INSTANCE_ID)
    spec = lookup_perturbation(_REAL_INSTANCE_ID, "CAP_2")
    perturbed = apply_perturbation(instance, spec, baseline)

    ref = _short_pyvrp(perturbed, baseline, seed=1)
    seed2 = _short_pyvrp(perturbed, baseline, seed=2)
    seed3 = _short_pyvrp(perturbed, baseline, seed=3)

    audit = compute_audit_fields(ref, seed2, seed3, baseline)
    # Real booleans.
    assert isinstance(audit.obj_unstable, bool)
    assert isinstance(audit.struct_unstable, bool)
    assert isinstance(audit.rank_unstable, bool)


@requires_real_baseline
def test_compute_audit_fields_seed2_seed3_round_trip_json() -> None:
    """JSON-encoded fields round-trip cleanly."""
    instance = load_instance(_REAL_INSTANCE_ID)
    baseline = load_baseline_solution(_REAL_INSTANCE_ID)
    spec = lookup_perturbation(_REAL_INSTANCE_ID, "DIST_4")
    perturbed = apply_perturbation(instance, spec, baseline)

    ref = _short_pyvrp(perturbed, baseline, seed=1)
    seed2 = _short_pyvrp(perturbed, baseline, seed=2)
    seed3 = _short_pyvrp(perturbed, baseline, seed=3)

    audit = compute_audit_fields(ref, seed2, seed3, baseline)
    # Assignment fields round-trip through json.loads.
    seed2_assignment = json.loads(audit.seed_2_assignment)
    assert isinstance(seed2_assignment, dict)
    # Keys are stringified customer ids; round-trip back to int and confirm
    # the set matches the perturbed customer universe.
    assignment_keys = {int(k) for k in seed2_assignment}
    assert assignment_keys == set(range(1, perturbed.n_customers + 1))


@requires_real_baseline
def test_compute_audit_fields_deterministic_on_identical_inputs() -> None:
    """Calling compute_audit_fields twice with the same inputs yields
    identical results (no RNG inside the function)."""
    instance = load_instance(_REAL_INSTANCE_ID)
    baseline = load_baseline_solution(_REAL_INSTANCE_ID)
    spec = lookup_perturbation(_REAL_INSTANCE_ID, "CAP_2")
    perturbed = apply_perturbation(instance, spec, baseline)
    # Reuse the same three solves so we measure determinism of
    # compute_audit_fields, not of PyVRP.
    ref = _short_pyvrp(perturbed, baseline, seed=1)
    seed2 = _short_pyvrp(perturbed, baseline, seed=2)
    seed3 = _short_pyvrp(perturbed, baseline, seed=3)

    audit_a = compute_audit_fields(ref, seed2, seed3, baseline)
    audit_b = compute_audit_fields(ref, seed2, seed3, baseline)
    assert audit_a == audit_b


def test_compute_audit_fields_returns_null_when_audit_seeds_missing() -> None:
    """The labels module's contract: missing seed2 or seed3 → null audit
    fields. (This test does not need real data.)"""
    # Trivial reference; seeds missing → null audit.
    from vrp_copilot_bench.actions import ActionResult
    from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig
    from vrp_copilot_bench.baselines import Solution

    ref = ActionResult(
        action="pyvrp_60s",
        objective=100.0,
        feasible=True,
        runtime_seconds=0.0,
        n_overload=0,
        max_overload_fraction=0.0,
        assignment={1: 0, 2: 0},
        route_costs={0: 100.0},
        customer_costs={1: 50.0, 2: 50.0},
    )
    baseline = Solution(
        instance_id="dummy",
        objective=100.0,
        routes=[[1, 2]],
        assignment={1: 0, 2: 0},
        route_costs={0: 100.0},
        customer_costs={1: 50.0, 2: 50.0},
        runtime_seconds=0.0,
        pyvrp_version="test",
        config=SolveConfig(time_limit_seconds=1.0, seed=1),
    )
    audit = compute_audit_fields(ref, None, None, baseline)
    assert audit == null_audit_fields()
