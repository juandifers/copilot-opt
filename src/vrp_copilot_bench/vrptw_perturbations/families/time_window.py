"""TIME_WINDOW perturbations — narrow or shift customer windows.

Definitions::

    TW_1: affected = route with highest average slack-to-latest-window
          tighten windows by 10% around midpoint

    TW_2: affected = route with lowest average slack-to-latest-window
          tighten windows by 20% around midpoint

    TW_3: affected = customers in final third of each baseline route
          shift windows earlier by 10% of original window width

    TW_4: affected = customers in first third of each baseline route
          shift windows later by 10% of original window width

Rules (applied per affected customer):

- Depot window is never modified.
- Clipped to ``[depot_open, depot_close]``.
- ``tw_early < tw_late`` is enforced; on collapse, the window becomes a
  1-unit window centered at the original midpoint.
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
    clip_window,
    compute_affected_diagnostics,
    customers_in_route_segment,
    pick_route_argmax,
    pick_route_argmin,
    route_customers,
)

if TYPE_CHECKING:
    from ...solvers.pyvrp_vrptw_wrapper import VRPTWSolveResult
    from ...vrptw_instances import VRPTWInstance


def _tighten_around_midpoint(
    tw_early: int, tw_late: int, fraction: float,
    depot_open: int, depot_close: int,
) -> tuple[int, int]:
    """Reduce width by ``fraction`` keeping midpoint fixed; then clip."""
    width = tw_late - tw_early
    new_width = max(1.0, width * (1.0 - fraction))
    mid = (tw_early + tw_late) / 2.0
    new_early = int(round(mid - new_width / 2.0))
    new_late = int(round(mid + new_width / 2.0))
    return clip_window(new_early, new_late, depot_open, depot_close)


def _shift_window(
    tw_early: int, tw_late: int, shift: int,
    depot_open: int, depot_close: int,
) -> tuple[int, int]:
    """Translate the whole window by ``shift`` (signed); then clip."""
    return clip_window(
        int(tw_early) + int(shift),
        int(tw_late) + int(shift),
        depot_open, depot_close,
    )


def apply_time_window(
    instance: "VRPTWInstance",
    spec: VRPTWPerturbationSpec,
    baseline: "VRPTWSolveResult",
    *,
    magnitude_override: float | None = None,
) -> VRPTWPerturbedInstance:
    if spec.family != "TIME_WINDOW":
        raise ValueError(
            f"apply_time_window requires TIME_WINDOW spec, got {spec.family!r}"
        )

    pid = spec.perturbation_id
    magnitude = (
        float(magnitude_override) if magnitude_override is not None
        else float(PERTURBATION_MAGNITUDES[pid])
    )

    new_windows = instance.time_windows.copy()
    depot_open = int(instance.time_windows[0, 0])
    depot_close = int(instance.time_windows[0, 1])

    # TW_5/TW_6 are Homberger-probe extension IDs: same tighten-around-
    # midpoint perturbation as TW_1/TW_2 (highest/lowest mean-slack route),
    # at the upper-half magnitudes 0.15 / 0.20 the probe spec calls for.
    if pid in ("TW_1", "TW_2", "TW_5", "TW_6"):
        if pid in ("TW_1", "TW_5"):
            route_idx = pick_route_argmax(baseline, "mean_slack_to_tw_late")
        else:
            route_idx = pick_route_argmin(baseline, "mean_slack_to_tw_late")
        affected = sorted(route_customers(baseline, route_idx))
        for c in affected:
            e, l = _tighten_around_midpoint(
                int(instance.time_windows[c, 0]),
                int(instance.time_windows[c, 1]),
                magnitude, depot_open, depot_close,
            )
            new_windows[c, 0] = e
            new_windows[c, 1] = l

    elif pid in ("TW_3", "TW_4"):
        segment = "final_third" if pid == "TW_3" else "first_third"
        affected = sorted(customers_in_route_segment(baseline, segment=segment))
        for c in affected:
            orig_e = int(instance.time_windows[c, 0])
            orig_l = int(instance.time_windows[c, 1])
            width = orig_l - orig_e
            shift = -int(round(magnitude * width)) if pid == "TW_3" else int(round(magnitude * width))
            e, l = _shift_window(orig_e, orig_l, shift, depot_open, depot_close)
            new_windows[c, 0] = e
            new_windows[c, 1] = l
    else:
        raise ValueError(f"unknown TIME_WINDOW perturbation_id {pid!r}")

    n_aff, dem_share, rt_share, touched = compute_affected_diagnostics(
        instance, baseline, affected,
    )

    return VRPTWPerturbedInstance(
        instance_id=instance.instance_id,
        perturbation_id=pid,
        perturbation_family=PERTURBATION_FAMILY_OF[pid],
        perturbation_magnitude=magnitude,
        n_customers=instance.n_customers,
        capacity=instance.capacity,
        n_vehicles=instance.n_vehicles,
        coords=instance.coords.copy(),
        demands=instance.demands.copy(),
        service_times=instance.service_times.copy(),
        time_windows=new_windows,
        travel_time_multiplier_mask=None,
        n_affected_customers=n_aff,
        affected_demand_share=dem_share,
        affected_route_share=rt_share,
        n_inserted_customers=0,
        affected_customers=tuple(affected),
        affected_baseline_routes=touched,
    )
