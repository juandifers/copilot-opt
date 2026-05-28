#!/usr/bin/env python3
"""Compute PyVRP 60s seed=1 baselines for all Stage A instances.

Runs PyVRP on each of the 68 instances listed in
``instances/stage_a_instances.txt`` (prereg §5.1) at the locked
reference protocol (PyVRP 60s, seed=1, single-threaded; prereg §7
``pyvrp_60s`` action and §8.1 primary reference) and caches each result
as a JSON file at ``data/baselines/<instance_id>.json``.

The script is **idempotent** and **resumable**:

- Instances that already have a cache file are skipped (``--force`` to
  recompute anyway).
- If interrupted mid-run, re-invoking picks up where it stopped — only
  the missing instances are computed.
- Per-instance failures are isolated: an exception in one instance does
  not abort the others. Failures are logged; no partial cache file is
  written.

Canonical-cache warning
-----------------------
Baseline solutions are noise-bounded by PyVRP's wall-clock-budgeted
search (~2 % objective stability per prereg §8.2) and are cached as
**canonical artifacts** the first time they are written. Re-running with
``--force`` will produce different baselines (within the noise band) and
will invalidate any downstream computations performed against the prior
cache — perturbation realizations that depend on the baseline route
partition (DEMAND, INSERTION; §6.3, §6.4), action results that compare
against a baseline, the multi-seed audit's reference-stability flags
(§8.2). Do not pass ``--force`` casually.

Wall-clock target on the project's reference hardware (M2 8-core MacBook):
~12 minutes with ``--workers 6 --time-limit 60``. Phase A's 3 s smoke
solve on X-n101-k25 took ~3.0 s elapsed; the full 68 × 60 s computation
fans out as two batches (small + large) under joblib loky and saturates
6 worker cores.

Usage::

    python scripts/compute_baselines.py
    python scripts/compute_baselines.py --baseline-dir data/baselines --workers 6
    python scripts/compute_baselines.py --force                  # recompute all
    python scripts/compute_baselines.py --instance X-n101-k25    # single instance
    python scripts/compute_baselines.py --backend threading      # for tests / debug
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from joblib import Parallel, delayed

# Allow running the script directly without an editable install.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vrp_copilot_bench.baselines import (  # noqa: E402
    DEFAULT_BASELINE_DIR,
    Solution,
    baseline_path,
)
from vrp_copilot_bench.instances import load_instance, list_stage_a_instances  # noqa: E402
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig, solve  # noqa: E402

logger = logging.getLogger(__name__)


DEFAULT_TIME_LIMIT_S: float = 60.0
DEFAULT_SEED: int = 1
DEFAULT_WORKERS: int = 6
_TMP_SUFFIX: str = ".tmp"


# ---------------------------------------------------------------------------
# Atomic JSON write (matches the idiom in checkpoint.py; reimplemented here
# to keep baselines.py independent of checkpoint internals — checkpoint is
# a closed module per the Phase B brief).


def _atomic_write_json(target: Path, payload: dict) -> None:
    """Write ``payload`` to ``target`` atomically.

    Strategy: serialise to a tmp file in the same directory as ``target``
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
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise

    try:
        dir_fd = os.open(str(target.parent), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError as exc:  # pragma: no cover - platform-dependent
        logger.debug("directory fsync failed for %s: %s", target.parent, exc)
    finally:
        os.close(dir_fd)


# ---------------------------------------------------------------------------
# Per-instance worker (top-level so loky can pickle it)


def _compute_one(
    instance_id: str,
    config: SolveConfig,
    baseline_dir: Path,
) -> tuple[str, str, str | None]:
    """Compute one baseline; return (instance_id, status, error_message_or_None).

    status is one of:
        - "skipped" (cache already exists; never reached unless caller
          forgot to filter, but defensive)
        - "computed" (success; JSON written)
        - "failed" (exception during solve or write)

    Errors are caught and reported (not re-raised) so a single bad
    instance doesn't abort a 68-instance run. The caller checks the
    status of each return value.
    """
    target = baseline_path(instance_id, baseline_dir)
    if target.exists():
        return (instance_id, "skipped", None)
    try:
        instance = load_instance(instance_id)
        result = solve(instance, config)
        sol = Solution.from_solve_result(instance_id, result, config)
        _atomic_write_json(target, sol.to_dict())
        return (instance_id, "computed", None)
    except BaseException as exc:  # noqa: BLE001 — we want to catch everything
        # Log with traceback for diagnosis; return error message to caller.
        logger.exception("baseline computation failed for %s", instance_id)
        return (instance_id, "failed", f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Orchestrator


def compute_baselines(
    instance_ids: list[str],
    baseline_dir: Path,
    config: SolveConfig,
    *,
    workers: int,
    backend: str,
    force: bool,
) -> dict[str, list[str]]:
    """Run ``_compute_one`` for each instance; return a status summary.

    Returns a dict with keys ``computed``, ``skipped``, ``failed``,
    each mapping to a list of instance IDs.
    """
    baseline_dir.mkdir(parents=True, exist_ok=True)

    if force:
        # Clear existing cache files so _compute_one's existence check
        # doesn't report "skipped" for previously-cached instances.
        for iid in instance_ids:
            p = baseline_path(iid, baseline_dir)
            if p.exists():
                p.unlink()
        to_run = list(instance_ids)
    else:
        to_run = [
            iid for iid in instance_ids
            if not baseline_path(iid, baseline_dir).exists()
        ]
    pre_skipped = [iid for iid in instance_ids if iid not in to_run]

    logger.info(
        "Baseline plan: %d to compute, %d already cached (skipped without --force).",
        len(to_run), len(pre_skipped),
    )

    results: list[tuple[str, str, str | None]]
    if not to_run:
        results = []
    else:
        # joblib SequentialBackend rejects extra kwargs; build them conditionally.
        parallel_kwargs: dict = {"n_jobs": workers, "backend": backend}
        results = list(
            Parallel(**parallel_kwargs)(
                delayed(_compute_one)(iid, config, baseline_dir)
                for iid in to_run
            )
        )

    summary: dict[str, list[str]] = {
        "computed": [],
        "skipped": list(pre_skipped),
        "failed": [],
    }
    for iid, status, _err in results:
        if status == "computed":
            summary["computed"].append(iid)
        elif status == "skipped":
            summary["skipped"].append(iid)
        elif status == "failed":
            summary["failed"].append(iid)
        else:
            raise RuntimeError(f"unexpected status {status!r} for {iid}")

    return summary


# ---------------------------------------------------------------------------
# CLI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="compute_baselines",
        description="Compute PyVRP 60s seed=1 baselines for Stage A.",
    )
    p.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                   help="Number of joblib workers (default 6).")
    p.add_argument("--time-limit", type=float, default=DEFAULT_TIME_LIMIT_S,
                   help="PyVRP time budget in seconds (default 60; prereg §7).")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED,
                   help="PyVRP RNG seed (default 1; prereg §8.1).")
    p.add_argument("--backend", default="loky", choices=("loky", "threading", "sequential"),
                   help='joblib backend; "loky" (default) for production, '
                        '"threading" for tests, "sequential" for debug.')
    p.add_argument("--force", action="store_true",
                   help="Recompute baselines even if cached "
                        "(WARNING: invalidates downstream artifacts).")
    p.add_argument("--instance", action="append", default=None, dest="instances",
                   help="Restrict to one or more named instances "
                        "(repeat the flag to list multiple). "
                        "Default: all 68 from the Stage A roster.")
    p.add_argument("--log-level", default="INFO",
                   choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.instances is not None:
        instance_ids = list(args.instances)
    else:
        instance_ids = list_stage_a_instances()

    config = SolveConfig(
        time_limit_seconds=args.time_limit,
        seed=args.seed,
    )

    if args.force:
        logger.warning(
            "--force: existing baselines will be overwritten. "
            "Downstream artifacts that referenced the prior cache are now stale."
        )

    backend = "loky" if args.backend == "loky" else (
        "threading" if args.backend == "threading" else "sequential"
    )
    summary = compute_baselines(
        instance_ids,
        args.baseline_dir,
        config,
        workers=args.workers,
        backend=backend,
        force=args.force,
    )

    n_computed = len(summary["computed"])
    n_skipped = len(summary["skipped"])
    n_failed = len(summary["failed"])
    print(
        f"Baselines: {n_computed} computed, {n_skipped} skipped, "
        f"{n_failed} failed."
    )
    if n_failed:
        print("Failed instances:")
        for iid in summary["failed"]:
            print(f"  {iid}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
