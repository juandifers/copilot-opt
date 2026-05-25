#!/usr/bin/env python3
"""Three-probe diagnostic script for Stage A §12 failures.

Probe A — 10 audit pairs at PyVRP 120s (seeds 1/2/3)
    Question: does doubling time budget reduce structural multi-modality?
    Output: data/probes/probe_a_120s.parquet

Probe B — CAPACITY de-escalation on 5 instances
    Grid: rho ∈ {0.01, 0.02, 0.05, 0.10} (standard: {0.02, 0.05, 0.10, 0.20})
    Question: does stepping back the magnitude fix STRUCT×CAPACITY?
    Output: data/probes/probe_b_cap_destep.parquet

Probe C — INSERTION de-escalation on same 5 instances
    Grid: gamma ∈ {0.15, 0.40, 0.80, 1.50} (standard: {0.30, 0.70, 1.20, 2.00})
    Question: does stepping back the magnitude fix RANK×INSERTION?
    Output: data/probes/probe_c_ins_destep.parquet

Usage:
    python scripts/run_probes.py [--n-jobs N] [--probe a|b|c|all]
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from joblib import Parallel, delayed
from sklearn.metrics import adjusted_rand_score

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vrp_copilot_bench.actions import BASE_ACTIONS, run_action
from vrp_copilot_bench.actions._conversion import solve_result_to_action_result
from vrp_copilot_bench.baselines import load_baseline_solution
from vrp_copilot_bench.instances import load_instance, n_customers_for
from vrp_copilot_bench.labels import (
    compute_losses_and_bands,
    _compute_reference_struct_unstable,
    _compute_reference_rank_unstable,
    _pairwise_ari,
)
from vrp_copilot_bench.perturbations import PerturbationSpec, apply_perturbation
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig, solve

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_probes")

# ---------------------------------------------------------------------------
# Fixed probe configuration
# ---------------------------------------------------------------------------

# Probe A: 10 audit pairs selected from Stage A (stratified by family,
# smallest struct-unstable instances to minimize wall-clock).
PROBE_A_PAIRS: list[tuple[str, str]] = [
    ("X-n101-k25", "CAP_3"),
    ("X-n106-k14", "CAP_4"),
    ("X-n110-k13", "CAP_3"),
    ("X-n106-k14", "DEM_2"),
    ("X-n125-k30", "DEM_3"),
    ("X-n139-k10", "DEM_3"),
    ("X-n106-k14", "DIST_3"),
    ("X-n106-k14", "DIST_2"),
    ("X-n125-k30", "INS_1"),
    ("X-n129-k18", "INS_1"),
]

# Probe B: de-escalated CAPACITY grid (Appendix A.1).
# standard grid: {CAP_1:0.02, CAP_2:0.05, CAP_3:0.10, CAP_4:0.20}
PROBE_B_CAP: dict[str, float] = {
    "pCAP_1": 0.01,
    "pCAP_2": 0.02,
    "pCAP_3": 0.05,
    "pCAP_4": 0.10,
}

# Probe C: de-escalated INSERTION grid (Appendix A.4).
# standard grid: {INS_1:0.30, INS_2:0.70, INS_3:1.20, INS_4:2.00}
# Keeping original pids so apply_insertion can look up n_new per pid.
PROBE_C_INS: dict[str, float] = {
    "INS_1": 0.15,
    "INS_2": 0.40,
    "INS_3": 0.80,
    "INS_4": 1.50,
}
# Probe id labels used in the parquet (avoids confusion with stage-A pids).
PROBE_C_LABELS: dict[str, str] = {
    "INS_1": "pINS_1",
    "INS_2": "pINS_2",
    "INS_3": "pINS_3",
    "INS_4": "pINS_4",
}

# Probes B and C share the same 5 instances, stratified by size.
PROBE_BC_INSTANCES: list[str] = [
    "X-n101-k25",   # 100 customers (small)
    "X-n125-k30",   # 124 customers (small)
    "X-n153-k22",   # 152 customers (medium)
    "X-n228-k23",   # 227 customers (medium)
    "X-n303-k21",   # 302 customers (large)
]

CLAIM_FAMILIES = ("OBJ", "PLAN_VALIDITY", "STRUCT", "RANK")

# ---------------------------------------------------------------------------
# Joblib worker functions (module-level for picklability)
# ---------------------------------------------------------------------------


def _worker_pyvrp(perturbed, time_limit: float, seed: int, action_name: str):
    """Run one PyVRP solve; return ActionResult."""
    config = SolveConfig(time_limit_seconds=time_limit, seed=seed)
    result = solve(perturbed, config)
    return solve_result_to_action_result(result, perturbed, action_name=action_name)


def _worker_action(action_name: str, perturbed, baseline):
    """Dispatch one base action; return ActionResult."""
    return run_action(action_name, perturbed, baseline)


# ---------------------------------------------------------------------------
# Probe A
# ---------------------------------------------------------------------------


def run_probe_a(n_jobs: int = 6) -> pd.DataFrame:
    """Run 10 audit pairs × 3 seeds at 120s. Return per-pair DataFrame."""
    log.info("=== PROBE A: 10 pairs × 3 seeds × 120s ===")
    log.info("Estimated wall-clock with %d workers: ~%d min", n_jobs,
             math.ceil(len(PROBE_A_PAIRS) * 3 * 120 / n_jobs / 60))

    # Build all perturbed instances (fast, no I/O).
    jobs: list[tuple] = []  # (perturbed, seed, pair_idx)
    pair_meta: list[dict] = []
    for inst_id, pert_id in PROBE_A_PAIRS:
        instance = load_instance(inst_id)
        baseline = load_baseline_solution(inst_id)
        family = pert_id.split("_")[0]
        family_long = {
            "CAP": "CAPACITY", "DEM": "DEMAND",
            "DIST": "DISTANCE", "INS": "INSERTION",
        }[family]
        spec = PerturbationSpec(
            perturbation_id=pert_id,
            family=family_long,
            magnitude=_standard_magnitude(pert_id),
        )
        perturbed = apply_perturbation(instance, spec, baseline)
        for seed in (1, 2, 3):
            action_name = f"pyvrp_120s_seed{seed}"
            jobs.append((perturbed, 120.0, seed, action_name))
        pair_meta.append({
            "instance_id": inst_id,
            "perturbation_id": pert_id,
            "perturbation_family": family_long,
            "n_customers": n_customers_for(inst_id),
            "baseline": baseline,
        })

    log.info("Dispatching %d PyVRP jobs (120s each)...", len(jobs))
    t0 = time.monotonic()
    results_flat = Parallel(n_jobs=n_jobs, backend="loky", verbose=5)(
        delayed(_worker_pyvrp)(p, tl, s, name)
        for p, tl, s, name in jobs
    )
    log.info("Probe A solves done in %.1f s", time.monotonic() - t0)

    # Reassemble: 3 results per pair.
    rows = []
    for i, meta in enumerate(pair_meta):
        s1 = results_flat[i * 3]
        s2 = results_flat[i * 3 + 1]
        s3 = results_flat[i * 3 + 2]

        ari_12 = _pairwise_ari(s1.assignment, s2.assignment)
        ari_13 = _pairwise_ari(s1.assignment, s3.assignment)
        ari_23 = _pairwise_ari(s2.assignment, s3.assignment)
        ari_min = min(ari_12, ari_13, ari_23)

        obj_unstable = not (
            math.isclose(s1.objective or 0, s2.objective or 0, rel_tol=0.02)
            and math.isclose(s1.objective or 0, s3.objective or 0, rel_tol=0.02)
        )
        struct_unstable = ari_min < 0.90
        rank_unstable = _compute_reference_rank_unstable(
            s1, s2, s3, meta["baseline"]
        )

        rows.append({
            "instance_id": meta["instance_id"],
            "perturbation_id": meta["perturbation_id"],
            "perturbation_family": meta["perturbation_family"],
            "n_customers": meta["n_customers"],
            "s1_obj": s1.objective,
            "s2_obj": s2.objective,
            "s3_obj": s3.objective,
            "ari_s1s2": round(ari_12, 6),
            "ari_s1s3": round(ari_13, 6),
            "ari_s2s3": round(ari_23, 6),
            "ari_min": round(ari_min, 6),
            "obj_unstable_120s": obj_unstable,
            "struct_unstable_120s": struct_unstable,
            "rank_unstable_120s": rank_unstable,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Probes B and C
# ---------------------------------------------------------------------------


def _run_probe_bc(
    probe_label: str,
    instances: list[str],
    pert_specs: list[tuple[str, str, float, str]],  # (probe_pid, std_pid, magnitude, family_long)
    n_jobs: int = 6,
) -> pd.DataFrame:
    """Generic runner for Probes B and C."""
    log.info("=== %s: %d instances × %d perturbations × %d actions ===",
             probe_label, len(instances), len(pert_specs), len(BASE_ACTIONS))

    # Build all (perturbed, baseline, action) triples.
    jobs = []  # (action_name, perturbed, baseline, instance_id, probe_pid)
    for inst_id in instances:
        instance = load_instance(inst_id)
        baseline = load_baseline_solution(inst_id)
        for probe_pid, std_pid, magnitude, family_long in pert_specs:
            spec = PerturbationSpec(
                perturbation_id=std_pid,  # real pid for n_new lookup in INSERTION
                family=family_long,
                magnitude=magnitude,
            )
            perturbed = apply_perturbation(instance, spec, baseline)
            # Run reference (pyvrp_60s seed=1) plus all base actions.
            for action_name in BASE_ACTIONS:
                jobs.append((action_name, perturbed, baseline, inst_id, probe_pid, magnitude))

    log.info("Dispatching %d action jobs...", len(jobs))
    t0 = time.monotonic()
    results = Parallel(n_jobs=n_jobs, backend="loky", verbose=5)(
        delayed(_worker_action)(action_name, perturbed, baseline)
        for action_name, perturbed, baseline, *_ in jobs
    )
    log.info("%s solves done in %.1f s", probe_label, time.monotonic() - t0)

    # Group results by (instance_id, probe_pid).
    key_to_actions: dict[tuple, dict[str, object]] = {}
    for (action_name, perturbed, baseline, inst_id, probe_pid, magnitude), result in zip(jobs, results):
        key = (inst_id, probe_pid)
        if key not in key_to_actions:
            key_to_actions[key] = {
                "instance_id": inst_id,
                "probe_pid": probe_pid,
                "perturbation_magnitude": magnitude,
                "perturbation_family": perturbed.perturbation_family,
                "baseline": baseline,
                "actions": {},
            }
        key_to_actions[key]["actions"][action_name] = result

    # Build cell-action rows (mirror Stage A schema subset).
    rows = []
    for (inst_id, probe_pid), grp in key_to_actions.items():
        action_results = grp["actions"]
        reference = action_results.get("pyvrp_60s")
        if reference is None:
            log.warning("Missing pyvrp_60s reference for %s / %s; skipping", inst_id, probe_pid)
            continue
        baseline = grp["baseline"]
        for claim_family in CLAIM_FAMILIES:
            for action_name, action_result in action_results.items():
                labels = compute_losses_and_bands(
                    action_result, reference, claim_family, baseline
                )
                rows.append({
                    "instance_id": inst_id,
                    "perturbation_id": probe_pid,
                    "perturbation_magnitude": grp["perturbation_magnitude"],
                    "perturbation_family": grp["perturbation_family"],
                    "claim_family": claim_family,
                    "action": action_name,
                    "action_objective": action_result.objective,
                    "action_feasible": action_result.feasible,
                    "action_n_overload": action_result.n_overload,
                    "action_max_overload": action_result.max_overload_fraction,
                    "reference_objective": reference.objective,
                    "reference_feasible": reference.feasible,
                    "loss_obj": labels.loss_obj,
                    "loss_struct": labels.loss_struct,
                    "loss_rank": labels.loss_rank,
                    "loss_plan_validity": labels.loss_plan_validity,
                    "band_obj": labels.band_obj,
                    "band_struct": labels.band_struct,
                    "band_rank": labels.band_rank,
                    "band_plan_validity": labels.band_plan_validity,
                })

    return pd.DataFrame(rows)


def run_probe_b(n_jobs: int = 6) -> pd.DataFrame:
    pert_specs = [
        (probe_pid, probe_pid.replace("p", ""), magnitude, "CAPACITY")
        for probe_pid, magnitude in PROBE_B_CAP.items()
    ]
    return _run_probe_bc("PROBE B (CAP destep)", PROBE_BC_INSTANCES, pert_specs, n_jobs)


def run_probe_c(n_jobs: int = 6) -> pd.DataFrame:
    pert_specs = [
        (PROBE_C_LABELS[std_pid], std_pid, magnitude, "INSERTION")
        for std_pid, magnitude in PROBE_C_INS.items()
    ]
    return _run_probe_bc("PROBE C (INS destep)", PROBE_BC_INSTANCES, pert_specs, n_jobs)


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------


def _standard_magnitude(perturbation_id: str) -> float:
    magnitudes = {
        "CAP_1": 0.02, "CAP_2": 0.05, "CAP_3": 0.10, "CAP_4": 0.20,
        "DIST_1": 2.0, "DIST_2": 2.0, "DIST_3": 2.0, "DIST_4": 2.0,
        "DEM_1": 0.10, "DEM_2": 0.50, "DEM_3": 0.50, "DEM_4": 1.00,
        "INS_1": 0.30, "INS_2": 0.70, "INS_3": 1.20, "INS_4": 2.00,
    }
    return magnitudes[perturbation_id]


def _band_fraction(df: pd.DataFrame, band_col: str, claim: str, fam: str,
                   action: str = "reuse_direct") -> dict:
    sub = df[(df["claim_family"] == claim) & (df["perturbation_family"] == fam)
             & (df["action"] == action)]
    if len(sub) == 0:
        return {"n": 0, "easy": float("nan"), "medium": float("nan"), "hard": float("nan")}
    return {
        "n": len(sub),
        "easy": (sub[band_col] == "easy").mean(),
        "medium": (sub[band_col] == "medium").mean(),
        "hard": (sub[band_col] == "hard").mean(),
    }


def summarize_probe_a(df: pd.DataFrame) -> str:
    lines = ["## Probe A — 120s Reference Stability (10 pairs)\n"]
    lines.append(f"n_pairs={len(df)}  time_budget=120s  seeds=1/2/3\n")
    lines.append(
        f"{'Instance':<20} {'Pert':<8} {'Family':<12} "
        f"{'ARI s1s2':>9} {'ARI s1s3':>9} {'ARI s2s3':>9} {'ARI_min':>8} "
        f"{'OBJ?':>5} {'STR?':>5} {'RNK?':>5}"
    )
    lines.append("-" * 100)
    for _, r in df.iterrows():
        lines.append(
            f"{r['instance_id']:<20} {r['perturbation_id']:<8} {r['perturbation_family']:<12} "
            f"{r['ari_s1s2']:>9.4f} {r['ari_s1s3']:>9.4f} {r['ari_s2s3']:>9.4f} {r['ari_min']:>8.4f} "
            f"{'Y' if r['obj_unstable_120s'] else 'N':>5} "
            f"{'Y' if r['struct_unstable_120s'] else 'N':>5} "
            f"{'Y' if r['rank_unstable_120s'] else 'N':>5}"
        )
    struct_rate_120 = df["struct_unstable_120s"].mean()
    rank_rate_120 = df["rank_unstable_120s"].mean()
    obj_rate_120 = df["obj_unstable_120s"].mean()
    lines.append("")
    lines.append(f"**Aggregate rates at 120s (n={len(df)}):**")
    lines.append(f"- obj_unstable:    {obj_rate_120:.3f}  (Stage A 60s baseline: 0.000)")
    lines.append(f"- struct_unstable: {struct_rate_120:.3f}  (Stage A 60s baseline: 0.926)")
    lines.append(f"- rank_unstable:   {rank_rate_120:.3f}  (Stage A 60s baseline: 0.699)")
    lines.append("")
    lines.append(f"ARI_min distribution (120s, struct-unstable pairs):")
    unstable_120 = df[df["struct_unstable_120s"] == True]["ari_min"]
    if len(unstable_120):
        lines.append(f"  median={unstable_120.median():.4f}  "
                     f"min={unstable_120.min():.4f}  max={unstable_120.max():.4f}")
    else:
        lines.append("  (no struct-unstable pairs at 120s)")
    lines.append("")
    lines.append("**Interpretation:** "
                 + ("doubling the time budget meaningfully reduces structural multi-modality."
                    if struct_rate_120 < 0.5
                    else "structural multi-modality persists at 120s — noise floor appears solver-structural."))
    return "\n".join(lines)


def summarize_probe_b(df: pd.DataFrame) -> str:
    lines = ["## Probe B — CAPACITY De-escalation (5 instances × 4 de-stepped perturbations)\n"]
    lines.append(f"De-escalated grid: rho ∈ {{0.01, 0.02, 0.05, 0.10}} "
                 f"(standard: {{0.02, 0.05, 0.10, 0.20}})\n")
    rd = df[(df["action"] == "reuse_direct") & (df["claim_family"] == "STRUCT")
            & (df["perturbation_family"] == "CAPACITY")]
    lines.append(f"{'Pert ID':<10} {'rho':>6}  {'n':>4}  {'easy':>6} {'med':>6} {'hard':>6}")
    lines.append("-" * 50)
    for probe_pid, rho in PROBE_B_CAP.items():
        sub = rd[rd["perturbation_id"] == probe_pid]
        if len(sub) == 0:
            continue
        easy = (sub["band_struct"] == "easy").mean()
        med  = (sub["band_struct"] == "medium").mean()
        hard = (sub["band_struct"] == "hard").mean()
        lines.append(f"{probe_pid:<10} {rho:>6.2f}  {len(sub):>4}  {easy:>6.3f} {med:>6.3f} {hard:>6.3f}")
    # Overall
    easy_all = (rd["band_struct"] == "easy").mean()
    lines.append(f"{'OVERALL':<10} {'—':>6}  {len(rd):>4}  {easy_all:>6.3f}")
    lines.append("")
    lines.append(f"Stage A STRUCT×CAPACITY easy fraction (rho∈{{0.02..0.20}}): 0.070")
    lines.append(f"Probe B STRUCT×CAPACITY easy fraction (rho∈{{0.01..0.10}}): {easy_all:.3f}")
    return "\n".join(lines)


def summarize_probe_c(df: pd.DataFrame) -> str:
    lines = ["## Probe C — INSERTION De-escalation (5 instances × 4 de-stepped perturbations)\n"]
    lines.append(f"De-escalated grid: gamma ∈ {{0.15, 0.40, 0.80, 1.50}} "
                 f"(standard: {{0.30, 0.70, 1.20, 2.00}})\n")
    rd = df[(df["action"] == "reuse_direct") & (df["claim_family"] == "RANK")
            & (df["perturbation_family"] == "INSERTION")]
    lines.append(f"{'Pert ID':<10} {'gamma':>6}  {'n':>4}  {'easy':>6} {'med':>6} {'hard':>6}")
    lines.append("-" * 50)
    for std_pid, gamma in PROBE_C_INS.items():
        probe_pid = PROBE_C_LABELS[std_pid]
        sub = rd[rd["perturbation_id"] == probe_pid]
        if len(sub) == 0:
            continue
        easy = (sub["band_rank"] == "easy").mean()
        med  = (sub["band_rank"] == "medium").mean()
        hard = (sub["band_rank"] == "hard").mean()
        lines.append(f"{probe_pid:<10} {gamma:>6.2f}  {len(sub):>4}  {easy:>6.3f} {med:>6.3f} {hard:>6.3f}")
    easy_all = (rd["band_rank"] == "easy").mean()
    lines.append(f"{'OVERALL':<10} {'—':>6}  {len(rd):>4}  {easy_all:>6.3f}")
    lines.append("")
    lines.append(f"Stage A RANK×INSERTION easy fraction (gamma∈{{0.30..2.00}}): 0.088")
    lines.append(f"Probe C RANK×INSERTION easy fraction (gamma∈{{0.15..1.50}}): {easy_all:.3f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-jobs", type=int, default=6)
    parser.add_argument("--probe", choices=["a", "b", "c", "all"], default="all")
    args = parser.parse_args()

    out_dir = Path("data/probes")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_lines: list[str] = [
        "# Probe Report\n",
        f"Generated: {pd.Timestamp.now().isoformat()[:19]}\n\n",
    ]

    if args.probe in ("a", "all"):
        df_a = run_probe_a(n_jobs=args.n_jobs)
        df_a.to_parquet(out_dir / "probe_a_120s.parquet", index=False)
        log.info("Saved probe_a_120s.parquet (%d rows)", len(df_a))
        print("\n" + "=" * 80)
        print(summarize_probe_a(df_a))
        report_lines.append(summarize_probe_a(df_a) + "\n\n")

    if args.probe in ("b", "all"):
        df_b = run_probe_b(n_jobs=args.n_jobs)
        df_b.to_parquet(out_dir / "probe_b_cap_destep.parquet", index=False)
        log.info("Saved probe_b_cap_destep.parquet (%d rows)", len(df_b))
        print("\n" + "=" * 80)
        print(summarize_probe_b(df_b))
        report_lines.append(summarize_probe_b(df_b) + "\n\n")

    if args.probe in ("c", "all"):
        df_c = run_probe_c(n_jobs=args.n_jobs)
        df_c.to_parquet(out_dir / "probe_c_ins_destep.parquet", index=False)
        log.info("Saved probe_c_ins_destep.parquet (%d rows)", len(df_c))
        print("\n" + "=" * 80)
        print(summarize_probe_c(df_c))
        report_lines.append(summarize_probe_c(df_c) + "\n\n")

    report_path = Path("prereg/probe_a_report.md")
    report_path.write_text("\n".join(report_lines))
    log.info("Report written to %s", report_path)


if __name__ == "__main__":
    main()
