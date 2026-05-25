#!/usr/bin/env python3
"""VRPTW perturbation pilot — 6 instances × 16 perturbations × 3 seeds.

Exploratory only. Lives alongside (not on top of) the preregistered CVRP
Stage A pipeline. Builds a per-cell parquet table plus an interpretive
Markdown report.

Pipeline
--------
1. Load 6 Solomon-100 VRPTW instances from ``data/vrptw_instances/``.
2. Compute one baseline per instance (PyVRP 60s, seed=1) on the
   unperturbed instance.
3. For each (instance, perturbation_id) cell:
     a. Apply the perturbation deterministically using the baseline.
     b. Solve the perturbed instance under PyVRP with 3 seeds (1/2/3).
     c. Evaluate the baseline's fixed routes on the perturbed instance
        ("reuse_direct").
     d. Compute OBJ/PLAN_VALIDITY/STRUCT/SCHEDULE losses + bands.
4. Write ``data/probes/vrptw_perturbation_pilot.parquet``.
5. Write ``prereg/vrptw_perturbation_pilot_report.md``.

CLI::

    python scripts/run_vrptw_perturbation_pilot.py \\
        --instances C101 C201 R101 R201 RC101 RC201 \\
        --time-limit 60 --n-jobs 6 \\
        --out-dir data/probes \\
        --report-path prereg/vrptw_perturbation_pilot_report.md
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.metrics import adjusted_rand_score

# Allow running directly without editable install.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper import (  # noqa: E402
    SCALING_FACTOR,
    VRPTWSolveResult,
    evaluate_vrptw_solution,
    solve_vrptw,
)
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig  # noqa: E402
from vrp_copilot_bench.vrptw_instances import (  # noqa: E402
    DEFAULT_VRPTW_INSTANCE_DIR,
    load_vrptw_instance,
)
from vrp_copilot_bench.vrptw_perturbations import (  # noqa: E402
    PERTURBATION_IDS,
    apply_vrptw_perturbation,
    lookup_vrptw_perturbation,
)


# ---------------------------------------------------------------------------
# Defaults / thresholds

DEFAULT_INSTANCES: tuple[str, ...] = (
    "C101", "C201", "R101", "R201", "RC101", "RC201",
)
DEFAULT_SEEDS: tuple[int, ...] = (1, 2, 3)

# Loss thresholds (bands)
OBJ_EASY, OBJ_MEDIUM = 0.05, 0.15
STRUCT_EASY, STRUCT_MEDIUM = 0.10, 0.30
SCHEDULE_EASY, SCHEDULE_MEDIUM = 0.02, 0.05
ARI_STRUCT_UNSTABLE_THRESHOLD = 0.90
OBJ_UNSTABLE_THRESHOLD = 0.02

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vrptw_perturbation_pilot")


# ---------------------------------------------------------------------------
# Worker functions (module-level so loky can pickle)


def _worker_solve_baseline(
    instance_id: str, time_limit: float, instance_dir: Path,
) -> tuple[str, VRPTWSolveResult]:
    inst = load_vrptw_instance(instance_id, instance_dir=instance_dir)
    cfg = SolveConfig(time_limit_seconds=time_limit, seed=1)
    return (instance_id, solve_vrptw(inst, cfg))


def _worker_solve_perturbed(
    instance_id: str,
    perturbation_id: str,
    seed: int,
    time_limit: float,
    instance_dir: Path,
    baseline: VRPTWSolveResult,
) -> tuple[str, str, int, VRPTWSolveResult]:
    inst = load_vrptw_instance(instance_id, instance_dir=instance_dir)
    spec = lookup_vrptw_perturbation(perturbation_id)
    perturbed = apply_vrptw_perturbation(inst, spec, baseline)
    cfg = SolveConfig(time_limit_seconds=time_limit, seed=seed)
    return (instance_id, perturbation_id, seed, solve_vrptw(perturbed, cfg))


# ---------------------------------------------------------------------------
# Metric helpers


def _ari_on_common(a: dict[int, int], b: dict[int, int]) -> float:
    """ARI of two assignments restricted to customers present in both."""
    common = sorted(set(a) & set(b))
    if len(common) < 2:
        return math.nan
    la = np.fromiter((a[c] for c in common), dtype=np.int64, count=len(common))
    lb = np.fromiter((b[c] for c in common), dtype=np.int64, count=len(common))
    return float(adjusted_rand_score(la, lb))


def _band_obj(x: float) -> str:
    if math.isnan(x):
        return "n/a"
    if x <= OBJ_EASY:
        return "easy"
    if x <= OBJ_MEDIUM:
        return "medium"
    return "hard"


def _band_struct(x: float) -> str:
    if math.isnan(x):
        return "n/a"
    if x <= STRUCT_EASY:
        return "easy"
    if x <= STRUCT_MEDIUM:
        return "medium"
    return "hard"


def _band_schedule(x: float) -> str:
    if math.isnan(x):
        return "n/a"
    if x <= SCHEDULE_EASY:
        return "easy"
    if x <= SCHEDULE_MEDIUM:
        return "medium"
    return "hard"


def _band_plan_validity(feasible: bool) -> str:
    return "easy" if feasible else "hard"


def _infeasibility_kind(reuse_eval) -> str:
    """One of {none, capacity, time_window, both, coverage}.

    'coverage' is a small extension to the spec to label ORDER_CHANGE
    cells where the existing routes are capacity- and TW-feasible but
    inserted customers are unserved.
    """
    cap_ok = reuse_eval.feasible_capacity_only
    tw_ok = reuse_eval.feasible_tw_only
    if cap_ok and tw_ok:
        if reuse_eval.is_complete:
            return "none"
        return "coverage"
    if not cap_ok and tw_ok:
        return "capacity"
    if cap_ok and not tw_ok:
        return "time_window"
    return "both"


def _median_arrival_shift(
    a_schedule: dict[int, Any], b_schedule: dict[int, Any], depot_horizon: int,
) -> tuple[float, int]:
    """Median absolute ``start_service`` difference, normalized.

    Returns ``(loss, n_common)``. ``loss`` is NaN if fewer than 1 common
    customer exists or ``depot_horizon == 0``.
    """
    common = sorted(set(a_schedule) & set(b_schedule))
    if not common or depot_horizon <= 0:
        return math.nan, 0
    diffs = np.array([
        abs(a_schedule[c].start_service - b_schedule[c].start_service)
        for c in common
    ], dtype=np.float64)
    return float(np.median(diffs) / float(depot_horizon)), len(common)


# ---------------------------------------------------------------------------
# Per-cell assembly


def _build_row(
    instance,
    spec,
    baseline: VRPTWSolveResult,
    references: dict[int, VRPTWSolveResult],
    perturbed,
    reuse_eval,
    runtime_reference_s: float,
    runtime_reuse_s: float,
    runtime_baseline_s: float,
) -> dict[str, Any]:
    """Assemble the per-cell parquet row from solver outputs."""
    ref_s1 = references[1]
    ref_s2 = references[2]
    ref_s3 = references[3]

    # Reference stability flags.
    ari12 = _ari_on_common(ref_s1.assignment, ref_s2.assignment)
    ari13 = _ari_on_common(ref_s1.assignment, ref_s3.assignment)
    ari23 = _ari_on_common(ref_s2.assignment, ref_s3.assignment)
    aris = [a for a in (ari12, ari13, ari23) if not math.isnan(a)]
    ari_min = min(aris) if aris else math.nan
    obj_values = [ref_s1.objective, ref_s2.objective, ref_s3.objective]
    obj_unstable = (
        (max(obj_values) - min(obj_values)) / min(obj_values)
        > OBJ_UNSTABLE_THRESHOLD
        if min(obj_values) > 0 else False
    )
    struct_unstable = (
        ari_min < ARI_STRUCT_UNSTABLE_THRESHOLD
        if not math.isnan(ari_min) else False
    )

    # OBJ
    reuse_obj = float(reuse_eval.objective)
    ref_obj_s1 = float(ref_s1.objective)
    loss_obj = (
        abs(reuse_obj - ref_obj_s1) / ref_obj_s1
        if ref_obj_s1 > 0 else math.nan
    )

    # PLAN_VALIDITY
    loss_plan_validity = 0.0 if reuse_eval.feasible else 1.0
    infeas_kind = _infeasibility_kind(reuse_eval)

    # STRUCT
    ari_reuse_vs_ref = _ari_on_common(
        reuse_eval.assignment, ref_s1.assignment,
    )
    loss_struct = 1.0 - ari_reuse_vs_ref if not math.isnan(ari_reuse_vs_ref) else math.nan

    # SCHEDULE
    depot_horizon_scaled = (
        (int(instance.time_windows[0, 1]) - int(instance.time_windows[0, 0]))
        * SCALING_FACTOR
    )
    loss_schedule, n_common = _median_arrival_shift(
        reuse_eval.per_customer_schedule,
        ref_s1.per_customer_schedule,
        depot_horizon_scaled,
    )
    schedule_disruption, _ = _median_arrival_shift(
        reuse_eval.per_customer_schedule,
        baseline.per_customer_schedule,
        depot_horizon_scaled,
    )
    schedule_feasibility_loss = 0.0 if reuse_eval.total_time_warp == 0 else 1.0

    # Touched-customer / route helpers (tuples → comma-separated strings
    # for parquet portability).
    aff_customers = ",".join(map(str, perturbed.affected_customers))
    aff_routes = ",".join(map(str, perturbed.affected_baseline_routes))

    return {
        # ---- identifiers / perturbation metadata
        "instance_id": instance.instance_id,
        "perturbation_id": spec.perturbation_id,
        "perturbation_family": perturbed.perturbation_family,
        "perturbation_magnitude": float(perturbed.perturbation_magnitude),
        "n_affected_customers": int(perturbed.n_affected_customers),
        "affected_demand_share": float(perturbed.affected_demand_share),
        "affected_route_share": float(perturbed.affected_route_share),
        "n_inserted_customers": int(perturbed.n_inserted_customers),
        "affected_customers": aff_customers,
        "affected_baseline_routes": aff_routes,

        # ---- baseline
        "baseline_obj": float(baseline.objective),
        "baseline_n_routes": int(baseline.n_routes),

        # ---- reference (3 seeds on perturbed instance)
        "reference_obj_s1": float(ref_s1.objective),
        "reference_obj_s2": float(ref_s2.objective),
        "reference_obj_s3": float(ref_s3.objective),
        "reference_obj_best": float(min(obj_values)),
        "reference_n_routes_s1": int(ref_s1.n_routes),
        "reference_n_routes_s2": int(ref_s2.n_routes),
        "reference_n_routes_s3": int(ref_s3.n_routes),
        "reference_ari_s1s2": float(ari12) if not math.isnan(ari12) else None,
        "reference_ari_s1s3": float(ari13) if not math.isnan(ari13) else None,
        "reference_ari_s2s3": float(ari23) if not math.isnan(ari23) else None,
        "reference_ari_min":  float(ari_min) if not math.isnan(ari_min) else None,
        "reference_struct_unstable": bool(struct_unstable),
        "reference_obj_unstable": bool(obj_unstable),

        # ---- reuse_direct on perturbed instance
        "reuse_obj": reuse_obj,
        "reuse_feasible": bool(reuse_eval.feasible),
        "reuse_feasible_capacity_only": bool(reuse_eval.feasible_capacity_only),
        "reuse_feasible_tw_only": bool(reuse_eval.feasible_tw_only),
        "reuse_total_time_warp": int(reuse_eval.total_time_warp),
        "reuse_total_wait": int(reuse_eval.total_wait),
        "reuse_total_duration": int(reuse_eval.total_duration),
        "reuse_n_late_customers": int(reuse_eval.n_late_customers),
        "reuse_max_lateness": int(reuse_eval.max_lateness),
        "reuse_median_arrival_shift":
            float(loss_schedule) if not math.isnan(loss_schedule) else None,
        "schedule_disruption":
            float(schedule_disruption) if not math.isnan(schedule_disruption) else None,
        "schedule_feasibility_loss": float(schedule_feasibility_loss),
        "infeasibility_kind": infeas_kind,

        # ---- four losses + bands
        "loss_obj": float(loss_obj) if not math.isnan(loss_obj) else None,
        "loss_plan_validity": float(loss_plan_validity),
        "loss_struct": float(loss_struct) if not math.isnan(loss_struct) else None,
        "loss_schedule": float(loss_schedule) if not math.isnan(loss_schedule) else None,
        "band_obj": _band_obj(loss_obj),
        "band_plan_validity": _band_plan_validity(reuse_eval.feasible),
        "band_struct": _band_struct(loss_struct),
        "band_schedule": _band_schedule(loss_schedule),

        # ---- timing / provenance
        "runtime_baseline_s": float(runtime_baseline_s),
        "runtime_reference_s": float(runtime_reference_s),
        "runtime_reuse_s": float(runtime_reuse_s),
        "pyvrp_version": baseline.pyvrp_version,
    }


# ---------------------------------------------------------------------------
# Main pipeline


def run_pilot(
    instances: tuple[str, ...],
    seeds: tuple[int, ...],
    time_limit: float,
    n_jobs: int,
    instance_dir: Path,
) -> pd.DataFrame:
    # ---- Step 1: baselines (parallel, one per instance)
    log.info(
        "Step 1/3: computing %d baselines (60s seed=1) — running in parallel",
        len(instances),
    )
    t0 = time.monotonic()
    baseline_jobs = [
        delayed(_worker_solve_baseline)(iid, time_limit, instance_dir)
        for iid in instances
    ]
    baseline_results: list[tuple[str, VRPTWSolveResult]] = Parallel(
        n_jobs=min(n_jobs, len(instances)),
        backend="loky", verbose=5,
    )(baseline_jobs)
    baselines: dict[str, VRPTWSolveResult] = dict(baseline_results)
    runtime_baseline = time.monotonic() - t0
    log.info("Step 1/3: %d baselines done in %.1fs", len(baselines), runtime_baseline)

    # ---- Step 2: reference solves (parallel; 3 seeds per cell)
    log.info(
        "Step 2/3: dispatching %d perturbed reference solves (%d cells × %d seeds)",
        len(instances) * len(PERTURBATION_IDS) * len(seeds),
        len(instances) * len(PERTURBATION_IDS), len(seeds),
    )
    t0 = time.monotonic()
    ref_jobs = []
    for iid in instances:
        baseline = baselines[iid]
        for pid in PERTURBATION_IDS:
            for seed in seeds:
                ref_jobs.append(delayed(_worker_solve_perturbed)(
                    iid, pid, seed, time_limit, instance_dir, baseline,
                ))
    ref_results = Parallel(n_jobs=n_jobs, backend="loky", verbose=5)(ref_jobs)
    runtime_reference = time.monotonic() - t0
    log.info("Step 2/3: %d reference solves done in %.1fs", len(ref_results), runtime_reference)

    # Bucket references by (instance_id, perturbation_id, seed).
    references: dict[str, dict[str, dict[int, VRPTWSolveResult]]] = {}
    for iid, pid, seed, r in ref_results:
        references.setdefault(iid, {}).setdefault(pid, {})[seed] = r

    # ---- Step 3: reuse_direct evaluations + row assembly (main-process loop)
    log.info("Step 3/3: computing %d reuse_direct evaluations + per-cell metrics",
             len(instances) * len(PERTURBATION_IDS))
    t0 = time.monotonic()
    rows: list[dict[str, Any]] = []
    for iid in instances:
        baseline = baselines[iid]
        runtime_baseline_s = baseline.runtime_seconds
        inst = load_vrptw_instance(iid, instance_dir=instance_dir)
        for pid in PERTURBATION_IDS:
            spec = lookup_vrptw_perturbation(pid)
            perturbed = apply_vrptw_perturbation(inst, spec, baseline)
            cell_refs = references[iid][pid]
            t_reuse0 = time.perf_counter()
            reuse_eval = evaluate_vrptw_solution(perturbed, baseline.routes)
            runtime_reuse_s = time.perf_counter() - t_reuse0
            runtime_reference_s = sum(
                cell_refs[s].runtime_seconds for s in seeds
            )
            rows.append(_build_row(
                instance=inst,
                spec=spec,
                baseline=baseline,
                references=cell_refs,
                perturbed=perturbed,
                reuse_eval=reuse_eval,
                runtime_reference_s=runtime_reference_s,
                runtime_reuse_s=runtime_reuse_s,
                runtime_baseline_s=runtime_baseline_s,
            ))
    log.info("Step 3/3: %d cells assembled in %.1fs", len(rows), time.monotonic() - t0)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Report rendering


def _band_counts(df: pd.DataFrame, col: str) -> dict[str, int]:
    return df[col].value_counts().to_dict()


def _format_band_row(counts: dict[str, int], total: int, columns: list[str]) -> str:
    parts = []
    for k in columns:
        v = counts.get(k, 0)
        pct = (100.0 * v / total) if total else 0.0
        parts.append(f"{v} ({pct:.1f}%)")
    return " | ".join(parts)


def _build_markdown_report(df: pd.DataFrame, parquet_path: Path,
                           time_limit: float, n_jobs: int) -> str:
    n_total = len(df)
    pyvrp_version = (
        df["pyvrp_version"].iloc[0] if n_total else "unknown"
    )

    lines: list[str] = []
    lines.append("# VRPTW Perturbation Pilot — Report\n")
    lines.append(f"Generated: {pd.Timestamp.now().isoformat(timespec='seconds')}\n")

    # ---- Purpose
    lines.append("## Purpose and research question\n")
    lines.append(
        "Does VRPTW remain structurally and operationally well-defined "
        "under realistic perturbations, and do the claim families OBJ, "
        "PLAN_VALIDITY, STRUCT, and SCHEDULE produce non-trivial "
        "sufficiency patterns?\n"
    )
    lines.append(
        "Exploratory companion to the preregistered CVRP Stage A "
        "benchmark. **No prereg changes** and no CVRP code modifications.\n"
    )

    # ---- Dataset / solver setup
    lines.append("## Dataset and solver setup\n")
    instance_list = sorted(df["instance_id"].unique().tolist())
    lines.append(
        f"- Instances: {', '.join(instance_list)} (Solomon-100, "
        f"PyVRP `Instances` mirror, CVRPLIB-extended VRPTW `.vrp` format).\n"
        f"- Seeds (per perturbation cell): 1, 2, 3.\n"
        f"- Time limit: {time_limit:.0f}s per PyVRP solve.\n"
        f"- Solver: PyVRP {pyvrp_version} via `pyvrp.solve(..., "
        f"stop=MaxRuntime, display=False, collect_stats=False)`.\n"
        f"- Workers: joblib loky, `n_jobs={n_jobs}`.\n"
        f"- Total cells: {n_total} ({len(instance_list)} instances × "
        f"{len(PERTURBATION_IDS)} perturbations).\n"
    )

    # ---- Perturbation grid
    lines.append("## Perturbation grid\n")
    lines.append(
        "Grid (4 per family) — selection logic uses the baseline schedule "
        "(seed=1 60s PyVRP on the unperturbed instance):\n"
    )
    lines.append(
        "| ID | Family | Selector | Magnitude |\n"
        "|---|---|---|---|\n"
        "| TT_1 | TRAVEL_TIME | route w/ highest total waiting | ×1.10 duration |\n"
        "| TT_2 | TRAVEL_TIME | route w/ lowest min slack-to-tw_late | ×1.20 |\n"
        "| TT_3 | TRAVEL_TIME | densest customer quartile | ×1.30 |\n"
        "| TT_4 | TRAVEL_TIME | farthest customer quartile | ×1.50 |\n"
        "| TW_1 | TIME_WINDOW | route w/ highest mean slack | tighten 10% |\n"
        "| TW_2 | TIME_WINDOW | route w/ lowest mean slack | tighten 20% |\n"
        "| TW_3 | TIME_WINDOW | final third of every route | shift earlier 10% |\n"
        "| TW_4 | TIME_WINDOW | first third of every route | shift later 10% |\n"
        "| ST_1 | SERVICE_TIME | route w/ highest total waiting | ×1.10 service |\n"
        "| ST_2 | SERVICE_TIME | route w/ lowest min slack | ×1.25 |\n"
        "| ST_3 | SERVICE_TIME | densest customer quartile | ×1.50 |\n"
        "| ST_4 | SERVICE_TIME | top-demand quartile | ×2.00 |\n"
        "| OC_1 | ORDER_CHANGE | +1 cust near highest-slack route, flexible TW | demand 0.05·cap |\n"
        "| OC_2 | ORDER_CHANGE | +1 cust near lowest-slack route, tight TW | demand 0.05·cap |\n"
        "| OC_3 | ORDER_CHANGE | +3 clust near densest region, flexible TW | demand 0.15·cap |\n"
        "| OC_4 | ORDER_CHANGE | +3 clust near low-slack route, tight TW | demand 0.20·cap |\n"
    )

    # ---- Scaling
    lines.append("## Scaling convention\n")
    lines.append(
        f"Same as the Phase 1 probe: all distance, duration, time-window, "
        f"and service-time integers are multiplied by **{SCALING_FACTOR}** "
        f"before being handed to PyVRP. Stability and schedule metrics in "
        f"this report are scale-invariant; absolute objectives are in "
        f"×{SCALING_FACTOR} distance units.\n"
    )
    lines.append(
        "TRAVEL_TIME perturbations modify the duration matrix only; "
        "distances are unchanged. So OBJ changes there reflect either "
        "(a) PyVRP picking different routes under the perturbed timing or "
        "(b) reuse on tighter-than-feasible timing — not raw distance "
        "scaling.\n"
    )

    # ---- Aggregate band rates by claim family
    lines.append("## Aggregate band rates by claim family\n")

    def render_family_table(col_name: str, band_cols: list[str]) -> str:
        counts = _band_counts(df, col_name)
        row = _format_band_row(counts, n_total, band_cols)
        return f"| {col_name} | {row} |"

    lines.append(
        "| Loss | easy | medium | hard |\n"
        "|---|---|---|---|\n"
        + render_family_table("band_obj", ["easy", "medium", "hard"]) + "\n"
        + render_family_table("band_struct", ["easy", "medium", "hard"]) + "\n"
        + render_family_table("band_schedule", ["easy", "medium", "hard"]) + "\n"
    )
    pv_counts = _band_counts(df, "band_plan_validity")
    pv_row = _format_band_row(pv_counts, n_total, ["easy", "hard"])
    lines.append(
        "PLAN_VALIDITY (binary):\n\n"
        "| Loss | easy (feasible) | hard (infeasible) |\n"
        "|---|---|---|\n"
        f"| band_plan_validity | {pv_row} |\n"
    )

    # ---- Aggregate band rates by perturbation family
    lines.append("## Aggregate band rates by perturbation family\n")
    fam_blocks: list[str] = []
    for fam in ("TRAVEL_TIME", "TIME_WINDOW", "SERVICE_TIME", "ORDER_CHANGE"):
        sub = df[df["perturbation_family"] == fam]
        n_sub = len(sub)
        if not n_sub:
            continue
        fam_blocks.append(f"### {fam} ({n_sub} cells)\n")
        fam_blocks.append("| Loss | easy | medium | hard |\n|---|---|---|---|\n")
        for col in ("band_obj", "band_struct", "band_schedule"):
            counts = _band_counts(sub, col)
            fam_blocks.append(
                f"| {col} | "
                f"{_format_band_row(counts, n_sub, ['easy', 'medium', 'hard'])} |\n"
            )
        pv_sub = _band_counts(sub, "band_plan_validity")
        pv_sub_row = _format_band_row(pv_sub, n_sub, ["easy", "hard"])
        fam_blocks.append(
            f"PLAN_VALIDITY: easy/hard → {pv_sub_row}\n"
        )
    lines.extend(fam_blocks)

    # ---- Reference stability
    lines.append("## Reference stability summary\n")
    obj_unst_rate = float(df["reference_obj_unstable"].mean())
    struct_unst_rate = float(df["reference_struct_unstable"].mean())
    median_ari = float(df["reference_ari_min"].dropna().median()) if df["reference_ari_min"].notna().any() else float("nan")
    lines.append(
        f"- Reference objective-instability rate (3-seed `(max-min)/min > 0.02`): "
        f"**{obj_unst_rate:.3f}** ({int(df['reference_obj_unstable'].sum())}/{n_total} cells)\n"
        f"- Reference structural-instability rate (3-seed pairwise `ari_min < 0.90`): "
        f"**{struct_unst_rate:.3f}** ({int(df['reference_struct_unstable'].sum())}/{n_total} cells)\n"
        f"- Median reference `ari_min`: **{median_ari:.3f}**\n"
    )

    # ---- PLAN_VALIDITY infeasibility breakdown
    lines.append("## PLAN_VALIDITY infeasibility breakdown\n")
    kinds = df["infeasibility_kind"].value_counts().to_dict()
    lines.append(
        "| infeasibility_kind | count | share |\n|---|---|---|\n"
    )
    for kind in ("none", "capacity", "time_window", "both", "coverage"):
        c = kinds.get(kind, 0)
        share = 100.0 * c / n_total if n_total else 0.0
        lines.append(f"| {kind} | {c} | {share:.1f}% |\n")

    # ---- SCHEDULE summary
    lines.append("## SCHEDULE summary\n")
    med_sch = float(df["loss_schedule"].dropna().median()) if df["loss_schedule"].notna().any() else float("nan")
    med_dis = float(df["schedule_disruption"].dropna().median()) if df["schedule_disruption"].notna().any() else float("nan")
    sch_feas_only_hard = df[
        (df["schedule_feasibility_loss"] == 0.0)
        & (df["band_schedule"] == "hard")
    ]
    n_sf_only = len(sch_feas_only_hard)
    lines.append(
        f"- Median `loss_schedule` (vs reference seed-1 schedule): **{med_sch:.4f}**\n"
        f"- Median `schedule_disruption` (vs baseline unperturbed schedule): **{med_dis:.4f}**\n"
        f"- Cells schedule-feasible (time_warp=0) but `band_schedule=hard`: "
        f"**{n_sf_only}/{n_total}** "
        f"({100.0 * n_sf_only / n_total:.1f}% — schedule shifts without TW violation)\n"
    )

    # ---- Interpretation
    lines.append("## Interpretation\n")
    obj_hard = (df["band_obj"] == "hard").mean()
    struct_hard = (df["band_struct"] == "hard").mean()
    sch_hard = (df["band_schedule"] == "hard").mean()
    pv_hard = (df["band_plan_validity"] == "hard").mean()
    lines.append(
        f"- **Non-trivial labels?** Hard rates: OBJ {obj_hard:.2f}, "
        f"STRUCT {struct_hard:.2f}, SCHEDULE {sch_hard:.2f}, "
        f"PLAN_VALIDITY {pv_hard:.2f}. The pilot produces a "
        f"mix of easy/medium/hard cells if these are away from 0 and 1.\n"
        f"- **STRUCT stability under perturbations:** the structural "
        f"reference is unstable on **{struct_unst_rate:.0%}** of cells. "
        f"This is the equivalent of CVRP Stage A's `reference_struct_unstable` "
        f"flag for the perturbed VRPTW instance.\n"
        f"- **Is SCHEDULE adding information beyond PLAN_VALIDITY?** "
        f"If a non-trivial fraction of cells have `schedule_feasibility_loss=0` "
        f"(no TW violation) but `band_schedule != easy` (the schedule still "
        f"shifts materially), SCHEDULE is signaling something PLAN_VALIDITY "
        f"misses: here, **{n_sf_only}/{n_total}** cells fit that pattern.\n"
    )

    # ---- Caveats
    lines.append("## Caveats\n")
    lines.append(
        f"- **Exploratory.** Not preregistered. Magnitudes are pilot-only and "
        f"may be re-tuned before any larger benchmark.\n"
        f"- **n = {n_total} cells** (6 instances × 16 perturbations). "
        f"Statistical conclusions are directional.\n"
        f"- **Solomon-100 only.** No Homberger / Gehring benchmarks.\n"
        f"- **No BKS / quality validation.** Objectives are in "
        f"×{SCALING_FACTOR} distance units.\n"
        f"- **`infeasibility_kind='coverage'`** is a small spec extension for "
        f"ORDER_CHANGE cells where the existing routes are capacity- and "
        f"TW-feasible but inserted customers are unserved by the baseline plan.\n"
    )

    lines.append(f"\nParquet output: `{parquet_path}`\n")

    return "".join(lines)


# ---------------------------------------------------------------------------
# CLI


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="run_vrptw_perturbation_pilot",
                                description=__doc__)
    p.add_argument("--instances", nargs="+", default=list(DEFAULT_INSTANCES))
    p.add_argument("--time-limit", type=float, default=60.0)
    p.add_argument("--n-jobs", type=int, default=6)
    p.add_argument("--instance-dir", type=Path,
                   default=DEFAULT_VRPTW_INSTANCE_DIR)
    p.add_argument("--out-dir", type=Path, default=Path("data/probes"))
    p.add_argument(
        "--report-path", type=Path,
        default=Path("prereg/vrptw_perturbation_pilot_report.md"),
    )
    args = p.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)

    df = run_pilot(
        instances=tuple(args.instances),
        seeds=DEFAULT_SEEDS,
        time_limit=args.time_limit,
        n_jobs=args.n_jobs,
        instance_dir=args.instance_dir,
    )

    parquet_path = args.out_dir / "vrptw_perturbation_pilot.parquet"
    df.to_parquet(parquet_path, index=False)
    log.info("Wrote %d rows to %s", len(df), parquet_path)

    report = _build_markdown_report(
        df, parquet_path, time_limit=args.time_limit, n_jobs=args.n_jobs,
    )
    args.report_path.write_text(report)
    log.info("Wrote report to %s", args.report_path)

    # Console summary
    print()
    print(f"Cells: {len(df)}")
    for col in ("band_obj", "band_struct", "band_schedule"):
        counts = df[col].value_counts().to_dict()
        print(f"  {col}: " + json.dumps(
            {k: int(v) for k, v in counts.items()}, sort_keys=True,
        ))
    pv_counts = df["band_plan_validity"].value_counts().to_dict()
    print(
        "  band_plan_validity: "
        + json.dumps({k: int(v) for k, v in pv_counts.items()}, sort_keys=True)
    )
    print(
        f"  reference_obj_unstable_rate    = "
        f"{df['reference_obj_unstable'].mean():.3f}"
    )
    print(
        f"  reference_struct_unstable_rate = "
        f"{df['reference_struct_unstable'].mean():.3f}"
    )
    if df["reference_ari_min"].notna().any():
        print(
            f"  median reference_ari_min       = "
            f"{df['reference_ari_min'].dropna().median():.3f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
