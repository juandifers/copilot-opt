"""Baseline solution dataclass and loader.

The baseline solution S for each Stage A instance is the result of running
PyVRP 60s seed=1 on the unperturbed instance (prereg §7's ``reuse_direct``
specifies S as "the baseline solution computed once per instance before
any perturbation"; §8.1 places PyVRP 60s seed=1 as the reference protocol).

A :class:`Solution` is the *cached* form of that result. It carries less
information than :class:`vrp_copilot_bench.actions.ActionResult` because:

- feasibility is True by construction (PyVRP doesn't return infeasible
  plans on standard CVRP at 60 s),
- ``n_overload`` and ``max_overload_fraction`` are zero by construction,
- there is no notion of a perturbation under which the plan is evaluated.

Distinct from ``ActionResult``: a Solution always corresponds to an
unperturbed PyVRP 60s seed=1 solve. Action wrappers (Item 5) produce
``ActionResult`` for the perturbed-instance case.

The cache is a JSON file per instance at ``data/baselines/<instance_id>.json``.
Use :func:`load_baseline_solution` to read; :mod:`scripts.compute_baselines`
to populate.

Stability note: PyVRP under wall-clock-bounded ``MaxRuntime`` is noise-bounded
to within ~2 % objective drift across runs (per prereg §8.2's
``reference_obj_unstable`` threshold). Cached Solutions are canonical artifacts
once written; recomputing with ``--force`` produces a different (within-band)
baseline and would invalidate any downstream artifacts that referenced the
prior cache. Do not re-run ``compute_baselines.py --force`` casually.
"""
from __future__ import annotations

import functools
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .solvers.pyvrp_wrapper import SolveConfig, SolveResult

logger = logging.getLogger(__name__)


#: Default directory for cached baseline solutions.
DEFAULT_BASELINE_DIR: Path = Path("data/baselines")


class BaselineNotFound(FileNotFoundError):
    """Raised when a requested instance has no cached baseline solution."""


@dataclass(frozen=True)
class Solution:
    """Cached baseline solution on an unperturbed instance.

    Fields parallel :class:`SolveResult` minus the per-action fields that
    only exist relative to a perturbation (``feasible`` is True by
    construction; ``n_overload`` and ``max_overload_fraction`` are zero).
    """

    instance_id: str
    objective: float
    routes: list[list[int]]
    assignment: dict[int, int]
    route_costs: dict[int, float]
    customer_costs: dict[int, float]
    runtime_seconds: float
    pyvrp_version: str
    config: SolveConfig

    # ----- JSON serialization -----
    # Convention matches ActionResult: int-keyed dicts are stringified at
    # write because JSON object keys are always strings; the loader coerces
    # back to int.

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "objective": float(self.objective),
            "routes": [list(int(c) for c in r) for r in self.routes],
            "assignment": {str(int(k)): int(v) for k, v in self.assignment.items()},
            "route_costs": {str(int(k)): float(v) for k, v in self.route_costs.items()},
            "customer_costs": {str(int(k)): float(v) for k, v in self.customer_costs.items()},
            "runtime_seconds": float(self.runtime_seconds),
            "pyvrp_version": self.pyvrp_version,
            "config": self.config.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Solution":
        return cls(
            instance_id=data["instance_id"],
            objective=float(data["objective"]),
            routes=[list(int(c) for c in r) for r in data["routes"]],
            assignment={int(k): int(v) for k, v in data["assignment"].items()},
            route_costs={int(k): float(v) for k, v in data["route_costs"].items()},
            customer_costs={int(k): float(v) for k, v in data["customer_costs"].items()},
            runtime_seconds=float(data["runtime_seconds"]),
            pyvrp_version=data["pyvrp_version"],
            config=SolveConfig.from_dict(data["config"]),
        )

    @classmethod
    def from_solve_result(
        cls, instance_id: str, result: SolveResult, config: SolveConfig
    ) -> "Solution":
        """Build a Solution from a freshly-computed :class:`SolveResult`."""
        return cls(
            instance_id=instance_id,
            objective=result.objective,
            routes=[list(r) for r in result.routes],
            assignment=dict(result.assignment),
            route_costs=dict(result.route_costs),
            customer_costs=dict(result.customer_costs),
            runtime_seconds=result.runtime_seconds,
            pyvrp_version=result.pyvrp_version,
            config=config,
        )


# ---------------------------------------------------------------------------
# Loader


def baseline_path(instance_id: str, baseline_dir: Path = DEFAULT_BASELINE_DIR) -> Path:
    """Canonical cache path for an instance's baseline."""
    return baseline_dir / f"{instance_id}.json"


@functools.lru_cache(maxsize=128)
def load_baseline_solution(
    instance_id: str, baseline_dir: Path = DEFAULT_BASELINE_DIR
) -> Solution:
    """Load the cached baseline solution for ``instance_id``.

    LRU-cached (Phase C): the runner runs 16 perturbations against each
    instance, plus optionally two audit-seed variants — that's up to 18
    action invocations per instance, every one of which calls this loader
    to fetch the same baseline. The cache turns 18 disk reads into one.
    Cache keying is by ``(instance_id, baseline_dir)``; the default path
    is the common case.

    Cache scope is **per-process**. ``joblib`` / ``loky`` workers run in
    separate Python processes and each have their own cache; the cache
    is not shared across workers. That is fine — workers also process
    blocks of keys from the same instance (the runner sorts small-first
    within each phase), so within-worker reuse already covers the
    important amortisation. To clear the cache (rarely useful in tests
    that monkey-patch the cache path), call
    ``load_baseline_solution.cache_clear()``.

    Raises
    ------
    BaselineNotFound
        If no cached file exists. The message points to
        ``scripts/compute_baselines.py``.
    """
    path = baseline_path(instance_id, baseline_dir)
    if not path.exists():
        raise BaselineNotFound(
            f"baseline cache missing for {instance_id!r}: {path}. "
            f"Run scripts/compute_baselines.py to populate it."
        )
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    sol = Solution.from_dict(data)
    if sol.instance_id != instance_id:
        raise ValueError(
            f"cache file at {path} reports instance_id {sol.instance_id!r}, "
            f"expected {instance_id!r}"
        )
    return sol
