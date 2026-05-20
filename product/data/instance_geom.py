"""VRPTW instance geometry for the product visual layer.

Loads Solomon / Homberger coordinates via the existing
`vrp_copilot_bench.vrptw_instances.load_vrptw_instance` parser and projects
them into a frontend-friendly JSON shape. Also assembles route polylines
from an augmented Run-1 payload.

Pure read-only: no model calls, no solver re-runs, no writes to the
underlying ``.vrp`` files.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

# The visual layer reuses the canonical loader from ``src/vrp_copilot_bench``.
# ``uvicorn product.api.main:app`` is normally launched from the repo root
# without that path on PYTHONPATH, so we ensure it lazily here.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Solomon (100-customer) instances live flat in ``data/vrptw_instances``;
# Homberger (200-customer) instances live in the ``homberger200`` subdir.
_SOLOMON_DIR = _REPO_ROOT / "data" / "vrptw_instances"
_HOMBERGER_DIR = _SOLOMON_DIR / "homberger200"


_COORD_NOTE = (
    "Coordinates are Solomon/Homberger synthetic Euclidean coordinates, "
    "not geographic lat/lon."
)


def _resolve_instance_dir(instance_id: str) -> Path:
    """Return the directory that contains ``<instance_id>.vrp``.

    Heuristic: Homberger 200-customer ids contain a ``_2_`` pattern
    (e.g. ``C1_2_1``, ``RC2_2_2``). Solomon 100-customer ids do not.
    Falls back to scanning both locations if the heuristic misses.
    """
    candidate = _SOLOMON_DIR / f"{instance_id}.vrp"
    if candidate.exists():
        return _SOLOMON_DIR
    candidate = _HOMBERGER_DIR / f"{instance_id}.vrp"
    if candidate.exists():
        return _HOMBERGER_DIR
    raise FileNotFoundError(
        f"VRPTW instance file not found for {instance_id!r} in "
        f"{_SOLOMON_DIR} or {_HOMBERGER_DIR}."
    )


def load_instance_geometry(instance_id: str) -> dict:
    """Load coordinates + per-customer metadata for a Run-1 instance.

    Returns a JSON-serialisable dict; ``depot`` is at customer_id 0 by
    convention (matches the project's instance indexing).
    """
    # Local import keeps the module importable even if vrplib is missing
    # — only fails when geometry is actually requested.
    from vrp_copilot_bench.vrptw_instances import load_vrptw_instance

    inst_dir = _resolve_instance_dir(instance_id)
    inst = load_vrptw_instance(instance_id, instance_dir=inst_dir)

    coords = inst.coords
    demands = inst.demands
    svc = inst.service_times
    tw = inst.time_windows

    def _row(idx: int) -> dict:
        return {
            "customer_id": int(idx),
            "x": float(coords[idx, 0]),
            "y": float(coords[idx, 1]),
            "demand": int(demands[idx]),
            "service_time": int(svc[idx]),
            "tw_early": int(tw[idx, 0]),
            "tw_late": int(tw[idx, 1]),
        }

    depot = _row(inst.depot_index)
    customers = [_row(i) for i in range(coords.shape[0]) if i != inst.depot_index]

    return {
        "instance_id": instance_id,
        "n_customers": int(inst.n_customers),
        "capacity": int(inst.capacity),
        "n_vehicles": int(inst.n_vehicles),
        "depot": depot,
        "customers": customers,
        "coordinate_system": "euclidean_synthetic",
        "notes": _COORD_NOTE,
    }


def geometry_lookup(geometry: dict) -> dict[int, dict]:
    """Map ``customer_id → customer geometry``, including the depot."""
    lookup: dict[int, dict] = {}
    depot = geometry.get("depot")
    if isinstance(depot, dict) and "customer_id" in depot:
        lookup[int(depot["customer_id"])] = depot
    for c in geometry.get("customers", []) or []:
        if isinstance(c, dict) and "customer_id" in c:
            lookup[int(c["customer_id"])] = c
    return lookup


def _routes_from_payload(payload: dict) -> list[dict]:
    """Return the route list to draw polylines for.

    Prefer ``payload.routes`` (STRUCT family). For SCHEDULE-only payloads,
    fall back to grouping ``customer_schedule`` by ``route_idx``, ordered
    by ``start_service`` (or ``arrival`` if start is missing).
    """
    routes = payload.get("routes")
    if isinstance(routes, list) and routes:
        return [r for r in routes if isinstance(r, dict)]

    schedule = payload.get("customer_schedule")
    if not isinstance(schedule, list) or not schedule:
        return []

    by_route: dict[int, list[dict]] = {}
    for row in schedule:
        if not isinstance(row, dict):
            continue
        idx = row.get("route_idx")
        if idx is None:
            continue
        try:
            idx_i = int(idx)
        except (TypeError, ValueError):
            continue
        by_route.setdefault(idx_i, []).append(row)

    synthesised: list[dict] = []
    for idx_i in sorted(by_route):
        rows = sorted(
            by_route[idx_i],
            key=lambda r: (
                r.get("start_service") if r.get("start_service") is not None
                else r.get("arrival") if r.get("arrival") is not None
                else 0
            ),
        )
        first = rows[0]
        synthesised.append(
            {
                "route_idx": idx_i,
                "display_route_number": first.get("display_route_number"),
                "route_label": first.get("route_label"),
                "customer_ids": [int(r["customer_id"]) for r in rows if r.get("customer_id") is not None],
            }
        )
    return synthesised


def build_route_polylines(
    payload_augmented: Optional[dict],
    geometry: Optional[dict],
) -> tuple[list[dict], list[str]]:
    """Assemble route polylines from an augmented payload + instance geometry.

    Returns ``(polylines, warnings)``. Warnings list customer IDs the
    geometry could not resolve so the caller can surface them to the UI
    instead of crashing.
    """
    warnings: list[str] = []
    if not payload_augmented or not geometry:
        return [], warnings

    routes = _routes_from_payload(payload_augmented)
    if not routes:
        return [], warnings

    lookup = geometry_lookup(geometry)
    depot = geometry.get("depot") or {}
    depot_id = int(depot.get("customer_id", 0))
    depot_x = float(depot.get("x", 0.0))
    depot_y = float(depot.get("y", 0.0))

    polylines: list[dict] = []
    for r in routes:
        try:
            route_idx = int(r.get("route_idx"))
        except (TypeError, ValueError):
            continue
        customer_ids = r.get("customer_ids") or []
        try:
            ids = [int(c) for c in customer_ids]
        except (TypeError, ValueError):
            ids = []

        points: list[dict] = [
            {"customer_id": depot_id, "x": depot_x, "y": depot_y, "kind": "depot"}
        ]
        for cid in ids:
            geom = lookup.get(cid)
            if geom is None:
                warnings.append(
                    f"customer_id={cid} on route_idx={route_idx} missing from "
                    f"instance geometry"
                )
                continue
            points.append(
                {
                    "customer_id": cid,
                    "x": float(geom["x"]),
                    "y": float(geom["y"]),
                    "kind": "customer",
                }
            )
        points.append(
            {"customer_id": depot_id, "x": depot_x, "y": depot_y, "kind": "depot"}
        )

        polylines.append(
            {
                "route_idx": route_idx,
                "route_label": r.get("route_label"),
                "display_route_number": r.get("display_route_number"),
                "customer_ids": ids,
                "points": points,
                "n_customers": len(ids),
            }
        )
    return polylines, warnings


__all__ = [
    "load_instance_geometry",
    "geometry_lookup",
    "build_route_polylines",
]
