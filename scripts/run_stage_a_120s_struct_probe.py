#!/usr/bin/env python3
"""Diagnostic probe: do 120s references clear §12.3 struct_unstable cells?

Re-collects PyVRP references at 120s (double the Stage A 60s budget)
on ~24 stratified cells drawn from the unstable subset of
``data/stage_a_vrptw.parquet``. Writes a probe parquet and a markdown
report covering quantile/band distributions (Step 1), the sampling
plan (Step 2), per-cell 120s ARI vs 60s ARI (Step 4) and an
extrapolation of the Stage A struct_unstable rate (Step 5).

Does **not** modify the Stage A parquet, does **not** perform the full
~256-cell re-collection prescribed by prereg §12.3/§12.5, and does
**not** re-run the action portfolio. References only.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from vrp_copilot_bench.vrptw import (  # noqa: E402
    SOFT_PERTURBATION_MAGNITUDES,
    SOFT_TIGHT_WINDOW_WIDTH_FRACTION,
    SolveConfig,
    VRPTWSolveResult,
    apply_vrptw_perturbation,
    load_vrptw_instance,
    lookup_vrptw_perturbation,
    solve_vrptw,
)
from vrp_copilot_bench.vrptw.baselines import (  # noqa: E402
    load_or_compute_baseline,
)
from vrp_copilot_bench.vrptw.checkpoint import CheckpointStore  # noqa: E402
from vrp_copilot_bench.vrptw.evaluation import (  # noqa: E402
    ARI_STRUCT_UNSTABLE_THRESHOLD,
    reference_stability,
)


# Module-level so loky can pickle it.
def _probe_reference_solve(
    instance_id: str,
    perturbation_id: str,
    seed: int,
    reference_time_limit: float,
    baseline_time_limit: float,
    instance_dir,
    checkpoint_root: str | None,
):
    """One 120s reference solve, using the cached 60s baseline.

    Mirrors :func:`run_vrptw_scale_check._worker_reference_solve` but
    decouples the baseline time limit (60s, matching Stage A) from the
    reference time limit (120s for the probe), so the probe's perturbed
    instance is byte-identical to Stage A's.
    """
    if checkpoint_root is not None:
        store = CheckpointStore(Path(checkpoint_root))
        if store.has_failure("refs", instance_id, perturbation_id, seed=seed):
            return instance_id, perturbation_id, seed, None, True
        cached = store.load_ref(instance_id, perturbation_id, seed)
        if cached is not None:
            return instance_id, perturbation_id, seed, cached, False
    else:
        store = None
    try:
        instance = load_vrptw_instance(instance_id, instance_dir)
        baseline = load_or_compute_baseline(
            instance_id, seed=1,
            time_limit_seconds=baseline_time_limit,
            instance_dir=instance_dir,
        )
        spec = lookup_vrptw_perturbation(perturbation_id)
        if spec.family == "ORDER_CHANGE":
            perturbed = apply_vrptw_perturbation(
                instance, spec, baseline.solve_result,
                magnitude_override=SOFT_PERTURBATION_MAGNITUDES[perturbation_id],
                tight_width_fraction=SOFT_TIGHT_WINDOW_WIDTH_FRACTION,
            )
        else:
            perturbed = apply_vrptw_perturbation(
                instance, spec, baseline.solve_result,
                magnitude_override=SOFT_PERTURBATION_MAGNITUDES[perturbation_id],
            )
        cfg = SolveConfig(
            time_limit_seconds=reference_time_limit, seed=seed,
        )
        result = solve_vrptw(perturbed, cfg)
        if store is not None:
            store.save_ref(instance_id, perturbation_id, seed, result)
        return instance_id, perturbation_id, seed, result, False
    except Exception as exc:
        if store is not None:
            store.save_failure(
                "refs", instance_id, perturbation_id, seed=seed, exc=exc,
            )
            return instance_id, perturbation_id, seed, None, True
        raise

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("stage_a_120s_probe")


STAGE_A_PARQUET = PROJECT_ROOT / "data" / "stage_a_vrptw.parquet"
PROBE_DIR = PROJECT_ROOT / "data" / "probes"
PROBE_CHECKPOINT_DIR = PROBE_DIR / "stage_a_120s_struct_probe_checkpoints"
PROBE_PARQUET = PROBE_DIR / "stage_a_120s_struct_probe.parquet"

FAMILIES = ("ORDER_CHANGE", "SERVICE_TIME", "TIME_WINDOW", "TRAVEL_TIME")
BANDS = ("marginal", "mid", "bimodal")
SEEDS = (1, 2, 3)


def band_of(ari: float) -> str:
    if ari < 0.60:
        return "bimodal"
    if ari < 0.80:
        return "mid"
    return "marginal"  # ARI in [0.80, 0.90); >=0.90 cells are stable


def select_probe_sample(
    unstable_cells: pd.DataFrame, k_per_stratum: int, rng_seed: int,
) -> pd.DataFrame:
    """Stratified pick across (family, ari_band)."""
    rng = np.random.default_rng(rng_seed)
    picks: list[int] = []
    notes: list[str] = []
    df = unstable_cells.copy()
    df["ari_band"] = df["reference_ari_min"].apply(band_of)
    for fam in FAMILIES:
        for band in BANDS:
            sub = df[(df["perturbation_family"] == fam) & (df["ari_band"] == band)]
            n = len(sub)
            if n == 0:
                notes.append(f"empty stratum {fam}/{band} — skipped (no cells)")
                continue
            k = min(k_per_stratum, n)
            idx = rng.choice(sub.index.values, size=k, replace=False)
            picks.extend(idx.tolist())
    for note in notes:
        log.warning(note)
    out = df.loc[picks].copy().reset_index(drop=True)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--time-limit", type=float, default=120.0,
                   help="Reference time limit for the probe (default 120s).")
    p.add_argument("--baseline-time-limit", type=float, default=60.0,
                   help="Baseline time limit (default 60s, matches Stage A "
                        "cache so the perturbed instance is identical).")
    p.add_argument("--rng-seed", type=int, default=20260514,
                   help="RNG seed for stratified sampling.")
    p.add_argument("--k-per-stratum", type=int, default=2,
                   help="Cells per (family, band) stratum (default 2).")
    p.add_argument("--n-jobs", type=int, default=6)
    p.add_argument("--instance-dir", type=Path, default=None)
    args = p.parse_args(argv)

    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    PROBE_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    # --- read Stage A wide table, derive cell-level unstable set ----------
    log.info("Reading %s", STAGE_A_PARQUET)
    df = pd.read_parquet(STAGE_A_PARQUET)
    cv = df.drop_duplicates(["instance_id", "perturbation_id"]).copy()
    unstable = cv[cv["reference_struct_unstable"] == True].copy()  # noqa: E712
    log.info(
        "Cells: %d total, %d unstable (rate=%.3f)",
        len(cv), len(unstable),
        float(cv["reference_struct_unstable"].mean()),
    )

    # --- stratified probe selection --------------------------------------
    probe = select_probe_sample(
        unstable, k_per_stratum=args.k_per_stratum, rng_seed=args.rng_seed,
    )
    log.info(
        "Probe selected: %d cells; per (family, band):\n%s",
        len(probe),
        probe.groupby(["perturbation_family", "ari_band"]).size().to_string(),
    )

    # --- re-collect references at args.time_limit -------------------------
    jobs = []
    for _, row in probe.iterrows():
        for seed in SEEDS:
            jobs.append(delayed(_probe_reference_solve)(
                row["instance_id"], row["perturbation_id"], seed,
                args.time_limit, args.baseline_time_limit,
                args.instance_dir, str(PROBE_CHECKPOINT_DIR),
            ))
    log.info(
        "Submitting %d reference solves at %.0fs each (n_jobs=%d)…",
        len(jobs), args.time_limit, args.n_jobs,
    )
    t0 = time.monotonic()
    results = Parallel(n_jobs=args.n_jobs, backend="loky", verbose=5)(jobs)
    elapsed = time.monotonic() - t0
    log.info("Reference solves complete: %.1fs wall-clock", elapsed)

    by_cell: dict[tuple[str, str], dict[int, object]] = {}
    failures: list[tuple[str, str, int]] = []
    for iid, pid, seed, result, failed in results:
        if failed or result is None:
            failures.append((iid, pid, int(seed)))
            continue
        by_cell.setdefault((iid, pid), {})[int(seed)] = result
    if failures:
        log.warning("Failed solves: %d (%s)", len(failures), failures[:5])

    # --- assemble probe rows ----------------------------------------------
    rows: list[dict[str, object]] = []
    for _, row in probe.iterrows():
        cell_key = (row["instance_id"], row["perturbation_id"])
        cell_results = by_cell.get(cell_key, {})
        s1 = cell_results.get(1)
        s2 = cell_results.get(2)
        s3 = cell_results.get(3)
        if s1 is None or s2 is None or s3 is None:
            log.warning(
                "Incomplete probe cell %s %s — missing seeds %s",
                row["instance_id"], row["perturbation_id"],
                [s for s in (1, 2, 3) if cell_results.get(s) is None],
            )
            rows.append({
                "instance_id": row["instance_id"],
                "perturbation_id": row["perturbation_id"],
                "perturbation_family": row["perturbation_family"],
                "ari_band_60s": row["ari_band"],
                "reference_ari_min_60s": float(row["reference_ari_min"]),
                "reference_obj_s1_60s": float(row["reference_obj_s1"]),
                "reference_obj_s2_60s": float(row["reference_obj_s2"]),
                "reference_obj_s3_60s": float(row["reference_obj_s3"]),
                "probe_complete": False,
                "reference_ari_min_120s": None,
                "reference_ari_s1s2_120s": None,
                "reference_ari_s1s3_120s": None,
                "reference_ari_s2s3_120s": None,
                "reference_obj_s1_120s": None,
                "reference_obj_s2_120s": None,
                "reference_obj_s3_120s": None,
                "clears_at_120s": None,
                "delta_ari_min": None,
            })
            continue
        stab = reference_stability(s1, s2, s3)
        ari_min_120 = float(stab.ari_min)
        ari_min_60 = float(row["reference_ari_min"])
        rows.append({
            "instance_id": row["instance_id"],
            "perturbation_id": row["perturbation_id"],
            "perturbation_family": row["perturbation_family"],
            "ari_band_60s": row["ari_band"],
            "reference_ari_min_60s": ari_min_60,
            "reference_obj_s1_60s": float(row["reference_obj_s1"]),
            "reference_obj_s2_60s": float(row["reference_obj_s2"]),
            "reference_obj_s3_60s": float(row["reference_obj_s3"]),
            "probe_complete": True,
            "reference_ari_min_120s": ari_min_120,
            "reference_ari_s1s2_120s": float(stab.ari_s1s2),
            "reference_ari_s1s3_120s": float(stab.ari_s1s3),
            "reference_ari_s2s3_120s": float(stab.ari_s2s3),
            "reference_obj_s1_120s": float(s1.objective),
            "reference_obj_s2_120s": float(s2.objective),
            "reference_obj_s3_120s": float(s3.objective),
            "clears_at_120s": bool(ari_min_120 >= ARI_STRUCT_UNSTABLE_THRESHOLD),
            "delta_ari_min": ari_min_120 - ari_min_60,
        })

    probe_df = pd.DataFrame(rows)
    probe_df.to_parquet(PROBE_PARQUET, index=False)
    log.info("Wrote %s (%d rows)", PROBE_PARQUET, len(probe_df))

    print()
    print(probe_df[[
        "instance_id", "perturbation_id", "perturbation_family",
        "ari_band_60s", "reference_ari_min_60s",
        "reference_ari_min_120s", "delta_ari_min", "clears_at_120s",
    ]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
