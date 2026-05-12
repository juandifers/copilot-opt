"""Cheap backend: Clarke-Wright parallel savings algorithm.

Deterministic. Uses the same distance matrix / EUC_2D conventions as the
nearest-neighbor backend so that scenario outputs are directly comparable.
Produces the same SolutionArtifact schema as every other backend.

The savings backend is stronger than nearest-neighbor on most CVRP
instances while still being orders of magnitude cheaper than PyVRP, which
is exactly what Phase 2 needs: a middle tier between the two extremes so
that "cheap vs strong" stops being a two-value signal and becomes a
graded one.
"""
from __future__ import annotations

import time

import numpy as np

from ..artifacts.solution import SolutionArtifact
from ..data.instance import VRPInstance
from .base import new_run_id


def _euclidean_matrix(coords: np.ndarray) -> np.ndarray:
    diff = coords[:, None, :] - coords[None, :, :]
    return np.rint(np.sqrt((diff ** 2).sum(axis=-1))).astype(float)


def _build_distance_matrix(instance: VRPInstance) -> np.ndarray:
    raw = instance.raw
    if "edge_weight" in raw and raw["edge_weight"] is not None:
        w = np.asarray(raw["edge_weight"], dtype=float)
        if w.ndim == 2 and w.shape[0] == w.shape[1]:
            return w
    coords = np.asarray(raw["node_coord"], dtype=float)
    return _euclidean_matrix(coords)


def _route_distance(route: list[int], dist: np.ndarray, depot: int) -> float:
    if not route:
        return 0.0
    total = float(dist[depot, route[0]])
    for a, b in zip(route, route[1:]):
        total += float(dist[a, b])
    total += float(dist[route[-1], depot])
    return total


def solve_savings(
    instance: VRPInstance,
    *,
    depot_index: int = 0,
) -> SolutionArtifact:
    """Clarke-Wright parallel savings construction.

    Deterministic ordering:
      - savings are sorted by (-saving, i, j) so ties resolve to the
        lexicographically smaller pair.
    """
    run_id = new_run_id()
    t0 = time.perf_counter()

    try:
        dist = _build_distance_matrix(instance)
        demand = np.asarray(instance.raw["demand"], dtype=float)
        capacity = float(instance.capacity)
        n_nodes = dist.shape[0]
        customers = [c for c in range(n_nodes) if c != depot_index]

        if any(demand[c] > capacity for c in customers):
            raise ValueError(
                "At least one customer demand exceeds vehicle capacity; "
                "savings construction cannot be feasible."
            )

        # Initialise: one route per customer.
        route_of: dict[int, int] = {c: i for i, c in enumerate(customers)}
        routes: list[list[int]] = [[c] for c in customers]
        loads: list[float] = [float(demand[c]) for c in customers]

        # Precompute savings for all i < j.
        saving_entries: list[tuple[float, int, int]] = []
        for idx_i, i in enumerate(customers):
            d0i = float(dist[depot_index, i])
            for j in customers[idx_i + 1:]:
                s = d0i + float(dist[depot_index, j]) - float(dist[i, j])
                if s > 0.0:
                    saving_entries.append((s, i, j))

        # Sort by decreasing savings; deterministic tiebreak on (i, j).
        saving_entries.sort(key=lambda t: (-t[0], t[1], t[2]))

        def _endpoints(r_idx: int) -> tuple[int, int]:
            r = routes[r_idx]
            return r[0], r[-1]

        for _, i, j in saving_entries:
            ri = route_of[i]
            rj = route_of[j]
            if ri == rj:
                continue
            # Merge is legal if the two customers lie at route endpoints.
            first_i, last_i = _endpoints(ri)
            first_j, last_j = _endpoints(rj)
            new_load = loads[ri] + loads[rj]
            if new_load > capacity:
                continue

            if last_i == i and first_j == j:
                merged = routes[ri] + routes[rj]
            elif last_j == j and first_i == i:
                merged = routes[rj] + routes[ri]
            elif last_i == i and last_j == j:
                merged = routes[ri] + list(reversed(routes[rj]))
            elif first_i == i and first_j == j:
                merged = list(reversed(routes[ri])) + routes[rj]
            else:
                continue

            # Commit merge: reuse ri slot, blank rj.
            routes[ri] = merged
            loads[ri] = new_load
            for c in merged:
                route_of[c] = ri
            routes[rj] = []
            loads[rj] = 0.0

        final_routes = [r for r in routes if r]
        final_loads = [float(sum(demand[c] for c in r)) for r in final_routes]
        final_distances = [_route_distance(r, dist, depot_index) for r in final_routes]
        objective = float(sum(final_distances))
        runtime = time.perf_counter() - t0

        return SolutionArtifact(
            instance_id=instance.instance_id,
            backend_name="savings",
            status="ok",
            objective=objective,
            runtime_sec=runtime,
            n_routes=len(final_routes),
            routes=final_routes,
            route_loads=final_loads,
            route_distances=final_distances,
            random_seed=None,
            time_limit_sec=None,
            solver_params={},
            solver_version="cw-savings-1.0",
            run_id=run_id,
            metadata={"depot_index": depot_index},
        )
    except Exception as e:
        return SolutionArtifact(
            instance_id=instance.instance_id,
            backend_name="savings",
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
            solver_version="cw-savings-1.0",
            run_id=run_id,
            metadata={"error": str(e)},
        )
