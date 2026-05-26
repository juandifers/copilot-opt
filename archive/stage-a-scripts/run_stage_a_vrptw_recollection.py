#!/usr/bin/env python3
"""§12.6 §12.3-clause: 120s reference re-collection for Stage A VRPTW.

Re-collects PyVRP references at 120s (the prereg's "scaled reference
protocol" per §8.4 and §12.6) for every Stage A cell where
``reference_struct_unstable`` is true in
``data/stage_a_vrptw.parquet``. Seeds 1/2/3, full multi-seed audit,
otherwise identical to Stage A. References only — does **not** re-run
the action portfolio. Baselines load from the existing 60s cache so
the perturbed instances are byte-identical to Stage A's.

Reuses the diagnostic probe's per-seed JSONs when present in the
re-collection checkpoint dir (caller pre-copies them in).

Output is a **new** parquet at ``data/stage_a_vrptw_recollected.parquet``.
The merge into a consolidated Stage A artifact is a separate, reviewed
step. This script never modifies ``data/stage_a_vrptw.parquet``.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("stage_a_recollection")


STAGE_A_PARQUET = PROJECT_ROOT / "data" / "stage_a_vrptw.parquet"
RECOLL_DIR = PROJECT_ROOT / "data"
RECOLL_CHECKPOINT_DIR = RECOLL_DIR / "stage_a_vrptw_recollection_checkpoints"
RECOLL_PARQUET = RECOLL_DIR / "stage_a_vrptw_recollected.parquet"
RECOLL_RUN_STATS = RECOLL_CHECKPOINT_DIR / "run_stats.json"

SEEDS = (1, 2, 3)


# Mirrors run_stage_a_120s_struct_probe.py:_probe_reference_solve so the
# probe's checkpoints drop in directly. Module-level for loky pickling.
def _recoll_reference_solve(
    instance_id: str,
    perturbation_id: str,
    seed: int,
    reference_time_limit: float,
    baseline_time_limit: float,
    instance_dir,
    checkpoint_root: str,
):
    """One 120s PyVRP reference solve, using the cached 60s baseline.

    Same shape as :func:`run_vrptw_scale_check._worker_reference_solve`
    but with the baseline time limit decoupled from the reference time
    limit, so the perturbed instance is byte-identical to Stage A's.
    """
    store = CheckpointStore(Path(checkpoint_root))
    if store.has_failure("refs", instance_id, perturbation_id, seed=seed):
        return instance_id, perturbation_id, seed, None, True, True
    cached = store.load_ref(instance_id, perturbation_id, seed)
    if cached is not None:
        return instance_id, perturbation_id, seed, cached, False, True
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
        store.save_ref(instance_id, perturbation_id, seed, result)
        return instance_id, perturbation_id, seed, result, False, False
    except Exception as exc:
        store.save_failure(
            "refs", instance_id, perturbation_id, seed=seed, exc=exc,
        )
        return instance_id, perturbation_id, seed, None, True, False


def _band(x: float) -> str:
    if not math.isfinite(x):
        return "n/a"
    if x < 0.60:
        return "bimodal"
    if x < 0.80:
        return "mid"
    if x < 0.90:
        return "marginal"
    return "stable"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--time-limit", type=float, default=120.0,
                   help="Reference time limit (default 120s — the scaled "
                        "protocol from §8.4 / §12.6).")
    p.add_argument("--baseline-time-limit", type=float, default=60.0,
                   help="Baseline time limit (default 60s, matches Stage A "
                        "cache so the perturbed instance is identical).")
    p.add_argument("--n-jobs", type=int, default=6)
    p.add_argument("--instance-dir", type=Path, default=None)
    p.add_argument("--limit-cells", type=int, default=None,
                   help="Debug: only process the first N unstable cells.")
    args = p.parse_args(argv)

    RECOLL_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    (RECOLL_CHECKPOINT_DIR / "refs").mkdir(exist_ok=True)
    (RECOLL_CHECKPOINT_DIR / "_failures").mkdir(exist_ok=True)

    # --- Identify the unstable cell set from Stage A ----------------------
    log.info("Reading %s", STAGE_A_PARQUET)
    df = pd.read_parquet(STAGE_A_PARQUET)
    cv = df.drop_duplicates(["instance_id", "perturbation_id"]).copy()
    n_cells = len(cv)
    unstable_mask = cv["reference_struct_unstable"] == True  # noqa: E712
    unstable = cv[unstable_mask].copy()
    log.info(
        "Stage A: %d cells, %d unstable (rate=%.4f)",
        n_cells, len(unstable),
        float(unstable_mask.mean()),
    )
    if args.limit_cells is not None:
        unstable = unstable.head(args.limit_cells)
        log.warning("DEBUG --limit-cells=%d → %d cells",
                    args.limit_cells, len(unstable))

    cells = list(zip(unstable["instance_id"], unstable["perturbation_id"]))

    # --- Submit jobs (cache hits return immediately) ----------------------
    jobs = [
        delayed(_recoll_reference_solve)(
            iid, pid, s,
            args.time_limit, args.baseline_time_limit,
            args.instance_dir, str(RECOLL_CHECKPOINT_DIR),
        )
        for (iid, pid) in cells
        for s in SEEDS
    ]
    log.info(
        "Submitting %d reference solves at %.0fs each (n_jobs=%d). "
        "Cells: %d. Seeds per cell: %d.",
        len(jobs), args.time_limit, args.n_jobs,
        len(cells), len(SEEDS),
    )
    t0 = time.monotonic()
    results = Parallel(n_jobs=args.n_jobs, backend="loky", verbose=5)(jobs)
    wall = time.monotonic() - t0
    log.info("Reference solves complete: %.1fs wall-clock", wall)

    # --- Aggregate results ------------------------------------------------
    by_cell: dict[tuple[str, str], dict[int, VRPTWSolveResult]] = {}
    failures: list[dict[str, object]] = []
    n_cache_hits = 0
    n_fresh = 0
    n_failures = 0
    for iid, pid, seed, result, failed, was_cached in results:
        if failed or result is None:
            n_failures += 1
            failures.append({
                "instance_id": iid, "perturbation_id": pid, "seed": int(seed),
            })
            continue
        by_cell.setdefault((iid, pid), {})[int(seed)] = result
        if was_cached:
            n_cache_hits += 1
        else:
            n_fresh += 1

    log.info(
        "Cache hits: %d  fresh: %d  failures: %d",
        n_cache_hits, n_fresh, n_failures,
    )

    # --- Build per-cell 120s rows ----------------------------------------
    rows: list[dict[str, object]] = []
    for _, src in unstable.iterrows():
        key = (src["instance_id"], src["perturbation_id"])
        seeds_present = by_cell.get(key, {})
        s1, s2, s3 = seeds_present.get(1), seeds_present.get(2), seeds_present.get(3)
        ari_60s = float(src["reference_ari_min"])
        band_60s = _band(ari_60s)
        if s1 is None or s2 is None or s3 is None:
            log.warning(
                "Incomplete recollection cell %s %s — missing seeds %s",
                key[0], key[1],
                [s for s in SEEDS if seeds_present.get(s) is None],
            )
            rows.append({
                "instance_id": src["instance_id"],
                "perturbation_id": src["perturbation_id"],
                "perturbation_family": src["perturbation_family"],
                "perturbation_magnitude": float(src["perturbation_magnitude"]),
                "reference_ari_min_60s": ari_60s,
                "ari_band_60s": band_60s,
                "reference_obj_s1_60s": float(src["reference_obj_s1"]),
                "reference_obj_s2_60s": float(src["reference_obj_s2"]),
                "reference_obj_s3_60s": float(src["reference_obj_s3"]),
                "reference_struct_unstable_60s": True,
                "recollect_complete": False,
                "reference_ari_min_120s": None,
                "reference_ari_s1s2_120s": None,
                "reference_ari_s1s3_120s": None,
                "reference_ari_s2s3_120s": None,
                "reference_obj_s1_120s": None,
                "reference_obj_s2_120s": None,
                "reference_obj_s3_120s": None,
                "reference_s1_feasible_120s": None,
                "reference_s2_feasible_120s": None,
                "reference_s3_feasible_120s": None,
                "reference_any_feasible_120s": None,
                "reference_all_feasible_120s": None,
                "reference_n_routes_s1_120s": None,
                "reference_n_routes_s2_120s": None,
                "reference_n_routes_s3_120s": None,
                "reference_obj_unstable_120s": None,
                "reference_struct_unstable_120s": None,
                "clears_at_120s": None,
                "delta_ari_min": None,
                "runtime_s1_120s": None,
                "runtime_s2_120s": None,
                "runtime_s3_120s": None,
            })
            continue
        stab = reference_stability(s1, s2, s3)
        ari_120 = float(stab.ari_min)
        rows.append({
            "instance_id": src["instance_id"],
            "perturbation_id": src["perturbation_id"],
            "perturbation_family": src["perturbation_family"],
            "perturbation_magnitude": float(src["perturbation_magnitude"]),
            "reference_ari_min_60s": ari_60s,
            "ari_band_60s": band_60s,
            "reference_obj_s1_60s": float(src["reference_obj_s1"]),
            "reference_obj_s2_60s": float(src["reference_obj_s2"]),
            "reference_obj_s3_60s": float(src["reference_obj_s3"]),
            "reference_struct_unstable_60s": True,
            "recollect_complete": True,
            "reference_ari_min_120s": ari_120,
            "reference_ari_s1s2_120s": float(stab.ari_s1s2)
                if not math.isnan(stab.ari_s1s2) else None,
            "reference_ari_s1s3_120s": float(stab.ari_s1s3)
                if not math.isnan(stab.ari_s1s3) else None,
            "reference_ari_s2s3_120s": float(stab.ari_s2s3)
                if not math.isnan(stab.ari_s2s3) else None,
            "reference_obj_s1_120s": float(s1.objective),
            "reference_obj_s2_120s": float(s2.objective),
            "reference_obj_s3_120s": float(s3.objective),
            "reference_s1_feasible_120s": bool(stab.s1_feasible),
            "reference_s2_feasible_120s": bool(stab.s2_feasible),
            "reference_s3_feasible_120s": bool(stab.s3_feasible),
            "reference_any_feasible_120s": bool(stab.any_feasible),
            "reference_all_feasible_120s": bool(stab.all_feasible),
            "reference_n_routes_s1_120s": int(stab.n_routes_s1),
            "reference_n_routes_s2_120s": int(stab.n_routes_s2),
            "reference_n_routes_s3_120s": int(stab.n_routes_s3),
            "reference_obj_unstable_120s": bool(stab.obj_unstable),
            "reference_struct_unstable_120s": bool(stab.struct_unstable),
            "clears_at_120s": bool(ari_120 >= ARI_STRUCT_UNSTABLE_THRESHOLD),
            "delta_ari_min": ari_120 - ari_60s,
            "runtime_s1_120s": float(s1.runtime_seconds),
            "runtime_s2_120s": float(s2.runtime_seconds),
            "runtime_s3_120s": float(s3.runtime_seconds),
        })

    out = pd.DataFrame(rows)
    RECOLL_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(RECOLL_PARQUET, index=False)
    log.info("Wrote %s (%d rows)", RECOLL_PARQUET, len(out))

    # Persist run stats (helps the report stay reproducible).
    RECOLL_RUN_STATS.write_text(json.dumps({
        "n_unstable_cells_input": int(len(unstable)),
        "n_solves_total": int(len(jobs)),
        "n_cache_hits": int(n_cache_hits),
        "n_fresh_solves": int(n_fresh),
        "n_failures": int(n_failures),
        "wall_clock_seconds": float(wall),
        "reference_time_limit_seconds": float(args.time_limit),
        "baseline_time_limit_seconds": float(args.baseline_time_limit),
        "seeds": list(SEEDS),
        "n_jobs": int(args.n_jobs),
        "failures": failures[:50],
    }, indent=2))
    log.info("Wrote %s", RECOLL_RUN_STATS)

    # Brief inline summary
    if out["recollect_complete"].all():
        n_cleared = int(out["clears_at_120s"].sum())
        n_total_unstable_after = int(len(unstable)) - n_cleared
        new_rate = n_total_unstable_after / n_cells
        log.info(
            "All %d cells re-collected. Cleared: %d. Residual unstable: %d. "
            "New overall rate: %d/%d = %.4f.",
            len(out), n_cleared, n_total_unstable_after,
            n_total_unstable_after, n_cells, new_rate,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
