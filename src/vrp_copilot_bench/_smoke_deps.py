"""Module-level fake runner dependencies for the loky-backed smoke test.

The runner imports its dependencies (``run_action``, ``load_instance``, etc.)
at module load time. Loky workers spawn fresh subprocesses that import the
runner module from scratch, so monkeypatching from a parent process does
not propagate to workers.

To exercise the loky backend end-to-end without real solver wrappers, the
runner consults the environment variable ``VRP_COPILOT_BENCH_USE_SMOKE_DEPS``
*at module load time*. When set to ``"1"``, the runner replaces its dep
imports with the module-level functions defined here. The env var
naturally inherits into loky subprocesses, so the workers' fresh import
of the runner picks up the same fakes.

Production never sets this env var. Tests use it only for the loky smoke
test in :mod:`tests.test_cli`.
"""
from __future__ import annotations

from typing import Any

from .actions import ActionResult


def load_instance(instance_id: str) -> Any:
    return {"id": instance_id, "kind": "instance"}


def load_baseline_solution(instance_id: str) -> Any:
    return {"id": instance_id, "kind": "baseline"}


def lookup_perturbation(instance_id: str, perturbation_id: str) -> Any:
    return {"id": perturbation_id, "kind": "spec"}


def apply_perturbation(instance: Any, spec: Any, baseline: Any | None = None) -> Any:
    return {"perturbed_from": instance, "spec": spec, "baseline": baseline}


def run_action(action_name: str, perturbed: Any, baseline: Any) -> ActionResult:
    """Deterministic synthetic ActionResult."""
    return ActionResult(
        action=action_name,
        objective=1000.0,
        feasible=True,
        runtime_seconds=0.01,
        n_overload=0,
        max_overload_fraction=0.0,
        assignment={1: 0, 2: 0, 3: 1, 4: 1},
        route_costs={0: 600.0, 1: 400.0},
        customer_costs={1: 100.0, 2: 110.0, 3: 95.0, 4: 105.0},
        meta={"smoke": True},
    )
