"""Localized demand inflation perturbation (exploratory, Phase 2).

Multiplies the demand of a selected subset of customers by a factor,
leaving the rest of the instance (coordinates, distances, capacity)
intact. This isolates a local capacity squeeze without global
distortion.

Customer selection (deterministic, locked):
  default := top 10% highest-demand customers (ties broken by
             lowest customer index for determinism)
  fallback := if more than half of customers tie at the same top
              demand value, fall back to "top 10% farthest from
              depot" instead.

The perturbed instance is re-emitted in the original NODE_COORD form
so both backends read it identically.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ..data.instance import VRPInstance, load_instance


def _euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(((a - b) ** 2).sum()))


def _select_customers(
    demand: np.ndarray,
    coords: np.ndarray,
    depot_index: int,
    pct: float = 0.10,
) -> tuple[list[int], str]:
    customer_idx = [i for i in range(len(demand)) if i != depot_index]
    n_customers = len(customer_idx)
    k = max(1, int(math.ceil(pct * n_customers)))

    demands = [(float(demand[i]), i) for i in customer_idx]
    demands.sort(key=lambda t: (-t[0], t[1]))

    # Check tie-break degeneracy: if too many customers share the same top
    # demand, demand-based selection is effectively arbitrary — fall back
    # to farthest-from-depot selection.
    top_value = demands[0][0]
    ties = sum(1 for d, _ in demands if d == top_value)
    if ties > n_customers // 2:
        depot_xy = coords[depot_index]
        dist_idx = [
            (_euclidean_distance(coords[i], depot_xy), i) for i in customer_idx
        ]
        dist_idx.sort(key=lambda t: (-t[0], t[1]))
        chosen = [i for _, i in dist_idx[:k]]
        return chosen, "top_pct_farthest_from_depot"

    chosen = [i for _, i in demands[:k]]
    return chosen, "top_pct_highest_demand"


def apply_localized_demand_inflation(
    instance: VRPInstance,
    factor: float,
    out_dir: Path,
    *,
    depot_index: int = 0,
    pct: float = 0.10,
) -> tuple[Path, dict]:
    if factor <= 1.0:
        raise ValueError(
            f"localized_demand_inflation factor must be > 1.0; got {factor}"
        )

    raw = instance.raw
    if "demand" not in raw or "node_coord" not in raw:
        raise ValueError(
            "localized_demand_inflation requires demand and node_coord."
        )

    coords = np.asarray(raw["node_coord"], dtype=float)
    demand = np.asarray(raw["demand"], dtype=float).copy()
    n_nodes = coords.shape[0]
    capacity = float(instance.capacity)

    chosen, rule = _select_customers(demand, coords, depot_index, pct=pct)
    for i in chosen:
        new_d = float(round(demand[i] * factor))
        # Keep the perturbation physically realizable: no single customer
        # may exceed capacity (routing would be trivially infeasible).
        if new_d > capacity:
            new_d = capacity
        demand[i] = new_d

    demand_int = demand.astype(int)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    factor_tag = str(factor).replace(".", "p")
    out_path = out_dir / f"{instance.instance_id}__locdem{factor_tag}.vrp"

    lines: list[str] = []
    name = f"{instance.instance_id}__locdem{factor_tag}"
    lines.append(f"NAME : {name}")
    lines.append(
        f"COMMENT : \"Phase 2 exploratory perturbation: "
        f"localized_demand_inflation factor={factor} rule={rule}\""
    )
    lines.append("TYPE : CVRP")
    lines.append(f"DIMENSION : {n_nodes}")
    lines.append("EDGE_WEIGHT_TYPE : EUC_2D")
    lines.append(f"CAPACITY : {int(capacity)}")
    lines.append("NODE_COORD_SECTION")
    for i in range(n_nodes):
        lines.append(f" {i + 1} {int(coords[i, 0])} {int(coords[i, 1])}")
    lines.append("DEMAND_SECTION")
    for i in range(n_nodes):
        lines.append(f" {i + 1} {int(demand_int[i])}")
    lines.append("DEPOT_SECTION")
    lines.append(f" {depot_index + 1}")
    lines.append(" -1")
    lines.append("EOF")

    out_path.write_text("\n".join(lines) + "\n")

    reloaded = load_instance(out_path)
    if reloaded.n_customers != instance.n_customers:
        raise RuntimeError(
            "Localized-demand rewrite changed n_customers."
        )

    metadata = {
        "factor": factor,
        "selected_count": len(chosen),
        "selection_rule": rule,
        "pct": pct,
    }
    return out_path, metadata
