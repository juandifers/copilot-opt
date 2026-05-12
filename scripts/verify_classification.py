#!/usr/bin/env python3
"""Sanity-check ``data/instances/uchoa_x_classification.csv``.

Independent re-derivation of the avg_route_size quintile boundaries from
the ``n_kmin`` column, asserting that the per-instance bin labels in the
CSV match what we'd recompute now. Also reports marginal counts per
classification dimension and (if the .vrp files are present locally)
cross-checks the CSV's ``n_customers`` against PyVRP's parser on a sample.

Run as::

    python scripts/verify_classification.py
    python scripts/verify_classification.py --csv path/to/x.csv

Exit codes: 0 if all checks pass, 1 if any check fails.
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np

DEFAULT_CSV: Path = Path("data/instances/uchoa_x_classification.csv")
DEFAULT_INSTANCE_DIR: Path = Path("data/instances")
QUINTILE_LABELS: tuple[str, ...] = ("VS", "S", "M", "L", "VL")
DEP_LEVELS = {"C", "E", "R"}
CUST_LEVELS = {"C", "R", "RC"}
DEM_LEVELS = {"U", "1-10", "5-10", "1-100", "50-100", "Q", "SL"}
EXPECTED_N_INSTANCES: int = 100
PYVRP_CROSS_CHECK_SAMPLE: int = 15


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as fh:
        non_comment = (ln for ln in fh if not ln.lstrip().startswith("#"))
        return list(csv.DictReader(non_comment))


def _label_for(x: float, bounds: tuple[float, float, float, float]) -> str:
    p20, p40, p60, p80 = bounds
    if x <= p20:
        return "VS"
    if x <= p40:
        return "S"
    if x <= p60:
        return "M"
    if x <= p80:
        return "L"
    return "VL"


def verify(csv_path: Path, instance_dir: Path | None) -> bool:
    """Return True iff all checks pass."""
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        return False

    rows = _read_csv(csv_path)
    ok = True

    print(f"Loaded {len(rows)} rows from {csv_path}.")
    if len(rows) != EXPECTED_N_INSTANCES:
        print(f"ERROR: expected {EXPECTED_N_INSTANCES} rows, got {len(rows)}",
              file=sys.stderr)
        ok = False

    # --- Schema and value validation ---------------------------------------
    required = {"instance_id", "n_customers", "depot_position",
                "customer_distribution", "demand_pattern", "avg_route_size",
                "n_kmin"}
    missing_cols = required - set(rows[0].keys() if rows else [])
    if missing_cols:
        print(f"ERROR: missing columns: {sorted(missing_cols)}", file=sys.stderr)
        return False

    seen_ids: set[str] = set()
    for r in rows:
        iid = r["instance_id"]
        if iid in seen_ids:
            print(f"ERROR: duplicate instance_id {iid!r}", file=sys.stderr)
            ok = False
        seen_ids.add(iid)
        if r["depot_position"] not in DEP_LEVELS:
            print(f"ERROR: {iid}: bad depot_position {r['depot_position']!r}",
                  file=sys.stderr)
            ok = False
        if r["customer_distribution"] not in CUST_LEVELS:
            print(f"ERROR: {iid}: bad customer_distribution "
                  f"{r['customer_distribution']!r}", file=sys.stderr)
            ok = False
        if r["demand_pattern"] not in DEM_LEVELS:
            print(f"ERROR: {iid}: bad demand_pattern {r['demand_pattern']!r}",
                  file=sys.stderr)
            ok = False
        if r["avg_route_size"] not in QUINTILE_LABELS:
            print(f"ERROR: {iid}: bad avg_route_size {r['avg_route_size']!r}",
                  file=sys.stderr)
            ok = False

    # --- Recompute quintile boundaries from n_kmin -------------------------
    n_kmin = np.array([float(r["n_kmin"]) for r in rows], dtype=np.float64)
    p20, p40, p60, p80 = np.percentile(n_kmin, [20, 40, 60, 80], method="linear")
    bounds = (float(p20), float(p40), float(p60), float(p80))
    print(
        f"Recomputed quintile boundaries: "
        f"p20={bounds[0]:.4f} p40={bounds[1]:.4f} "
        f"p60={bounds[2]:.4f} p80={bounds[3]:.4f}"
    )

    # --- Bin-label consistency ---------------------------------------------
    mismatches: list[tuple[str, float, str, str]] = []
    for r in rows:
        x = float(r["n_kmin"])
        expected = _label_for(x, bounds)
        if r["avg_route_size"] != expected:
            mismatches.append(
                (r["instance_id"], x, r["avg_route_size"], expected)
            )
    if mismatches:
        ok = False
        print(f"ERROR: {len(mismatches)} avg_route_size labels disagree with "
              f"recomputed bounds:", file=sys.stderr)
        for iid, x, got, expected in mismatches[:10]:
            print(f"  {iid}: n_kmin={x:.2f} got={got!r} expected={expected!r}",
                  file=sys.stderr)
    else:
        print("All 100 avg_route_size labels are consistent with the recomputed boundaries.")

    # --- Marginal counts per dimension -------------------------------------
    print("\nMarginal counts per classification dimension:")
    for col in ("depot_position", "customer_distribution",
                "demand_pattern", "avg_route_size"):
        counts = Counter(r[col] for r in rows)
        formatted = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"  {col}: {formatted}")

    # --- Eligibility breakdown ---------------------------------------------
    n_le_500 = sum(1 for r in rows if int(r["n_customers"]) <= 500)
    n_gt_500 = len(rows) - n_le_500
    print(
        f"\nEligibility (n_customers ≤ 500): "
        f"{n_le_500} eligible, {n_gt_500} excluded."
    )

    # --- PyVRP cross-check on .vrp files we have locally -------------------
    if instance_dir is not None and instance_dir.is_dir():
        try:
            from pyvrp import read  # type: ignore[import-not-found]
        except ImportError:
            print("\nPyVRP not installed; skipping n_customers cross-check.",
                  file=sys.stderr)
        else:
            present = [r for r in rows if (instance_dir / f"{r['instance_id']}.vrp").exists()]
            if not present:
                print(f"\nNo .vrp files in {instance_dir} to cross-check.")
            else:
                rng = random.Random(20260429)
                k = min(PYVRP_CROSS_CHECK_SAMPLE, len(present))
                sample = rng.sample(present, k=k)
                print(f"\nCross-checking n_customers against PyVRP on "
                      f"{len(sample)} instances:")
                for r in sample:
                    iid = r["instance_id"]
                    csv_n = int(r["n_customers"])
                    parsed = read(str(instance_dir / f"{iid}.vrp"), round_func="round")
                    pyvrp_n = parsed.num_clients
                    flag = "OK " if csv_n == pyvrp_n else "FAIL"
                    print(f"  {flag} {iid}: csv={csv_n} pyvrp={pyvrp_n}")
                    if csv_n != pyvrp_n:
                        ok = False

    return ok


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    p.add_argument("--instance-dir", type=Path, default=DEFAULT_INSTANCE_DIR,
                   help="Directory of .vrp files (used for PyVRP cross-check).")
    p.add_argument("--no-pyvrp", action="store_true",
                   help="Skip the PyVRP n_customers cross-check.")
    args = p.parse_args(argv)
    instance_dir = None if args.no_pyvrp else args.instance_dir

    ok = verify(args.csv, instance_dir)
    print()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
