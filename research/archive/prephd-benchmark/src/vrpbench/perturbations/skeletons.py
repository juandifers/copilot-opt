"""Skeletons for additional perturbation families (Phase 1 non-goal).

These are intentionally minimal: they define the interface but are not
wired into the pilot experiment. Enabling them is gated on a PROCEED
decision plus a dedicated activation-screening pass.
"""
from __future__ import annotations

from pathlib import Path

from ..data.instance import VRPInstance


def apply_demand_scaling(
    instance: VRPInstance,
    factor: float,
    out_dir: Path,
) -> Path:
    """Scale every customer demand by `factor` (>1 tightens capacity, <1 loosens).

    NOT IMPLEMENTED in Phase 1. Raises to prevent accidental silent activation.
    """
    raise NotImplementedError(
        "demand_scaling perturbation is a skeleton; do not use in Phase 1."
    )


def apply_distance_inflation(
    instance: VRPInstance,
    factor: float,
    out_dir: Path,
) -> Path:
    """Multiply every pairwise distance by `factor` (>1 inflates).

    NOT IMPLEMENTED in Phase 1. Raises to prevent accidental silent activation.
    """
    raise NotImplementedError(
        "distance_inflation perturbation is a skeleton; do not use in Phase 1."
    )
