#!/usr/bin/env python3
"""Pilot parquet inspection — checks 7.1 through 7.9 of docs/pilot_runbook.md.

Usage::

    python scripts/inspect_pilot.py data/pilot.parquet

Prints a PASS/WARN/FAIL table, one row per check. Exits 0 unless any check
returns FAIL; WARN does not block. WARN is reserved for the §12.x
verification-style checks (label distribution, decoupling rate, reference
stability) — these are informational at pilot scale because 3 instances is
too small to commit to the [0.10, 0.90] / >0.20 / <0.05 bounds.

Checks 7.1, 7.2, 7.3, 7.4, 7.5, 7.9 fail hard if violated — they're
schema / wiring / propagation checks that must pass before Stage A. See
docs/pilot_runbook.md §7 for the criteria.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# Allow running the script without an editable install.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd
import pyarrow.parquet as pq

from vrp_copilot_bench.baselines import load_baseline_solution
from vrp_copilot_bench.consolidate import SCHEMA, SCHEMA_VERSION
from vrp_copilot_bench.work_plan import select_audit_subset


# ---------------------------------------------------------------------------
# Check result type


@dataclass
class CheckResult:
    name: str
    status: str  # "PASS" / "WARN" / "FAIL"
    detail: str


# Columns required to be non-null on every row (mirrors consolidate._REQUIRED_NON_NULL).
_REQUIRED_NON_NULL: tuple[str, ...] = (
    "instance_id",
    "perturbation_family",
    "perturbation_id",
    "perturbation_magnitude",
    "claim_family",
    "action",
    "action_feasible",
    "action_n_overload",
    "action_max_overload",
    "action_runtime_s",
    "action_assignment",
    "action_route_costs",
    "reference_objective",
    "reference_feasible",
    "reference_assignment",
    "reference_route_costs",
    "reference_runtime_s",
    "baseline_solution_feasible_under_perturbation",
    "band_obj",
    "band_struct",
    "band_rank",
)

# claim_family → required-non-null loss column for that claim
_REQUIRED_PER_CLAIM: dict[str, str] = {
    "OBJ": "loss_obj",
    "STRUCT": "loss_struct",
    "RANK": "loss_rank",
}


# ---------------------------------------------------------------------------
# Individual checks


def check_7_1_schema_version(parquet_path: Path) -> CheckResult:
    """Schema metadata carries ``_schema_version = v1.0``."""
    meta = pq.read_metadata(str(parquet_path))
    arrow_meta = meta.schema.to_arrow_schema().metadata or {}
    stamped = arrow_meta.get(b"_schema_version")
    if stamped is None:
        return CheckResult(
            "7.1 schema version",
            "FAIL",
            "no _schema_version key in parquet metadata",
        )
    if stamped.decode() != SCHEMA_VERSION:
        return CheckResult(
            "7.1 schema version",
            "FAIL",
            f"expected {SCHEMA_VERSION!r}, got {stamped.decode()!r}",
        )
    return CheckResult("7.1 schema version", "PASS", f"v={stamped.decode()}")


def check_7_2_shape(df: pd.DataFrame, n_pilot_instances: int) -> CheckResult:
    """Row count and column count match the cell-action cross-product."""
    expected_rows = n_pilot_instances * 16 * 4 * 5
    expected_cols = len(SCHEMA)
    if df.shape != (expected_rows, expected_cols):
        return CheckResult(
            "7.2 row/column count",
            "FAIL",
            f"expected ({expected_rows}, {expected_cols}), got {df.shape}",
        )
    return CheckResult(
        "7.2 row/column count",
        "PASS",
        f"shape={df.shape}",
    )


def check_7_3_required_non_null(df: pd.DataFrame) -> CheckResult:
    """No NaN in required-non-null columns."""
    null_counts = df[list(_REQUIRED_NON_NULL)].isna().sum()
    offenders = {c: int(n) for c, n in null_counts.items() if n > 0}
    if offenders:
        return CheckResult(
            "7.3 required non-null",
            "FAIL",
            f"nulls: {offenders}",
        )
    return CheckResult(
        "7.3 required non-null",
        "PASS",
        f"{len(_REQUIRED_NON_NULL)} cols checked, all non-null",
    )


def check_7_4_per_claim_loss(df: pd.DataFrame) -> CheckResult:
    """For each claim family, the matching loss column is non-null on its rows."""
    offenders: dict[str, int] = {}
    for claim, loss_col in _REQUIRED_PER_CLAIM.items():
        mask = df["claim_family"] == claim
        n_null = int(df.loc[mask, loss_col].isna().sum())
        if n_null > 0:
            offenders[f"{claim}/{loss_col}"] = n_null
    # PLAN_VALIDITY × reuse_direct only: loss_plan_validity must be non-null.
    pv_reuse_mask = (df["claim_family"] == "PLAN_VALIDITY") & (df["action"] == "reuse_direct")
    n_pv_null = int(df.loc[pv_reuse_mask, "loss_plan_validity"].isna().sum())
    if n_pv_null > 0:
        offenders["PLAN_VALIDITY/reuse_direct/loss_plan_validity"] = n_pv_null
    if offenders:
        return CheckResult(
            "7.4 per-claim loss",
            "FAIL",
            f"nulls: {offenders}",
        )
    return CheckResult(
        "7.4 per-claim loss",
        "PASS",
        "OBJ/STRUCT/RANK losses + PLAN_VALIDITY×reuse_direct all populated",
    )


def check_7_5_audit_population(
    df: pd.DataFrame, pilot_instances: set[str]
) -> CheckResult:
    """Audit fields are non-null exactly on pairs in select_audit_subset()."""
    all_audit_pairs = set(select_audit_subset())
    expected_audit_pairs = {p for p in all_audit_pairs if p[0] in pilot_instances}

    actual_audit_pairs: set[tuple[str, str]] = set()
    has_audit = df["audit_seed_2_obj"].notna()
    for _, row in df.loc[has_audit, ["instance_id", "perturbation_id"]].drop_duplicates().iterrows():
        actual_audit_pairs.add((row["instance_id"], row["perturbation_id"]))

    extra = actual_audit_pairs - expected_audit_pairs
    missing = expected_audit_pairs - actual_audit_pairs
    if extra or missing:
        return CheckResult(
            "7.5 audit population",
            "FAIL",
            f"expected {len(expected_audit_pairs)} pairs; "
            f"extra={sorted(extra)} missing={sorted(missing)}",
        )

    # Sanity: each audited pair has exactly 4 claim_family × 5 action = 20 rows.
    audit_rows_per_pair: dict[tuple[str, str], int] = defaultdict(int)
    for _, row in df.loc[has_audit].iterrows():
        audit_rows_per_pair[(row["instance_id"], row["perturbation_id"])] += 1
    bad_counts = {p: n for p, n in audit_rows_per_pair.items() if n != 20}
    if bad_counts:
        return CheckResult(
            "7.5 audit population",
            "FAIL",
            f"per-pair row counts off (expected 20): {bad_counts}",
        )

    return CheckResult(
        "7.5 audit population",
        "PASS",
        f"{len(expected_audit_pairs)} audit pairs × 20 rows each",
    )


def check_7_6_label_distribution(df: pd.DataFrame) -> CheckResult:
    """For each (claim × perturbation family), check easy-band fraction in [0.10, 0.90].

    Informational at pilot scale: 3 instances per cell is far too small for
    the §12.1 bound to hold reliably; this surfaces 0% / 100% blocks as a
    warning signal, not a hard failure.
    """
    band_col_by_claim = {
        "OBJ": "band_obj",
        "STRUCT": "band_struct",
        "RANK": "band_rank",
    }
    out_of_bounds: list[str] = []
    block_count = 0
    # Restrict to reuse_direct rows: per prereg §12.1 the sufficiency
    # label is defined relative to reuse_direct, so the easy-band fraction
    # is computed on that subset.
    df_reuse = df[df["action"] == "reuse_direct"]
    for claim, band_col in band_col_by_claim.items():
        for family in ("CAPACITY", "DISTANCE", "DEMAND", "INSERTION"):
            block = df_reuse[
                (df_reuse["claim_family"] == claim)
                & (df_reuse["perturbation_family"] == family)
            ]
            if len(block) == 0:
                continue
            easy_frac = (block[band_col] == "easy").mean()
            block_count += 1
            if easy_frac < 0.10 or easy_frac > 0.90:
                out_of_bounds.append(
                    f"{claim}×{family}: easy={easy_frac:.2f} (n={len(block)})"
                )

    if out_of_bounds:
        return CheckResult(
            "7.6 label distribution",
            "WARN",
            f"{len(out_of_bounds)}/{block_count} blocks outside [0.10, 0.90]: "
            f"{out_of_bounds[:3]}{' ...' if len(out_of_bounds) > 3 else ''}",
        )
    return CheckResult(
        "7.6 label distribution",
        "PASS",
        f"all {block_count} blocks in [0.10, 0.90] (pilot-scale, informational)",
    )


def check_7_7_feasibility_decoupling(df: pd.DataFrame) -> CheckResult:
    """§12.4 feasibility-decoupling diagnostic: on CAPACITY × OBJ × reuse_direct
    rows, the fraction with band_obj=='easy' AND action_feasible==False should
    exceed 0.20.

    The §9.5 column for operational validity on each row is ``action_feasible``
    (the per-action feasibility flag, not a separate ``operational_validity``).
    Informational at pilot scale (n ≈ 12 cells).
    """
    cap_obj_reuse = df[
        (df["claim_family"] == "OBJ")
        & (df["perturbation_family"] == "CAPACITY")
        & (df["action"] == "reuse_direct")
    ]
    if len(cap_obj_reuse) == 0:
        return CheckResult(
            "7.7 feasibility decoupling",
            "WARN",
            "no CAP × OBJ × reuse_direct rows; cannot evaluate",
        )
    easy_obj = cap_obj_reuse["band_obj"] == "easy"
    if easy_obj.sum() == 0:
        return CheckResult(
            "7.7 feasibility decoupling",
            "WARN",
            f"no easy band_obj rows in n={len(cap_obj_reuse)} (perturbations may be too aggressive at pilot scale)",
        )
    infeasible = cap_obj_reuse["action_feasible"] == False  # noqa: E712
    decoupling_rate = (easy_obj & infeasible).sum() / easy_obj.sum()
    if decoupling_rate <= 0.20:
        return CheckResult(
            "7.7 feasibility decoupling",
            "WARN",
            f"rate={decoupling_rate:.2f} ≤ 0.20 (pilot n={int(easy_obj.sum())}; "
            f"§12.4 evaluated on Stage A)",
        )
    return CheckResult(
        "7.7 feasibility decoupling",
        "PASS",
        f"rate={decoupling_rate:.2f} > 0.20 (n={int(easy_obj.sum())})",
    )


def check_7_8_reference_stability(df: pd.DataFrame) -> CheckResult:
    """§12.3: on audit pairs, the fraction with ANY instability flag firing
    should be < 0.05. Informational at pilot scale (n ≈ 10 audit pairs)."""
    has_audit = df["audit_seed_2_obj"].notna()
    audit_rows = df.loc[
        has_audit, ["instance_id", "perturbation_id",
                    "reference_obj_unstable",
                    "reference_struct_unstable",
                    "reference_rank_unstable"]
    ].drop_duplicates(subset=["instance_id", "perturbation_id"])
    if len(audit_rows) == 0:
        return CheckResult(
            "7.8 reference stability",
            "WARN",
            "no audit pairs in pilot",
        )
    any_unstable = (
        audit_rows["reference_obj_unstable"].astype("boolean").fillna(False)
        | audit_rows["reference_struct_unstable"].astype("boolean").fillna(False)
        | audit_rows["reference_rank_unstable"].astype("boolean").fillna(False)
    )
    rate = float(any_unstable.mean())
    if rate >= 0.05:
        return CheckResult(
            "7.8 reference stability",
            "WARN",
            f"unstable rate={rate:.2f} ≥ 0.05 across {len(audit_rows)} audit pair(s); "
            f"§12.3 evaluated on Stage A",
        )
    return CheckResult(
        "7.8 reference stability",
        "PASS",
        f"unstable rate={rate:.2f} across {len(audit_rows)} audit pair(s)",
    )


def check_7_9_dist_4_ranking(
    df: pd.DataFrame, pilot_instances: set[str]
) -> CheckResult:
    """DIST_4 sanity: the reference's top-3 baseline groups (recovered from
    the audit seed_2_top3 / seed_3_top3 fields) must include the highest-cost
    baseline route.

    Why this is the most thesis-relevant check at pilot scale: DIST_4 inflates
    distances on the highest-cost baseline route, so under the prereg §9.4
    delta form, that route's customers must show the largest impact-delta.
    If group 0 (or whichever group has the highest baseline cost) is absent
    from the seed-2 / seed-3 top-3 on a DIST_4 cell, the delta-form ranking
    metric is computing the wrong thing somewhere.

    Coverage: we can only check this against the audit fields, which are
    populated on DIST_4 pairs that fell in the audit subset. The pilot
    typically has 2 of 3 DIST_4 pairs in the audit subset (X-n101-k25 and
    X-n251-k28); X-n429-k61's DIST_4 is unaudited so we skip it here.
    """
    dist_4_audited = df[
        (df["perturbation_id"] == "DIST_4")
        & (df["action"] == "pyvrp_60s")
        & df["audit_seed_2_top3"].notna()
    ].drop_duplicates(subset=["instance_id"])

    if len(dist_4_audited) == 0:
        return CheckResult(
            "7.9 DIST_4 ranking",
            "WARN",
            "no audited DIST_4 cells in pilot; skipped",
        )

    detail_per_instance: list[str] = []
    failures: list[str] = []
    for _, row in dist_4_audited.iterrows():
        instance_id = row["instance_id"]
        baseline = load_baseline_solution(instance_id)
        if not baseline.route_costs:
            failures.append(f"{instance_id}: baseline has no route_costs")
            continue
        highest_cost_group = max(baseline.route_costs, key=baseline.route_costs.get)
        seed2_top3 = json.loads(row["audit_seed_2_top3"])
        seed3_top3 = json.loads(row["audit_seed_3_top3"])
        in_seed2 = highest_cost_group in seed2_top3
        in_seed3 = highest_cost_group in seed3_top3
        detail_per_instance.append(
            f"{instance_id}: hi={highest_cost_group}, "
            f"s2={seed2_top3}{'✓' if in_seed2 else '✗'}, "
            f"s3={seed3_top3}{'✓' if in_seed3 else '✗'}"
        )
        if not in_seed2:
            failures.append(f"{instance_id}: highest-cost group {highest_cost_group} missing from seed-2 top-3 {seed2_top3}")
        if not in_seed3:
            failures.append(f"{instance_id}: highest-cost group {highest_cost_group} missing from seed-3 top-3 {seed3_top3}")

    if failures:
        return CheckResult(
            "7.9 DIST_4 ranking",
            "FAIL",
            "; ".join(failures),
        )
    return CheckResult(
        "7.9 DIST_4 ranking",
        "PASS",
        f"{len(dist_4_audited)} DIST_4 cell(s) audited; all include highest-cost baseline route in seed-2 and seed-3 top-3 ({'; '.join(detail_per_instance)})",
    )


# ---------------------------------------------------------------------------
# Driver


def _print_table(results: list[CheckResult]) -> None:
    name_w = max(len(r.name) for r in results)
    status_w = max(len(r.status) for r in results)
    print()
    print(f"{'Check':<{name_w}}  {'Status':<{status_w}}  Detail")
    print(f"{'-' * name_w}  {'-' * status_w}  {'-' * 60}")
    for r in results:
        print(f"{r.name:<{name_w}}  {r.status:<{status_w}}  {r.detail}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="inspect_pilot",
        description="Run pilot parquet sanity checks (docs/pilot_runbook.md §7).",
    )
    parser.add_argument("parquet", type=Path,
                        help="Path to the pilot parquet (e.g. data/pilot.parquet).")
    parser.add_argument("--instances", default="instances/pilot_instances.txt",
                        help="Path to the pilot instance roster file (default: "
                             "instances/pilot_instances.txt).")
    args = parser.parse_args(argv)

    if not args.parquet.exists():
        print(f"ERROR: parquet not found at {args.parquet}", file=sys.stderr)
        return 2

    pilot_instances: set[str] = set()
    pilot_roster_path = Path(args.instances)
    if pilot_roster_path.exists():
        for line in pilot_roster_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pilot_instances.add(line)
    if not pilot_instances:
        print(f"ERROR: no pilot instances loaded from {pilot_roster_path}",
              file=sys.stderr)
        return 2

    df = pd.read_parquet(args.parquet)

    results: list[CheckResult] = []
    results.append(check_7_1_schema_version(args.parquet))
    results.append(check_7_2_shape(df, n_pilot_instances=len(pilot_instances)))
    results.append(check_7_3_required_non_null(df))
    results.append(check_7_4_per_claim_loss(df))
    results.append(check_7_5_audit_population(df, pilot_instances))
    results.append(check_7_6_label_distribution(df))
    results.append(check_7_7_feasibility_decoupling(df))
    results.append(check_7_8_reference_stability(df))
    results.append(check_7_9_dist_4_ranking(df, pilot_instances))

    _print_table(results)

    n_fail = sum(1 for r in results if r.status == "FAIL")
    n_warn = sum(1 for r in results if r.status == "WARN")
    n_pass = sum(1 for r in results if r.status == "PASS")
    print(f"Summary: {n_pass} PASS, {n_warn} WARN, {n_fail} FAIL")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
