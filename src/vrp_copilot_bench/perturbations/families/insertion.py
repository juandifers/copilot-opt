"""INSERTION perturbation family (prereg §6.4, amended in v0.4).

Adds new customers to the instance with deterministically-seeded coordinates
and demands. The four perturbations differ in (a) how many customers are
added, (b) where they are spatially placed, and (c) how much demand they
collectively bring:

| ID    | n_new | spatial pattern                                | γ    |
|-------|-------|------------------------------------------------|------|
| INS_1 | 1     | uniformly within 1 std-dev of depot            | 0.30 |
| INS_2 | 3     | tight cluster, centroid near busiest baseline  | 0.70 |
| INS_3 | 5     | scattered uniformly across the convex hull     | 1.20 |
| INS_4 | 10    | tight cluster, centroid in low-density region  | 2.00 |

Total inserted demand = ``round(γ × vehicle_capacity)``; per-customer
demand is uniform (``per = max(1, round(γ × capacity / n_new))``). New
customer indices are appended after the source customers; the depot
stays at row 0.

Determinism uses prereg §6.4 (v0.4) seeding:

    seed = sha256(f"{instance_id}_{perturbation_id}").hexdigest()[:16] → int → mod 2³²
    rng = numpy.random.default_rng(seed)

The per-(instance, perturbation_id) input ensures INS_1..INS_4 on the
same instance draw distinct RNG streams (v0.3's per-instance seed caused
INS_1's only sample to coincide with INS_2's first sample, etc.).

scipy is not a project dependency, so INS_3's "uniform over the convex
hull" is implemented as bounding-box rejection sampling with a pure-numpy
hull (Andrew's monotone chain) and a cross-product point-in-polygon test.
"""
from __future__ import annotations

import hashlib
import logging
import math

import numpy as np

from ...baselines import Solution
from ...instances import Instance
from .. import PerturbationSpec
from ..types import PerturbedInstance
from ._common import argmax_with_tiebreak, compute_k_nn_spread

logger = logging.getLogger(__name__)

#: k for INS_4's low-density centroid (matches DISTANCE's k=5 spec).
_K_NN: int = 5

#: Bound for INS_3's rejection sampling. Bounding-box vs hull-area ratio
#: is typically ~2–3 on Uchoa-X, so 100 attempts per requested point
#: leaves a comfortable margin.
_REJECTION_ATTEMPTS_PER_POINT: int = 100


def apply_insertion(
    instance: Instance,
    spec: PerturbationSpec,
    baseline: Solution | None = None,
) -> PerturbedInstance:
    """Realize an INSERTION perturbation.

    Raises
    ------
    ValueError
        If ``baseline is None`` (every INS variant either uses the
        baseline directly — INS_2 — or computes from instance state but
        the action wrapper still needs a baseline in scope; we require
        it for all four for signature uniformity per the prompt) or
        if ``spec`` is not an INSERTION spec.
    """
    if spec.family != "INSERTION":
        raise ValueError(
            f"apply_insertion requires an INSERTION spec, got {spec.family!r} "
            f"(perturbation_id={spec.perturbation_id!r})"
        )
    if baseline is None:
        raise ValueError(
            f"apply_insertion requires a baseline solution for "
            f"{instance.instance_id!r} (perturbation_id={spec.perturbation_id!r})"
        )

    pid = spec.perturbation_id
    gamma = float(spec.magnitude)
    n_new = _N_NEW_PER_PID[pid]
    rng = _seed_rng(instance.instance_id, pid)

    # Deterministic spatial sampling, then integer-round (Uchoa-X convention).
    if pid == "INS_1":
        new_xy = _sample_near_depot(instance.coords, n_new=n_new, rng=rng)
    elif pid == "INS_2":
        new_xy = _sample_cluster_busy_route(
            instance.coords, instance.demands, baseline, n_new=n_new, rng=rng
        )
    elif pid == "INS_3":
        new_xy = _sample_scattered_hull(instance.coords, n_new=n_new, rng=rng)
    elif pid == "INS_4":
        new_xy = _sample_cluster_low_density(instance.coords, n_new=n_new, rng=rng)
    else:
        raise ValueError(
            f"unknown INSERTION perturbation_id {pid!r}; "
            f"expected one of INS_1..INS_4"
        )

    new_xy_int = np.round(new_xy).astype(np.float64)

    # Demand: uniform per-customer; total ≈ round(γ × capacity), with
    # per-customer rounding error of at most n_new / 2 in the sum.
    target_total = int(round(gamma * instance.capacity))
    per_customer = max(1, int(round(target_total / n_new)))
    new_demands = np.full(n_new, per_customer, dtype=np.int64)

    # Append: depot at 0, original 1..n, new at n+1..n+n_new.
    n_orig = instance.n_customers
    new_n = n_orig + n_new
    coords_out = np.zeros((new_n + 1, 2), dtype=np.float64)
    coords_out[: n_orig + 1] = instance.coords
    coords_out[n_orig + 1 :] = new_xy_int

    demands_out = np.zeros(new_n + 1, dtype=np.int64)
    demands_out[: n_orig + 1] = instance.demands
    demands_out[n_orig + 1 :] = new_demands

    inserted_demand_total = int(new_demands.sum())
    orig_total = int(instance.demands[1:].sum())
    new_total = orig_total + inserted_demand_total
    affected_demand_share = (
        inserted_demand_total / new_total if new_total else 0.0
    )

    return PerturbedInstance(
        instance_id=instance.instance_id,
        perturbation_id=pid,
        perturbation_family="INSERTION",
        perturbation_magnitude=gamma,
        n_customers=new_n,
        coords=coords_out,
        demands=demands_out,
        capacity=instance.capacity,
        n_vehicles=instance.n_vehicles,
        distance_multiplier_mask=None,
        n_affected_customers=n_new,
        affected_demand_share=affected_demand_share,
        # Per prompt: any route could absorb new customers; report 1.0
        # as a convention so the parquet column has a defined value.
        affected_route_share=1.0,
    )


# ---------------------------------------------------------------------------
# Per-pid table


_N_NEW_PER_PID: dict[str, int] = {
    "INS_1": 1,
    "INS_2": 3,
    "INS_3": 5,
    "INS_4": 10,
}


# ---------------------------------------------------------------------------
# Seeding (prereg §6.4, v0.4)


def _seed_rng(instance_id: str, perturbation_id: str) -> np.random.Generator:
    """Per-(instance, perturbation_id) deterministic seed.

    Hash input changed in prereg v0.4 from ``instance_id`` alone to
    ``f"{instance_id}_{perturbation_id}"`` — see CHANGES log §19 v0.4.
    """
    payload = f"{instance_id}_{perturbation_id}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    seed_int = int(digest[:16], 16) % (2**32)
    return np.random.default_rng(seed_int)


# ---------------------------------------------------------------------------
# Spatial samplers


def _sample_near_depot(
    coords: np.ndarray, *, n_new: int, rng: np.random.Generator
) -> np.ndarray:
    """INS_1: uniformly within 1 std-dev of the depot.

    "1 std-dev" = the RMS distance from depot to existing customers,
    treated as a scalar radius. Sampling is uniform over the disk of
    that radius (uniform-area ~ ``r * sqrt(U)`` for ``U ~ Uniform(0,1)``).
    """
    depot = coords[0]
    customers = coords[1:]
    radial = np.sqrt(((customers - depot) ** 2).sum(axis=1))
    radius = float(np.sqrt((radial ** 2).mean()))
    theta = rng.uniform(0.0, 2 * math.pi, size=n_new)
    r_sample = radius * np.sqrt(rng.uniform(0.0, 1.0, size=n_new))
    out = np.empty((n_new, 2), dtype=np.float64)
    out[:, 0] = depot[0] + r_sample * np.cos(theta)
    out[:, 1] = depot[1] + r_sample * np.sin(theta)
    return out


def _sample_cluster_busy_route(
    coords: np.ndarray,
    demands: np.ndarray,
    baseline: Solution,
    *,
    n_new: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """INS_2: tight cluster, centroid near busiest baseline route.

    "Busiest" = highest-LOAD route (sum of demands), tie-break lowest
    route index. Distinct from DIST_4 / DEM_4, which use highest *cost*.

    centroid = mean of customer coords in that route.
    route_radius = max distance from centroid to any customer in the route.
    new customers ~ centroid + Normal(0, std=route_radius/3) per axis.
    """
    n_routes = len(baseline.routes)
    if n_routes == 0:
        raise ValueError("INS_2 requires at least one baseline route")
    loads = [int(demands[r].sum()) for r in baseline.routes]
    ri = argmax_with_tiebreak(loads)
    route_customers = baseline.routes[ri]
    route_xy = coords[route_customers]
    centroid = route_xy.mean(axis=0)
    radii = np.sqrt(((route_xy - centroid) ** 2).sum(axis=1))
    route_radius = float(radii.max())
    sigma = route_radius / 3.0 if route_radius > 0 else 1.0
    return centroid + rng.normal(0.0, sigma, size=(n_new, 2))


def _sample_scattered_hull(
    coords: np.ndarray, *, n_new: int, rng: np.random.Generator
) -> np.ndarray:
    """INS_3: uniform over the convex hull of existing customers.

    Implemented as bounding-box rejection sampling against the hull
    (no scipy dependency). Hull computed via Andrew's monotone chain;
    point-in-polygon via consecutive cross-product sign checks.
    """
    customer_xy = coords[1:]
    hull = _convex_hull_ccw(customer_xy)
    min_xy = customer_xy.min(axis=0)
    max_xy = customer_xy.max(axis=0)
    out = np.empty((n_new, 2), dtype=np.float64)
    n_collected = 0
    max_attempts = n_new * _REJECTION_ATTEMPTS_PER_POINT
    for _ in range(max_attempts):
        if n_collected == n_new:
            break
        candidate = rng.uniform(min_xy, max_xy)
        if _point_in_convex_polygon(candidate, hull):
            out[n_collected] = candidate
            n_collected += 1
    if n_collected < n_new:
        raise RuntimeError(
            f"_sample_scattered_hull: failed to draw {n_new} points "
            f"in {max_attempts} attempts (collected {n_collected})"
        )
    return out


def _sample_cluster_low_density(
    coords: np.ndarray, *, n_new: int, rng: np.random.Generator
) -> np.ndarray:
    """INS_4: tight cluster, centroid at the customer with the largest
    k-NN spread (least dense local region; tie-break lowest customer index).

    new customers ~ centroid + Normal(0, std=centroid_spread/3) per axis,
    where ``centroid_spread`` is the centroid customer's own k-NN spread
    (the mean distance to its 5 nearest customer neighbors).

    Why local spread rather than a global ``customer_std``: INS_4 is
    "tight cluster, centroid in low-density region" — the right scale of
    "tight" is local to the centroid. In a sparse region neighbors are
    far apart by construction, so dividing that spread by 3 gives a
    cluster that's wider in absolute terms but tight *relative to local
    density*. A global ``customer_std/2`` would produce clusters that
    span half the instance, which doesn't match "tight" in any reading.
    """
    spread = compute_k_nn_spread(coords, k=_K_NN)
    spread_list = spread.tolist()
    # spread is indexed 0..n-1 for customers 1..n; argmax returns the
    # customer offset, which we convert to the 1-indexed customer.
    customer_offset = argmax_with_tiebreak(spread_list)
    centroid = coords[customer_offset + 1]
    centroid_spread = float(spread[customer_offset])
    sigma = centroid_spread / 3.0 if centroid_spread > 0 else 1.0
    return centroid + rng.normal(0.0, sigma, size=(n_new, 2))


# ---------------------------------------------------------------------------
# Convex hull (Andrew's monotone chain) and point-in-polygon


def _convex_hull_ccw(points: np.ndarray) -> np.ndarray:
    """Return the convex hull of ``points`` as an ``(h, 2)`` array of
    vertices in counter-clockwise order, no duplicate first/last point.

    Uses Andrew's monotone chain — O(n log n). Collinear points on the
    hull boundary are dropped (strict ``> 0`` cross-product test).

    Requires at least 3 non-collinear points; for the X-set this holds.
    """
    if points.shape[0] < 3:
        raise ValueError(
            f"_convex_hull_ccw: need >= 3 points, got {points.shape[0]}"
        )
    # Sort lexicographically: first by x, then by y.
    sorted_idx = np.lexsort((points[:, 1], points[:, 0]))
    pts = points[sorted_idx]

    lower: list[np.ndarray] = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[np.ndarray] = []
    for p in pts[::-1]:
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    # Drop the last point of each list (duplicate of the other's first).
    hull = lower[:-1] + upper[:-1]
    return np.array(hull, dtype=np.float64)


def _cross(o: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """2D cross product of ``OA × OB``. Positive = left turn."""
    return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))


def _point_in_convex_polygon(pt: np.ndarray, hull_ccw: np.ndarray) -> bool:
    """True iff ``pt`` is inside (or on) the convex polygon defined by
    ``hull_ccw`` (vertices listed CCW, no duplicate close).
    """
    n = hull_ccw.shape[0]
    for i in range(n):
        a = hull_ccw[i]
        b = hull_ccw[(i + 1) % n]
        # CCW polygon: interior is to the left of every directed edge.
        # cross(a→b, a→pt) >= 0 → left or on edge.
        if _cross(a, b, pt) < 0.0:
            return False
    return True
