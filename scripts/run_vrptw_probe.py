#!/usr/bin/env python3
"""Phase 1 VRPTW stability probe — unperturbed, 6 instances × 3 seeds.

Exploratory external-validity probe. Asks whether adding VRPTW
time-window constraints makes PyVRP route partitions more stable across
seeds than the CVRP Stage A baseline observed.

**Not** a preregistered replacement for Stage A: no perturbations, no
BKS/quality validation, no claim families.

Usage::

    python scripts/run_vrptw_probe.py
    python scripts/run_vrptw_probe.py --time-limit 60 --n-jobs 6
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
import time
from pathlib import Path

import pandas as pd
from joblib import Parallel, delayed

# Allow running directly without editable install.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vrp_copilot_bench.labels import _obj_unstable, _pairwise_ari  # noqa: E402
from vrp_copilot_bench.solvers.pyvrp_vrptw_wrapper import (  # noqa: E402
    SCALING_FACTOR,
    VRPTWSolveResult,
    solve_vrptw,
)
from vrp_copilot_bench.solvers.pyvrp_wrapper import SolveConfig  # noqa: E402
from vrp_copilot_bench.vrptw_instances import (  # noqa: E402
    DEFAULT_VRPTW_INSTANCE_DIR,
    load_vrptw_instance,
)


# ---------------------------------------------------------------------------
# Fixed defaults

INSTANCES: tuple[str, ...] = (
    "C101", "C201", "R101", "R201", "RC101", "RC201",
)
SEEDS: tuple[int, ...] = (1, 2, 3)
TIME_LIMIT_S: float = 60.0
ARI_THRESHOLD: float = 0.90
OBJ_INSTABILITY_THRESHOLD: float = 0.02  # matches labels._obj_unstable

# CVRP Stage A reference points for the qualitative comparison block.
CVRP_OBJ_UNSTABLE_RATE: float = 0.000
CVRP_STRUCT_UNSTABLE_RATE: float = 0.926
CVRP_MEDIAN_MIN_ARI: float = 0.476

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_vrptw_probe")


# ---------------------------------------------------------------------------
# Joblib worker (module-level so loky can pickle)


def _worker_solve(
    instance_id: str, time_limit: float, seed: int, instance_dir: Path
) -> tuple[str, int, VRPTWSolveResult]:
    instance = load_vrptw_instance(instance_id, instance_dir=instance_dir)
    cfg = SolveConfig(time_limit_seconds=time_limit, seed=seed)
    result = solve_vrptw(instance, cfg)
    return (instance_id, seed, result)


# ---------------------------------------------------------------------------
# Main probe loop


def run_probe(
    instances: tuple[str, ...],
    seeds: tuple[int, ...],
    time_limit: float,
    n_jobs: int,
    instance_dir: Path,
) -> pd.DataFrame:
    """Fan out (instance × seed) jobs; assemble per-instance rows."""
    instance_meta: dict[str, dict] = {}
    for iid in instances:
        inst = load_vrptw_instance(iid, instance_dir=instance_dir)
        instance_meta[iid] = {
            "n_customers": inst.n_customers,
            "capacity": inst.capacity,
            "n_vehicles": inst.n_vehicles,
        }

    jobs = [(iid, time_limit, seed, instance_dir)
            for iid in instances for seed in seeds]
    log.info(
        "Dispatching %d VRPTW solves: %d instances × %d seeds × %.0fs each",
        len(jobs), len(instances), len(seeds), time_limit,
    )

    t0 = time.monotonic()
    results = Parallel(n_jobs=n_jobs, backend="loky", verbose=5)(
        delayed(_worker_solve)(iid, tl, s, idir)
        for iid, tl, s, idir in jobs
    )
    wall_s = time.monotonic() - t0
    log.info("All solves done in %.1fs", wall_s)

    # Bucket results by instance, ordered by seed.
    by_instance: dict[str, dict[int, VRPTWSolveResult]] = {}
    pyvrp_version = ""
    for iid, seed, r in results:
        by_instance.setdefault(iid, {})[seed] = r
        pyvrp_version = r.pyvrp_version

    rows = []
    for iid in instances:
        per_seed = by_instance[iid]
        s1, s2, s3 = per_seed[seeds[0]], per_seed[seeds[1]], per_seed[seeds[2]]

        ari_12 = _pairwise_ari(s1.assignment, s2.assignment)
        ari_13 = _pairwise_ari(s1.assignment, s3.assignment)
        ari_23 = _pairwise_ari(s2.assignment, s3.assignment)
        ari_min = min(ari_12, ari_13, ari_23)

        obj_unstable = _obj_unstable(s1.objective, s2.objective, s3.objective)
        struct_unstable = ari_min < ARI_THRESHOLD
        n_routes_unstable = len({s1.n_routes, s2.n_routes, s3.n_routes}) > 1
        total_runtime_s = s1.runtime_seconds + s2.runtime_seconds + s3.runtime_seconds

        meta = instance_meta[iid]
        rows.append({
            "instance_id": iid,
            "n_customers": meta["n_customers"],
            "capacity": meta["capacity"],
            "n_vehicles": meta["n_vehicles"],
            "s1_obj": s1.objective,
            "s2_obj": s2.objective,
            "s3_obj": s3.objective,
            "s1_n_routes": s1.n_routes,
            "s2_n_routes": s2.n_routes,
            "s3_n_routes": s3.n_routes,
            "s1_feasible": s1.feasible,
            "s2_feasible": s2.feasible,
            "s3_feasible": s3.feasible,
            "ari_s1s2": round(ari_12, 6),
            "ari_s1s3": round(ari_13, 6),
            "ari_s2s3": round(ari_23, 6),
            "ari_min": round(ari_min, 6),
            "obj_unstable": obj_unstable,
            "struct_unstable": struct_unstable,
            "n_routes_unstable": n_routes_unstable,
            "total_runtime_s": round(total_runtime_s, 3),
            "distance_time_scaling": f"x{SCALING_FACTOR}",
            "pyvrp_version": pyvrp_version,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Reporting


def _aggregate_rates(df: pd.DataFrame) -> dict:
    obj_rate = float(df["obj_unstable"].astype(bool).mean())
    struct_rate = float(df["struct_unstable"].astype(bool).mean())
    routes_rate = float(df["n_routes_unstable"].astype(bool).mean())
    return {
        "n": int(len(df)),
        "obj_unstable_rate": obj_rate,
        "struct_unstable_rate": struct_rate,
        "n_routes_unstable_rate": routes_rate,
        "median_ari_min": float(df["ari_min"].median()),
        "min_ari_min": float(df["ari_min"].min()),
        "max_ari_min": float(df["ari_min"].max()),
    }


def _format_yn(v) -> str:
    return "Y" if bool(v) else "N"


def _build_markdown_report(
    df: pd.DataFrame,
    time_limit: float,
    n_jobs: int,
    pyvrp_version: str,
    parquet_path: Path,
) -> str:
    rates = _aggregate_rates(df)
    lines: list[str] = []
    lines.append("# VRPTW Phase 1 Stability Probe — Report\n")
    lines.append(f"Generated: {pd.Timestamp.now().isoformat(timespec='seconds')}\n")
    lines.append("")

    lines.append("## Purpose")
    lines.append("")
    lines.append(
        "Exploratory external-validity probe. The preregistered CVRP Stage A "
        "benchmark found that PyVRP route partitions are highly unstable across "
        "seeds (`struct_unstable ≈ 0.926`, `median ari_min ≈ 0.476`) while "
        "objective references are stable (`obj_unstable ≈ 0`). This raised the "
        "concern that the `loss_struct` metric measures solver/partition "
        "multimodality rather than perturbation-induced structural change."
    )
    lines.append("")
    lines.append(
        "**Research question:** does adding VRPTW time-window constraints make "
        "PyVRP route structure more stable across seeds, by reducing the number "
        "of feasible high-quality partitions the solver can land on?"
    )
    lines.append("")
    lines.append(
        "This phase runs **unperturbed** VRPTW only. Perturbations and a full "
        "Stage-A-style protocol are explicitly deferred."
    )
    lines.append("")

    lines.append("## Dataset and solver setup")
    lines.append("")
    lines.append(
        f"- Instances: {', '.join(df['instance_id'].tolist())} "
        f"(Solomon-100; sourced from PyVRP `Instances` GitHub mirror, "
        f"CVRPLIB-extended VRPTW `.vrp` format).\n"
        f"- Seeds: {list(SEEDS)}.\n"
        f"- Time limit: {time_limit:.0f}s per solve.\n"
        f"- Solver: PyVRP {pyvrp_version} via `pyvrp.solve(..., "
        f"stop=MaxRuntime, display=False, collect_stats=False)`.\n"
        f"- Workers: joblib loky, `n_jobs={n_jobs}`."
    )
    lines.append("")

    lines.append("## Scaling convention")
    lines.append("")
    lines.append(
        f"PyVRP requires integer distance, duration, time-window, and "
        f"service-duration values. To preserve one decimal of Euclidean "
        f"distance precision while keeping every quantity on a common "
        f"integer scale, all four are multiplied by **{SCALING_FACTOR}** "
        f"before being handed to PyVRP:"
    )
    lines.append("")
    lines.append("```")
    lines.append(f"distance_matrix[i, j] = round({SCALING_FACTOR} * euclidean(coords[i], coords[j]))")
    lines.append("duration_matrix       = distance_matrix")
    lines.append(f"time_windows          = round({SCALING_FACTOR} * raw_time_windows)")
    lines.append(f"service_times         = round({SCALING_FACTOR} * raw_service_times)")
    lines.append("```")
    lines.append("")
    lines.append(
        f"The objective column is therefore in ×{SCALING_FACTOR} distance "
        f"units. Stability metrics (pairwise ARI, relative objective drift, "
        f"route-count delta) are scale-invariant, so this rescaling does not "
        f"affect the probe's conclusions. **No BKS comparison is performed.**"
    )
    lines.append("")

    lines.append("## Per-instance results")
    lines.append("")
    header = (
        f"| {'Instance':<8} | {'n':>3} | "
        f"{'s1_obj':>9} {'s2_obj':>9} {'s3_obj':>9} | "
        f"{'r1':>3} {'r2':>3} {'r3':>3} | "
        f"{'f1':>2} {'f2':>2} {'f3':>2} | "
        f"{'ari12':>6} {'ari13':>6} {'ari23':>6} {'ari_min':>7} | "
        f"{'OBJ?':>4} {'STR?':>4} {'RTE?':>4} |"
    )
    sep = "|" + "---|" * 9
    lines.append(header)
    lines.append(sep)
    for _, r in df.iterrows():
        lines.append(
            f"| {r['instance_id']:<8} | {r['n_customers']:>3} | "
            f"{r['s1_obj']:>9.1f} {r['s2_obj']:>9.1f} {r['s3_obj']:>9.1f} | "
            f"{r['s1_n_routes']:>3} {r['s2_n_routes']:>3} {r['s3_n_routes']:>3} | "
            f"{_format_yn(r['s1_feasible']):>2} {_format_yn(r['s2_feasible']):>2} "
            f"{_format_yn(r['s3_feasible']):>2} | "
            f"{r['ari_s1s2']:>6.3f} {r['ari_s1s3']:>6.3f} "
            f"{r['ari_s2s3']:>6.3f} {r['ari_min']:>7.3f} | "
            f"{_format_yn(r['obj_unstable']):>4} "
            f"{_format_yn(r['struct_unstable']):>4} "
            f"{_format_yn(r['n_routes_unstable']):>4} |"
        )
    lines.append("")
    lines.append(
        f"Legend: `r{1,2,3}` = number of routes per seed; "
        f"`f{1,2,3}` = feasibility per seed (Y/N); "
        f"`OBJ?` = `(max - min) / min > {OBJ_INSTABILITY_THRESHOLD}` across seeds; "
        f"`STR?` = `ari_min < {ARI_THRESHOLD}`; "
        f"`RTE?` = at least two seeds disagree on the route count."
    )
    lines.append("")

    lines.append("## Aggregate rates")
    lines.append("")
    lines.append(f"- `n_instances` = {rates['n']}")
    lines.append(f"- `obj_unstable_rate`      = {rates['obj_unstable_rate']:.3f}")
    lines.append(f"- `struct_unstable_rate`   = {rates['struct_unstable_rate']:.3f}")
    lines.append(f"- `n_routes_unstable_rate` = {rates['n_routes_unstable_rate']:.3f}")
    lines.append(f"- `median ari_min`         = {rates['median_ari_min']:.3f}")
    lines.append(
        f"- `ari_min` range          = [{rates['min_ari_min']:.3f}, "
        f"{rates['max_ari_min']:.3f}]"
    )
    lines.append("")

    lines.append("## Comparison vs. CVRP Stage A (qualitative)")
    lines.append("")
    lines.append(
        f"| metric | CVRP Stage A | VRPTW Phase 1 |\n"
        f"|---|---|---|\n"
        f"| `obj_unstable_rate`      | {CVRP_OBJ_UNSTABLE_RATE:.3f} "
        f"| {rates['obj_unstable_rate']:.3f} |\n"
        f"| `struct_unstable_rate`   | {CVRP_STRUCT_UNSTABLE_RATE:.3f} "
        f"| {rates['struct_unstable_rate']:.3f} |\n"
        f"| `median ari_min`         | {CVRP_MEDIAN_MIN_ARI:.3f} "
        f"| {rates['median_ari_min']:.3f} |"
    )
    lines.append("")

    # Heuristic interpretation, with explicit caveat language.
    if rates["struct_unstable_rate"] < CVRP_STRUCT_UNSTABLE_RATE - 0.20:
        verdict = (
            "VRPTW route partitions appear **substantially more stable** "
            "across seeds than the CVRP baseline. Consistent with the "
            "hypothesis that time windows reduce the size of the feasible "
            "high-quality partition set the solver can land on."
        )
    elif rates["struct_unstable_rate"] > CVRP_STRUCT_UNSTABLE_RATE + 0.05:
        verdict = (
            "VRPTW route partitions appear **at least as unstable** as the "
            "CVRP baseline. Time windows alone do not collapse the partition "
            "set the solver explores."
        )
    else:
        verdict = (
            "Result is **inconclusive at this n**. The 6-instance probe "
            "lacks the statistical power to separate the VRPTW structural "
            "instability rate from the CVRP baseline."
        )
    lines.append("**Interpretation:** " + verdict)
    lines.append("")

    lines.append("## Caveats")
    lines.append("")
    lines.append(
        "- **No perturbations.** This phase only measures unperturbed "
        "reference stability across PyVRP seeds. Perturbed VRPTW probes "
        "are explicitly out of scope.\n"
        "- **No BKS / quality validation.** Objectives are in "
        f"×{SCALING_FACTOR}-scaled distance units and are not compared "
        "against published Solomon best-known solutions. The probe only "
        "asks how stable the solver is, not how good its solutions are.\n"
        "- **Small n.** Six instances × three seeds = 18 solves. This is "
        "a feasibility probe, not a preregistered evaluation. "
        "Conclusions are directional only.\n"
        "- **Exploratory.** This is an external-validity check against the "
        "preregistered CVRP Stage A benchmark, not a replacement for it. "
        "Preregistration (`prereg/PREREG_v0.5.md`) and the Stage A "
        "pipeline are unchanged."
    )
    lines.append("")

    lines.append(f"Parquet output: `{parquet_path}`")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="run_vrptw_probe", description=__doc__)
    p.add_argument(
        "--instances", nargs="+", default=list(INSTANCES),
        help="Instance IDs to run. Default: the 6 hardcoded probe instances.",
    )
    p.add_argument("--time-limit", type=float, default=TIME_LIMIT_S)
    p.add_argument("--n-jobs", type=int, default=6)
    p.add_argument("--instance-dir", type=Path, default=DEFAULT_VRPTW_INSTANCE_DIR)
    p.add_argument("--out-dir", type=Path, default=Path("data/probes"))
    p.add_argument(
        "--report-path", type=Path,
        default=Path("prereg/vrptw_probe_phase1_report.md"),
    )
    args = p.parse_args(argv)

    instances = tuple(args.instances)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)

    df = run_probe(
        instances=instances,
        seeds=SEEDS,
        time_limit=args.time_limit,
        n_jobs=args.n_jobs,
        instance_dir=args.instance_dir,
    )

    parquet_path = args.out_dir / "vrptw_probe_phase1.parquet"
    df.to_parquet(parquet_path, index=False)
    log.info("Wrote %d rows to %s", len(df), parquet_path)

    pyvrp_version = df["pyvrp_version"].iloc[0] if len(df) else "unknown"
    report = _build_markdown_report(
        df,
        time_limit=args.time_limit,
        n_jobs=args.n_jobs,
        pyvrp_version=pyvrp_version,
        parquet_path=parquet_path,
    )
    args.report_path.write_text(report)
    log.info("Wrote report to %s", args.report_path)

    rates = _aggregate_rates(df)
    print()
    print("Aggregate rates:")
    print(f"  obj_unstable_rate      = {rates['obj_unstable_rate']:.3f}")
    print(f"  struct_unstable_rate   = {rates['struct_unstable_rate']:.3f}")
    print(f"  n_routes_unstable_rate = {rates['n_routes_unstable_rate']:.3f}")
    print(f"  median ari_min         = {rates['median_ari_min']:.3f}")
    print(f"  ari_min range          = [{rates['min_ari_min']:.3f}, {rates['max_ari_min']:.3f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
