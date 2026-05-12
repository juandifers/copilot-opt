"""Customer insertion perturbation (exploratory, Phase 2).

Adds a small number of new customers to an instance, placed deterministically
near the densest existing cluster (fallback: the centroid of the
regional-distance selection region). Each inserted customer has a demand
equal to the median positive demand of the original instance and
coordinates offset from the chosen centroid by a deterministic pattern.

This family changes the instance DIMENSION, which is why it is flagged
exploratory: comparisons across n_customers values are not apples-to-apples
with capacity / regional_distance scenarios.

Deterministic offsets: the new customers are placed on a small square grid
surrounding the centroid at radius 25 units (EUC_2D), assigned stable
offsets in (dx, dy) pairs. Customer indices continue after the last
existing node id.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ..data.instance import VRPInstance, load_instance


# Deterministic offsets: up to 12 positions around a centroid.
_DETERMINISTIC_OFFSETS: list[tuple[int, int]] = [
    (30, 0), (-30, 0), (0, 30), (0, -30),
    (25, 25), (-25, 25), (25, -25), (-25, -25),
    (45, 10), (-45, 10), (10, 45), (-10, -45),
]


def _densest_cluster_centroid(
    coords: np.ndarray,
    depot_index: int,
) -> np.ndarray:
    """Pick the centroid of the half-space x > median_x, i.e. the same
    region used by regional_distance_inflation. This keeps the insertion
    location aligned with the perturbation geography.

    Concretely: centroid of customers with x > median_x.
    Fallback: overall customer centroid if the region is empty.
    """
    customer_idx = [i for i in range(coords.shape[0]) if i != depot_index]
    xs = coords[customer_idx, 0]
    median_x = float(np.median(xs))
    region = [i for i in customer_idx if float(coords[i, 0]) > median_x]
    if region:
        pts = coords[region]
    else:
        pts = coords[customer_idx]
    return pts.mean(axis=0)


def apply_customer_insertion(
    instance: VRPInstance,
    count: int,
    out_dir: Path,
    *,
    depot_index: int = 0,
) -> tuple[Path, dict]:
    if count < 1:
        raise ValueError(f"count must be >= 1; got {count}")
    if count > len(_DETERMINISTIC_OFFSETS):
        raise ValueError(
            f"count {count} exceeds deterministic offset pool "
            f"({len(_DETERMINISTIC_OFFSETS)})"
        )

    raw = instance.raw
    if "demand" not in raw or "node_coord" not in raw:
        raise ValueError("customer_insertion requires demand and node_coord.")

    coords = np.asarray(raw["node_coord"], dtype=float)
    demand = np.asarray(raw["demand"], dtype=float)
    capacity = float(instance.capacity)
    n_nodes = coords.shape[0]

    # Median positive demand — note demand[depot] is normally 0, so we
    # filter strictly positive values before taking the median.
    positive_demand = [float(d) for d in demand if d > 0]
    if not positive_demand:
        raise ValueError("No positive demand in instance; cannot insert customers.")
    med = float(np.median(positive_demand))
    insert_demand = int(round(med))
    if insert_demand <= 0:
        insert_demand = 1
    if insert_demand > capacity:
        insert_demand = int(capacity)

    centroid = _densest_cluster_centroid(coords, depot_index)
    new_coords = []
    for i in range(count):
        dx, dy = _DETERMINISTIC_OFFSETS[i]
        new_coords.append((int(round(centroid[0] + dx)),
                           int(round(centroid[1] + dy))))

    combined_coords = np.vstack([coords, np.array(new_coords, dtype=float)])
    combined_demand = np.concatenate([demand, np.full(count, insert_demand, dtype=float)])
    new_n_nodes = n_nodes + count

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{instance.instance_id}__insert{count}.vrp"

    name = f"{instance.instance_id}__insert{count}"
    lines: list[str] = []
    lines.append(f"NAME : {name}")
    lines.append(
        f"COMMENT : \"Phase 2 exploratory perturbation: "
        f"customer_insertion count={count} demand={insert_demand}\""
    )
    lines.append("TYPE : CVRP")
    lines.append(f"DIMENSION : {new_n_nodes}")
    lines.append("EDGE_WEIGHT_TYPE : EUC_2D")
    lines.append(f"CAPACITY : {int(capacity)}")
    lines.append("NODE_COORD_SECTION")
    for i in range(new_n_nodes):
        lines.append(
            f" {i + 1} {int(combined_coords[i, 0])} {int(combined_coords[i, 1])}"
        )
    lines.append("DEMAND_SECTION")
    for i in range(new_n_nodes):
        lines.append(f" {i + 1} {int(combined_demand[i])}")
    lines.append("DEPOT_SECTION")
    lines.append(f" {depot_index + 1}")
    lines.append(" -1")
    lines.append("EOF")

    out_path.write_text("\n".join(lines) + "\n")

    reloaded = load_instance(out_path)
    if reloaded.n_customers != instance.n_customers + count:
        raise RuntimeError("Customer insertion did not change n_customers as expected.")

    metadata = {
        "count": count,
        "insert_demand": insert_demand,
        "centroid_x": float(centroid[0]),
        "centroid_y": float(centroid[1]),
    }
    return out_path, metadata
