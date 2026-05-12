"""``PerturbedInstance`` — output type of every perturbation realization.

A :class:`PerturbedInstance` mirrors :class:`vrp_copilot_bench.instances.Instance`
with potentially modified scalar/vector fields, plus diagnostic metadata that
flows into the parquet schema (prereg §4.1: ``perturbation_family``,
``perturbation_magnitude``, ``n_affected_customers``, ``affected_demand_share``,
``affected_route_share``).

Field naming follows :class:`Instance` (``coords``, ``demands``, ``capacity``,
``n_vehicles``) so that an action wrapper can compute distances and dispatch
to PyVRP from a ``PerturbedInstance`` the same way it does from an
``Instance``.

DISTANCE perturbations leave coords/demands alone and instead populate
``distance_multiplier_mask`` — an ``(n+1, n+1)`` array applied element-wise
to the Euclidean distance matrix at solve time. Other families set the mask
to ``None``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PerturbedInstance:
    """An instance with one perturbation applied.

    Coordinates and demands always include the depot at index 0.
    ``coords`` has shape ``(n_customers + 1, 2)``; ``demands`` has shape
    ``(n_customers + 1,)`` with ``demands[0] == 0``.

    For INSERTION perturbations, ``n_customers`` exceeds the source
    instance's customer count; the new customers occupy the trailing
    indices of ``coords`` / ``demands``.

    ``distance_multiplier_mask`` is an ``(n_customers + 1, n_customers + 1)``
    float array (default 1.0 entries) that DISTANCE perturbations populate.
    The mask is symmetric and equal to ``None`` when no scaling is applied,
    so action wrappers can short-circuit the multiply.
    """

    instance_id: str
    perturbation_id: str
    perturbation_family: str  # "CAPACITY" / "DISTANCE" / "DEMAND" / "INSERTION"
    perturbation_magnitude: float

    n_customers: int
    coords: np.ndarray  # (n_customers + 1, 2)
    demands: np.ndarray  # (n_customers + 1,)
    capacity: int
    n_vehicles: int

    distance_multiplier_mask: np.ndarray | None  # (n_customers + 1, n_customers + 1) or None

    n_affected_customers: int
    affected_demand_share: float
    affected_route_share: float
