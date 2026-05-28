"""Strong backend: PyVRP with fixed seed and time limit.

Reproducibility fields (seed, time_limit_sec, solver_version) are always
recorded on the returned SolutionArtifact, as required by the Phase 1
protocol. PyVRP is stochastic; any claim drawn from these artifacts must
be interpreted in the light of (seed, time_limit).
"""
from __future__ import annotations

import importlib.metadata
import time
from pathlib import Path

import numpy as np
import pyvrp
from pyvrp import read as pyvrp_read, solve as pyvrp_solve
from pyvrp.stop import MaxRuntime

from ..artifacts.solution import SolutionArtifact
from ..data.instance import VRPInstance
from .base import new_run_id


def _pyvrp_version() -> str:
    try:
        return importlib.metadata.version("pyvrp")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def solve_pyvrp(
    instance: VRPInstance,
    *,
    seed: int = 1,
    time_limit_sec: float = 60.0,
    round_func: str = "round",
    instance_path_override: Path | None = None,
) -> SolutionArtifact:
    """Run PyVRP on an instance.

    Parameters
    ----------
    instance
        The VRPInstance. Its ``path`` points at an on-disk .vrp that PyVRP
        will re-read (PyVRP uses its own parser).
    seed
        Random seed; must be recorded for reproducibility.
    time_limit_sec
        Wall-clock stopping budget.
    round_func
        PyVRP rounding mode for distances. CVRPLIB X instances use EUC_2D
        with nearest-integer distances, so ``"round"`` is the standard.
    instance_path_override
        For perturbation runs: a different .vrp file path is passed in, and
        the artifact is still tagged with the base ``instance.instance_id``.
    """
    run_id = new_run_id()
    path = Path(instance_path_override) if instance_path_override else instance.path
    t0 = time.perf_counter()

    try:
        data = pyvrp_read(str(path), round_func=round_func)
        result = pyvrp_solve(data, stop=MaxRuntime(time_limit_sec), seed=seed, display=False)
        best = result.best

        # Extract routes as lists of 1-indexed customer ids (CVRPLIB convention).
        # PyVRP routes use Client objects; .visits() returns 0-indexed client idx
        # where 0 is the depot client in the internal indexing. We convert to
        # the CVRPLIB 1-indexed customer ids.
        routes: list[list[int]] = []
        route_loads: list[float] = []
        route_distances: list[float] = []
        for route in best.routes():
            visits = list(route.visits())
            if not visits:
                continue
            # In PyVRP's ProblemData read from CVRPLIB, clients are indexed
            # starting at the first non-depot client. We need to map back to
            # CVRPLIB 1..n. CVRPLIB depots are index 0, so the PyVRP client
            # index i corresponds to CVRPLIB customer (i+1) when there's a
            # single depot at index 0. PyVRP's visits() returns locations
            # relative to the problem data; for single-depot CVRP the mapping
            # is client_i_in_pyvrp -> cvrplib_customer = i - num_depots + 1.
            num_depots = data.num_depots
            cust_route = [int(v) - num_depots + 1 for v in visits]
            routes.append(cust_route)
            route_loads.append(float(route.delivery()[0]) if route.delivery() else 0.0)
            route_distances.append(float(route.distance()))

        status = "ok" if best.is_feasible() else "infeasible"
        objective = float(best.distance_cost())
        runtime = time.perf_counter() - t0

        return SolutionArtifact(
            instance_id=instance.instance_id,
            backend_name="pyvrp",
            status=status,
            objective=objective,
            runtime_sec=runtime,
            n_routes=best.num_routes(),
            routes=routes,
            route_loads=route_loads,
            route_distances=route_distances,
            random_seed=seed,
            time_limit_sec=time_limit_sec,
            solver_params={"round_func": round_func, "stop": f"MaxRuntime({time_limit_sec})"},
            solver_version=f"pyvrp-{_pyvrp_version()}",
            run_id=run_id,
            metadata={
                "is_feasible": best.is_feasible(),
                "num_clients": best.num_clients(),
                "num_iterations": result.num_iterations,
                "pyvrp_runtime": float(result.runtime),
                "instance_path": str(path),
            },
        )
    except Exception as e:
        return SolutionArtifact(
            instance_id=instance.instance_id,
            backend_name="pyvrp",
            status="error",
            objective=None,
            runtime_sec=time.perf_counter() - t0,
            n_routes=None,
            routes=[],
            route_loads=[],
            route_distances=[],
            random_seed=seed,
            time_limit_sec=time_limit_sec,
            solver_params={"round_func": round_func},
            solver_version=f"pyvrp-{_pyvrp_version()}",
            run_id=run_id,
            metadata={"error": f"{type(e).__name__}: {e}", "instance_path": str(path)},
        )
