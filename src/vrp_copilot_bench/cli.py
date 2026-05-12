"""CLI for the Stage A runner.

Top-level entrypoint: ``python -m vrp_copilot_bench.cli`` (or via the
``scripts/run_stage_a.py`` wrapper). Three modes:

- ``--dry-run``: enumerate the work plan, print a runtime estimate, exit 0.
- ``--consolidate-only``: skip dispatch; build parquet from existing
  checkpoints. Honours ``--allow-empty``.
- default: dispatch + consolidate. Optionally restricted to previously-
  failed keys via ``--retry-failures``.

Per the cross-phase rule, this is the only module that uses ``print``
for user-facing output. Library modules use ``logging``.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .actions import ACTIONS
from .checkpoint import list_failures
from .consolidate import consolidate_to_parquet
from .runner import (
    DEFAULT_BACKEND,
    DEFAULT_PROGRESS_LOG_EVERY,
    DEFAULT_TASK_TIMEOUT_S,
    run_stage_a,
)
from .work_plan import (
    DEFAULT_LARGE_THRESHOLD,
    enumerate_stage_a,
    filter_completed,
    is_large_instance,
    order_by_size,
)


def _parse_instances_flag(raw: str | None) -> set[str] | None:
    """Parse ``--instances X-n101-k25,X-n251-k28`` (or a path to a roster file).

    Returns a set of instance IDs, or None if the flag was not provided.
    Accepts either an inline comma-separated list or a path to a one-ID-
    per-line roster file (same format as ``instances/stage_a_instances.txt``).
    The pilot runbook uses the file form (``instances/pilot_instances.txt``).
    """
    if raw is None:
        return None
    candidate = Path(raw)
    if candidate.exists():
        ids: set[str] = set()
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                ids.add(line)
        return ids
    return {tok.strip() for tok in raw.split(",") if tok.strip()}

#: Per-action wall-clock cost estimates (seconds, single-threaded), used
#: by ``--dry-run`` to compute the runtime estimate. Aligned with prereg
#: §7's action set; ``pyvrp_60s_seed2`` and ``_seed3`` cost the same as
#: their non-audit counterpart.
ACTION_COSTS_S: dict[str, float] = {
    "reuse_direct": 0.05,
    "nearest_neighbor": 0.5,
    "clarke_wright": 1.0,
    "pyvrp_10s": 10.0,
    "pyvrp_60s": 60.0,
    "pyvrp_60s_seed2": 60.0,
    "pyvrp_60s_seed3": 60.0,
}
assert set(ACTION_COSTS_S) == set(ACTIONS), "cost model out of sync with ACTIONS"

#: Multiplicative overhead applied on top of the wall-clock estimate to
#: account for I/O, joblib pool startup, perturbation realisation, etc.
_ESTIMATE_OVERHEAD: float = 1.10


# ---------------------------------------------------------------------------
# Estimation


def estimate_runtime_seconds(
    keys: list,
    *,
    workers_normal: int,
    workers_large: int,
    large_threshold: int,
) -> float:
    """Two-phase wall-clock estimate based on :data:`ACTION_COSTS_S`.

    Each phase's wall time ≈ total CPU-seconds / worker count, summed
    across phases, plus a 10 % overhead.
    """
    small_cpu_s = sum(
        ACTION_COSTS_S[k.action]
        for k in keys
        if not is_large_instance(k, large_threshold)
    )
    large_cpu_s = sum(
        ACTION_COSTS_S[k.action]
        for k in keys
        if is_large_instance(k, large_threshold)
    )
    small_phase = small_cpu_s / max(workers_normal, 1)
    large_phase = large_cpu_s / max(workers_large, 1)
    return (small_phase + large_phase) * _ESTIMATE_OVERHEAD


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.2f} h"


# ---------------------------------------------------------------------------
# Argument parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_stage_a",
        description="Run Stage A of the VRP copilot sufficiency benchmark.",
    )

    # Paths
    p.add_argument("--checkpoint-dir", type=Path, default=Path("data/checkpoints"))
    p.add_argument("--output", type=Path, default=Path("data/stage_a.parquet"))

    # Worker pool
    p.add_argument("--workers-normal", type=int, default=6,
                   help="Workers for small-instance phase (default 6).")
    p.add_argument("--workers-large", type=int, default=4,
                   help="Workers for large-instance phase (default 4). Drop "
                        "to 3 if Stage A's first hour shows swap activity.")
    p.add_argument("--large-threshold", type=int, default=DEFAULT_LARGE_THRESHOLD,
                   help="n_customers threshold above which an instance counts as large.")
    p.add_argument("--backend", default=DEFAULT_BACKEND,
                   help='joblib backend; "loky" (default) or "threading" for tests.')
    p.add_argument("--task-timeout-s", type=int, default=DEFAULT_TASK_TIMEOUT_S,
                   help="Per-task timeout in seconds; aborts the phase if a task hangs.")
    p.add_argument("--progress-log-every", type=int, default=DEFAULT_PROGRESS_LOG_EVERY,
                   help="Log a progress line every N completions.")

    # Modes
    p.add_argument("--dry-run", action="store_true",
                   help="Print the work plan and runtime estimate; exit without running.")
    p.add_argument("--consolidate-only", action="store_true",
                   help="Skip dispatch; only build parquet from existing checkpoints.")
    p.add_argument("--allow-empty", action="store_true",
                   help="When consolidating, allow zero checkpoints to produce "
                        "an empty parquet (default: hard failure).")
    p.add_argument("--retry-failures", action="store_true",
                   help="Run only previously-failed keys (read from "
                        "<checkpoint-dir>/_failures/).")
    p.add_argument("--instances", default=None,
                   help="Comma-separated instance IDs or path to a roster file "
                        "(e.g. 'instances/pilot_instances.txt'). When set, the "
                        "work plan is restricted to keys for these instances. "
                        "Used by the 3-instance pilot; see docs/pilot_runbook.md.")

    # Logging
    p.add_argument("--log-level", default="INFO",
                   choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return p


# ---------------------------------------------------------------------------
# Main


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    instance_filter = _parse_instances_flag(args.instances)

    # ---- Dry-run ----
    if args.dry_run:
        keys = enumerate_stage_a()
        if instance_filter is not None:
            keys = [k for k in keys if k.instance_id in instance_filter]
        keys = order_by_size(keys)
        keys = filter_completed(keys, args.checkpoint_dir)
        eta = estimate_runtime_seconds(
            keys,
            workers_normal=args.workers_normal,
            workers_large=args.workers_large,
            large_threshold=args.large_threshold,
        )
        print(f"Would run {len(keys)} cell-actions.")
        print(f"Estimated wall-time: {format_duration(eta)} "
              f"(overhead factor {_ESTIMATE_OVERHEAD:.2f}).")
        return 0

    # ---- Dispatch (unless --consolidate-only) ----
    if not args.consolidate_only:
        keys: list | None = None
        if args.retry_failures:
            failures = list_failures(args.checkpoint_dir)
            if not failures:
                print("No failures recorded; nothing to retry.")
                return 0
            keys = list(failures.keys())
            if instance_filter is not None:
                keys = [k for k in keys if k.instance_id in instance_filter]
            print(f"Retrying {len(keys)} previously-failed keys.")
        elif instance_filter is not None:
            keys = [k for k in enumerate_stage_a() if k.instance_id in instance_filter]
            print(f"Restricted to {len(keys)} keys across "
                  f"{len(instance_filter)} instance(s) via --instances.")

        summary = run_stage_a(
            checkpoint_dir=args.checkpoint_dir,
            workers_normal=args.workers_normal,
            workers_large=args.workers_large,
            large_threshold=args.large_threshold,
            backend=args.backend,
            progress_log_every=args.progress_log_every,
            task_timeout_s=args.task_timeout_s,
            keys=keys,
        )
        print(summary)
        if summary.n_failed > 0:
            print(f"\nWARNING: {summary.n_failed} failures. "
                  f"Re-run with --retry-failures to retry.")

    # ---- Consolidate ----
    consolidation = consolidate_to_parquet(
        args.checkpoint_dir,
        args.output,
        allow_empty=args.allow_empty,
    )
    print(consolidation)
    if not consolidation.ok:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
