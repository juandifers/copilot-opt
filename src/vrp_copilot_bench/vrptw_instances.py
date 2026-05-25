"""VRPTW Solomon-100 instance loader (Phase 1 probe only).

Parallel to :mod:`vrp_copilot_bench.instances`; lives outside the
preregistered CVRP pipeline. Reads ``.vrp`` files (CVRPLIB-extended
VRPTW format, ``TYPE : CVRPTW``) via :func:`vrplib.read_instance`.

The ``.vrp`` files on the PyVRP Instances mirror encode the original
Solomon-100 problems verbatim; ``vrplib`` returns one consistent dict
shape across the six probe instances. We do robust key extraction with
a small alias table so the loader degrades gracefully if a future
``vrplib`` release renames a field.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np


_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

#: Default directory for VRPTW ``.vrp`` files.
DEFAULT_VRPTW_INSTANCE_DIR: Path = _PROJECT_ROOT / "data" / "vrptw_instances"


@dataclass(frozen=True)
class VRPTWInstance:
    """A Solomon-style VRPTW instance.

    Indexing convention matches :class:`vrp_copilot_bench.instances.Instance`:
    the depot is at index 0 and customers occupy indices 1..n_customers.

    All arrays carry the depot row at index 0.
    Time windows and service times are in the units of the source file
    (no ×10 rescaling here — the wrapper applies that at solve time so
    raw inspection of a ``VRPTWInstance`` matches the published Solomon
    numbers).
    """

    instance_id: str
    n_customers: int
    capacity: int
    n_vehicles: int
    coords: np.ndarray          # shape (n+1, 2), float64
    demands: np.ndarray         # shape (n+1,),  int64
    service_times: np.ndarray   # shape (n+1,),  int64
    time_windows: np.ndarray    # shape (n+1, 2), int64 — [tw_early, tw_late]
    depot_index: int = 0


# ---------------------------------------------------------------------------
# Key-alias helpers (defensive against vrplib field renames)

_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "coords":       ("node_coord", "node_coords", "coords", "coord"),
    "demands":      ("demand", "demands"),
    "capacity":     ("capacity", "vehicle_capacity"),
    "vehicles":     ("vehicles", "num_vehicles", "n_vehicles", "fleet_size"),
    "service_time": ("service_time", "service_times"),
    "time_window":  ("time_window", "time_windows"),
}


def _pick(data: dict, logical_key: str):
    """Return ``data[alias]`` for the first matching alias, else raise."""
    for alias in _KEY_ALIASES[logical_key]:
        if alias in data:
            return data[alias]
    raise KeyError(
        f"vrplib payload is missing {logical_key!r} "
        f"(tried aliases {_KEY_ALIASES[logical_key]}); "
        f"available keys: {sorted(data)}"
    )


def _broadcast_to_per_node(value, n_nodes: int, *, depot_value: int = 0) -> np.ndarray:
    """Coerce a scalar-or-array field to an ``(n_nodes,)`` int64 array.

    Solomon files encode ``SERVICE_TIME`` as a single scalar in the
    CVRPLIB-extended ``.vrp`` re-encoding because every customer shares
    the same service duration. We expand it to one entry per node,
    forcing the depot's entry to ``depot_value`` (0 by default).
    """
    arr = np.asarray(value)
    if arr.ndim == 0:
        out = np.full(n_nodes, int(arr), dtype=np.int64)
    elif arr.ndim == 1:
        if arr.size != n_nodes:
            raise ValueError(
                f"expected {n_nodes} entries, got {arr.size}: {arr!r}"
            )
        out = arr.astype(np.int64, copy=False)
    else:
        raise ValueError(f"unexpected service-time shape {arr.shape}")
    out = out.copy()
    out[0] = depot_value
    return out


# ---------------------------------------------------------------------------
# Public API


def _instance_dir(override: Path | None = None) -> Path:
    if override is not None:
        return override
    env = os.environ.get("VRP_COPILOT_BENCH_VRPTW_INSTANCE_DIR")
    return Path(env) if env else DEFAULT_VRPTW_INSTANCE_DIR


def load_vrptw_instance(
    instance_id: str, instance_dir: Path | None = None
) -> VRPTWInstance:
    """Load a Solomon-style VRPTW instance from a ``.vrp`` file.

    Reads ``<instance_dir>/<instance_id>.vrp`` via :func:`vrplib.read_instance`
    in ``"vrplib"`` mode (the PyVRP mirror's CVRPLIB-extended VRPTW format).
    See module docstring for the rationale.

    Raises
    ------
    FileNotFoundError
        If the file is missing.
    KeyError
        If the vrplib payload is missing a required field.
    """
    import vrplib

    path = _instance_dir(instance_dir) / f"{instance_id}.vrp"
    if not path.exists():
        raise FileNotFoundError(
            f"VRPTW instance file not found: {path}. "
            f"Run scripts/download_vrptw_instances.py."
        )

    data = vrplib.read_instance(str(path), instance_format="vrplib")

    coords = np.asarray(_pick(data, "coords"), dtype=np.float64)
    if coords.ndim != 2 or coords.shape[1] != 2:
        raise ValueError(
            f"{instance_id}: unexpected coords shape {coords.shape}"
        )
    n_nodes = coords.shape[0]
    n_customers = n_nodes - 1

    demands = np.asarray(_pick(data, "demands"), dtype=np.int64).copy()
    if demands.shape != (n_nodes,):
        raise ValueError(
            f"{instance_id}: demands shape {demands.shape} does not match "
            f"({n_nodes},)"
        )
    demands[0] = 0  # depot demand is always zero

    capacity = int(_pick(data, "capacity"))
    n_vehicles = int(_pick(data, "vehicles"))

    service_times = _broadcast_to_per_node(
        _pick(data, "service_time"), n_nodes, depot_value=0,
    )

    time_windows = np.asarray(_pick(data, "time_window"), dtype=np.int64).copy()
    if time_windows.shape != (n_nodes, 2):
        raise ValueError(
            f"{instance_id}: time_window shape {time_windows.shape} does not "
            f"match ({n_nodes}, 2)"
        )

    return VRPTWInstance(
        instance_id=instance_id,
        n_customers=n_customers,
        capacity=capacity,
        n_vehicles=n_vehicles,
        coords=coords,
        demands=demands,
        service_times=service_times,
        time_windows=time_windows,
        depot_index=0,
    )
