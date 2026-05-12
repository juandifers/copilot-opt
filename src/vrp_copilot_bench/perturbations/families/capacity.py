"""CAPACITY perturbation family (prereg §6.1).

Reduces the vehicle capacity by a fractional amount ρ:

    new_capacity = round(capacity * (1 - ρ))

Coordinates, demands, and the customer set are unchanged. CAP_1..CAP_4
differ only in ρ ∈ {0.02, 0.05, 0.10, 0.20}.
"""
from __future__ import annotations

import logging

import numpy as np

from ...instances import Instance
from ...baselines import Solution
from .. import PerturbationSpec
from ..types import PerturbedInstance

logger = logging.getLogger(__name__)


def apply_capacity(
    instance: Instance,
    spec: PerturbationSpec,
    baseline: Solution | None = None,
) -> PerturbedInstance:
    """Realize a CAPACITY perturbation.

    The new capacity is ``round(capacity * (1 - ρ))``, where ρ is the
    spec's magnitude. Rounding uses banker's rounding (Python's built-in)
    after coercing through ``int``; on the Uchoa-X integer-capacity inputs
    the magnitudes 0.02/0.05/0.10/0.20 produce stable integer results.

    Coordinates, demands, customer count, and vehicle count are copied
    verbatim from ``instance``. The distance multiplier mask is ``None``.

    Diagnostic metadata:
      - ``n_affected_customers = 0``
      - ``affected_demand_share = 0.0``
      - ``affected_route_share`` = fraction of baseline routes whose load
        exceeds the new capacity. Requires ``baseline`` to compute; if
        ``baseline is None`` the field is set to ``0.0`` and a debug-level
        message is logged. (Prereg §4.1's diagnostic columns are nullable
        in spirit; we use 0.0 as the no-baseline sentinel for parquet
        compatibility, since these are float columns.)
    """
    if spec.family != "CAPACITY":
        raise ValueError(
            f"apply_capacity requires a CAPACITY spec, got {spec.family!r} "
            f"(perturbation_id={spec.perturbation_id!r})"
        )

    rho = float(spec.magnitude)
    new_capacity = int(round(instance.capacity * (1.0 - rho)))

    if baseline is not None:
        loads = _route_loads(baseline.routes, instance.demands)
        n_routes = len(loads)
        n_overloaded = int(np.sum(loads > new_capacity))
        affected_route_share = n_overloaded / n_routes if n_routes else 0.0
    else:
        logger.debug(
            "apply_capacity called without baseline for %s; affected_route_share=0.0",
            instance.instance_id,
        )
        affected_route_share = 0.0

    return PerturbedInstance(
        instance_id=instance.instance_id,
        perturbation_id=spec.perturbation_id,
        perturbation_family="CAPACITY",
        perturbation_magnitude=rho,
        n_customers=instance.n_customers,
        coords=instance.coords.copy(),
        demands=instance.demands.copy(),
        capacity=new_capacity,
        n_vehicles=instance.n_vehicles,
        distance_multiplier_mask=None,
        n_affected_customers=0,
        affected_demand_share=0.0,
        affected_route_share=affected_route_share,
    )


def _route_loads(routes: list[list[int]], demands: np.ndarray) -> np.ndarray:
    """Return the total demand carried by each route, in route order."""
    return np.array([int(demands[r].sum()) for r in routes], dtype=np.int64)
