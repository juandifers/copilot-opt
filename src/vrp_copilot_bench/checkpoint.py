"""Atomic per-action-run checkpoint store.

Layout::

    <checkpoint_dir>/
        X-n101-k25_CAP_1_reuse_direct.json
        X-n101-k25_CAP_1_nearest_neighbor.json
        ...
        _failures/
            X-n101-k25_CAP_4_pyvrp_60s.json   # only on failure

The store is the simplest thing that meets the runner's requirements: one
JSON file per ``(instance_id, perturbation_id, action)`` key, written
atomically via ``os.replace``. The aggregate Parquet is built only at the
end, never incrementally — concurrent writers would corrupt it.

``ActionRunKey`` lives here (rather than in ``work_plan``) because the
checkpoint module is the one that owns the on-disk format. ``work_plan``
re-exports it in Phase 2.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .actions import ACTIONS, ActionResult

log = logging.getLogger(__name__)

_FAILURE_SUBDIR = "_failures"
_TMP_SUFFIX = ".tmp"
_JSON_SUFFIX = ".json"


@dataclass(frozen=True)
class ActionRunKey:
    """Identifies a single action run.

    Note: this is *not* the cell-action key from the prereg. A cell-action
    is (instance, perturbation, action, claim_family); claim families are a
    labelling fan-out applied at consolidation time. One on-disk record
    backs four cell-action rows.
    """

    instance_id: str
    perturbation_id: str
    action: str

    def __post_init__(self) -> None:
        for name, value in (
            ("instance_id", self.instance_id),
            ("perturbation_id", self.perturbation_id),
            ("action", self.action),
        ):
            if not value:
                raise ValueError(f"ActionRunKey.{name} must be non-empty")
            if "/" in value or os.sep in value:
                raise ValueError(f"ActionRunKey.{name} must not contain path separators: {value!r}")
        if "_" in self.instance_id:
            # Single-underscore filename format relies on instance ids having
            # no underscores (hyphens are fine, e.g. ``X-n101-k25``). If that
            # ever changes we'd need a different delimiter.
            raise ValueError(
                f"instance_id must not contain '_' under the current filename "
                f"convention (got {self.instance_id!r})"
            )
        if self.action not in ACTIONS:
            raise ValueError(
                f"unknown action {self.action!r}; expected one of {ACTIONS}"
            )


# ---------------------------------------------------------------------------
# Filename serialisation


def _format_basename(key: ActionRunKey) -> str:
    return f"{key.instance_id}_{key.perturbation_id}_{key.action}{_JSON_SUFFIX}"


def _parse_basename(basename: str) -> ActionRunKey:
    """Inverse of :func:`_format_basename`.

    Parses by suffix-matching against the fixed :data:`ACTIONS` tuple, then
    rsplits the remainder once to recover ``instance_id`` and a
    ``FAMILY_INDEX`` perturbation id. This relies on the conventions checked
    in :meth:`ActionRunKey.__post_init__`.
    """
    if not basename.endswith(_JSON_SUFFIX):
        raise ValueError(f"not a checkpoint filename: {basename!r}")
    stem = basename[: -len(_JSON_SUFFIX)]

    # Try the longest action suffixes first so e.g. ``pyvrp_60s`` does not
    # get confused for an action whose name is a strict tail of another.
    for action in sorted(ACTIONS, key=len, reverse=True):
        suffix = f"_{action}"
        if stem.endswith(suffix):
            rest = stem[: -len(suffix)]
            try:
                instance_id, family, index = rest.rsplit("_", 2)
            except ValueError as exc:
                raise ValueError(
                    f"cannot parse perturbation segment from {basename!r}"
                ) from exc
            perturbation_id = f"{family}_{index}"
            return ActionRunKey(instance_id, perturbation_id, action)
    raise ValueError(f"no known action suffix in {basename!r}")


# ---------------------------------------------------------------------------
# Public API


def checkpoint_path(checkpoint_dir: Path, key: ActionRunKey) -> Path:
    """Path where a successful result for ``key`` is stored."""
    return checkpoint_dir / _format_basename(key)


def failure_path(checkpoint_dir: Path, key: ActionRunKey) -> Path:
    """Path where a failure record for ``key`` is stored."""
    return checkpoint_dir / _FAILURE_SUBDIR / _format_basename(key)


def has_checkpoint(checkpoint_dir: Path, key: ActionRunKey) -> bool:
    """True iff a successful checkpoint exists for ``key``.

    Failure records do *not* count — they should be retried.
    """
    return checkpoint_path(checkpoint_dir, key).is_file()


def save_result(checkpoint_dir: Path, key: ActionRunKey, result: ActionResult) -> None:
    """Atomically persist ``result`` for ``key``.

    Writes a sibling ``*.tmp.<pid>.<rand>`` file in the same directory,
    fsyncs, then ``os.replace``s it onto the final path. Concurrent calls
    for *different* keys are safe; concurrent calls for the *same* key
    leave one of the writes as the winner (last-writer-wins) but never a
    corrupt file.
    """
    target = checkpoint_path(checkpoint_dir, key)
    payload = result.to_dict()
    _atomic_write_json(target, payload)


def load_result(checkpoint_dir: Path, key: ActionRunKey) -> ActionResult:
    target = checkpoint_path(checkpoint_dir, key)
    with target.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return ActionResult.from_dict(payload)


def save_failure(checkpoint_dir: Path, key: ActionRunKey, exc: BaseException) -> None:
    """Record a failure so the runner doesn't loop on it.

    Stored as a JSON document with the exception class name and message.
    Atomic, like :func:`save_result`.
    """
    target = failure_path(checkpoint_dir, key)
    payload = {
        "instance_id": key.instance_id,
        "perturbation_id": key.perturbation_id,
        "action": key.action,
        "exception_class": type(exc).__name__,
        "message": str(exc),
    }
    _atomic_write_json(target, payload)


def list_completed(checkpoint_dir: Path) -> set[ActionRunKey]:
    """Return all keys with a *successful* checkpoint on disk.

    Tmp/partial files (``*.tmp.*``) and unparseable filenames are skipped.
    Failures live in a sibling subdir and are excluded.
    """
    if not checkpoint_dir.is_dir():
        return set()
    completed: set[ActionRunKey] = set()
    for entry in checkpoint_dir.iterdir():
        if not entry.is_file():
            continue
        if not entry.name.endswith(_JSON_SUFFIX):
            continue
        if _TMP_SUFFIX in entry.name:
            # Belt-and-braces: tmp files end with ``.tmp.<rand>`` and never
            # in ``.json``, but skip anything that looks partial.
            continue
        try:
            completed.add(_parse_basename(entry.name))
        except ValueError:
            log.warning("skipping unparseable checkpoint filename: %s", entry.name)
            continue
    return completed


def list_failures(checkpoint_dir: Path) -> dict[ActionRunKey, str]:
    """Return ``{key: exception_class}`` for every failure record on disk."""
    failures_dir = checkpoint_dir / _FAILURE_SUBDIR
    if not failures_dir.is_dir():
        return {}
    out: dict[ActionRunKey, str] = {}
    for entry in failures_dir.iterdir():
        if not entry.is_file() or not entry.name.endswith(_JSON_SUFFIX):
            continue
        if _TMP_SUFFIX in entry.name:
            continue
        try:
            key = _parse_basename(entry.name)
        except ValueError:
            log.warning("skipping unparseable failure filename: %s", entry.name)
            continue
        try:
            with entry.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            out[key] = str(payload.get("exception_class", "Unknown"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("failure record %s unreadable: %s", entry, exc)
            out[key] = "Unreadable"
    return out


# ---------------------------------------------------------------------------
# Helpers


def _atomic_write_json(target: Path, payload: dict) -> None:
    """Write ``payload`` to ``target`` atomically.

    Strategy: serialise to a tmp file in the *same directory* as ``target``
    so ``os.replace`` is a same-filesystem rename (atomic on macOS/Linux);
    fsync the file before the rename so the bytes are durable; fsync the
    directory so the rename itself is durable.
    """
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + _TMP_SUFFIX + ".",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True, separators=(",", ":"))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        # Best-effort cleanup; if the replace already happened the unlink
        # will simply fail and we ignore it.
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise

    # Make the rename itself durable. If this fsync fails (e.g. the FS
    # doesn't support directory fsync, as on some Windows setups), we don't
    # want to lose the data — log and continue.
    try:
        dir_fd = os.open(str(target.parent), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError as exc:  # pragma: no cover - platform-dependent
        log.debug("directory fsync failed for %s: %s", target.parent, exc)
    finally:
        os.close(dir_fd)


def iter_completed_paths(checkpoint_dir: Path) -> Iterable[Path]:
    """Yield paths of successful checkpoints, in arbitrary order.

    Used by the consolidation pass; included here to keep filename-format
    knowledge in one place.
    """
    if not checkpoint_dir.is_dir():
        return
    for entry in checkpoint_dir.iterdir():
        if (
            entry.is_file()
            and entry.name.endswith(_JSON_SUFFIX)
            and _TMP_SUFFIX not in entry.name
        ):
            yield entry
