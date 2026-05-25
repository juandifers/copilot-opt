#!/usr/bin/env python3
"""Stage A VRPTW benchmark runner.

Drives the 56-instance Solomon-100 sufficiency benchmark per
``prereg/PREREG_v1.0_vrptw.md`` (locked at commit
``09c4c03fa087c4b0b9d568f1de258e94ee003ef5``, tag ``prereg-v1.0-vrptw``).

Pipeline: reuses :func:`run_scale_check` with the Stage A defaults
(soft_grid, expanded action portfolio, multi-seed reference audit) and
points it at the Stage A output paths + a per-key checkpoint directory.
On completion, writes a Stage A run report covering wall-clocks, failure
counts, reference-stability rates, and headline band distributions.

CLI
===
::

    python scripts/run_stage_a_vrptw.py             # full 56-instance run
    python scripts/run_stage_a_vrptw.py --instances C101 --perturbations TT_1
                                                    # smoke variant

A re-run with the same ``--checkpoint-dir`` resumes from any cached
solves or rows written by a previous run; failed (instance, perturbation,
seed/action) keys are not auto-retried.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Reuse the scale-check pipeline + its helpers.
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from run_vrptw_scale_check import (  # noqa: E402
    PERTURBATION_FAMILY_OF,
    PERTURBATION_IDS,
    _read_roster,
    run_scale_check,
)

from vrp_copilot_bench.vrptw.checkpoint import CheckpointStore  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("stage_a_vrptw")


# ---------------------------------------------------------------------------
# Defaults

DEFAULT_ROSTER = PROJECT_ROOT / "instances" / "solomon100_stage_a.txt"
DEFAULT_PARQUET_WIDE = PROJECT_ROOT / "data" / "stage_a_vrptw.parquet"
DEFAULT_PARQUET_LONG = PROJECT_ROOT / "data" / "stage_a_vrptw_claim_rows.parquet"
DEFAULT_CHECKPOINT_DIR = PROJECT_ROOT / "data" / "stage_a_vrptw_checkpoints"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "data" / "stage_a_vrptw_run_report.md"


# ---------------------------------------------------------------------------
# Run report


def _band_counts(series: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in Counter(series.dropna().tolist()).items()}


def _percent(num: float, denom: float) -> str:
    if denom <= 0:
        return "n/a"
    return f"{100.0 * num / denom:.1f}%"


def _build_run_report(
    *,
    wide_df: pd.DataFrame,
    long_df: pd.DataFrame,
    instances: tuple[str, ...],
    perturbation_ids: tuple[str, ...],
    seeds: tuple[int, ...],
    expected_wide_rows: int,
    expected_long_rows: int,
    time_limit: float,
    pyvrp10s_time_limit: float,
    n_jobs: int,
    checkpoint_dir: Path,
    stats: dict[str, Any],
    failures: list[dict[str, Any]],
    parquet_wide: Path,
    parquet_long: Path,
    wall_clock_total_s: float,
) -> str:
    lines: list[str] = []
    push = lines.append

    push("# Stage A VRPTW run report")
    push("")
    push(
        "Stage A of the VRPTW sufficiency benchmark per "
        "`prereg/PREREG_v1.0_vrptw.md` (lock tag `prereg-v1.0-vrptw`)."
    )
    push("")

    # --- 1. Phase wall-clocks ---------------------------------------------
    push("## 1. Wall-clock by phase")
    push("")
    push("| phase | seconds | hh:mm:ss |")
    push("|---|---:|---|")
    for label, key in (
        ("baselines",       "phase_baselines_seconds"),
        ("references",      "phase_references_seconds"),
        ("pyvrp_10s solves", "phase_pyvrp10s_seconds"),
        ("row assembly",    "phase_assemble_seconds"),
    ):
        s = float(stats.get(key, 0.0))
        m, sec = divmod(int(s), 60)
        h, m = divmod(m, 60)
        push(f"| {label} | {s:.1f} | {h:02d}:{m:02d}:{sec:02d} |")
    m, sec = divmod(int(wall_clock_total_s), 60)
    h, m = divmod(m, 60)
    push(f"| **total run-script** | {wall_clock_total_s:.1f} | {h:02d}:{m:02d}:{sec:02d} |")
    push("")

    # --- 2. Row counts ----------------------------------------------------
    push("## 2. Row counts (expected vs actual)")
    push("")
    push("| table | expected | actual | match |")
    push("|---|---:|---:|---|")
    for label, exp, got in (
        ("wide", expected_wide_rows, len(wide_df)),
        ("long claim", expected_long_rows, len(long_df)),
    ):
        match = "OK" if exp == got else f"DIFF ({got - exp:+d})"
        push(f"| {label} | {exp} | {got} | {match} |")
    push("")
    push(
        f"Cached rows reused from checkpoint dir: "
        f"{int(stats.get('n_cached_rows', 0))} / {len(wide_df)}"
    )
    push("")

    # --- 3. Reference feasibility ----------------------------------------
    push("## 3. Reference feasibility")
    push("")
    if "reference_all_feasible" in wide_df.columns:
        # Each cell appears in multiple action rows, so dedupe by (iid, pid).
        cell_view = wide_df.drop_duplicates(["instance_id", "perturbation_id"])
        n_cells = len(cell_view)
        n_all = int(cell_view["reference_all_feasible"].sum())
        n_any = int(cell_view["reference_any_feasible"].sum())
        n_all_infeasible = int((~cell_view["reference_any_feasible"]).sum())
        push(
            f"- Cells where all 3 reference seeds feasible: "
            f"**{n_all} / {n_cells}** ({_percent(n_all, n_cells)})"
        )
        push(
            f"- Cells where at least one seed feasible: "
            f"**{n_any} / {n_cells}** ({_percent(n_any, n_cells)})"
        )
        push(
            f"- Cells where all 3 seeds infeasible: "
            f"**{n_all_infeasible} / {n_cells}** "
            f"({_percent(n_all_infeasible, n_cells)})"
        )
        push("")
        if n_all_infeasible:
            push("### All-3-seeds-infeasible cells")
            push("")
            push("| instance | perturbation | failure_kind |")
            push("|---|---|---|")
            infeasible_rows = cell_view[~cell_view["reference_any_feasible"]]
            for _, r in infeasible_rows.iterrows():
                push(
                    f"| {r['instance_id']} | {r['perturbation_id']} "
                    f"| {r['reference_failure_kind']} |"
                )
            push("")
    failed_ref_cells = stats.get("failed_ref_cells", [])
    failed_ref_keys = stats.get("failed_ref_keys", [])
    push(
        f"- Reference solves that raised exceptions: "
        f"**{len(failed_ref_keys)} keys** across **{len(failed_ref_cells)} cells**."
    )
    if failed_ref_cells:
        push("")
        push("### Reference-failure cells")
        push("")
        push("| instance | perturbation |")
        push("|---|---|")
        for c in failed_ref_cells:
            push(f"| {c['instance_id']} | {c['perturbation_id']} |")
    push("")

    # --- 4. Action failures by action ------------------------------------
    push("## 4. Action failures by action")
    push("")
    by_action: Counter[str] = Counter()
    repr_msg: dict[str, str] = {}
    for f in failures:
        if f.get("phase") != "actions":
            continue
        a = str(f.get("action") or "?")
        by_action[a] += 1
        if a not in repr_msg:
            repr_msg[a] = str(f.get("error_message", ""))[:200]
    if by_action:
        push("| action | failures | representative message |")
        push("|---|---:|---|")
        for a, n in sorted(by_action.items()):
            msg = repr_msg.get(a, "").replace("|", "\\|")
            push(f"| `{a}` | {n} | {msg} |")
    else:
        push("No action-level failures recorded.")
    push("")

    push("### Failures by phase (full breakdown)")
    push("")
    push("| phase | count |")
    push("|---|---:|")
    phase_counts: Counter[str] = Counter(f.get("phase", "?") for f in failures)
    if phase_counts:
        for p, n in sorted(phase_counts.items()):
            push(f"| {p} | {n} |")
    else:
        push("| (none) | 0 |")
    push("")

    # --- 5. Reference stability ------------------------------------------
    push("## 5. Reference stability")
    push("")
    if not wide_df.empty:
        cell_view = wide_df.drop_duplicates(["instance_id", "perturbation_id"])
        obj_rate = float(cell_view["reference_obj_unstable"].mean())
        struct_rate = float(cell_view["reference_struct_unstable"].mean())
        push(f"- `reference_obj_unstable` rate (overall): **{obj_rate:.3f}**")
        push(f"- `reference_struct_unstable` rate (overall): **{struct_rate:.3f}**")
        ari_med = cell_view["reference_ari_min"].dropna().median()
        push(f"- median `reference_ari_min` (overall): **{float(ari_med):.3f}**")
        push("")
        push("### By perturbation family")
        push("")
        push("| family | n cells | obj_unstable | struct_unstable | median ari_min |")
        push("|---|---:|---:|---:|---:|")
        for fam, sub in cell_view.groupby("perturbation_family"):
            n = len(sub)
            o = float(sub["reference_obj_unstable"].mean())
            s = float(sub["reference_struct_unstable"].mean())
            ari = sub["reference_ari_min"].dropna()
            med = float(ari.median()) if len(ari) else float("nan")
            push(f"| {fam} | {n} | {o:.3f} | {s:.3f} | {med:.3f} |")
    push("")
    push(
        "Compare against the 18-instance expanded-action pilot rates "
        "(obj=0.000, struct=0.194) and the Phase-1 unperturbed probe "
        "(struct=0.167, median ari_min=1.000)."
    )
    push("")

    # --- 6. Band distributions -------------------------------------------
    push("## 6. Headline band distributions (long table)")
    push("")
    if not long_df.empty:
        for fam in ("OBJ", "PLAN_VALIDITY", "STRUCT", "SCHEDULE"):
            push(f"### {fam}")
            push("")
            sub_fam = long_df[long_df["claim_family"] == fam]
            actions = sorted(sub_fam["action"].unique().tolist())
            push("| action | easy | medium | hard | n/a | easy_rate |")
            push("|---|---:|---:|---:|---:|---:|")
            for a in actions:
                sub = sub_fam[sub_fam["action"] == a]
                counts = _band_counts(sub["band"])
                easy = counts.get("easy", 0)
                med = counts.get("medium", 0)
                hard = counts.get("hard", 0)
                na = counts.get("n/a", 0)
                excl_na = easy + med + hard
                rate = (easy / excl_na) if excl_na else float("nan")
                push(
                    f"| `{a}` | {easy} | {med} | {hard} | {na} | "
                    f"{rate:.3f} |"
                )
            push("")
    push("")

    # --- 7. Anomalies / log notes ----------------------------------------
    push("## 7. Anomalies / notes")
    push("")
    notes: list[str] = []
    if stats.get("failed_ref_keys"):
        notes.append(
            f"- {len(stats['failed_ref_keys'])} reference-solve exception(s) "
            f"recorded; see `_failures/` for tracebacks."
        )
    if stats.get("failed_pyvrp10s_cells"):
        notes.append(
            f"- {len(stats['failed_pyvrp10s_cells'])} pyvrp_10s solve "
            f"exception(s) recorded."
        )
    if stats.get("failed_action_keys"):
        notes.append(
            f"- {len(stats['failed_action_keys'])} action-row exception(s) "
            f"recorded."
        )
    if int(stats.get("n_cached_rows", 0)) > 0:
        notes.append(
            f"- {int(stats['n_cached_rows'])} wide rows were loaded from "
            f"checkpoint cache (this was a resumed run)."
        )
    if not notes:
        notes.append("- No exceptions, no cache hits — clean fresh run.")
    for n in notes:
        push(n)
    push("")

    # --- 8. Artifacts -----------------------------------------------------
    push("## 8. Artifacts")
    push("")
    push(f"- Wide parquet: `{parquet_wide}`")
    push(f"- Long parquet: `{parquet_long}`")
    push(f"- Checkpoint dir: `{checkpoint_dir}`")
    push(
        f"- Failure records: `{checkpoint_dir}/_failures/` "
        f"({len(failures)} records)"
    )
    push("")
    push("## 9. Config")
    push("")
    push(
        f"- Instances: {len(instances)} from `instances/solomon100_stage_a.txt`"
    )
    push(f"- Perturbations: {len(perturbation_ids)} (soft_grid)")
    push(f"- Reference seeds: {list(seeds)}")
    push(f"- Reference time limit: {time_limit}s per solve")
    push(f"- pyvrp_10s time limit: {pyvrp10s_time_limit}s")
    push(f"- Parallel workers: {n_jobs}")
    push("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_stage_a_vrptw",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--roster", type=Path, default=DEFAULT_ROSTER,
        help=f"Roster file (default {DEFAULT_ROSTER.name}).",
    )
    p.add_argument(
        "--instances", nargs="+", default=None, metavar="ID",
        help="Override the roster with explicit instance IDs (smoke runs).",
    )
    p.add_argument(
        "--perturbations", nargs="+", default=None, metavar="PID",
        help="Subset of perturbations (default: all 16 soft_grid IDs).",
    )
    p.add_argument(
        "--seeds", nargs="+", type=int, default=[1, 2, 3],
        help="Reference seeds (default: 1 2 3).",
    )
    p.add_argument("--time-limit", type=float, default=60.0)
    p.add_argument("--n-jobs", type=int, default=6)
    p.add_argument("--pyvrp10s-time-limit", type=float, default=10.0)
    p.add_argument("--instance-dir", type=Path, default=None)
    p.add_argument(
        "--parquet-wide", type=Path, default=DEFAULT_PARQUET_WIDE,
        help=f"Wide-table parquet output (default {DEFAULT_PARQUET_WIDE}).",
    )
    p.add_argument(
        "--parquet-long", type=Path, default=DEFAULT_PARQUET_LONG,
        help=f"Long claim-table parquet output (default {DEFAULT_PARQUET_LONG}).",
    )
    p.add_argument(
        "--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR,
        help=f"Per-key checkpoint dir (default {DEFAULT_CHECKPOINT_DIR}).",
    )
    p.add_argument(
        "--report-path", type=Path, default=DEFAULT_REPORT_PATH,
        help=f"Run-report markdown output (default {DEFAULT_REPORT_PATH}).",
    )
    p.add_argument(
        "--force-baselines", action="store_true",
        help="Recompute baselines even if a matching cache file exists.",
    )
    return p.parse_args(argv)


def _expected_row_counts(
    instances: tuple[str, ...],
    perturbation_ids: tuple[str, ...],
) -> tuple[int, int]:
    n_oc = sum(1 for pid in perturbation_ids
               if PERTURBATION_FAMILY_OF.get(pid) == "ORDER_CHANGE")
    n_non_oc = len(perturbation_ids) - n_oc
    # expanded ladder: 5 actions for OC, 4 actions for non-OC.
    per_instance = 5 * n_oc + 4 * n_non_oc
    n_wide = per_instance * len(instances)
    n_long = 4 * n_wide  # 4 claim families
    return n_wide, n_long


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    instances = (
        tuple(args.instances) if args.instances else _read_roster(args.roster)
    )
    if not instances:
        log.error("No instances to run.")
        return 2
    pids = (
        tuple(args.perturbations) if args.perturbations else tuple(PERTURBATION_IDS)
    )
    for pid in pids:
        if pid not in PERTURBATION_FAMILY_OF:
            log.error("Unknown perturbation id %r", pid)
            return 2
    seeds = tuple(int(s) for s in args.seeds)

    args.parquet_wide.parent.mkdir(parents=True, exist_ok=True)
    args.parquet_long.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    expected_wide, expected_long = _expected_row_counts(instances, pids)

    log.info(
        "Stage A VRPTW: instances=%d perturbations=%d seeds=%d "
        "time_limit=%.1fs pyvrp10s=%.1fs n_jobs=%d",
        len(instances), len(pids), len(seeds),
        args.time_limit, args.pyvrp10s_time_limit, args.n_jobs,
    )
    log.info(
        "Expected: wide=%d rows, long=%d rows", expected_wide, expected_long,
    )
    log.info("Checkpoint dir: %s", args.checkpoint_dir)
    log.info(
        "Outputs: %s, %s", args.parquet_wide, args.parquet_long,
    )

    t0 = time.monotonic()
    wide_df, claim_df = run_scale_check(
        instances=instances,
        perturbation_ids=pids,
        seeds=seeds,
        time_limit=args.time_limit,
        n_jobs=args.n_jobs,
        instance_dir=args.instance_dir,
        force_baselines=args.force_baselines,
        expanded_actions=True,
        pyvrp10s_time_limit=args.pyvrp10s_time_limit,
        checkpoint_dir=args.checkpoint_dir,
    )
    wall_clock_total = time.monotonic() - t0

    # Write parquets.
    wide_df.to_parquet(args.parquet_wide, index=False)
    claim_df.to_parquet(args.parquet_long, index=False)
    log.info(
        "Wrote %s (%d rows), %s (%d rows)",
        args.parquet_wide, len(wide_df), args.parquet_long, len(claim_df),
    )

    # Build run report.
    store = CheckpointStore(args.checkpoint_dir)
    stats = store.read_stats() or {}
    failures = store.list_failures()
    report = _build_run_report(
        wide_df=wide_df, long_df=claim_df,
        instances=instances, perturbation_ids=pids, seeds=seeds,
        expected_wide_rows=expected_wide, expected_long_rows=expected_long,
        time_limit=args.time_limit, pyvrp10s_time_limit=args.pyvrp10s_time_limit,
        n_jobs=args.n_jobs, checkpoint_dir=args.checkpoint_dir,
        stats=stats, failures=failures,
        parquet_wide=args.parquet_wide, parquet_long=args.parquet_long,
        wall_clock_total_s=wall_clock_total,
    )
    args.report_path.write_text(report)
    log.info("Wrote run report %s (%d chars)", args.report_path, len(report))

    print()
    print(f"Wide rows:    {len(wide_df)} (expected {expected_wide})")
    print(f"Long rows:    {len(claim_df)} (expected {expected_long})")
    print(f"Failures:     {len(failures)}")
    print(f"Wall-clock:   {wall_clock_total:.1f}s")
    print(f"Wide parquet: {args.parquet_wide}")
    print(f"Long parquet: {args.parquet_long}")
    print(f"Checkpoints:  {args.checkpoint_dir}")
    print(f"Run report:   {args.report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
