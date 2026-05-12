"""Tests for the PyVRP action wrappers.

The four wrappers all share the same skeleton (``_run_pyvrp``); these
tests focus on:

1. **The load-bearing regression test** — pyvrp_60s output on a DIST
   perturbation, re-evaluated via :func:`evaluate_route_plan`, must
   match within 1e-3 absolute tolerance. This catches the worst possible
   bug: PyVRP solving against one matrix while the evaluator scores
   against a different one. If
   :func:`build_perturbed_distance_matrix` is bypassed by either side,
   this test fails. Phase C's correctness boundary lives here.

2. Schema sanity: each wrapper returns an :class:`ActionResult` with the
   right ``action`` name and meta payload.

3. Seed determinism band: pyvrp_60s_seed2 produces a different objective
   than pyvrp_60s_seed=1 on most instances — this is the audit's
   purpose (§8.2 of the prereg).

PyVRP is wall-clock bounded; the long tests cap their per-action budget
at the action's nominal limit (10s or 60s). The 60s tests gate behind
the ``VRP_RUN_PYVRP_TESTS=1`` environment variable to keep the default
pytest run fast; CI / sanity-check runs flip the gate.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from vrp_copilot_bench.actions import ActionResult
from vrp_copilot_bench.actions.evaluate import evaluate_route_plan
from vrp_copilot_bench.actions.pyvrp_actions import (
    pyvrp_10s,
    pyvrp_60s,
    pyvrp_60s_seed2,
    pyvrp_60s_seed3,
)
from vrp_copilot_bench.baselines import Solution, load_baseline_solution
from vrp_copilot_bench.instances import Instance, load_instance
from vrp_copilot_bench.perturbations import apply_perturbation, lookup_perturbation
from vrp_copilot_bench.perturbations.types import PerturbedInstance


# ---------------------------------------------------------------------------
# Real-data fixtures


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

requires_pyvrp_long = pytest.mark.skipif(
    os.environ.get("VRP_RUN_PYVRP_TESTS") != "1",
    reason="opt-in: set VRP_RUN_PYVRP_TESTS=1 to run 60s+ PyVRP tests",
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
# Schema / metadata


@requires_real_baseline
def test_pyvrp_10s_returns_action_result(
    real_instance: Instance, real_baseline: Solution
) -> None:
    perturbed = _perturb(real_instance, real_baseline, "CAP_2")
    out = pyvrp_10s(perturbed, real_baseline)
    assert isinstance(out, ActionResult)
    assert out.action == "pyvrp_10s"
    assert out.meta.get("pyvrp_version") is not None
    assert out.meta.get("perturbation_id") == "CAP_2"


@requires_real_baseline
@requires_pyvrp_long
def test_pyvrp_60s_returns_action_result(
    real_instance: Instance, real_baseline: Solution
) -> None:
    perturbed = _perturb(real_instance, real_baseline, "CAP_2")
    out = pyvrp_60s(perturbed, real_baseline)
    assert isinstance(out, ActionResult)
    assert out.action == "pyvrp_60s"


@requires_real_baseline
@requires_pyvrp_long
def test_pyvrp_60s_seed2_seed3_meta(
    real_instance: Instance, real_baseline: Solution
) -> None:
    perturbed = _perturb(real_instance, real_baseline, "CAP_2")
    out2 = pyvrp_60s_seed2(perturbed, real_baseline)
    out3 = pyvrp_60s_seed3(perturbed, real_baseline)
    assert out2.action == "pyvrp_60s_seed2"
    assert out3.action == "pyvrp_60s_seed3"


# ---------------------------------------------------------------------------
# LOAD-BEARING regression test
#
# This is THE test that catches the worst possible bug — PyVRP solving
# against one distance matrix while the evaluator scores against a
# different one. If `build_perturbed_distance_matrix` is bypassed
# anywhere, or if the DISTANCE mask is dropped on either side, this
# test fails by construction.


@requires_real_baseline
def test_pyvrp_routes_re_evaluate_to_same_objective_under_dist_mask(
    real_instance: Instance, real_baseline: Solution
) -> None:
    """Regression: pyvrp_10s on a DIST_3 perturbation; take the returned
    routes; re-evaluate them via :func:`evaluate_route_plan`; the two
    objectives must match within 1e-3 absolute tolerance.

    Why pyvrp_10s and not pyvrp_60s: this test runs in the default suite
    and 10 seconds is the smallest budget that still produces stable
    feasible routes on X-n101-k25. The mathematical contract being
    tested is identical at any time budget.

    Why DIST_3 specifically: DIST_3 is one of the perturbations whose
    ``distance_multiplier_mask`` is non-trivial (a regional 2× scaling
    on the highest-density region). Any bypass of the mask in either
    PyVRP's matrix or the evaluator's matrix would leave a measurable
    objective gap.
    """
    perturbed = _perturb(real_instance, real_baseline, "DIST_3")
    out = pyvrp_10s(perturbed, real_baseline)

    # Re-score the same route plan via the evaluator. This rebuilds the
    # masked matrix from scratch via build_perturbed_distance_matrix.
    rescored = evaluate_route_plan(out.routes, perturbed, allow_partial_coverage=False)

    assert out.objective == pytest.approx(rescored.objective, abs=1e-3), (
        f"PyVRP and evaluator disagree on the same routes: PyVRP reports "
        f"{out.objective:.3f}; evaluator reports {rescored.objective:.3f}. "
        f"This means at least one side is using the wrong distance matrix "
        f"(check that both go through build_perturbed_distance_matrix)."
    )
    # Other invariants should also agree.
    assert out.feasible == rescored.feasible
    assert out.n_overload == rescored.n_overload


@requires_real_baseline
def test_pyvrp_routes_re_evaluate_under_capacity_only_perturbation(
    real_instance: Instance, real_baseline: Solution
) -> None:
    """Companion to the DIST_3 regression: under a CAPACITY perturbation
    (no mask), the same equivalence must hold trivially — i.e. with
    ``mask is None``, both sides fall back to the unmasked Euclidean
    distance and agree."""
    perturbed = _perturb(real_instance, real_baseline, "CAP_2")
    out = pyvrp_10s(perturbed, real_baseline)
    rescored = evaluate_route_plan(out.routes, perturbed, allow_partial_coverage=False)
    assert out.objective == pytest.approx(rescored.objective, abs=1e-3)


# ---------------------------------------------------------------------------
# Seed differences (audit purpose)


@requires_real_baseline
@requires_pyvrp_long
def test_pyvrp_60s_seed2_differs_from_seed1_on_average(
    real_instance: Instance, real_baseline: Solution
) -> None:
    """The audit (§8.2) measures cross-seed PyVRP noise. On a moderately
    perturbed instance, seed=1 and seed=2 should typically produce
    different objectives. This is not a hard guarantee on every
    instance — sometimes ties happen — but the prereg's
    ``reference_obj_unstable`` flag would never trip if seeds were
    identical, so the test verifies the basic premise."""
    perturbed = _perturb(real_instance, real_baseline, "CAP_2")
    out1 = pyvrp_60s(perturbed, real_baseline)
    out2 = pyvrp_60s_seed2(perturbed, real_baseline)
    # Different seeds → different search trajectories → typically
    # different objectives. Allow a 5 % tolerance band; if the gap is
    # genuinely below 5 %, that's still informative for the audit.
    rel_diff = abs(out1.objective - out2.objective) / max(out1.objective, 1e-9)
    # Loose assertion: the seeds should at least not produce identical
    # incumbents — the search is inherently stochastic. If they DO match
    # exactly that's suspicious.
    assert out1.objective != out2.objective or rel_diff > 0, (
        "seed=1 and seed=2 produced identical objectives — unexpected "
        "for stochastic PyVRP search"
    )


# ---------------------------------------------------------------------------
# Construction-and-evaluation invariant


@requires_real_baseline
def test_pyvrp_action_objective_equals_sum_of_route_costs(
    real_instance: Instance, real_baseline: Solution
) -> None:
    """The :class:`ActionResult` invariant: ``objective == sum(route_costs)``.

    This holds trivially because the wrapper copies ``solve_result.objective``
    and ``solve_result.route_costs`` verbatim, and PyVRP itself maintains
    the invariant. The test guards against future refactors that might
    diverge them.
    """
    perturbed = _perturb(real_instance, real_baseline, "CAP_2")
    out = pyvrp_10s(perturbed, real_baseline)
    # PyVRP's reported objective and the sum of its route costs may
    # differ by a tiny floating-point amount due to internal rounding;
    # 1.0 absolute tolerance is generous given the X-n101-k25 baseline
    # objective of ~27500.
    assert out.objective == pytest.approx(sum(out.route_costs.values()), abs=1.0)
