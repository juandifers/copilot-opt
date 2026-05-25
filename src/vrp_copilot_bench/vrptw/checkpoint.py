"""On-disk checkpoint store for Stage A VRPTW runs.

The store is keyed by ``(instance, perturbation [, seed] [, action])``. Workers
check the appropriate key before computing; on hit they short-circuit. On miss
they compute and persist the result. Failures (exceptions raised inside a
worker) are recorded once per key under ``_failures/`` and never auto-retried.

Layout::

    <root>/
      refs/<iid>__<pid>__seed<s>.json     VRPTWSolveResult per (cell, seed)
      pyvrp10s/<iid>__<pid>.json          VRPTWSolveResult per cell
      rows/<iid>__<pid>__<action>.json    wide-row dict per (cell, action)
      _failures/<phase>__<key>.json       failure record per failed key
      manifest.json                       run configuration snapshot

The JSON encoder converts numpy scalars and tuple-keyed dicts to native Python
types so the files round-trip cleanly. Dict-of-int keys are encoded as strings
(per JSON spec) and converted back on read.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import logging
import traceback
from pathlib import Path
from typing import Any

import numpy as np

from ..solvers.pyvrp_vrptw_wrapper import (
    RouteSummary,
    VRPTWSolveResult,
    VisitSchedule,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON I/O


class _Encoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:  # noqa: D401
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if isinstance(o, Path):
            return str(o)
        return super().default(o)


def _write_json(path: Path, obj: Any) -> None:
    """Atomic JSON write (write to .tmp then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump(obj, f, cls=_Encoder)
    tmp.replace(path)


def _read_json(path: Path) -> Any:
    with path.open("r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# VRPTWSolveResult round-trip


def _int_keyed(d: dict[Any, Any]) -> dict[int, Any]:
    return {int(k): v for k, v in d.items()}


def _solve_result_to_payload(r: VRPTWSolveResult) -> dict[str, Any]:
    return dataclasses.asdict(r)


def _solve_result_from_payload(d: dict[str, Any]) -> VRPTWSolveResult:
    route_summaries = [
        RouteSummary(**rs) for rs in d.get("route_summaries", [])
    ]
    per_customer_schedule = {
        int(k): VisitSchedule(**v)
        for k, v in d.get("per_customer_schedule", {}).items()
    }
    return VRPTWSolveResult(
        objective=float(d["objective"]),
        feasible=bool(d["feasible"]),
        routes=[list(map(int, r)) for r in d["routes"]],
        assignment=_int_keyed(d["assignment"]),
        route_costs={int(k): float(v) for k, v in d["route_costs"].items()},
        runtime_seconds=float(d["runtime_seconds"]),
        pyvrp_version=str(d["pyvrp_version"]),
        n_routes=int(d["n_routes"]),
        total_duration=(
            float(d["total_duration"]) if d.get("total_duration") is not None else None
        ),
        route_summaries=route_summaries,
        per_customer_schedule=per_customer_schedule,
    )


# ---------------------------------------------------------------------------
# Store


class CheckpointStore:
    """Per-key cache + failure log on disk.

    Construct with the root directory; use ``mkdir`` to create the layout.
    All read methods return ``None`` on miss so callers can treat the cache
    as a transparent layer.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.refs_dir = self.root / "refs"
        self.pyvrp10s_dir = self.root / "pyvrp10s"
        self.rows_dir = self.root / "rows"
        self.failures_dir = self.root / "_failures"

    def mkdir(self) -> None:
        for d in (self.refs_dir, self.pyvrp10s_dir, self.rows_dir, self.failures_dir):
            d.mkdir(parents=True, exist_ok=True)

    # --- manifest / stats -------------------------------------------------

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        _write_json(self.root / "manifest.json", manifest)

    def write_stats(self, stats: dict[str, Any]) -> None:
        _write_json(self.root / "stats.json", stats)

    def read_stats(self) -> dict[str, Any] | None:
        path = self.root / "stats.json"
        if not path.exists():
            return None
        return _read_json(path)

    # --- references -------------------------------------------------------

    def _ref_path(self, iid: str, pid: str, seed: int) -> Path:
        return self.refs_dir / f"{iid}__{pid}__seed{int(seed)}.json"

    def load_ref(self, iid: str, pid: str, seed: int) -> VRPTWSolveResult | None:
        path = self._ref_path(iid, pid, seed)
        if not path.exists():
            return None
        try:
            return _solve_result_from_payload(_read_json(path))
        except Exception as exc:  # pragma: no cover — defensive
            log.warning("Corrupt ref checkpoint %s: %s — ignoring", path, exc)
            return None

    def save_ref(self, iid: str, pid: str, seed: int, result: VRPTWSolveResult) -> None:
        _write_json(self._ref_path(iid, pid, seed), _solve_result_to_payload(result))

    # --- pyvrp_10s --------------------------------------------------------

    def _py10s_path(self, iid: str, pid: str) -> Path:
        return self.pyvrp10s_dir / f"{iid}__{pid}.json"

    def load_pyvrp10s(self, iid: str, pid: str) -> VRPTWSolveResult | None:
        path = self._py10s_path(iid, pid)
        if not path.exists():
            return None
        try:
            return _solve_result_from_payload(_read_json(path))
        except Exception as exc:  # pragma: no cover — defensive
            log.warning("Corrupt pyvrp10s checkpoint %s: %s — ignoring", path, exc)
            return None

    def save_pyvrp10s(self, iid: str, pid: str, result: VRPTWSolveResult) -> None:
        _write_json(self._py10s_path(iid, pid), _solve_result_to_payload(result))

    # --- rows -------------------------------------------------------------

    def _row_path(self, iid: str, pid: str, action: str) -> Path:
        return self.rows_dir / f"{iid}__{pid}__{action}.json"

    def load_row(self, iid: str, pid: str, action: str) -> dict[str, Any] | None:
        path = self._row_path(iid, pid, action)
        if not path.exists():
            return None
        try:
            return _read_json(path)
        except Exception as exc:  # pragma: no cover — defensive
            log.warning("Corrupt row checkpoint %s: %s — ignoring", path, exc)
            return None

    def save_row(self, iid: str, pid: str, action: str, row: dict[str, Any]) -> None:
        _write_json(self._row_path(iid, pid, action), row)

    # --- failures ---------------------------------------------------------

    def has_failure(
        self, phase: str, iid: str, pid: str,
        seed: int | None = None, action: str | None = None,
    ) -> bool:
        return self._failure_path(phase, iid, pid, seed, action).exists()

    def _failure_path(
        self, phase: str, iid: str, pid: str,
        seed: int | None, action: str | None,
    ) -> Path:
        parts = [phase, iid, pid]
        if seed is not None:
            parts.append(f"seed{int(seed)}")
        if action is not None:
            parts.append(action)
        return self.failures_dir / ("__".join(parts) + ".json")

    def save_failure(
        self, phase: str, iid: str, pid: str, *,
        seed: int | None = None, action: str | None = None,
        exc: BaseException,
    ) -> Path:
        record = {
            "phase": phase,
            "instance_id": iid,
            "perturbation_id": pid,
            "seed": seed,
            "action": action,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": "".join(traceback.format_exception(exc)),
            "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        path = self._failure_path(phase, iid, pid, seed, action)
        _write_json(path, record)
        return path

    def list_failures(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.failures_dir.exists():
            return out
        for p in sorted(self.failures_dir.glob("*.json")):
            try:
                out.append(_read_json(p))
            except Exception as exc:  # pragma: no cover — defensive
                log.warning("Corrupt failure record %s: %s", p, exc)
        return out


__all__ = ["CheckpointStore"]
