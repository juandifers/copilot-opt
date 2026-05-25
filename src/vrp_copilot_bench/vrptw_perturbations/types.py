"""Type definitions for the VRPTW perturbation pilot.

Parallel to :mod:`vrp_copilot_bench.perturbations.types` — kept separate so
this exploratory pilot does not touch the preregistered CVRP perturbation
package.

A :class:`VRPTWPerturbedInstance` mirrors :class:`vrp_copilot_bench.vrptw_instances.VRPTWInstance`
with potentially modified time-window, service-time, demand, or customer-set
fields, plus an optional ``travel_time_multiplier_mask`` for TRAVEL_TIME
perturbations and a small bundle of diagnostics.

Convention reminders:
- Arrays carry the depot row at index 0; customers occupy 1..n.
- ``time_windows`` and ``service_times`` are in **raw Solomon units** (not
  scaled). The wrapper applies the ×10 scaling at solve / evaluate time.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


PERTURBATION_FAMILIES: tuple[str, ...] = (
    "TRAVEL_TIME", "TIME_WINDOW", "SERVICE_TIME", "ORDER_CHANGE",
)


PERTURBATION_IDS: tuple[str, ...] = (
    "TT_1", "TT_2", "TT_3", "TT_4",
    "TW_1", "TW_2", "TW_3", "TW_4",
    "ST_1", "ST_2", "ST_3", "ST_4",
    "OC_1", "OC_2", "OC_3", "OC_4",
)


#: Additional perturbation IDs used by the Homberger-200 methodology
#: probe. Not part of Stage A's canonical 16; they apply upper-half
#: magnitudes the Stage A soft_grid does not cover. Stage A scripts
#: default to ``PERTURBATION_IDS`` so this extension is dormant unless a
#: caller opts in explicitly with ``--perturbations``.
HOMBERGER_PROBE_PERTURBATION_IDS: tuple[str, ...] = (
    "TT_5", "TW_5", "TW_6", "OC_5",
)

#: 8 perturbation IDs the Homberger probe iterates per instance:
#: 4 families × 2 upper-half magnitudes.
HOMBERGER_PROBE_GRID_IDS: tuple[str, ...] = (
    "TT_4", "TT_5",   # 1.30, 1.50
    "TW_5", "TW_6",   # 0.15, 0.20
    "ST_3", "ST_4",   # 1.25, 1.50
    "OC_4", "OC_5",   # 0.20, 0.25
)


PERTURBATION_FAMILY_OF: dict[str, str] = {
    **{f"TT_{i}": "TRAVEL_TIME" for i in (1, 2, 3, 4, 5)},
    **{f"TW_{i}": "TIME_WINDOW" for i in (1, 2, 3, 4, 5, 6)},
    **{f"ST_{i}": "SERVICE_TIME" for i in (1, 2, 3, 4)},
    **{f"OC_{i}": "ORDER_CHANGE" for i in (1, 2, 3, 4, 5)},
}


#: Magnitude per perturbation_id. Units depend on family:
#: TT_*: duration multiplier. ST_*: service-time multiplier.
#: TW_*: fractional tighten/shift amount. OC_*: fractional demand share.
PERTURBATION_MAGNITUDES: dict[str, float] = {
    "TT_1": 1.10, "TT_2": 1.20, "TT_3": 1.30, "TT_4": 1.50,
    "TT_5": 1.50,
    "TW_1": 0.10, "TW_2": 0.20, "TW_3": 0.10, "TW_4": 0.10,
    "TW_5": 0.15, "TW_6": 0.20,
    "ST_1": 1.10, "ST_2": 1.25, "ST_3": 1.50, "ST_4": 2.00,
    "OC_1": 0.05, "OC_2": 0.05, "OC_3": 0.15, "OC_4": 0.20,
    "OC_5": 0.25,
}


#: v2 "soft_grid" magnitudes — used by the diagnostic v2 pilot and the
#: Homberger-200 probe (probe rows resolve to TT_4/TT_5/TW_5/TW_6/ST_3/
#: ST_4/OC_4/OC_5 here). OC demand shares are unchanged; the OC tight
#: window width is controlled separately via
#: :data:`SOFT_TIGHT_WINDOW_WIDTH_FRACTION`.
SOFT_PERTURBATION_MAGNITUDES: dict[str, float] = {
    "TT_1": 1.05, "TT_2": 1.10, "TT_3": 1.20, "TT_4": 1.30,
    "TT_5": 1.50,
    "TW_1": 0.05, "TW_2": 0.10, "TW_3": 0.05, "TW_4": 0.05,
    "TW_5": 0.15, "TW_6": 0.20,
    "ST_1": 1.05, "ST_2": 1.10, "ST_3": 1.25, "ST_4": 1.50,
    "OC_1": 0.05, "OC_2": 0.05, "OC_3": 0.15, "OC_4": 0.20,
    "OC_5": 0.25,
}

#: v1 default tight-window fraction for OC_2/OC_4 (25% of median width).
V1_TIGHT_WINDOW_WIDTH_FRACTION: float = 0.25
#: v2 soft_grid tight-window fraction for OC_2/OC_4 (40% of median width).
SOFT_TIGHT_WINDOW_WIDTH_FRACTION: float = 0.40


@dataclass(frozen=True)
class VRPTWPerturbationSpec:
    """Identifier + family + magnitude. Populated by ``apply_*`` helpers."""

    perturbation_id: str
    family: str  # one of PERTURBATION_FAMILIES
    magnitude: float

    @property
    def short_family(self) -> str:
        return self.perturbation_id.split("_", 1)[0]


@dataclass(frozen=True)
class VRPTWPerturbedInstance:
    """A VRPTW instance with one perturbation applied.

    Field shape matches :class:`vrp_copilot_bench.vrptw_instances.VRPTWInstance`
    so the PyVRP wrapper can consume both via duck typing on
    ``n_customers``, ``coords``, ``demands``, ``service_times``,
    ``time_windows``, ``capacity``, and ``n_vehicles``.

    ``travel_time_multiplier_mask`` is an ``(n+1, n+1)`` float array
    populated only by TRAVEL_TIME perturbations; it is multiplied into the
    duration matrix before rounding. ``None`` everywhere else, so the
    wrapper short-circuits.
    """

    instance_id: str
    perturbation_id: str
    perturbation_family: str
    perturbation_magnitude: float

    n_customers: int
    capacity: int
    n_vehicles: int

    coords: np.ndarray         # (n+1, 2) float64
    demands: np.ndarray        # (n+1,)   int64
    service_times: np.ndarray  # (n+1,)   int64
    time_windows: np.ndarray   # (n+1, 2) int64

    travel_time_multiplier_mask: np.ndarray | None  # (n+1, n+1) float64 or None

    n_affected_customers: int
    affected_demand_share: float
    affected_route_share: float
    n_inserted_customers: int
    affected_customers: tuple[int, ...]
    affected_baseline_routes: tuple[int, ...]

    @property
    def depot_index(self) -> int:
        return 0
