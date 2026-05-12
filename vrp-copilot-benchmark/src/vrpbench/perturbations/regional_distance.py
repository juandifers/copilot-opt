"""Regional distance inflation perturbation.

Inflates pairwise distances whose edge touches a geographically-selected
"region" of the instance. Because CVRPLIB X instances store coordinates,
not an explicit distance matrix, the perturbed file is rewritten in
EXPLICIT / FULL_MATRIX form so that both backends (PyVRP and the cheap
ones) read exactly the same inflated distances.

Region selection rule (deterministic, locked):
  default := customers with x-coordinate strictly greater than median x.
  depot is never in the region.

Edge inflation rule:
  d'(i,j) = factor * d(i,j)      if i in region OR j in region
  d'(i,j) = d(i,j)               otherwise
  d'(i,i) = 0 always.

The result is a valid CVRPLIB-ish .vrp file with:
  EDGE_WEIGHT_TYPE : EXPLICIT
  EDGE_WEIGHT_FORMAT : FULL_MATRIX
  EDGE_WEIGHT_SECTION
followed by DEMAND_SECTION and DEPOT_SECTION.
NODE_COORD_SECTION is retained for downstream observability/debugging,
but the explicit matrix is what's used for routing.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..data.instance import VRPInstance, load_instance


def _euclidean_matrix(coords: np.ndarray) -> np.ndarray:
    diff = coords[:, None, :] - coords[None, :, :]
    return np.rint(np.sqrt((diff ** 2).sum(axis=-1))).astype(float)


def _select_region_customers(
    coords: np.ndarray,
    depot_index: int,
) -> list[int]:
    customer_idx = [i for i in range(coords.shape[0]) if i != depot_index]
    xs = coords[customer_idx, 0]
    median_x = float(np.median(xs))
    return [i for i in customer_idx if float(coords[i, 0]) > median_x]


def apply_regional_distance_inflation(
    instance: VRPInstance,
    factor: float,
    out_dir: Path,
    *,
    depot_index: int = 0,
) -> tuple[Path, dict]:
    """Produce a perturbed .vrp file with inflated distances in a region.

    Returns (perturbed_path, metadata_dict).
    """
    if factor < 1.0:
        raise ValueError(
            f"regional_distance_inflation factor must be >= 1.0; got {factor}"
        )

    raw = instance.raw
    if "node_coord" not in raw or raw["node_coord"] is None:
        raise ValueError(
            "regional_distance_inflation requires node coordinates; "
            f"instance {instance.instance_id} lacks node_coord."
        )

    coords = np.asarray(raw["node_coord"], dtype=float)
    n_nodes = coords.shape[0]
    base = _euclidean_matrix(coords)

    region = set(_select_region_customers(coords, depot_index))

    inflated = base.copy()
    for i in range(n_nodes):
        for j in range(n_nodes):
            if i == j:
                inflated[i, j] = 0.0
                continue
            if (i in region) or (j in region):
                inflated[i, j] = base[i, j] * factor
    inflated = np.rint(inflated).astype(int)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    factor_tag = str(factor).replace(".", "p")
    out_path = out_dir / f"{instance.instance_id}__regdist{factor_tag}.vrp"

    demand = np.asarray(raw["demand"], dtype=int)
    capacity = int(instance.capacity)
    name = f"{instance.instance_id}__regdist{factor_tag}"

    lines: list[str] = []
    lines.append(f"NAME : {name}")
    lines.append(
        f"COMMENT : \"Phase 2 perturbation: "
        f"regional_distance_inflation factor={factor}\""
    )
    lines.append("TYPE : CVRP")
    lines.append(f"DIMENSION : {n_nodes}")
    lines.append("EDGE_WEIGHT_TYPE : EXPLICIT")
    lines.append("EDGE_WEIGHT_FORMAT : FULL_MATRIX")
    lines.append(f"CAPACITY : {capacity}")
    lines.append("EDGE_WEIGHT_SECTION")
    for i in range(n_nodes):
        row = " ".join(str(int(inflated[i, j])) for j in range(n_nodes))
        lines.append(" " + row)
    lines.append("NODE_COORD_SECTION")
    for i in range(n_nodes):
        lines.append(f" {i + 1} {int(coords[i, 0])} {int(coords[i, 1])}")
    lines.append("DEMAND_SECTION")
    for i in range(n_nodes):
        lines.append(f" {i + 1} {int(demand[i])}")
    lines.append("DEPOT_SECTION")
    lines.append(f" {depot_index + 1}")
    lines.append(" -1")
    lines.append("EOF")

    out_path.write_text("\n".join(lines) + "\n")

    reloaded = load_instance(out_path)
    if reloaded.n_customers != instance.n_customers:
        raise RuntimeError("Regional distance rewrite changed n_customers.")

    metadata = {
        "factor": factor,
        "region_size": len(region),
        "region_rule": "x_gt_median_x",
        "edge_weight_type": "EXPLICIT",
    }
    return out_path, metadata
