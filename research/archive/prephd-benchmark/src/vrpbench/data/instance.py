"""Instance loading and registry construction."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vrplib

logger = logging.getLogger(__name__)


@dataclass
class VRPInstance:
    instance_id: str
    path: Path
    raw: dict[str, Any]
    n_customers: int
    capacity: float
    has_coords: bool
    has_demand: bool
    edge_weight_type: str
    k_min: int | None
    bks_objective: float | None = None
    bks_routes: list[list[int]] | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def n_nodes(self) -> int:
        """Nodes including depot."""
        return self.n_customers + 1


def _extract_k_from_name(name: str) -> int | None:
    """Pull the 'k<int>' hint from a CVRPLIB X name like 'X-n101-k25'."""
    import re
    m = re.search(r"-k(\d+)", name)
    return int(m.group(1)) if m else None


def load_instance(vrp_path: Path) -> VRPInstance:
    vrp_path = Path(vrp_path)
    raw = vrplib.read_instance(str(vrp_path))
    warnings_: list[str] = []

    dim = raw.get("dimension")
    if dim is None:
        raise ValueError(f"{vrp_path.name}: missing DIMENSION")
    n_customers = int(dim) - 1  # depot excluded

    capacity = raw.get("capacity")
    if capacity is None:
        warnings_.append("missing CAPACITY")
        capacity = float("nan")

    has_coords = "node_coord" in raw and raw["node_coord"] is not None
    has_demand = "demand" in raw and raw["demand"] is not None
    if not has_coords:
        warnings_.append("missing node coords")
    if not has_demand:
        warnings_.append("missing demand")

    ewt = raw.get("edge_weight_type", "UNKNOWN")
    k_hint = _extract_k_from_name(vrp_path.stem)

    # Best Known Solution (optional)
    bks_objective: float | None = None
    bks_routes: list[list[int]] | None = None
    sol_path = vrp_path.with_suffix(".sol")
    if sol_path.exists():
        try:
            sol = vrplib.read_solution(str(sol_path))
            bks_routes = [list(r) for r in sol.get("routes", [])]
            if "cost" in sol and sol["cost"] is not None:
                bks_objective = float(sol["cost"])
        except Exception as e:  # solution files can be messy
            warnings_.append(f".sol unreadable: {e}")

    return VRPInstance(
        instance_id=vrp_path.stem,
        path=vrp_path,
        raw=raw,
        n_customers=n_customers,
        capacity=float(capacity),
        has_coords=has_coords,
        has_demand=has_demand,
        edge_weight_type=str(ewt),
        k_min=k_hint,
        bks_objective=bks_objective,
        bks_routes=bks_routes,
        warnings=warnings_,
    )


def build_registry(raw_dir: Path) -> pd.DataFrame:
    raw_dir = Path(raw_dir)
    rows: list[dict] = []
    vrp_files = sorted(raw_dir.glob("*.vrp"))
    logger.info("Found %d .vrp files under %s", len(vrp_files), raw_dir)

    for p in vrp_files:
        try:
            inst = load_instance(p)
            rows.append({
                "instance_id": inst.instance_id,
                "path": str(p),
                "n_customers": inst.n_customers,
                "n_nodes": inst.n_nodes,
                "capacity": inst.capacity,
                "has_coords": inst.has_coords,
                "has_demand": inst.has_demand,
                "edge_weight_type": inst.edge_weight_type,
                "k_min_hint": inst.k_min,
                "bks_objective": inst.bks_objective,
                "bks_routes_available": inst.bks_routes is not None,
                "parse_ok": True,
                "warnings": "; ".join(inst.warnings),
            })
        except Exception as e:
            logger.error("Failed to parse %s: %s", p, e)
            rows.append({
                "instance_id": p.stem,
                "path": str(p),
                "n_customers": None,
                "n_nodes": None,
                "capacity": None,
                "has_coords": False,
                "has_demand": False,
                "edge_weight_type": None,
                "k_min_hint": None,
                "bks_objective": None,
                "bks_routes_available": False,
                "parse_ok": False,
                "warnings": f"parse failure: {e}",
            })

    df = pd.DataFrame(rows).sort_values("instance_id").reset_index(drop=True)
    return df


def stratify(df: pd.DataFrame) -> pd.DataFrame:
    """Attach small/medium/large bin labels based on n_customers."""
    def label(n):
        if n is None or (isinstance(n, float) and np.isnan(n)):
            return "invalid"
        if 100 <= n <= 150:
            return "small"
        if 150 < n <= 200:
            return "medium"
        if 200 < n <= 250:
            return "large"
        return "out_of_range"
    out = df.copy()
    out["bin_label"] = out["n_customers"].map(label)
    return out
