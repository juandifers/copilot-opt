"""Shim re-exporting :mod:`vrp_copilot_bench.vrptw_perturbations`.

Future-facing import surface — new VRPTW code should reference
``vrp_copilot_bench.vrptw.perturbations`` (or the top-level
``vrp_copilot_bench.vrptw``). Existing pilot scripts continue to import
from the legacy package directly, which is left unchanged.
"""
from __future__ import annotations

from ..vrptw_perturbations import (
    PERTURBATION_FAMILIES,
    PERTURBATION_FAMILY_OF,
    PERTURBATION_IDS,
    PERTURBATION_MAGNITUDES,
    VRPTWPerturbationSpec,
    VRPTWPerturbedInstance,
    apply_vrptw_perturbation,
    enumerate_vrptw_perturbations,
    lookup_vrptw_perturbation,
)
from ..vrptw_perturbations.types import (
    SOFT_PERTURBATION_MAGNITUDES,
    SOFT_TIGHT_WINDOW_WIDTH_FRACTION,
    V1_TIGHT_WINDOW_WIDTH_FRACTION,
)

__all__ = [
    "PERTURBATION_FAMILIES",
    "PERTURBATION_FAMILY_OF",
    "PERTURBATION_IDS",
    "PERTURBATION_MAGNITUDES",
    "SOFT_PERTURBATION_MAGNITUDES",
    "SOFT_TIGHT_WINDOW_WIDTH_FRACTION",
    "V1_TIGHT_WINDOW_WIDTH_FRACTION",
    "VRPTWPerturbationSpec",
    "VRPTWPerturbedInstance",
    "apply_vrptw_perturbation",
    "enumerate_vrptw_perturbations",
    "lookup_vrptw_perturbation",
]
