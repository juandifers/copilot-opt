"""Reuse-direct evaluator: re-evaluate a fixed solution under a perturbation.

Given a baseline ``SolutionArtifact`` S (the PyVRP 60s solution on the
unperturbed instance) and a perturbed ``VRPInstance``, recompute objective
and route loads using the perturbed distance matrix and perturbed demand
without touching the routes themselves. No optimization, no construction,
no local search — pure evaluation.

If a route's load exceeds the perturbed capacity, the artifact is marked
``status="infeasible"`` so downstream consumers can choose how to handle
that case. The objective is still computed (sum of recomputed route
distances) so that the loss for the objective claim family is observable
even when the fixed solution is no longer admissible.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from vrpbench.artifacts.solution import SolutionArtifact
from vrpbench.backends.base import new_run_id
from vrpbench.data.instance import VRPInstance


def _build_distance_matrix(instance: VRPInstance) -> np.ndarray:
    """Build the distance matrix the way the cheap backends do.

    Prefers the explicit ``edge_weight`` field if present (used by
    regional_distance_inflation), otherwise rounds Euclidean distances on
    the coordinates (CVRPLIB EUC_2D convention).
    """
    raw = instance.raw
    if "edge_weight" in raw and raw["edge_weight"] is not None:
        w = np.asarray(raw["edge_weight"], dtype=float)
        if w.ndim == 2 and w.shape[0] == w.shape[1]:
            return w
    coords = np.asarray(raw["node_coord"], dtype=float)
    diff = coords[:, None, :] - coords[None, :, :]
    return np.rint(np.sqrt((diff ** 2).sum(axis=-1))).astype(float)


def evaluate_fixed_solution(
    baseline: SolutionArtifact,
    perturbed_instance: VRPInstance,
    *,
    depot_index: int = 0,
) -> SolutionArtifact:
    """Evaluate ``baseline.routes`` under the perturbed instance.

    Returns a new SolutionArtifact tagged ``backend_name="reuse_direct"``
    with recomputed objective, route distances, and route loads. The
    instance_id, routes, n_routes, and seed are inherited from the
    baseline. Status is ``"ok"`` if every route fits within the perturbed
    capacity, ``"infeasible"`` otherwise. ``"error"`` is reserved for
    structural problems (missing demand, missing distances, etc).
    """
    run_id = new_run_id()
    t0 = time.perf_counter()
    raw = perturbed_instance.raw

    try:
        if "demand" not in raw or raw["demand"] is None:
            raise ValueError("perturbed instance missing demand vector")
        demand = np.asarray(raw["demand"], dtype=float)
        capacity = float(perturbed_instance.capacity)
        dist = _build_distance_matrix(perturbed_instance)

        n_nodes = dist.shape[0]
        if demand.shape[0] != n_nodes:
            raise ValueError(
                f"demand/dist size mismatch: {demand.shape[0]} vs {n_nodes}"
            )

        routes = [list(r) for r in baseline.routes]
        route_distances: list[float] = []
        route_loads: list[float] = []
        max_overload = 0.0
        feasible = True

        for route in routes:
            if not route:
                route_distances.append(0.0)
                route_loads.append(0.0)
                continue
            # Verify customer indices fall within the perturbed-instance
            # node range. Phase 3 only handles perturbations that keep
            # n_customers fixed (capacity_reduction, regional_distance);
            # but guard anyway.
            for c in route:
                if not (0 < c < n_nodes):
                    raise ValueError(
                        f"route customer {c} out of range for perturbed n_nodes={n_nodes}"
                    )
            d = float(dist[depot_index, route[0]])
            for a, b in zip(route[:-1], route[1:]):
                d += float(dist[a, b])
            d += float(dist[route[-1], depot_index])
            load = float(demand[route].sum())
            route_distances.append(d)
            route_loads.append(load)
            if load > capacity + 1e-9:
                feasible = False
                max_overload = max(max_overload, load - capacity)

        objective = float(sum(route_distances))
        status = "ok" if feasible else "infeasible"
        runtime = time.perf_counter() - t0

        return SolutionArtifact(
            instance_id=baseline.instance_id,
            backend_name="reuse_direct",
            status=status,
            objective=objective,
            runtime_sec=runtime,
            n_routes=len(routes),
            routes=routes,
            route_loads=route_loads,
            route_distances=route_distances,
            random_seed=baseline.random_seed,
            time_limit_sec=None,
            solver_params={
                "source_baseline_run_id": baseline.run_id,
                "source_baseline_backend": baseline.backend_name,
                "depot_index": depot_index,
            },
            solver_version="reuse_direct-1.0",
            run_id=run_id,
            metadata={
                "perturbed_capacity": capacity,
                "max_overload": max_overload,
                "feasible_under_perturbation": feasible,
                "perturbed_instance_path": str(perturbed_instance.path),
            },
        )
    except Exception as e:  # pragma: no cover - defensive
        return SolutionArtifact(
            instance_id=baseline.instance_id,
            backend_name="reuse_direct",
            status="error",
            objective=None,
            runtime_sec=time.perf_counter() - t0,
            n_routes=baseline.n_routes,
            routes=[list(r) for r in baseline.routes],
            route_loads=[],
            route_distances=[],
            random_seed=baseline.random_seed,
            time_limit_sec=None,
            solver_params={
                "source_baseline_run_id": baseline.run_id,
                "source_baseline_backend": baseline.backend_name,
            },
            solver_version="reuse_direct-1.0",
            run_id=run_id,
            metadata={
                "error": f"{type(e).__name__}: {e}",
                "feasible_under_perturbation": False,
            },
        )


def answerability(art: SolutionArtifact) -> dict[str, bool]:
    """Per-claim-family answerability flags for a reuse_direct artifact.

    'Answerable' means we can compute the claim error at all. We do NOT
    treat infeasibility as unanswerable for the objective claim — the user
    explicitly defined reuse_direct as fixed-solution evaluation, and the
    objective of the fixed routes is well-defined under the perturbation
    even when capacity is exceeded. Downstream consumers can join with
    ``status`` if they want a stricter "safe to use" criterion.
    """
    return {
        "objective_resource_delta": art.status in ("ok", "infeasible") and art.objective is not None,
        "topk_route_ranking": art.status in ("ok", "infeasible") and bool(art.routes),
        "assignment_structure": art.status in ("ok", "infeasible") and bool(art.routes),
    }
