"""ORDER_CHANGE perturbations — append new customers to the instance.

Definitions::

    OC_1: insert 1 customer near highest-slack route
          flexible time window
          demand   = 0.05 × vehicle capacity
          service  = median original customer service time

    OC_2: insert 1 customer near lowest-slack route
          tight time window
          demand   = 0.05 × vehicle capacity
          service  = median original customer service time

    OC_3: insert 3 clustered customers near densest region
          flexible time windows
          total demand   = 0.15 × vehicle capacity (per-cust = total/3)
          service        = median original customer service time

    OC_4: insert 3 clustered customers near low-slack route
          tight time windows
          total demand   = 0.20 × vehicle capacity (per-cust = total/3)
          service        = median original customer service time

Determinism is via ``sha256(f"{instance_id}_{perturbation_id}")[:16]`` →
``int`` → ``mod 2**32`` → ``numpy.random.default_rng`` (mirrors the CVRP
INSERTION family).

Time-window definitions:
- *flexible*  → width  = median existing customer window width
                center = reference-route median customer baseline start_service
- *tight*    → width  = 25% of median existing customer window width
                center = baseline start_service of the reference-route
                         customer with the lowest slack-to-tw_late

All inserted windows are clipped to the depot horizon and forced to
have ``tw_early < tw_late``.

Fleet size is held constant — solvers may report infeasibility if added
demand exceeds available capacity. That is part of the PLAN_VALIDITY signal.
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import numpy as np

from ..types import (
    PERTURBATION_FAMILY_OF,
    PERTURBATION_MAGNITUDES,
    VRPTWPerturbationSpec,
    VRPTWPerturbedInstance,
)
from ._common import (
    clip_window,
    densest_quartile_customers,
    pick_route_argmax,
    pick_route_argmin,
    route_customers,
)

if TYPE_CHECKING:
    from ...solvers.pyvrp_vrptw_wrapper import VRPTWSolveResult
    from ...vrptw_instances import VRPTWInstance


def _seed_rng(instance_id: str, perturbation_id: str) -> np.random.Generator:
    digest = hashlib.sha256(
        f"{instance_id}_{perturbation_id}".encode()
    ).hexdigest()[:16]
    seed_int = int(digest, 16) % (2 ** 32)
    return np.random.default_rng(seed_int)


def _route_centroid_and_spread(
    instance: "VRPTWInstance", route: list[int],
) -> tuple[np.ndarray, float]:
    """Return ``(centroid, spread)`` for the customers on ``route``.

    ``spread`` is the std-dev of customer coordinates (single number; max
    over the two axes), used to size the placement jitter.
    """
    coords = np.asarray([instance.coords[c] for c in route])
    centroid = coords.mean(axis=0)
    spread = float(max(coords.std(axis=0).max(), 1.0))
    return centroid, spread


def _region_centroid(
    instance: "VRPTWInstance", region: list[int],
) -> tuple[np.ndarray, float]:
    return _route_centroid_and_spread(instance, region)


def _median_window_width(instance: "VRPTWInstance") -> float:
    widths = (
        instance.time_windows[1:, 1] - instance.time_windows[1:, 0]
    ).astype(np.float64)
    return float(np.median(widths))


def _median_service(instance: "VRPTWInstance") -> int:
    return int(np.median(instance.service_times[1:]))


def _baseline_start_service(
    baseline: "VRPTWSolveResult", customer_id: int,
) -> int:
    """Baseline scaled start_service for the given customer, in ×10 units."""
    return int(baseline.per_customer_schedule[customer_id].start_service)


def _reference_route_for_oc(
    pid: str, instance: "VRPTWInstance", baseline: "VRPTWSolveResult",
) -> tuple[list[int], np.ndarray, float]:
    """Return ``(reference_customer_list, centroid, spread)`` for the OC variant.

    For OC_3 (region-based) the reference list is the densest quartile
    customers; for OC_1/2/4 it's the customers on the chosen baseline
    route.
    """
    if pid == "OC_1":
        idx = pick_route_argmax(baseline, "mean_slack_to_tw_late")
        ref = route_customers(baseline, idx)
    elif pid in ("OC_2", "OC_4", "OC_5"):
        # OC_5 is the Homberger-probe extension: same lowest-slack-route
        # 3-cluster insertion as OC_4, at the upper-half demand share 0.25.
        idx = pick_route_argmin(baseline, "mean_slack_to_tw_late")
        ref = route_customers(baseline, idx)
    elif pid == "OC_3":
        ref = densest_quartile_customers(instance.coords)
    else:
        raise ValueError(f"unknown ORDER_CHANGE perturbation_id {pid!r}")
    centroid, spread = _route_centroid_and_spread(instance, ref)
    return ref, centroid, spread


def _flexible_window(
    reference: list[int], instance: "VRPTWInstance",
    baseline: "VRPTWSolveResult", scaling: int,
) -> tuple[int, int]:
    """Flexible (wide) window in **raw** units, centered at the reference
    route's median baseline start_service.

    Returns ``(tw_early, tw_late)`` in raw (unscaled) time units, suitable
    for direct storage in ``VRPTWInstance.time_windows``.
    """
    width_raw = _median_window_width(instance)
    starts_scaled = [
        _baseline_start_service(baseline, c) for c in reference
        if c in baseline.per_customer_schedule
    ]
    if starts_scaled:
        center_raw = float(np.median(starts_scaled)) / scaling
    else:  # fallback to depot midpoint
        center_raw = (
            float(instance.time_windows[0, 0])
            + float(instance.time_windows[0, 1])
        ) / 2.0
    e = int(round(center_raw - width_raw / 2.0))
    l = int(round(center_raw + width_raw / 2.0))
    return clip_window(
        e, l,
        int(instance.time_windows[0, 0]),
        int(instance.time_windows[0, 1]),
    )


def _tight_window(
    reference: list[int], instance: "VRPTWInstance",
    baseline: "VRPTWSolveResult", scaling: int,
    *,
    width_fraction: float = 0.25,
) -> tuple[int, int]:
    """Tight (narrow) window in **raw** units, centered at the lowest-slack
    customer's baseline start_service on the reference route.

    ``width_fraction`` controls how tight (default 0.25 = 25% of median
    existing window width; v2 soft_grid uses 0.40).
    """
    width_raw = float(width_fraction) * _median_window_width(instance)
    width_raw = max(1.0, width_raw)
    # Find the lowest-slack customer in the reference (smallest tw_late - start).
    candidates = [
        (baseline.per_customer_schedule[c].slack_to_tw_late, c)
        for c in reference if c in baseline.per_customer_schedule
    ]
    if candidates:
        candidates.sort()  # lowest slack first
        target_c = candidates[0][1]
        center_raw = (
            _baseline_start_service(baseline, target_c) / scaling
        )
    else:
        center_raw = (
            float(instance.time_windows[0, 0])
            + float(instance.time_windows[0, 1])
        ) / 2.0
    e = int(round(center_raw - width_raw / 2.0))
    l = int(round(center_raw + width_raw / 2.0))
    return clip_window(
        e, l,
        int(instance.time_windows[0, 0]),
        int(instance.time_windows[0, 1]),
    )


def _sample_insertion_coords(
    centroid: np.ndarray, spread: float, n_new: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Gaussian jitter around ``centroid``; clipped to a sane range.

    The jitter std-dev is ``spread / 3`` for single inserts (OC_1, OC_2)
    and ``spread / 4`` for the clustered inserts (OC_3, OC_4) so the
    "tight cluster" stays tight.
    """
    sigma = spread / 3.0 if n_new == 1 else spread / 4.0
    return centroid + rng.normal(0.0, sigma, size=(n_new, 2))


def apply_order_change(
    instance: "VRPTWInstance",
    spec: VRPTWPerturbationSpec,
    baseline: "VRPTWSolveResult",
    *,
    magnitude_override: float | None = None,
    tight_width_fraction: float = 0.25,
) -> VRPTWPerturbedInstance:
    if spec.family != "ORDER_CHANGE":
        raise ValueError(
            f"apply_order_change requires ORDER_CHANGE spec, got {spec.family!r}"
        )

    pid = spec.perturbation_id
    gamma = (
        float(magnitude_override) if magnitude_override is not None
        else float(PERTURBATION_MAGNITUDES[pid])
    )

    # PyVRP scaling factor matters for the OC window centering — we work
    # in raw units here and let the wrapper rescale, so import it lazily
    # only for the conversion math.
    from ...solvers.pyvrp_vrptw_wrapper import SCALING_FACTOR

    n_new = 1 if pid in ("OC_1", "OC_2") else 3
    # OC_5 inherits OC_4's "tight window" style.
    tw_style = "flexible" if pid in ("OC_1", "OC_3") else "tight"

    reference, centroid, spread = _reference_route_for_oc(pid, instance, baseline)
    rng = _seed_rng(instance.instance_id, pid)

    new_xy = _sample_insertion_coords(centroid, spread, n_new, rng)
    new_xy = np.round(new_xy, decimals=2)  # mild integerization

    # Demand: total = gamma * capacity, split evenly with per-customer floor 1.
    total_demand = max(1, int(round(gamma * instance.capacity)))
    per_demand = max(1, int(round(total_demand / n_new)))
    new_demands = np.full(n_new, per_demand, dtype=np.int64)

    median_st = max(1, _median_service(instance))
    new_service = np.full(n_new, median_st, dtype=np.int64)

    if tw_style == "flexible":
        e, l = _flexible_window(reference, instance, baseline, SCALING_FACTOR)
    else:
        e, l = _tight_window(
            reference, instance, baseline, SCALING_FACTOR,
            width_fraction=tight_width_fraction,
        )
    new_windows = np.tile(np.array([e, l], dtype=np.int64), (n_new, 1))

    # Build the grown arrays.
    n_orig = instance.n_customers
    new_n = n_orig + n_new

    coords_out = np.zeros((new_n + 1, 2), dtype=np.float64)
    coords_out[: n_orig + 1] = instance.coords
    coords_out[n_orig + 1:] = new_xy

    demands_out = np.zeros(new_n + 1, dtype=np.int64)
    demands_out[: n_orig + 1] = instance.demands
    demands_out[n_orig + 1:] = new_demands

    service_out = np.zeros(new_n + 1, dtype=np.int64)
    service_out[: n_orig + 1] = instance.service_times
    service_out[n_orig + 1:] = new_service

    windows_out = np.zeros((new_n + 1, 2), dtype=np.int64)
    windows_out[: n_orig + 1] = instance.time_windows
    windows_out[n_orig + 1:] = new_windows

    # Diagnostics: affected customers are the *new* customer IDs; their
    # demand share is relative to original total demand; affected routes
    # is the dominant reference route (single index for OC_1/2/4; the
    # routes touched by the dense quartile for OC_3).
    inserted_ids = tuple(range(n_orig + 1, n_orig + n_new + 1))
    total_orig_demand = int(instance.demands[1:].sum())
    affected_demand_share = (
        float(total_demand) / total_orig_demand if total_orig_demand else 0.0
    )

    if pid == "OC_3":
        # Routes the dense quartile touches.
        region_set = set(reference)
        touched = tuple(sorted(
            idx for idx, r in enumerate(baseline.routes)
            if any(c in region_set for c in r)
        ))
    elif pid == "OC_1":
        touched = (pick_route_argmax(baseline, "mean_slack_to_tw_late"),)
    else:  # OC_2, OC_4, OC_5
        touched = (pick_route_argmin(baseline, "mean_slack_to_tw_late"),)

    return VRPTWPerturbedInstance(
        instance_id=instance.instance_id,
        perturbation_id=pid,
        perturbation_family=PERTURBATION_FAMILY_OF[pid],
        perturbation_magnitude=gamma,
        n_customers=new_n,
        capacity=instance.capacity,
        n_vehicles=instance.n_vehicles,
        coords=coords_out,
        demands=demands_out,
        service_times=service_out,
        time_windows=windows_out,
        travel_time_multiplier_mask=None,
        n_affected_customers=n_new,
        affected_demand_share=affected_demand_share,
        affected_route_share=(len(touched) / len(baseline.routes))
                              if baseline.routes else 0.0,
        n_inserted_customers=n_new,
        affected_customers=inserted_ids,
        affected_baseline_routes=touched,
    )
