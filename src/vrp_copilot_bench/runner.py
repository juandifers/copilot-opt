"""Stage A runner — the load-bearing orchestration module.

Pipeline::

    enumerate_stage_a → order_by_size → filter_completed →
    partition by is_large_instance → dispatch each phase via joblib.Parallel

Per-key worker in :func:`run_one_action`:

1. Skip if a successful checkpoint already exists (idempotent).
2. Load instance, baseline, perturbation spec; apply perturbation; run
   action; persist via :func:`save_result`.
3. On any exception, persist a failure record via :func:`save_failure` and
   return — never re-raise. A worker raising would kill the parallel pool.

Two-phase dispatch is by design: small instances run at ``workers_normal``
(6 by default on the M2 target), then large instances (n_customers >
``large_threshold``) run at ``workers_large`` (4) to keep memory pressure
in check. Sorting by size inside each phase means the cheapest work
completes first, surfacing bugs within minutes rather than hours.

Importing this module does *not* spawn workers — joblib only spawns when
``run_stage_a`` is called.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from joblib import Parallel, delayed

from .actions import run_action
from .baselines import load_baseline_solution
from .checkpoint import (
    ActionRunKey,
    has_checkpoint,
    save_failure,
    save_result,
)
from .instances import load_instance
from .perturbations import apply_perturbation, lookup_perturbation
from .work_plan import (
    DEFAULT_LARGE_THRESHOLD,
    enumerate_stage_a,
    filter_completed,
    is_large_instance,
    order_by_size,
)

# Test hook: when this env var is set at module load time, swap the
# downstream dep references for the synthetic ones in
# :mod:`._smoke_deps`. Used only by the loky smoke test in
# ``tests/test_cli.py`` — production never sets this. The env var
# inherits into loky-spawned subprocesses, so workers' fresh import of
# this module also picks up the fakes.
if os.environ.get("VRP_COPILOT_BENCH_USE_SMOKE_DEPS") == "1":  # pragma: no cover - test hook
    from ._smoke_deps import (  # noqa: F811 - intentional rebinding
        apply_perturbation,
        load_baseline_solution,
        load_instance,
        lookup_perturbation,
        run_action,
    )

log = logging.getLogger(__name__)

DEFAULT_BACKEND: str = "loky"
DEFAULT_PROGRESS_LOG_EVERY: int = 100

#: Per-task timeout (seconds) passed to ``joblib.Parallel`` as a hung-worker
#: backstop. The longest legitimate action is ``pyvrp_60s`` at ~60 s; 300 s
#: is a 5× safety margin. If a single task exceeds this, joblib raises
#: ``TimeoutError`` from the result iterator and the dispatch aborts —
#: subsequent keys are not run, and the timed-out key is *not* checkpointed
#: as a failure (joblib does not surface which key timed out). The user
#: re-runs and the timed-out key is retried.
DEFAULT_TASK_TIMEOUT_S: int = 300


# ---------------------------------------------------------------------------
# Result types


@dataclass(frozen=True)
class RunFailure:
    """One failure during a Stage A dispatch."""

    key: ActionRunKey
    exception_class: str
    message: str


@dataclass(frozen=True)
class RunSummary:
    """Outcome of one ``run_stage_a`` invocation."""

    n_attempted: int
    n_succeeded: int
    n_failed: int
    wall_time_seconds: float
    failures: tuple[RunFailure, ...] = field(default_factory=tuple)

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        head = (
            f"RunSummary: {self.n_succeeded}/{self.n_attempted} succeeded, "
            f"{self.n_failed} failed in {self.wall_time_seconds:.1f}s"
        )
        if not self.failures:
            return head
        tail = "\n".join(f"  - {f.key}: {f.exception_class}: {f.message}" for f in self.failures)
        return f"{head}\n{tail}"


# ---------------------------------------------------------------------------
# Startup cleanup (Phase 1 Q3 deferred here)


def cleanup_stale_tmp_files(checkpoint_dir: Path) -> int:
    """Remove ``*.tmp.*`` files left behind by previous crashed writes.

    Returns the number of files removed. Safe to call when the directory
    does not exist or is empty.
    """
    if not checkpoint_dir.is_dir():
        return 0

    removed = 0
    for tmp in checkpoint_dir.glob("*.tmp.*"):
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
            removed += 1

    failures_dir = checkpoint_dir / "_failures"
    if failures_dir.is_dir():
        for tmp in failures_dir.glob("*.tmp.*"):
            if tmp.is_file():
                tmp.unlink(missing_ok=True)
                removed += 1

    if removed:
        log.info("cleaned up %d stale tmp files in %s", removed, checkpoint_dir)
    return removed


# ---------------------------------------------------------------------------
# Per-key worker


def run_one_action(key: ActionRunKey, checkpoint_dir: Path) -> RunFailure | None:
    """Execute one action run, persisting either a result or a failure record.

    Idempotent: re-invocation on a key with an existing successful
    checkpoint is a no-op. Catches *all* exceptions (including
    ``KeyboardInterrupt`` is **not** caught — see note) and writes a
    failure record so the parallel run can continue.

    Returns ``None`` on success or skip; a :class:`RunFailure` on failure.
    Never re-raises.

    Note on KeyboardInterrupt: a Ctrl-C during a worker run propagates so
    joblib can shut the pool down cleanly. Anything else (RuntimeError,
    ValueError, MemoryError, even non-Exception BaseExceptions like
    ``SystemExit``) is captured to a failure record.
    """
    if has_checkpoint(checkpoint_dir, key):
        return None

    try:
        instance = load_instance(key.instance_id)
        baseline = load_baseline_solution(key.instance_id)
        perturbation_spec = lookup_perturbation(key.instance_id, key.perturbation_id)
        # Baseline is required for DEMAND, DIST_4, and INSERTION
        # perturbation realisations (they select customers/routes from
        # the baseline plan). CAPACITY and DIST_1/2/3 ignore the
        # argument; passing it is harmless.
        perturbed = apply_perturbation(instance, perturbation_spec, baseline)
        result = run_action(key.action, perturbed, baseline)
        save_result(checkpoint_dir, key, result)
        return None
    except KeyboardInterrupt:
        # Let the pool tear down; do not wedge a partial failure record.
        raise
    except BaseException as exc:
        # Best-effort: if even saving the failure fails, log and keep going.
        try:
            save_failure(checkpoint_dir, key, exc)
        except Exception:  # noqa: BLE001
            log.exception("failed to save failure record for %s", key)
        return RunFailure(
            key=key,
            exception_class=type(exc).__name__,
            message=str(exc),
        )


# ---------------------------------------------------------------------------
# Progress tracking


class _ProgressTracker:
    """Lightweight ETA tracker. Logs every ``log_every`` completions.

    Single-threaded by construction: the dispatch consumes the joblib
    result generator from the parent process, so ``step`` is never called
    concurrently.
    """

    def __init__(self, total: int, log_every: int = DEFAULT_PROGRESS_LOG_EVERY) -> None:
        self.total = total
        self.log_every = log_every
        self.completed = 0
        self._start_monotonic: float | None = None

    def start(self) -> None:
        self._start_monotonic = time.monotonic()

    def step(self) -> None:
        self.completed += 1
        if self.completed % self.log_every == 0 or self.completed == self.total:
            self._log()

    def _log(self) -> None:
        if self._start_monotonic is None:
            return
        elapsed = max(time.monotonic() - self._start_monotonic, 1e-9)
        rate = self.completed / elapsed
        remaining = max(self.total - self.completed, 0)
        eta_minutes = (remaining / rate / 60.0) if rate > 0 else float("inf")
        log.info(
            "%d/%d done (%.2f keys/s, ETA %.1f min)",
            self.completed,
            self.total,
            rate,
            eta_minutes,
        )


# ---------------------------------------------------------------------------
# Dispatch


def _dispatch_phase(
    keys: list[ActionRunKey],
    checkpoint_dir: Path,
    n_workers: int,
    backend: str,
    progress: _ProgressTracker,
    phase_name: str,
    task_timeout_s: int = DEFAULT_TASK_TIMEOUT_S,
) -> list[RunFailure]:
    """Run one phase under ``joblib.Parallel`` with streaming results.

    Uses ``return_as='generator'`` (joblib >= 1.3) so the parent can update
    progress as each key completes rather than after the whole batch.

    ``task_timeout_s`` is passed to joblib as the per-task timeout. If any
    task exceeds it, the iterator raises ``TimeoutError`` and we abort the
    phase — see :data:`DEFAULT_TASK_TIMEOUT_S` for the rationale.
    """
    if not keys:
        log.info("phase %r: no keys, skipping", phase_name)
        return []

    log.info(
        "phase %r: dispatching %d keys, %d workers, backend=%r, task_timeout=%ds",
        phase_name,
        len(keys),
        n_workers,
        backend,
        task_timeout_s,
    )

    failures: list[RunFailure] = []
    # joblib's SequentialBackend (used when n_jobs == 1) emits a UserWarning
    # if ``timeout`` is set, since it can't enforce it. Skip the timeout in
    # that case — the user opted into single-worker mode for debuggability.
    parallel_kwargs = {
        "n_jobs": n_workers,
        "backend": backend,
        "return_as": "generator",
        "verbose": 0,
    }
    if n_workers > 1:
        parallel_kwargs["timeout"] = task_timeout_s
    parallel = Parallel(**parallel_kwargs)
    results = parallel(
        delayed(run_one_action)(key, checkpoint_dir) for key in keys
    )
    try:
        for outcome in results:
            progress.step()
            if outcome is not None:
                failures.append(outcome)
    except TimeoutError as exc:
        log.error(
            "phase %r: a task exceeded the %ds timeout — pool aborted (%s). "
            "Subsequent keys were not dispatched; re-run to retry.",
            phase_name,
            task_timeout_s,
            exc,
        )

    log.info(
        "phase %r: done; %d successes, %d failures",
        phase_name,
        len(keys) - len(failures),
        len(failures),
    )
    return failures


def run_stage_a(
    checkpoint_dir: Path,
    workers_normal: int = 6,
    workers_large: int = 4,
    large_threshold: int = DEFAULT_LARGE_THRESHOLD,
    backend: str = DEFAULT_BACKEND,
    progress_log_every: int = DEFAULT_PROGRESS_LOG_EVERY,
    keys: list[ActionRunKey] | None = None,
    task_timeout_s: int = DEFAULT_TASK_TIMEOUT_S,
) -> RunSummary:
    """Run Stage A end-to-end. Resumable.

    Steps:

    1. Clean stray ``*.tmp.*`` files from a previously crashed run.
    2. Enumerate keys (or use ``keys`` if provided), sort small-first, drop
       already-completed.
    3. Partition by ``is_large_instance``.
    4. Dispatch the small phase at ``workers_normal``, then the large phase
       at ``workers_large``.
    5. Return a :class:`RunSummary` with counts and the failure list from
       this invocation.

    Pass ``keys`` to run a specific subset (e.g., to retry failed keys via
    the CLI's ``--retry-failures`` mode, or for tests). When ``keys`` is
    ``None`` (default), :func:`enumerate_stage_a` produces the full grid.
    Either way the list still flows through ``order_by_size`` and
    ``filter_completed``.

    The two phases use the same ``backend`` (default ``"loky"``). Tests can
    pass ``backend="threading"`` to keep monkeypatches visible to workers.
    """
    cleanup_stale_tmp_files(checkpoint_dir)

    if keys is None:
        keys = enumerate_stage_a()
    else:
        keys = list(keys)  # defensive copy; callers may mutate
    keys = order_by_size(keys)
    keys = filter_completed(keys, checkpoint_dir)

    small_keys = [k for k in keys if not is_large_instance(k, large_threshold)]
    large_keys = [k for k in keys if is_large_instance(k, large_threshold)]
    log.info(
        "partitioned: %d small (≤%d customers), %d large (>%d customers)",
        len(small_keys),
        large_threshold,
        len(large_keys),
        large_threshold,
    )

    progress = _ProgressTracker(total=len(keys), log_every=progress_log_every)
    progress.start()
    t0 = time.monotonic()

    failures: list[RunFailure] = []
    failures.extend(
        _dispatch_phase(
            small_keys, checkpoint_dir, workers_normal, backend, progress,
            "small", task_timeout_s=task_timeout_s,
        )
    )
    failures.extend(
        _dispatch_phase(
            large_keys, checkpoint_dir, workers_large, backend, progress,
            "large", task_timeout_s=task_timeout_s,
        )
    )

    wall = time.monotonic() - t0
    n_attempted = len(keys)
    n_failed = len(failures)
    n_succeeded = n_attempted - n_failed

    summary = RunSummary(
        n_attempted=n_attempted,
        n_succeeded=n_succeeded,
        n_failed=n_failed,
        wall_time_seconds=wall,
        failures=tuple(failures),
    )
    log.info(
        "Stage A run complete: %d/%d succeeded, %d failed, wall=%.1fs",
        n_succeeded,
        n_attempted,
        n_failed,
        wall,
    )
    return summary
