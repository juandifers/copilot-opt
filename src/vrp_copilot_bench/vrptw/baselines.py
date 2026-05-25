"""VRPTW baseline cache.

A *baseline* for the scale-check is one PyVRP solve at ``seed=1`` and a
fixed time limit on the **unperturbed** instance. The result is cached
to ``data/vrptw_baselines/{instance_id}.json`` so the scale-check (and
any future re-run) only re-solves when something changes.

Cache-hit conditions (all must match):

- ``instance_id``
- ``seed``
- ``time_limit_seconds``
- ``pyvrp_version`` (PyVRP's optimizer changes have observable effects)

The cache stores enough to reconstruct the baseline schedule on demand:
``routes`` plus an ``assignment`` map. The schedule itself is re-derived
on load via :func:`evaluate_vrptw_solution` so we don't have to persist
PyVRP's scaled timing payload (which can be voluminous and version-
sensitive). The objective/n_routes/runtime are stored for reporting.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .instances import DEFAULT_VRPTW_INSTANCE_DIR, load_vrptw_instance
from .solver import (
    EvaluatedVRPTW,
    SolveConfig,
    VRPTWSolveResult,
    evaluate_vrptw_solution,
    solve_vrptw,
)

logger = logging.getLogger(__name__)


try:
    _PYVRP_VERSION: str = version("pyvrp")
except PackageNotFoundError:  # pragma: no cover
    _PYVRP_VERSION = "unknown"


#: Project-relative default baseline cache directory.
DEFAULT_BASELINE_DIR: Path = (
    Path(__file__).resolve().parents[3] / "data" / "vrptw_baselines"
)


@dataclass(frozen=True)
class CachedBaseline:
    """In-memory representation of one cached baseline.

    Carries the original :class:`VRPTWSolveResult` (re-derived from the
    routes on cache hit, populated directly on cache miss) so callers
    have the same API regardless of provenance.

    ``cache_path`` and ``from_cache`` are useful for diagnostic reporting.
    """

    instance_id: str
    seed: int
    time_limit_seconds: float
    pyvrp_version: str
    n_routes: int
    objective: float
    generalized_cost: float
    routes: list[list[int]]
    assignment: dict[int, int]
    runtime_seconds: float
    created_at: str
    solver_config: dict[str, Any] = field(default_factory=dict)
    solve_result: VRPTWSolveResult | None = None  # for in-process use
    cache_path: Path | None = None
    from_cache: bool = False


# ---------------------------------------------------------------------------
# Internals


def _cache_path(instance_id: str, baseline_dir: Path) -> Path:
    return baseline_dir / f"{instance_id}.json"


def _read_cache_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Discarding malformed baseline cache %s: %s", path, exc)
        return None


def _solver_config_dict(time_limit: float, seed: int) -> dict[str, Any]:
    return {
        "time_limit_seconds": float(time_limit),
        "seed": int(seed),
        "stop": "MaxRuntime",
        "collect_stats": False,
    }


def _generalized_cost(distance: float, duration: float | None) -> float:
    """``distance + 0.1 * duration``. ``duration=None`` → just distance."""
    if duration is None:
        return float(distance)
    return float(distance) + 0.1 * float(duration)


def _entry_matches(
    entry: dict[str, Any], *, seed: int, time_limit: float,
) -> bool:
    return (
        int(entry.get("seed", -1)) == int(seed)
        and float(entry.get("time_limit_seconds", -1.0))
        == float(time_limit)
        and str(entry.get("pyvrp_version", "")) == _PYVRP_VERSION
    )


# ---------------------------------------------------------------------------
# Public API


def load_or_compute_baseline(
    instance_id: str,
    *,
    seed: int = 1,
    time_limit_seconds: float = 60.0,
    baseline_dir: Path | None = None,
    instance_dir: Path | None = None,
    force: bool = False,
) -> CachedBaseline:
    """Return a :class:`CachedBaseline` for ``instance_id``.

    Loads from ``{baseline_dir}/{instance_id}.json`` if a matching entry
    exists (and ``force`` is False). Otherwise runs PyVRP via
    :func:`solve_vrptw` and persists the result.

    On cache hit, the ``VRPTWSolveResult`` is reconstructed by
    re-evaluating the stored routes under the unperturbed instance —
    this gives callers the same schedule payload they'd get from a fresh
    solve at negligible cost.
    """
    baseline_dir = baseline_dir or DEFAULT_BASELINE_DIR
    baseline_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path(instance_id, baseline_dir)

    if not force:
        entry = _read_cache_file(cache_path)
        if entry is not None and _entry_matches(
            entry, seed=seed, time_limit=time_limit_seconds,
        ):
            instance = load_vrptw_instance(instance_id, instance_dir)
            routes = [list(map(int, r)) for r in entry["routes"]]
            ev = evaluate_vrptw_solution(instance, routes)
            solve_result = _evaluated_to_solve_result(
                ev, instance_id=instance_id,
                runtime_seconds=float(entry["runtime_seconds"]),
                pyvrp_version=str(entry["pyvrp_version"]),
            )
            return CachedBaseline(
                instance_id=instance_id,
                seed=int(entry["seed"]),
                time_limit_seconds=float(entry["time_limit_seconds"]),
                pyvrp_version=str(entry["pyvrp_version"]),
                n_routes=int(entry["n_routes"]),
                objective=float(entry["objective"]),
                generalized_cost=float(entry["generalized_cost"]),
                routes=routes,
                assignment={int(k): int(v) for k, v in entry["assignment"].items()},
                runtime_seconds=float(entry["runtime_seconds"]),
                created_at=str(entry["created_at"]),
                solver_config=dict(entry.get("solver_config", {})),
                solve_result=solve_result,
                cache_path=cache_path,
                from_cache=True,
            )

    # Cache miss: solve fresh.
    instance = load_vrptw_instance(instance_id, instance_dir)
    config = SolveConfig(time_limit_seconds=time_limit_seconds, seed=seed)
    t0 = time.perf_counter()
    result = solve_vrptw(instance, config)
    elapsed = time.perf_counter() - t0
    if not result.feasible:
        raise RuntimeError(
            f"Baseline solve for {instance_id} returned infeasible plan; "
            "scale-check baselines must be feasible."
        )

    gc = _generalized_cost(result.objective, result.total_duration)
    created_at = _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    entry = {
        "instance_id": instance_id,
        "seed": int(seed),
        "time_limit_seconds": float(time_limit_seconds),
        "pyvrp_version": result.pyvrp_version,
        "n_routes": int(result.n_routes),
        "objective": float(result.objective),
        "generalized_cost": float(gc),
        "routes": [[int(c) for c in r] for r in result.routes],
        "assignment": {str(k): int(v) for k, v in result.assignment.items()},
        "runtime_seconds": float(elapsed),
        "created_at": created_at,
        "solver_config": _solver_config_dict(time_limit_seconds, seed),
    }
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp.write_text(json.dumps(entry, indent=2, sort_keys=True))
    tmp.replace(cache_path)
    logger.info(
        "Wrote baseline cache %s (obj=%.1f, routes=%d, %.1fs)",
        cache_path, result.objective, result.n_routes, elapsed,
    )

    return CachedBaseline(
        instance_id=instance_id,
        seed=int(seed),
        time_limit_seconds=float(time_limit_seconds),
        pyvrp_version=result.pyvrp_version,
        n_routes=int(result.n_routes),
        objective=float(result.objective),
        generalized_cost=float(gc),
        routes=[[int(c) for c in r] for r in result.routes],
        assignment={int(k): int(v) for k, v in result.assignment.items()},
        runtime_seconds=float(elapsed),
        created_at=created_at,
        solver_config=_solver_config_dict(time_limit_seconds, seed),
        solve_result=result,
        cache_path=cache_path,
        from_cache=False,
    )


def _evaluated_to_solve_result(
    ev: EvaluatedVRPTW,
    *,
    instance_id: str,
    runtime_seconds: float,
    pyvrp_version: str,
) -> VRPTWSolveResult:
    """Adapt an :class:`EvaluatedVRPTW` (fixed-route) into a
    :class:`VRPTWSolveResult` so cached baselines have the same payload
    as fresh solves. Routes/assignment/schedule all transfer; route_costs
    is approximated from the route summaries.
    """
    route_costs = {
        rs.route_idx: float(rs.distance) for rs in ev.route_summaries
    }
    return VRPTWSolveResult(
        objective=float(ev.objective),
        feasible=bool(ev.feasible),
        routes=[list(map(int, r)) for r in ev.routes],
        assignment=dict(ev.assignment),
        route_costs=route_costs,
        runtime_seconds=float(runtime_seconds),
        pyvrp_version=str(pyvrp_version),
        n_routes=len(ev.routes),
        total_duration=float(ev.total_duration),
        route_summaries=list(ev.route_summaries),
        per_customer_schedule=dict(ev.per_customer_schedule),
    )


__all__ = [
    "CachedBaseline",
    "DEFAULT_BASELINE_DIR",
    "load_or_compute_baseline",
]
