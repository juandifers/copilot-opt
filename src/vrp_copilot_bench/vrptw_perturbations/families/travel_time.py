"""TRAVEL_TIME perturbations — duration-matrix multipliers.

Definitions::

    TT_1: affected = baseline route with highest total waiting time
          duration multiplier = 1.10

    TT_2: affected = baseline route with lowest minimum slack-to-latest-window
          duration multiplier = 1.20

    TT_3: affected = densest geographic customer quartile
          duration multiplier = 1.30

    TT_4: affected = farthest customer quartile from depot
          duration multiplier = 1.50

For route-based variants (TT_1, TT_2) the multiplier is applied to every
arc touching a customer in the affected route. For region-based variants
(TT_3, TT_4) it is applied to every arc touching an affected customer.
**Distance is unchanged** — only the duration matrix scales.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ..types import (
    PERTURBATION_FAMILY_OF,
    PERTURBATION_MAGNITUDES,
    VRPTWPerturbationSpec,
    VRPTWPerturbedInstance,
)
from ._common import (
    compute_affected_diagnostics,
    densest_quartile_customers,
    farthest_quartile_customers,
    pick_route_argmax,
    pick_route_argmin,
    route_customers,
)

if TYPE_CHECKING:
    from ...solvers.pyvrp_vrptw_wrapper import VRPTWSolveResult
    from ...vrptw_instances import VRPTWInstance


def _build_travel_time_mask(n_nodes: int, affected: list[int], multiplier: float) -> np.ndarray:
    """Mask of shape ``(n_nodes, n_nodes)``; ``multiplier`` on arcs touching
    any affected customer, ``1.0`` elsewhere. Symmetric. Diagonal stays 1.0.
    """
    mask = np.ones((n_nodes, n_nodes), dtype=np.float64)
    if not affected:
        return mask
    arr = np.array(affected, dtype=np.int64)
    mask[arr, :] = multiplier
    mask[:, arr] = multiplier
    np.fill_diagonal(mask, 1.0)
    return mask


def apply_travel_time(
    instance: "VRPTWInstance",
    spec: VRPTWPerturbationSpec,
    baseline: "VRPTWSolveResult",
    *,
    magnitude_override: float | None = None,
) -> VRPTWPerturbedInstance:
    if spec.family != "TRAVEL_TIME":
        raise ValueError(
            f"apply_travel_time requires TRAVEL_TIME spec, got {spec.family!r}"
        )

    pid = spec.perturbation_id
    multiplier = (
        float(magnitude_override) if magnitude_override is not None
        else float(PERTURBATION_MAGNITUDES[pid])
    )
    n = instance.n_customers

    if pid == "TT_1":
        route_idx = pick_route_argmax(baseline, "wait_duration")
        affected = sorted(route_customers(baseline, route_idx))
    elif pid == "TT_2":
        route_idx = pick_route_argmin(baseline, "min_slack_to_tw_late")
        affected = sorted(route_customers(baseline, route_idx))
    elif pid == "TT_3":
        affected = densest_quartile_customers(instance.coords)
    elif pid in ("TT_4", "TT_5"):
        # TT_5 is the Homberger-probe extension: same farthest-quartile
        # selection as TT_4, at the upper-half multiplier 1.50.
        affected = farthest_quartile_customers(instance.coords)
    else:
        raise ValueError(f"unknown TRAVEL_TIME perturbation_id {pid!r}")

    mask = _build_travel_time_mask(n + 1, affected, multiplier)

    n_aff, dem_share, rt_share, touched = compute_affected_diagnostics(
        instance, baseline, affected,
    )

    return VRPTWPerturbedInstance(
        instance_id=instance.instance_id,
        perturbation_id=pid,
        perturbation_family=PERTURBATION_FAMILY_OF[pid],
        perturbation_magnitude=multiplier,
        n_customers=n,
        capacity=instance.capacity,
        n_vehicles=instance.n_vehicles,
        coords=instance.coords.copy(),
        demands=instance.demands.copy(),
        service_times=instance.service_times.copy(),
        time_windows=instance.time_windows.copy(),
        travel_time_multiplier_mask=mask,
        n_affected_customers=n_aff,
        affected_demand_share=dem_share,
        affected_route_share=rt_share,
        n_inserted_customers=0,
        affected_customers=tuple(affected),
        affected_baseline_routes=touched,
    )
