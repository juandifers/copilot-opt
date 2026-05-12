"""DISTANCE perturbation family (prereg §6.2).

Multiplies distances within a selected region by 2.0. Specifically:

- depot↔customer distances for customers in the region are scaled by 2.0
- customer↔customer distances for pairs *both* in the region are scaled by 2.0
- all other distances are unchanged

The 2.0 factor is fixed across DIST_1..DIST_4; the four perturbations
differ in which region is selected:

- DIST_1: 1/4 of customers farthest from depot, low local density (k-NN spread > median)
- DIST_2: 1/4 of customers farthest from depot, high local density (k-NN spread <= median)
- DIST_3: 1/4 of customers closest to depot
- DIST_4: all customers in the highest-cost baseline route

The output ``PerturbedInstance`` carries a ``distance_multiplier_mask``
of shape ``(n_customers + 1, n_customers + 1)`` populated with the
per-edge multiplier (1.0 default; 2.0 for affected edges). Action wrappers
apply the mask element-wise to the Euclidean distance matrix.

Coordinates, demands, capacity, customer count, and vehicle count are
unchanged — DISTANCE leaves the topology of the problem alone and only
re-scales selected edges.

Region-size convention: the "1/4" is always ``ceil(n_customers / 4)``,
applied uniformly across DIST_1/2/3 (DIST_4 is sized by the baseline).
"""
from __future__ import annotations

import logging
import math

import numpy as np

from ...baselines import Solution
from ...instances import Instance
from .. import PerturbationSpec
from ..types import PerturbedInstance
from ._common import argmax_with_tiebreak, compute_k_nn_spread

logger = logging.getLogger(__name__)

#: Distance multiplier applied to every edge in the affected region.
#: Locked to 2.0 by prereg §6.2 (raised from v0.1's 1.25 to produce
#: non-degenerate label distributions across OBJ/STRUCT/RANK).
_MULTIPLIER: float = 2.0

#: k for the k-nearest-neighbor density metric used by DIST_1/DIST_2.
_K_NN: int = 5


def apply_distance(
    instance: Instance,
    spec: PerturbationSpec,
    baseline: Solution | None = None,
) -> PerturbedInstance:
    """Realize a DISTANCE perturbation.

    DIST_4 requires ``baseline`` (highest-cost route is read from it);
    DIST_1/2/3 do not. ``affected_route_share`` is computed from the
    baseline if provided, otherwise reported as 0.0 with a debug log
    (matches the CAPACITY no-baseline sentinel).
    """
    if spec.family != "DISTANCE":
        raise ValueError(
            f"apply_distance requires a DISTANCE spec, got {spec.family!r} "
            f"(perturbation_id={spec.perturbation_id!r})"
        )

    pid = spec.perturbation_id
    n = instance.n_customers
    if pid in ("DIST_1", "DIST_2"):
        region = _select_density_partition(
            instance.coords,
            want_low_density=(pid == "DIST_1"),
        )
    elif pid == "DIST_3":
        region = _select_closest_quartile(instance.coords)
    elif pid == "DIST_4":
        if baseline is None:
            raise ValueError(
                f"apply_distance for DIST_4 requires a baseline solution "
                f"(instance_id={instance.instance_id!r})"
            )
        region = _select_highest_cost_route(baseline)
    else:
        raise ValueError(
            f"unknown DISTANCE perturbation_id {pid!r}; "
            f"expected one of DIST_1..DIST_4"
        )

    mask = _build_distance_mask(n, region)

    n_affected = len(region)
    total_demand = int(instance.demands[1:].sum())
    affected_demand = int(instance.demands[region].sum()) if region else 0
    affected_demand_share = (
        affected_demand / total_demand if total_demand else 0.0
    )

    if baseline is not None:
        region_set = set(region)
        n_routes = len(baseline.routes)
        n_touched = sum(
            1 for r in baseline.routes if any(c in region_set for c in r)
        )
        affected_route_share = n_touched / n_routes if n_routes else 0.0
    else:
        logger.debug(
            "apply_distance called without baseline for %s; "
            "affected_route_share=0.0 (perturbation_id=%s)",
            instance.instance_id, pid,
        )
        affected_route_share = 0.0

    return PerturbedInstance(
        instance_id=instance.instance_id,
        perturbation_id=pid,
        perturbation_family="DISTANCE",
        perturbation_magnitude=float(spec.magnitude),  # 2.0
        n_customers=n,
        coords=instance.coords.copy(),
        demands=instance.demands.copy(),
        capacity=instance.capacity,
        n_vehicles=instance.n_vehicles,
        distance_multiplier_mask=mask,
        n_affected_customers=n_affected,
        affected_demand_share=affected_demand_share,
        affected_route_share=affected_route_share,
    )


# ---------------------------------------------------------------------------
# Region selection


def _select_closest_quartile(coords: np.ndarray) -> list[int]:
    """The ``ceil(n/4)`` customers closest to the depot (1-indexed).

    Tie-break: lowest customer index wins.
    """
    n = coords.shape[0] - 1
    d2d = _depot_distances(coords)
    ordered = sorted(range(1, n + 1), key=lambda c: (d2d[c - 1], c))
    k = math.ceil(n / 4)
    return sorted(ordered[:k])


def _select_farthest_quartile(coords: np.ndarray) -> list[int]:
    """The ``ceil(n/4)`` customers farthest from the depot (1-indexed).

    Tie-break: lowest customer index wins (so an equidistant pair is
    resolved by index, not by stable-sort order).
    """
    n = coords.shape[0] - 1
    d2d = _depot_distances(coords)
    ordered = sorted(range(1, n + 1), key=lambda c: (-d2d[c - 1], c))
    k = math.ceil(n / 4)
    return sorted(ordered[:k])


def _select_density_partition(
    coords: np.ndarray, *, want_low_density: bool
) -> list[int]:
    """Partition the farthest 1/4 by k-NN spread vs the **global** median.

    The k-NN spread is the mean Euclidean distance from a customer to its
    ``k=5`` nearest *customer* neighbors (the depot is not in the neighbor
    pool). The median is taken across **all** customers' spreads, not
    just the farthest 25%; this anchors "low density" to instance-scale
    sparsity rather than self-referential subset sparsity.

    DIST_1 (low density) := spread > median.
    DIST_2 (high density) := spread <= median.

    The two sets are disjoint and cover the farthest 25% (a customer
    whose spread equals the median exactly falls into DIST_2 by the
    ``<=`` rule). The split ratio is data-dependent — for the X-set
    instances tested, splits run roughly 12/13 of 25, but degenerate
    cases where one of DIST_1/DIST_2 is empty are not ruled out by the
    spec.
    """
    farthest = _select_farthest_quartile(coords)
    spread = compute_k_nn_spread(coords, k=_K_NN)
    median = float(np.median(spread))
    if want_low_density:
        return [c for c in farthest if spread[c - 1] > median]
    return [c for c in farthest if spread[c - 1] <= median]


def _select_highest_cost_route(baseline: Solution) -> list[int]:
    """Customers belonging to the highest-cost baseline route. Ties: lowest route index."""
    n_routes = len(baseline.routes)
    if n_routes == 0:
        raise ValueError(
            f"DIST_4 requires at least one baseline route, got 0 "
            f"(instance_id={baseline.instance_id!r})"
        )
    costs = [baseline.route_costs[i] for i in range(n_routes)]
    ri = argmax_with_tiebreak(costs)
    return sorted(baseline.routes[ri])


# ---------------------------------------------------------------------------
# Geometric helpers


def _depot_distances(coords: np.ndarray) -> np.ndarray:
    """Euclidean distance from depot (index 0) to each customer; shape (n,)."""
    depot = coords[0]
    return np.sqrt(((coords[1:] - depot) ** 2).sum(axis=1))


def _build_distance_mask(n_customers: int, region: list[int]) -> np.ndarray:
    """Construct the ``(n+1, n+1)`` multiplier mask for a given region.

    Default 1.0 everywhere. Entries set to 2.0:
      - ``mask[0, c]`` and ``mask[c, 0]`` for each ``c`` in ``region``
      - ``mask[c1, c2]`` for every ordered pair ``(c1, c2)`` of distinct
        region customers

    The diagonal stays at 1.0 (self-distance is 0 — the multiplier on it
    is operationally a no-op; we leave it neutral for cleanliness).
    """
    mask = np.ones((n_customers + 1, n_customers + 1), dtype=np.float64)
    if not region:
        return mask
    region_arr = np.array(region, dtype=np.int64)
    # Depot ↔ region (both directions).
    mask[0, region_arr] = _MULTIPLIER
    mask[region_arr, 0] = _MULTIPLIER
    # Region ↔ region (broadcast assigns the full block, then we restore the
    # diagonal entries within that block to 1.0).
    block_idx = np.ix_(region_arr, region_arr)
    mask[block_idx] = _MULTIPLIER
    mask[region_arr, region_arr] = 1.0  # diagonal stays neutral
    return mask
