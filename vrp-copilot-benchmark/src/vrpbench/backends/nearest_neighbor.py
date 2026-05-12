"""Cheap backend: capacity-feasible nearest-neighbor construction.

Deterministic, no tunable parameters. Useful as a lower-quality reference
to exercise structural-disagreement gating against PyVRP.
"""
from __future__ import annotations

import time

import numpy as np

from ..artifacts.solution import SolutionArtifact
from ..data.instance import VRPInstance
from .base import new_run_id


def _euclidean_matrix(coords: np.ndarray) -> np.ndarray:
    diff = coords[:, None, :] - coords[None, :, :]
    # CVRPLIB EUC_2D convention: round distances to nearest integer.
    return np.rint(np.sqrt((diff ** 2).sum(axis=-1))).astype(float)


def _build_distance_matrix(instance: VRPInstance) -> np.ndarray:
    raw = instance.raw
    if "edge_weight" in raw and raw["edge_weight"] is not None:
        w = np.asarray(raw["edge_weight"], dtype=float)
        if w.ndim == 2 and w.shape[0] == w.shape[1]:
            return w
    coords = np.asarray(raw["node_coord"], dtype=float)
    return _euclidean_matrix(coords)


def solve_nearest_neighbor(
    instance: VRPInstance,
    *,
    depot_index: int = 0,
) -> SolutionArtifact:
    run_id = new_run_id()
    t0 = time.perf_counter()

    try:
        dist = _build_distance_matrix(instance)
        demand = np.asarray(instance.raw["demand"], dtype=float)
        capacity = float(instance.capacity)
        n_nodes = dist.shape[0]

        unvisited = set(range(n_nodes)) - {depot_index}
        routes: list[list[int]] = []
        route_loads: list[float] = []
        route_distances: list[float] = []

        while unvisited:
            current = depot_index
            load = 0.0
            distance = 0.0
            route: list[int] = []
            while True:
                candidates = [c for c in unvisited if load + demand[c] <= capacity]
                if not candidates:
                    break
                nxt = min(candidates, key=lambda c: dist[current, c])
                route.append(nxt)
                load += demand[nxt]
                distance += float(dist[current, nxt])
                unvisited.discard(nxt)
                current = nxt
            if not route:
                # A customer demand exceeds vehicle capacity - cannot serve.
                raise ValueError(
                    f"No feasible next customer; remaining demand may exceed capacity "
                    f"(capacity={capacity})."
                )
            distance += float(dist[current, depot_index])
            routes.append(route)
            route_loads.append(load)
            route_distances.append(distance)

        objective = float(sum(route_distances))
        runtime = time.perf_counter() - t0

        return SolutionArtifact(
            instance_id=instance.instance_id,
            backend_name="nearest_neighbor",
            status="ok",
            objective=objective,
            runtime_sec=runtime,
            n_routes=len(routes),
            routes=routes,
            route_loads=route_loads,
            route_distances=route_distances,
            random_seed=None,
            time_limit_sec=None,
            solver_params={},
            solver_version="nn-1.0",
            run_id=run_id,
            metadata={"depot_index": depot_index},
        )
    except Exception as e:
        return SolutionArtifact(
            instance_id=instance.instance_id,
            backend_name="nearest_neighbor",
            status="error",
            objective=None,
            runtime_sec=time.perf_counter() - t0,
            n_routes=None,
            routes=[],
            route_loads=[],
            route_distances=[],
            random_seed=None,
            time_limit_sec=None,
            solver_params={},
            solver_version="nn-1.0",
            run_id=run_id,
            metadata={"error": str(e)},
        )
