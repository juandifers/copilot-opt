"""SERVICE_TIME perturbations — multiply customer service durations.

Definitions::

    ST_1: affected = baseline route with highest total waiting time
          service time × 1.10

    ST_2: affected = baseline route with lowest minimum slack-to-latest-window
          service time × 1.25

    ST_3: affected = densest geographic customer quartile
          service time × 1.50

    ST_4: affected = top-demand customer quartile
          service time × 2.00

Depot service time (always 0 in Solomon) is never modified.
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
    pick_route_argmax,
    pick_route_argmin,
    route_customers,
    top_demand_quartile,
)

if TYPE_CHECKING:
    from ...solvers.pyvrp_vrptw_wrapper import VRPTWSolveResult
    from ...vrptw_instances import VRPTWInstance


def apply_service_time(
    instance: "VRPTWInstance",
    spec: VRPTWPerturbationSpec,
    baseline: "VRPTWSolveResult",
    *,
    magnitude_override: float | None = None,
) -> VRPTWPerturbedInstance:
    if spec.family != "SERVICE_TIME":
        raise ValueError(
            f"apply_service_time requires SERVICE_TIME spec, got {spec.family!r}"
        )

    pid = spec.perturbation_id
    multiplier = (
        float(magnitude_override) if magnitude_override is not None
        else float(PERTURBATION_MAGNITUDES[pid])
    )

    if pid == "ST_1":
        route_idx = pick_route_argmax(baseline, "wait_duration")
        affected = sorted(route_customers(baseline, route_idx))
    elif pid == "ST_2":
        route_idx = pick_route_argmin(baseline, "min_slack_to_tw_late")
        affected = sorted(route_customers(baseline, route_idx))
    elif pid == "ST_3":
        affected = densest_quartile_customers(instance.coords)
    elif pid == "ST_4":
        affected = top_demand_quartile(instance.demands)
    else:
        raise ValueError(f"unknown SERVICE_TIME perturbation_id {pid!r}")

    new_service = instance.service_times.copy()
    for c in affected:
        new_service[c] = int(round(int(instance.service_times[c]) * multiplier))
    # Depot service time is always 0; guard against accidental modification.
    new_service[0] = int(instance.service_times[0])

    n_aff, dem_share, rt_share, touched = compute_affected_diagnostics(
        instance, baseline, affected,
    )

    return VRPTWPerturbedInstance(
        instance_id=instance.instance_id,
        perturbation_id=pid,
        perturbation_family=PERTURBATION_FAMILY_OF[pid],
        perturbation_magnitude=multiplier,
        n_customers=instance.n_customers,
        capacity=instance.capacity,
        n_vehicles=instance.n_vehicles,
        coords=instance.coords.copy(),
        demands=instance.demands.copy(),
        service_times=new_service,
        time_windows=instance.time_windows.copy(),
        travel_time_multiplier_mask=None,
        n_affected_customers=n_aff,
        affected_demand_share=dem_share,
        affected_route_share=rt_share,
        n_inserted_customers=0,
        affected_customers=tuple(affected),
        affected_baseline_routes=touched,
    )
