"""Instance loader: PyVRP-backed parser for CVRPLIB X-set instances.

Reads ``.vrp`` files from ``data/instances/`` and converts them into the
project's :class:`Instance` dataclass via ``pyvrp.read``. The Stage A
roster is stored in ``instances/stage_a_instances.txt`` (one ID per line),
written by ``scripts/select_instances.py`` (prereg §5.1). The roster file
is the source of truth — :func:`list_stage_a_instances` re-reads it on
every call.

Default paths are anchored to the project root via ``__file__``. Tests and
external callers can override per call (``instance_dir=``, ``roster_path=``)
or via environment variables (``VRP_COPILOT_BENCH_INSTANCE_DIR``,
``VRP_COPILOT_BENCH_ROSTER_PATH``).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

# pyvrp.read is a compiled module — imported lazily inside load_instance
# so that work_plan / runner code paths that don't actually load instances
# (dry-run, enumeration, sorting) don't pay the import cost.

_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

#: Default directory for CVRPLIB ``.vrp`` files.
DEFAULT_INSTANCE_DIR: Path = _PROJECT_ROOT / "data" / "instances"

#: Default path for the Stage A roster.
DEFAULT_ROSTER_PATH: Path = _PROJECT_ROOT / "instances" / "stage_a_instances.txt"

_UCHOA_ID_RE = re.compile(r"^X-n(\d+)-k\d+$")


def _instance_dir(override: Path | None = None) -> Path:
    if override is not None:
        return override
    env = os.environ.get("VRP_COPILOT_BENCH_INSTANCE_DIR")
    return Path(env) if env else DEFAULT_INSTANCE_DIR


def _roster_path(override: Path | None = None) -> Path:
    if override is not None:
        return override
    env = os.environ.get("VRP_COPILOT_BENCH_ROSTER_PATH")
    return Path(env) if env else DEFAULT_ROSTER_PATH


@dataclass(frozen=True)
class Instance:
    """A CVRP instance.

    Coordinates and demands include the depot at index 0; customers are at
    indices 1..n_customers. ``coords`` has shape ``(n_customers + 1, 2)``;
    ``demands`` has shape ``(n_customers + 1,)`` with ``demands[0] == 0``.
    Distances are computed downstream as needed (typically Euclidean).
    """

    instance_id: str
    n_customers: int
    capacity: int
    n_vehicles: int
    coords: np.ndarray
    demands: np.ndarray
    depot_index: int = 0


def list_stage_a_instances(*, roster_path: Path | None = None) -> list[str]:
    """Read the Stage A roster from disk.

    File format: one instance ID per line; blank lines and lines starting
    with ``#`` are ignored. Order is preserved.

    Raises
    ------
    FileNotFoundError
        If the roster file does not exist.
    ValueError
        If the file exists but contains no valid IDs.
    """
    p = _roster_path(roster_path)
    if not p.exists():
        raise FileNotFoundError(
            f"Stage A roster not found at {p}. "
            f"Run scripts/select_instances.py to generate it (prereg §5.1)."
        )
    ids: list[str] = []
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ids.append(line)
    if not ids:
        raise ValueError(f"Stage A roster at {p} contains no instance IDs.")
    return ids


@lru_cache(maxsize=None)
def n_customers_for(instance_id: str) -> int:
    """Parse customer count from the Uchoa-X id.

    ``X-n101-k25`` → 100 (1 depot + 100 customers). Pure name parsing;
    does not load the instance file.
    """
    m = _UCHOA_ID_RE.match(instance_id)
    if not m:
        raise ValueError(
            f"cannot parse customer count from non-Uchoa-X id: {instance_id!r}"
        )
    return int(m.group(1)) - 1


def load_instance(instance_id: str, *, instance_dir: Path | None = None) -> Instance:
    """Load a CVRPLIB X-set instance via PyVRP's parser.

    Reads ``<instance_dir>/<instance_id>.vrp`` with ``round_func='round'``
    (matching standard CVRPLIB integer-distance conventions) and converts
    the resulting :class:`pyvrp._pyvrp.ProblemData` into :class:`Instance`.

    Raises
    ------
    FileNotFoundError
        If the ``.vrp`` file is missing — points to the download script.
    ValueError
        If the parsed problem has unexpected structure (multiple depots,
        non-CVRP fields, etc.).
    """
    from pyvrp import read

    path = _instance_dir(instance_dir) / f"{instance_id}.vrp"
    if not path.exists():
        raise FileNotFoundError(
            f"instance file not found: {path}. "
            f"Run scripts/download_instances.py to fetch the X-set."
        )

    data = read(str(path), round_func="round")

    if data.num_depots != 1:
        raise ValueError(
            f"{instance_id}: expected exactly 1 depot, got {data.num_depots}"
        )
    n_customers = data.num_clients

    coords = np.zeros((n_customers + 1, 2), dtype=np.float64)
    demands = np.zeros(n_customers + 1, dtype=np.int64)
    depot = data.location(0)
    coords[0] = (depot.x, depot.y)
    for i in range(n_customers):
        client = data.location(i + 1)
        coords[i + 1] = (client.x, client.y)
        demands[i + 1] = int(client.delivery[0])

    vehicle_types = list(data.vehicle_types())
    if len(vehicle_types) != 1:
        raise ValueError(
            f"{instance_id}: expected exactly 1 vehicle type, got {len(vehicle_types)}"
        )
    vt = vehicle_types[0]
    capacity = int(vt.capacity[0])
    n_vehicles = int(vt.num_available)

    return Instance(
        instance_id=instance_id,
        n_customers=n_customers,
        capacity=capacity,
        n_vehicles=n_vehicles,
        coords=coords,
        demands=demands,
        depot_index=0,
    )
