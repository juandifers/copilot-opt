"""Cross-axis scatter concatenation.

Reads each axis's per-axis `reports/scatter.csv` (if it exists),
validates it against the shared schema, and emits a single
unified scatter CSV under `analysis/unified_scatter.csv`.

Usage:

    python -m product.evaluation.run2_stress.analysis.concat_scatter

The script is deliberately small. Any analytical work (plotting,
aggregation, per-(axis, system, metric) tables) happens downstream
in a notebook reading `unified_scatter.csv`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from product.evaluation.run2_stress.shared.validators import (
    ALLOWED_AXES,
    SCATTER_COLUMNS,
    validate_scatter_schema,
)


def _stress_root() -> Path:
    return Path(__file__).resolve().parents[1]


def candidate_scatter_files() -> list[Path]:
    """Return the per-axis scatter file paths that exist on disk."""
    root = _stress_root()
    found: list[Path] = []
    for axis in sorted(ALLOWED_AXES):
        reports = root / axis / "reports"
        if not reports.exists():
            continue
        for name in sorted(p.name for p in reports.iterdir() if p.suffix == ".csv"):
            if name == "scatter.csv" or name.startswith("scatter_"):
                found.append(reports / name)
    return found


def concat_scatter(paths: list[Path]) -> pd.DataFrame:
    """Read and concatenate each path; raises if any path fails the
    shared schema validator."""
    frames: list[pd.DataFrame] = []
    for path in paths:
        errs = validate_scatter_schema(path)
        if errs:
            raise ValueError(
                f"{path} does not conform to the shared scatter schema: "
                + "; ".join(errs)
            )
        df = pd.read_csv(path, keep_default_na=False, dtype=str)
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=SCATTER_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="concat_scatter",
        description="Concatenate per-axis scatter files into a unified CSV.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "unified_scatter.csv",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        type=Path,
        default=None,
        help=(
            "Optional explicit list of per-axis scatter files. Default: "
            "discover via candidate_scatter_files()."
        ),
    )
    args = parser.parse_args(argv)

    paths = args.paths or candidate_scatter_files()
    if not paths:
        print(
            "no per-axis scatter files found under "
            "product/evaluation/run2_stress/<axis>/reports/",
            file=sys.stderr,
        )
        return 1

    df = concat_scatter(paths)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"wrote {args.out} ({len(df)} rows, from {len(paths)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
