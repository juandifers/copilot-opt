"""DEMAND perturbation family (prereg §6.3).

Inflates the demand of every customer in a baseline-route subset by a
factor of ``(1 + δ)``:

    new_demand[c] = round(old_demand[c] * (1 + δ))   for c in subset

The four perturbations differ in subset selection and δ:

- DEM_1, DEM_2: smallest baseline-route customer cluster (lowest customer count)
- DEM_3: median-cost baseline route
- DEM_4: highest-cost baseline route

Tie-breaking (where the spec is otherwise ambiguous): lowest baseline
route index wins. The route index is the position of the route in
``baseline.routes`` — the same key used by ``baseline.route_costs``.
"""
from __future__ import annotations

import logging

import numpy as np

from ...instances import Instance
from ...baselines import Solution
from .. import PerturbationSpec
from ..types import PerturbedInstance
from ._common import argmax_with_tiebreak, argmin_with_tiebreak

logger = logging.getLogger(__name__)


def apply_demand(
    instance: Instance,
    spec: PerturbationSpec,
    baseline: Solution | None = None,
) -> PerturbedInstance:
    """Realize a DEMAND perturbation.

    Raises
    ------
    ValueError
        If ``baseline is None`` (DEMAND requires a baseline solution to
        identify the subset of customers to inflate).
    ValueError
        If ``spec.perturbation_id`` is not one of DEM_1..DEM_4 or
        ``spec.family`` is not ``"DEMAND"``.
    """
    if spec.family != "DEMAND":
        raise ValueError(
            f"apply_demand requires a DEMAND spec, got {spec.family!r} "
            f"(perturbation_id={spec.perturbation_id!r})"
        )
    if baseline is None:
        raise ValueError(
            f"apply_demand requires a baseline solution for "
            f"{instance.instance_id!r} (perturbation_id={spec.perturbation_id!r})"
        )

    delta = float(spec.magnitude)
    route_index = _select_route_index(spec.perturbation_id, baseline)
    subset = list(baseline.routes[route_index])

    new_demands = instance.demands.copy()
    for c in subset:
        new_demands[c] = int(round(int(instance.demands[c]) * (1.0 + delta)))

    subset_demand_orig = int(instance.demands[subset].sum())
    total_demand_orig = int(instance.demands[1:].sum())
    affected_demand_share = (
        subset_demand_orig / total_demand_orig if total_demand_orig else 0.0
    )
    n_routes = len(baseline.routes)
    affected_route_share = 1.0 / n_routes if n_routes else 0.0

    return PerturbedInstance(
        instance_id=instance.instance_id,
        perturbation_id=spec.perturbation_id,
        perturbation_family="DEMAND",
        perturbation_magnitude=delta,
        n_customers=instance.n_customers,
        coords=instance.coords.copy(),
        demands=new_demands,
        capacity=instance.capacity,
        n_vehicles=instance.n_vehicles,
        distance_multiplier_mask=None,
        n_affected_customers=len(subset),
        affected_demand_share=affected_demand_share,
        affected_route_share=affected_route_share,
    )


def _select_route_index(perturbation_id: str, baseline: Solution) -> int:
    """Pick the baseline-route index to inflate, per prereg §6.3.

    Tie-breaks on lowest route index.
    """
    n_routes = len(baseline.routes)
    if n_routes == 0:
        raise ValueError(
            f"DEMAND perturbation needs at least one baseline route, got 0 "
            f"(instance_id={baseline.instance_id!r})"
        )

    if perturbation_id in ("DEM_1", "DEM_2"):
        # Smallest baseline-route customer cluster (lowest customer count).
        sizes = [len(r) for r in baseline.routes]
        return argmin_with_tiebreak(sizes)

    if perturbation_id == "DEM_3":
        # Median-cost route. Sort indices by cost ascending; take index n//2.
        # Stable sort + index-as-secondary-key keeps the tie-break deterministic.
        costs = [(baseline.route_costs[i], i) for i in range(n_routes)]
        costs.sort()
        return costs[n_routes // 2][1]

    if perturbation_id == "DEM_4":
        # Highest-cost route.
        costs = [baseline.route_costs[i] for i in range(n_routes)]
        return argmax_with_tiebreak(costs)

    raise ValueError(
        f"unknown DEMAND perturbation_id {perturbation_id!r}; "
        f"expected one of DEM_1..DEM_4"
    )
