"""Tests for :func:`vrp_copilot_bench.actions.run_action` — the Phase C
dispatcher.

The contract is small but load-bearing:

- All seven action names in :data:`ACTIONS` route to the right
  implementation function.
- An unknown action name raises :class:`ValueError` with a helpful list.
- :class:`ActionFailure` raised by an implementation propagates out of
  :func:`run_action` (the runner is the only layer that catches it).
- Each dispatched action returns a valid :class:`ActionResult` with the
  expected ``action`` field.

The PyVRP action paths inside the dispatcher are exercised at the
schema level only (one short pyvrp_10s call); the long-running
correctness checks live in :mod:`tests.test_pyvrp_actions`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from vrp_copilot_bench.actions import (
    ACTIONS,
    ActionFailure,
    ActionResult,
    run_action,
)
from vrp_copilot_bench.actions import (
    _ACTION_IMPLEMENTATIONS,
    clarke_wright_action,
    nearest_neighbor_action,
    pyvrp_10s,
    pyvrp_60s,
    pyvrp_60s_seed2,
    pyvrp_60s_seed3,
    reuse_direct,
)
from vrp_copilot_bench.baselines import Solution, load_baseline_solution
from vrp_copilot_bench.instances import Instance, load_instance
from vrp_copilot_bench.perturbations import apply_perturbation, lookup_perturbation
from vrp_copilot_bench.perturbations.types import PerturbedInstance
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig


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


@pytest.fixture(scope="module")
def real_instance() -> Instance:
    return load_instance(_REAL_INSTANCE_ID)


@pytest.fixture(scope="module")
def real_baseline() -> Solution:
    return load_baseline_solution(_REAL_INSTANCE_ID)


# ---------------------------------------------------------------------------
# Routing — every action name resolves to the right implementation


def test_dispatcher_covers_all_seven_actions() -> None:
    """The dispatcher table covers exactly :data:`ACTIONS` — no extras,
    no missing."""
    assert set(_ACTION_IMPLEMENTATIONS.keys()) == set(ACTIONS)


@pytest.mark.parametrize(
    "name,expected_impl",
    [
        ("reuse_direct", reuse_direct),
        ("nearest_neighbor", nearest_neighbor_action),
        ("clarke_wright", clarke_wright_action),
        ("pyvrp_10s", pyvrp_10s),
        ("pyvrp_60s", pyvrp_60s),
        ("pyvrp_60s_seed2", pyvrp_60s_seed2),
        ("pyvrp_60s_seed3", pyvrp_60s_seed3),
    ],
)
def test_dispatcher_routes_correctly(name: str, expected_impl) -> None:
    assert _ACTION_IMPLEMENTATIONS[name] is expected_impl


# ---------------------------------------------------------------------------
# Unknown action


def test_run_action_unknown_name_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown action"):
        run_action("not_a_real_action", None, None)


def test_run_action_unknown_name_lists_valid_actions() -> None:
    """The error message references the seven valid actions so users can
    self-correct."""
    with pytest.raises(ValueError) as excinfo:
        run_action("typo_action", None, None)
    msg = str(excinfo.value)
    # All seven canonical names appear in the message.
    for name in ACTIONS:
        assert name in msg


# ---------------------------------------------------------------------------
# ActionFailure propagation


def test_oversized_demand_returns_infeasible_result_not_raises() -> None:
    """When a customer's demand exceeds capacity, heuristics now return an
    infeasible ActionResult (feasible=False, n_overload>0) rather than raising
    ActionFailure. This keeps the group intact for consolidation.
    """
    coords = np.array([[0.0, 0.0], [10.0, 0.0]], dtype=np.float64)
    demands = np.array([0, 100], dtype=np.int64)
    perturbed = PerturbedInstance(
        instance_id="failure_synth",
        perturbation_id="CAP_4",
        perturbation_family="CAPACITY",
        perturbation_magnitude=0.20,
        n_customers=1,
        coords=coords,
        demands=demands,
        capacity=50,  # less than demand[1]
        n_vehicles=5,
        distance_multiplier_mask=None,
        n_affected_customers=0,
        affected_demand_share=0.0,
        affected_route_share=0.0,
    )
    fake_baseline = Solution(
        instance_id="failure_synth",
        objective=0.0,
        routes=[[1]],
        assignment={1: 0},
        route_costs={0: 0.0},
        customer_costs={1: 0.0},
        runtime_seconds=0.0,
        pyvrp_version="test",
        config=SolveConfig(time_limit_seconds=1.0, seed=1),
    )

    for action_name in ("nearest_neighbor", "clarke_wright"):
        result = run_action(action_name, perturbed, fake_baseline)
        assert result.feasible is False
        assert result.n_overload > 0
        # All customers are served (the oversized one on its own singleton route).
        assert set(result.assignment.keys()) == {1}


# ---------------------------------------------------------------------------
# Each dispatched action returns a valid ActionResult


@requires_real_baseline
@pytest.mark.parametrize(
    "action_name",
    ["reuse_direct", "nearest_neighbor", "clarke_wright", "pyvrp_10s"],
)
def test_run_action_returns_valid_action_result(
    real_instance: Instance, real_baseline: Solution, action_name: str
) -> None:
    """Every fast-path action returns an :class:`ActionResult` with the
    expected ``action`` field. (60s actions are exercised separately;
    they share the same ``_run_pyvrp`` body as pyvrp_10s.)"""
    spec = lookup_perturbation(real_instance.instance_id, "CAP_2")
    perturbed = apply_perturbation(real_instance, spec, real_baseline)

    result = run_action(action_name, perturbed, real_baseline)
    assert isinstance(result, ActionResult)
    assert result.action == action_name
    # Every action's result must satisfy the cost invariant.
    assert result.objective == pytest.approx(
        sum(result.route_costs.values()), abs=1.0
    )
