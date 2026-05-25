"""VRPTW perturbation pilot package.

Exploratory only. Lives alongside the preregistered CVRP pipeline
(``vrp_copilot_bench.perturbations``) without sharing any modules.

Public API
----------
- :class:`VRPTWPerturbationSpec` / :class:`VRPTWPerturbedInstance` types.
- :func:`enumerate_vrptw_perturbations` returns the 16 pilot specs.
- :func:`lookup_vrptw_perturbation` resolves a spec by id.
- :func:`apply_vrptw_perturbation` dispatches to the family implementation
  and returns a :class:`VRPTWPerturbedInstance`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .types import (
    HOMBERGER_PROBE_GRID_IDS,
    HOMBERGER_PROBE_PERTURBATION_IDS,
    PERTURBATION_FAMILIES,
    PERTURBATION_FAMILY_OF,
    PERTURBATION_IDS,
    PERTURBATION_MAGNITUDES,
    VRPTWPerturbationSpec,
    VRPTWPerturbedInstance,
)

if TYPE_CHECKING:
    from ..solvers.pyvrp_vrptw_wrapper import VRPTWSolveResult
    from ..vrptw_instances import VRPTWInstance


def enumerate_vrptw_perturbations(
    ids: tuple[str, ...] = PERTURBATION_IDS,
) -> list[VRPTWPerturbationSpec]:
    """Return spec list for ``ids``. Default = Stage A canonical 16."""
    return [
        VRPTWPerturbationSpec(
            perturbation_id=pid,
            family=PERTURBATION_FAMILY_OF[pid],
            magnitude=PERTURBATION_MAGNITUDES[pid],
        )
        for pid in ids
    ]


#: Index covering Stage A canonical 16 + Homberger probe extension IDs.
#: Built from the union so ``lookup_vrptw_perturbation`` resolves any
#: known perturbation_id regardless of which roster the caller iterates.
_INDEX: dict[str, VRPTWPerturbationSpec] = {
    s.perturbation_id: s
    for s in enumerate_vrptw_perturbations(
        PERTURBATION_IDS + HOMBERGER_PROBE_PERTURBATION_IDS
    )
}


def lookup_vrptw_perturbation(perturbation_id: str) -> VRPTWPerturbationSpec:
    try:
        return _INDEX[perturbation_id]
    except KeyError as exc:
        raise ValueError(
            f"unknown VRPTW perturbation_id {perturbation_id!r}; "
            f"expected one of {sorted(_INDEX)}"
        ) from exc


def apply_vrptw_perturbation(
    instance: "VRPTWInstance",
    spec: VRPTWPerturbationSpec,
    baseline: "VRPTWSolveResult",
    *,
    magnitude_override: float | None = None,
    tight_width_fraction: float = 0.25,
) -> VRPTWPerturbedInstance:
    """Dispatch to the appropriate family implementation.

    All families require ``baseline`` (every selector is baseline-aware).

    ``magnitude_override`` lets the v2 pilot inject softer magnitudes
    without touching the canonical magnitude registry. ``tight_width_fraction``
    only affects ORDER_CHANGE OC_2/OC_4 (tight-window variants).
    """
    # Late import to avoid pulling PyVRP at package load time.
    from .families import (
        apply_order_change,
        apply_service_time,
        apply_time_window,
        apply_travel_time,
    )

    if spec.family == "TRAVEL_TIME":
        return apply_travel_time(
            instance, spec, baseline,
            magnitude_override=magnitude_override,
        )
    if spec.family == "TIME_WINDOW":
        return apply_time_window(
            instance, spec, baseline,
            magnitude_override=magnitude_override,
        )
    if spec.family == "SERVICE_TIME":
        return apply_service_time(
            instance, spec, baseline,
            magnitude_override=magnitude_override,
        )
    if spec.family == "ORDER_CHANGE":
        return apply_order_change(
            instance, spec, baseline,
            magnitude_override=magnitude_override,
            tight_width_fraction=tight_width_fraction,
        )
    raise ValueError(f"unknown perturbation family {spec.family!r}")


__all__ = [
    "VRPTWPerturbationSpec",
    "VRPTWPerturbedInstance",
    "PERTURBATION_IDS",
    "PERTURBATION_FAMILIES",
    "PERTURBATION_FAMILY_OF",
    "PERTURBATION_MAGNITUDES",
    "HOMBERGER_PROBE_PERTURBATION_IDS",
    "HOMBERGER_PROBE_GRID_IDS",
    "enumerate_vrptw_perturbations",
    "lookup_vrptw_perturbation",
    "apply_vrptw_perturbation",
]
