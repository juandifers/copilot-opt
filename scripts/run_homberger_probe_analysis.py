#!/usr/bin/env python3
"""Run the Homberger-200 probe analysis layer.

Inputs: the wide + long parquets the data-collection step
(``run_stage_a_vrptw.py`` pointed at the Homberger roster) produced.
Outputs: the 7 methodology / predictor CSVs and the probe README.

Usage::

    python scripts/run_homberger_probe_analysis.py \
        --wide  data/homberger_probe_cells.parquet \
        --long  data/homberger_probe_claim_rows.parquet \
        --stage-a-long data/stage_a_vrptw_consolidated_claim_rows.parquet \
        --output-dir reports/homberger_probe

The driver also evaluates the 5 success criteria and prints whether
a 180 s reference fallback is recommended (it does *not* auto-launch
the re-collection — that's a separate ``run_stage_a_vrptw.py`` call
with ``--time-limit 180`` and the unstable cells listed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pandas as pd  # noqa: E402

from vrp_copilot_bench.homberger_probe.analysis import (  # noqa: E402
    PROBE_GRID_IDS,
    write_methodology_outputs,
)
from vrp_copilot_bench.homberger_probe.predictor_eval import (  # noqa: E402
    write_predictor_eval_outputs,
)
from vrp_copilot_bench.homberger_probe.readme import (  # noqa: E402
    write_homberger_readme,
)


DEFAULT_WIDE = Path("data/homberger_probe_cells.parquet")
DEFAULT_LONG = Path("data/homberger_probe_claim_rows.parquet")
DEFAULT_STAGE_A_LONG = Path("data/stage_a_vrptw_consolidated_claim_rows.parquet")
DEFAULT_OUTPUT_DIR = Path("reports/homberger_probe")

#: Fraction of cells with min-ARI < 0.85 above which we recommend the
#: 180 s reference fallback per the probe spec.
FALLBACK_UNSTABLE_THRESHOLD: float = 0.30


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="run_homberger_probe_analysis",
                                description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wide", type=Path, default=DEFAULT_WIDE)
    p.add_argument("--long", type=Path, default=DEFAULT_LONG)
    p.add_argument("--stage-a-long", type=Path, default=DEFAULT_STAGE_A_LONG)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--time-limit", type=float, default=120.0,
                   help="Reference budget the wide-table cells used (for the README).")
    p.add_argument("--pyvrp10s-time-limit", type=float, default=10.0)
    p.add_argument("--fallback-applied", action="store_true",
                   help="Mark the README as having applied the 180 s fallback.")
    p.add_argument("--fallback-cells", type=int, default=0)
    p.add_argument("--skip-predictor-eval", action="store_true",
                   help="Skip the predictor zero-shot evaluation step.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading wide parquet: {args.wide}")
    wide = pd.read_parquet(args.wide)
    print(f"  {len(wide)} rows, {len(wide.columns)} cols")

    print(f"Loading long parquet: {args.long}")
    long_df = pd.read_parquet(args.long)
    print(f"  {len(long_df)} rows, {len(long_df.columns)} cols")

    stage_a_long = None
    if args.stage_a_long.exists():
        print(f"Loading Stage A long: {args.stage_a_long}")
        stage_a_long = pd.read_parquet(args.stage_a_long)
        print(f"  {len(stage_a_long)} rows for Stage A comparison")
    else:
        print(f"Stage A long not found at {args.stage_a_long} — skipping ΔStage A column.")

    print("Computing methodology metrics…")
    meth = write_methodology_outputs(
        wide, long_df, args.output_dir, stage_a_long_df=stage_a_long,
    )

    predictor_eval = pd.DataFrame()
    predictor_sweep = pd.DataFrame()
    if not args.skip_predictor_eval:
        print("Running predictor zero-shot evaluation…")
        predictor_eval, _, predictor_sweep = write_predictor_eval_outputs(
            args.stage_a_long, args.long, args.output_dir,
        )
    else:
        print("Skipping predictor zero-shot per --skip-predictor-eval.")

    instances_used = sorted(long_df["instance_id"].unique().tolist())
    perturbations_used = sorted(long_df["perturbation_id"].unique().tolist())
    seeds_used = [1, 2, 3]  # locked by wide-table schema

    print("Writing README…")
    readme_path = write_homberger_readme(
        args.output_dir,
        stability=meth["stability"],
        methodology=meth["methodology"],
        nonmonotone=meth["nonmonotone"],
        nonmonotone_summary=meth["nonmonotone_summary"],
        rung_gaps=meth["rung_gaps"],
        predictor_eval=predictor_eval,
        predictor_sweep=predictor_sweep,
        instances_used=instances_used,
        perturbations_used=perturbations_used,
        seeds_used=seeds_used,
        time_limit_s=args.time_limit,
        pyvrp10s_time_limit_s=args.pyvrp10s_time_limit,
        fallback_applied=args.fallback_applied,
        fallback_cells=args.fallback_cells,
    )
    print(f"README written: {readme_path}")

    # Fallback recommendation.
    stability = meth["stability"]
    unstable = stability[stability["reference_ari_min"] < 0.85]
    frac_unstable = len(unstable) / max(len(stability), 1)
    print()
    print("180 s reference-fallback check:")
    print(f"  cells with min-ARI < 0.85: {len(unstable)} / {len(stability)}  "
          f"({frac_unstable:.1%})")
    if frac_unstable > FALLBACK_UNSTABLE_THRESHOLD:
        cells_payload = unstable[
            ["instance_id", "perturbation_id", "reference_ari_min"]
        ].to_dict(orient="records")
        recco_path = args.output_dir / "homberger_probe_180s_fallback_recco.json"
        recco_path.write_text(json.dumps({
            "unstable_fraction": frac_unstable,
            "threshold": FALLBACK_UNSTABLE_THRESHOLD,
            "cells_to_resolve_at_180s": cells_payload,
        }, indent=2))
        print(f"  > {FALLBACK_UNSTABLE_THRESHOLD:.0%} threshold tripped — "
              f"see {recco_path} for the cell list.")
        print("  Re-run those cells via:")
        print("    python scripts/run_stage_a_vrptw.py --time-limit 180 "
              "--instances <iid…> --perturbations <pid…> "
              "--instance-dir data/vrptw_instances/homberger200 "
              "--parquet-wide data/homberger_probe_cells_180s.parquet ...")
    else:
        print(f"  ≤ {FALLBACK_UNSTABLE_THRESHOLD:.0%} threshold — fallback not recommended.")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
