#!/usr/bin/env python3
"""Stage 1 of the Homberger reference-budget pilot.

Runs pyvrp_10s × 3 seeds on 9 stratified cells (3 C / 3 R / 3 RC) from
the existing Homberger probe, computes the 3-seed ARI summary, compares
each cell's ARI_min against the *current* reference value in
``reports/homberger_probe/homberger_probe_reference_stability.csv``
(which may be 120 s or 180 s after the fallback merge), and writes the
pilot CSV + a one-paragraph verdict.

The pilot **passes** iff every instance class has at least 2 of 3 cells
with ``delta_ARI = reference_ARI_min - pilot_ARI_min ≤ 0.05``.

Pass → Stage 2 (caller decides; this script only emits the verdict).
Fail → the pilot artefact + a short addendum become the deliverable.

Usage::

    python scripts/run_homberger_reference_pilot.py
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pandas as pd  # noqa: E402

from vrp_copilot_bench.vrptw.baselines import load_or_compute_baseline  # noqa: E402
from vrp_copilot_bench.vrptw.evaluation import reference_stability  # noqa: E402
from vrp_copilot_bench.vrptw.instances import load_vrptw_instance  # noqa: E402
from vrp_copilot_bench.vrptw.solver import (  # noqa: E402
    SolveConfig,
    solve_vrptw,
)
from vrp_copilot_bench.vrptw_perturbations import (  # noqa: E402
    apply_vrptw_perturbation,
    lookup_vrptw_perturbation,
)


# 9 pilot cells, 3 per class. Spans easy / borderline / hard reference
# stability, all 4 perturbation families represented.
PILOT_CELLS: tuple[tuple[str, str], ...] = (
    # C-class
    ("C1_2_1",  "OC_4"),  # easy:    reference ARI_min ≈ 1.000
    ("C1_2_1",  "ST_3"),  # border:  reference ARI_min ≈ 0.916
    ("C2_2_2",  "ST_4"),  # hard:    reference ARI_min ≈ 0.649
    # R-class
    ("R2_2_1",  "TT_5"),  # easy:    reference ARI_min ≈ 1.000
    ("R1_2_1",  "TW_5"),  # border:  reference ARI_min ≈ 0.935
    ("R2_2_1",  "ST_3"),  # hard:    reference ARI_min ≈ 0.683
    # RC-class
    ("RC1_2_1", "OC_4"),  # easy:    reference ARI_min ≈ 1.000
    ("RC1_2_2", "TT_5"),  # border:  reference ARI_min ≈ 0.932
    ("RC1_2_1", "TT_4"),  # hard:    reference ARI_min ≈ 0.697 (180 s)
)


HOMBERGER_INSTANCE_DIR: Path = PROJECT_ROOT / "data" / "vrptw_instances" / "homberger200"
PILOT_REFERENCE_CSV: Path = PROJECT_ROOT / "reports" / "homberger_probe" / "homberger_probe_reference_stability.csv"
PILOT_TIME_LIMIT_S: float = 10.0
PILOT_SEEDS: tuple[int, ...] = (1, 2, 3)
DELTA_ARI_THRESHOLD: float = 0.05


def _instance_class(iid: str) -> str:
    if iid.startswith("RC"):
        return "RC"
    return iid[0]


def _row_for_cell(
    iid: str, pid: str, *, reference_lookup: pd.DataFrame,
) -> dict:
    cls = _instance_class(iid)
    print(f"  [{cls}] {iid} × {pid}: loading instance + baseline…")
    instance = load_vrptw_instance(iid, HOMBERGER_INSTANCE_DIR)
    # The probe baselines were written at either 120 s (cells untouched
    # by the 180 s fallback) or 180 s (instances whose 120 s ARI was
    # rejected). Read the cached time-limit directly so we always hit
    # the cache instead of triggering a fresh solve.
    baseline_path = PROJECT_ROOT / "data" / "vrptw_baselines" / f"{iid}.json"
    cached_entry = json.loads(baseline_path.read_text())
    cached_tl = float(cached_entry["time_limit_seconds"])
    cache = load_or_compute_baseline(
        iid, seed=int(cached_entry["seed"]),
        time_limit_seconds=cached_tl,
        baseline_dir=PROJECT_ROOT / "data" / "vrptw_baselines",
        instance_dir=HOMBERGER_INSTANCE_DIR,
    )
    assert cache.from_cache, (
        f"baseline cache miss on {iid} at t={cached_tl}; aborting"
    )
    assert cache.solve_result is not None
    spec = lookup_vrptw_perturbation(pid)
    perturbed = apply_vrptw_perturbation(instance, spec, cache.solve_result)

    seed_results = {}
    for seed in PILOT_SEEDS:
        cfg = SolveConfig(time_limit_seconds=PILOT_TIME_LIMIT_S, seed=seed)
        t0 = time.perf_counter()
        seed_results[seed] = solve_vrptw(perturbed, cfg)
        dt = time.perf_counter() - t0
        print(f"      seed={seed}: obj={seed_results[seed].objective:.1f} "
              f"feasible={seed_results[seed].feasible} ({dt:.2f}s)")

    stab = reference_stability(*[seed_results[s] for s in PILOT_SEEDS])
    pilot_ari_min = float(stab.ari_min) if not math.isnan(stab.ari_min) else float("nan")

    # Pull the existing reference summary for direct comparison.
    ref_row = reference_lookup[
        (reference_lookup["instance_id"] == iid)
        & (reference_lookup["perturbation_id"] == pid)
    ]
    if not len(ref_row):
        raise RuntimeError(f"no reference stability row for {iid} × {pid}")
    ref_row = ref_row.iloc[0]
    ref_ari_min = float(ref_row["reference_ari_min"])

    delta_ari = ref_ari_min - pilot_ari_min
    passes = (not math.isnan(delta_ari)) and (delta_ari <= DELTA_ARI_THRESHOLD)

    print(f"      ARI: ref={ref_ari_min:.3f}  pilot={pilot_ari_min:.3f}  "
          f"Δ={delta_ari:+.3f}  {'PASS' if passes else 'FAIL'}")

    return {
        "instance_id": iid,
        "perturbation_id": pid,
        "perturbation_family": str(ref_row["perturbation_family"]),
        "perturbation_magnitude": float(perturbed.perturbation_magnitude),
        "instance_class": cls,
        "reference_ari_s1s2": float(ref_row["reference_ari_s1s2"]),
        "reference_ari_s1s3": float(ref_row["reference_ari_s1s3"]),
        "reference_ari_s2s3": float(ref_row["reference_ari_s2s3"]),
        "reference_ari_min": ref_ari_min,
        "pilot_ari_s1s2": float(stab.ari_s1s2),
        "pilot_ari_s1s3": float(stab.ari_s1s3),
        "pilot_ari_s2s3": float(stab.ari_s2s3),
        "pilot_ari_min": pilot_ari_min,
        "pilot_obj_s1": float(seed_results[1].objective),
        "pilot_obj_s2": float(seed_results[2].objective),
        "pilot_obj_s3": float(seed_results[3].objective),
        "pilot_s1_feasible": bool(stab.s1_feasible),
        "pilot_s2_feasible": bool(stab.s2_feasible),
        "pilot_s3_feasible": bool(stab.s3_feasible),
        "pilot_failure_kind": str(stab.failure_kind),
        "delta_ari": delta_ari,
        "passes_threshold": bool(passes),
    }


def _summary_md(df: pd.DataFrame, *, output_md: Path) -> dict:
    per_class: dict[str, dict] = {}
    for cls, grp in df.groupby("instance_class"):
        n = len(grp)
        n_pass = int(grp["passes_threshold"].sum())
        per_class[cls] = {
            "n": n,
            "n_pass": n_pass,
            "pass_rate": n_pass / n,
            "min_delta": float(grp["delta_ari"].min()),
            "max_delta": float(grp["delta_ari"].max()),
            "median_pilot_ari": float(grp["pilot_ari_min"].median()),
            "median_ref_ari": float(grp["reference_ari_min"].median()),
        }
    classes_passing = {cls: v["n_pass"] >= 2 for cls, v in per_class.items()}
    overall = all(classes_passing.values())

    lines = [
        "# Homberger reference-budget pilot — Stage 1 verdict",
        "",
        f"**Cells:** {len(df)} (3 per instance class). ",
        f"**Pilot budget:** pyvrp_10s × 3 seeds.",
        f"**Decision rule:** every class needs ≥ 2 of 3 cells with "
        f"`delta_ARI ≤ {DELTA_ARI_THRESHOLD}` (= reference ARI_min "
        f"– pilot ARI_min).",
        "",
        f"## Verdict: {'**PASS — proceed to Stage 2.**' if overall else '**FAIL — do not launch Stage 2.**'}",
        "",
        "| class | n | passing | pass-rate | min Δ | max Δ | median pilot ARI | median ref ARI |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for cls in ("C", "R", "RC"):
        v = per_class.get(cls)
        if v is None:
            continue
        lines.append(
            f"| {cls} | {v['n']} | {v['n_pass']} | {v['pass_rate']:.0%} | "
            f"{v['min_delta']:+.3f} | {v['max_delta']:+.3f} | "
            f"{v['median_pilot_ari']:.3f} | {v['median_ref_ari']:.3f} |"
        )

    lines += ["", "## Per-cell detail", ""]
    detail = df[[
        "instance_class", "instance_id", "perturbation_id",
        "perturbation_family", "reference_ari_min", "pilot_ari_min",
        "delta_ari", "passes_threshold",
    ]].copy()
    for c in ("reference_ari_min", "pilot_ari_min", "delta_ari"):
        detail[c] = detail[c].astype(float).round(3)
    lines.append(
        "| class | instance | pert | family | ref ARI_min | "
        "pilot ARI_min | Δ ARI | pass |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for _, r in detail.iterrows():
        lines.append(
            f"| {r['instance_class']} | {r['instance_id']} | "
            f"{r['perturbation_id']} | {r['perturbation_family']} | "
            f"{r['reference_ari_min']:+.3f} | "
            f"{r['pilot_ari_min']:+.3f} | "
            f"{r['delta_ari']:+.3f} | "
            f"{'✓' if r['passes_threshold'] else '✗'} |"
        )

    if overall:
        lines += [
            "",
            "## Interpretation",
            "",
            "pyvrp_10s × 3 seeds reproduces the reference ARI distribution "
            "within tolerance on every instance class. The cheaper reference "
            "is methodologically defensible for the v2 calibrated-perturbation "
            "re-run. Stage 2 launches.",
        ]
    else:
        failing = [cls for cls, ok in classes_passing.items() if not ok]
        lines += [
            "",
            "## Interpretation",
            "",
            f"At least one instance class failed the per-class gate: "
            f"{', '.join(failing)}. This is itself a finding: objective "
            "equivalence between pyvrp_10s and the reference budget does "
            "not extend to seed-stability equivalence on the affected "
            "class. Stage 2 will **not** launch under the v1.4 spec.",
        ]

    output_md.write_text("\n".join(lines) + "\n")
    return {
        "per_class": per_class,
        "classes_passing": classes_passing,
        "overall": overall,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path,
                   default=PROJECT_ROOT / "reports" / "homberger_probe")
    args = p.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    reference_lookup = pd.read_csv(PILOT_REFERENCE_CSV)
    print(f"Reference stability CSV: {PILOT_REFERENCE_CSV}")
    print(f"  {len(reference_lookup)} rows; pilot cells: {len(PILOT_CELLS)}")

    rows: list[dict] = []
    t_total = time.perf_counter()
    for iid, pid in PILOT_CELLS:
        rows.append(_row_for_cell(iid, pid, reference_lookup=reference_lookup))
    print(f"\nTotal pilot wall-clock: {time.perf_counter() - t_total:.1f}s")

    df = pd.DataFrame(rows)
    out_csv = args.output_dir / "homberger_reference_pilot.csv"
    df.to_csv(out_csv, index=False)
    print(f"Wrote {out_csv}")

    out_md = args.output_dir / "homberger_reference_pilot_summary.md"
    summary = _summary_md(df, output_md=out_md)
    print(f"Wrote {out_md}")
    print(f"\nVerdict: {'PASS' if summary['overall'] else 'FAIL'}")
    for cls, v in summary["per_class"].items():
        print(f"  {cls}: {v['n_pass']}/{v['n']} passing")
    return 0 if summary["overall"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
