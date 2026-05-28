#!/usr/bin/env python3
"""Splice the 180 s fallback re-collection into the 120 s probe wide/long
parquets.

For the 28 cells whose 120 s 3-seed min-ARI < 0.85 (per
``reports/homberger_probe/homberger_probe_180s_fallback_recco.json``)
this script overwrites the rows in the original wide + long parquets
with their 180 s re-solve counterparts. The other 52 cells stay at
120 s. The merged parquets are written to a new path so the original
120 s artefacts are preserved.

Usage::

    python scripts/merge_homberger_180s_fallback.py
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


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="merge_homberger_180s_fallback")
    p.add_argument("--wide-120s", type=Path,
                   default=Path("data/homberger_probe_cells.parquet"))
    p.add_argument("--long-120s", type=Path,
                   default=Path("data/homberger_probe_claim_rows.parquet"))
    p.add_argument("--wide-180s", type=Path,
                   default=Path("data/homberger_probe_cells_180s.parquet"))
    p.add_argument("--long-180s", type=Path,
                   default=Path("data/homberger_probe_claim_rows_180s.parquet"))
    p.add_argument("--recco-json", type=Path,
                   default=Path("reports/homberger_probe/homberger_probe_180s_fallback_recco.json"))
    p.add_argument("--wide-merged", type=Path,
                   default=Path("data/homberger_probe_cells_merged.parquet"))
    p.add_argument("--long-merged", type=Path,
                   default=Path("data/homberger_probe_claim_rows_merged.parquet"))
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    print(f"Loading 120 s wide: {args.wide_120s}")
    wide_120 = pd.read_parquet(args.wide_120s)
    print(f"  {len(wide_120)} rows")
    print(f"Loading 120 s long: {args.long_120s}")
    long_120 = pd.read_parquet(args.long_120s)
    print(f"  {len(long_120)} rows")
    print(f"Loading 180 s wide: {args.wide_180s}")
    wide_180 = pd.read_parquet(args.wide_180s)
    print(f"  {len(wide_180)} rows")
    print(f"Loading 180 s long: {args.long_180s}")
    long_180 = pd.read_parquet(args.long_180s)
    print(f"  {len(long_180)} rows")

    recco = json.loads(args.recco_json.read_text())
    cells = {
        (c["instance_id"], c["perturbation_id"])
        for c in recco["cells_to_resolve_at_180s"]
    }
    print(f"Splicing {len(cells)} unstable cells from 180 s into 120 s parquets")

    # Filter the 180 s outputs to just the unstable cells.
    def _filter_to_cells(df: pd.DataFrame) -> pd.DataFrame:
        key = list(zip(df["instance_id"], df["perturbation_id"]))
        keep = [k in cells for k in key]
        return df[keep].reset_index(drop=True)

    wide_keep_180 = _filter_to_cells(wide_180)
    long_keep_180 = _filter_to_cells(long_180)
    print(f"  180 s rows kept: wide={len(wide_keep_180)}, long={len(long_keep_180)}")

    # Drop those cells from the 120 s outputs.
    def _drop_cells(df: pd.DataFrame) -> pd.DataFrame:
        key = list(zip(df["instance_id"], df["perturbation_id"]))
        keep = [k not in cells for k in key]
        return df[keep].reset_index(drop=True)

    wide_120_kept = _drop_cells(wide_120)
    long_120_kept = _drop_cells(long_120)
    print(f"  120 s rows kept: wide={len(wide_120_kept)}, long={len(long_120_kept)}")

    # Concat + sort.
    merged_wide = pd.concat([wide_120_kept, wide_keep_180], ignore_index=True)
    merged_long = pd.concat([long_120_kept, long_keep_180], ignore_index=True)
    merged_wide = merged_wide.sort_values(
        ["instance_id", "perturbation_id", "action"]
    ).reset_index(drop=True)
    merged_long = merged_long.sort_values(
        ["instance_id", "perturbation_id", "action", "claim_family"]
    ).reset_index(drop=True)

    # Audit annotation: tag the 180 s rows so downstream code can identify them.
    is_180 = list(zip(merged_wide["instance_id"], merged_wide["perturbation_id"]))
    merged_wide["reference_time_limit_s"] = [180.0 if k in cells else 120.0 for k in is_180]
    is_180_long = list(zip(merged_long["instance_id"], merged_long["perturbation_id"]))
    merged_long["reference_time_limit_s"] = [180.0 if k in cells else 120.0 for k in is_180_long]

    # Sanity: row counts must match the original.
    assert len(merged_wide) == len(wide_120), (
        f"merged wide row count {len(merged_wide)} != original {len(wide_120)}"
    )
    assert len(merged_long) == len(long_120), (
        f"merged long row count {len(merged_long)} != original {len(long_120)}"
    )

    print(f"Writing merged wide: {args.wide_merged}")
    merged_wide.to_parquet(args.wide_merged, index=False)
    print(f"Writing merged long: {args.long_merged}")
    merged_long.to_parquet(args.long_merged, index=False)
    print(f"Merged: wide={len(merged_wide)} rows, long={len(merged_long)} rows")
    print(f"  cells at 180 s reference: {len(cells)} / "
          f"{merged_wide.groupby(['instance_id','perturbation_id']).ngroups}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
