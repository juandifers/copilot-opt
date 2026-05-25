"""Shared helpers for the VRPTW perturbation families.

These mirror the CVRP-side ``perturbations/families/_common.py`` helpers
but live separately so the pilot package has zero coupling to the
preregistered code.

All helpers operate on a baseline ``VRPTWSolveResult`` — the seed=1 60s
PyVRP solve on the *unperturbed* instance. The result must carry
``route_summaries`` and ``per_customer_schedule`` (populated by the
augmented :func:`solve_vrptw`).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ...solvers.pyvrp_vrptw_wrapper import VRPTWSolveResult


# ---------------------------------------------------------------------------
# Baseline-derived route selectors


def _routes_by(baseline: "VRPTWSolveResult", key_name: str) -> list[tuple[int, float]]:
    """Return ``[(route_idx, value), ...]`` from ``route_summaries`` for ``key_name``."""
    out: list[tuple[int, float]] = []
    for rs in baseline.route_summaries:
        out.append((rs.route_idx, float(getattr(rs, key_name))))
    return out


def pick_route_argmax(baseline: "VRPTWSolveResult", key_name: str) -> int:
    """Route index with the maximum value of ``key_name``; ties → lowest idx."""
    pairs = _routes_by(baseline, key_name)
    if not pairs:
        raise ValueError("baseline has no routes")
    best_v, best_i = pairs[0][1], pairs[0][0]
    for idx, v in pairs[1:]:
        if v > best_v or (v == best_v and idx < best_i):
            best_v, best_i = v, idx
    return best_i


def pick_route_argmin(baseline: "VRPTWSolveResult", key_name: str) -> int:
    pairs = _routes_by(baseline, key_name)
    if not pairs:
        raise ValueError("baseline has no routes")
    best_v, best_i = pairs[0][1], pairs[0][0]
    for idx, v in pairs[1:]:
        if v < best_v or (v == best_v and idx < best_i):
            best_v, best_i = v, idx
    return best_i


def route_customers(baseline: "VRPTWSolveResult", route_idx: int) -> list[int]:
    """Customer-ID list for the given baseline route, in visit order."""
    return list(baseline.routes[route_idx])


# ---------------------------------------------------------------------------
# Geometric selectors


def _depot_distances(coords: np.ndarray) -> np.ndarray:
    """Euclidean distance from depot (row 0) to each customer. Shape (n,)."""
    return np.sqrt(((coords[1:] - coords[0]) ** 2).sum(axis=1))


def _knn_spread(coords: np.ndarray, k: int = 5) -> np.ndarray:
    """Mean distance to k nearest *customer* neighbors, per customer. Shape (n,).

    Smaller values = locally dense. The depot is excluded from the
    neighbor pool. Self-distances masked to +inf before sorting.
    """
    cc = coords[1:]
    n = cc.shape[0]
    if n < k + 1:
        raise ValueError(f"need n >= k+1, got n={n}, k={k}")
    diff = cc[:, None, :] - cc[None, :, :]
    dists = np.sqrt((diff ** 2).sum(axis=2))
    np.fill_diagonal(dists, np.inf)
    sorted_dists = np.sort(dists, axis=1)
    return sorted_dists[:, :k].mean(axis=1)


def densest_quartile_customers(coords: np.ndarray, k: int = 5) -> list[int]:
    """``ceil(n/4)`` customers with the smallest k-NN spread (most-dense)."""
    n = coords.shape[0] - 1
    spread = _knn_spread(coords, k=k)
    ordered = sorted(range(1, n + 1), key=lambda c: (spread[c - 1], c))
    cut = math.ceil(n / 4)
    return sorted(ordered[:cut])


def farthest_quartile_customers(coords: np.ndarray) -> list[int]:
    """``ceil(n/4)`` customers farthest from the depot."""
    n = coords.shape[0] - 1
    d2d = _depot_distances(coords)
    ordered = sorted(range(1, n + 1), key=lambda c: (-d2d[c - 1], c))
    cut = math.ceil(n / 4)
    return sorted(ordered[:cut])


def top_demand_quartile(demands: np.ndarray) -> list[int]:
    """``ceil(n/4)`` customers with the largest demand."""
    n = demands.shape[0] - 1
    ordered = sorted(range(1, n + 1), key=lambda c: (-int(demands[c]), c))
    cut = math.ceil(n / 4)
    return sorted(ordered[:cut])


# ---------------------------------------------------------------------------
# Position-in-route helpers


def customers_in_route_segment(
    baseline: "VRPTWSolveResult", *, segment: str,
) -> list[int]:
    """All customers occupying ``segment`` of each baseline route.

    ``segment in {'first_third', 'final_third'}``. For very short routes
    (n < 3) the segment is a single customer, picked so both segments
    remain non-empty.
    """
    if segment not in ("first_third", "final_third"):
        raise ValueError(f"unknown segment {segment!r}")
    out: list[int] = []
    for route in baseline.routes:
        n = len(route)
        if n == 0:
            continue
        if n <= 2:
            if segment == "first_third":
                out.append(route[0])
            else:
                out.append(route[-1])
            continue
        cut = max(1, n // 3)
        if segment == "first_third":
            out.extend(route[:cut])
        else:
            out.extend(route[n - cut:])
    return sorted(set(out))


# ---------------------------------------------------------------------------
# Diagnostics


def compute_affected_diagnostics(
    instance, baseline: "VRPTWSolveResult", affected: list[int],
) -> tuple[int, float, float, tuple[int, ...]]:
    """Return ``(n_affected, demand_share, route_share, affected_routes)``.

    ``demand_share`` is over the **original** total demand;
    ``route_share`` is the fraction of baseline routes touched by at least
    one affected customer.
    """
    if not affected:
        return 0, 0.0, 0.0, ()
    affected_set = set(affected)
    total_demand = int(instance.demands[1:].sum())
    aff_demand = int(sum(int(instance.demands[c]) for c in affected))
    demand_share = aff_demand / total_demand if total_demand else 0.0
    n_routes = len(baseline.routes)
    touched = sorted(
        idx for idx, r in enumerate(baseline.routes)
        if any(c in affected_set for c in r)
    )
    route_share = len(touched) / n_routes if n_routes else 0.0
    return len(affected), demand_share, route_share, tuple(touched)


# ---------------------------------------------------------------------------
# Time-window clipping


def clip_window(
    tw_early: int, tw_late: int, depot_open: int, depot_close: int,
) -> tuple[int, int]:
    """Clip a window to ``[depot_open, depot_close]`` ensuring ``early < late``.

    If clipping would collapse the window, return a 1-unit window centered
    as close as possible to the original midpoint.
    """
    early = max(int(tw_early), int(depot_open))
    late = min(int(tw_late), int(depot_close))
    if early >= late:
        # Center 1-unit window at the original midpoint, clipped.
        mid = max(depot_open, min(depot_close - 1, (tw_early + tw_late) // 2))
        early = mid
        late = mid + 1
    return early, late
