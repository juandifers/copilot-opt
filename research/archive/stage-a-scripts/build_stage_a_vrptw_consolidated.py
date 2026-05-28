#!/usr/bin/env python3
"""Consolidate Stage A VRPTW with 120s re-collected references.

Produces ``data/stage_a_vrptw_consolidated.parquet`` (wide) and
``data/stage_a_vrptw_consolidated_claim_rows.parquet`` (long) by
overlaying the 120 s re-collected reference data for 256 cells on top of
the original Stage A artifact, while keeping the action portfolio
evaluations and the per-claim-family loss/band values untouched (per the
task spec: the re-collection was references-only; actions were not
re-run; the wide table doesn't store action assignments so losses cannot
be recomputed without re-running actions).

What this script touches per re-collected cell:
- Reference-prefixed wide columns (objectives, feasibility, ari_*,
  obj_best_feasible, failure_kind, n_routes_*, runtime_reference_s).
- ``reference_struct_unstable`` applies the v1.1 amendment: None when no
  120 s seed is feasible (the 7 §8.3 cells).
- Provenance columns added at the table level:
    * ``reference_recollected``  : bool (True for the 256 cells)
    * ``reference_ari_min_60s``  : float | None  (original 60 s ari_min
                                   on the 256 cells; None on the 640
                                   non-re-collected cells)
    * ``reference_time_limit_s`` : int (120 for the 256, 60 for the 640)

What this script does NOT touch:
- Any ``action_*`` column (action's own evaluation under the 60 s ref).
- Any ``loss_*`` / ``band_*`` column (computed at Stage A time against
  the 60 s seed-1 reference; not re-computable without action
  assignments).
- ``baseline_*`` columns (baselines unchanged at 60 s by design).

Long table:
- Reference-derived columns (``reference_struct_unstable``,
  ``reference_obj_unstable``, ``reference_valid``) are recomputed from
  the consolidated wide table so wide and long agree.
- ``loss``, ``band``, ``sufficient_binary`` are carried over unchanged
  (they reflect the 60 s reference; recomputing them requires
  re-running actions, which the task spec forbids).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from vrp_copilot_bench.vrptw.evaluation import (  # noqa: E402
    ARI_STRUCT_UNSTABLE_THRESHOLD,
)

STAGE_A_WIDE = PROJECT_ROOT / "data" / "stage_a_vrptw.parquet"
STAGE_A_LONG = PROJECT_ROOT / "data" / "stage_a_vrptw_claim_rows.parquet"
RECOLL = PROJECT_ROOT / "data" / "stage_a_vrptw_recollected.parquet"
OUT_WIDE = PROJECT_ROOT / "data" / "stage_a_vrptw_consolidated.parquet"
OUT_LONG = PROJECT_ROOT / "data" / "stage_a_vrptw_consolidated_claim_rows.parquet"


REFERENCE_COLS_REPLACE: tuple[tuple[str, str], ...] = (
    # (wide_col, recoll_col)
    ("reference_obj_s1",          "reference_obj_s1_120s"),
    ("reference_obj_s2",          "reference_obj_s2_120s"),
    ("reference_obj_s3",          "reference_obj_s3_120s"),
    ("reference_s1_feasible",     "reference_s1_feasible_120s"),
    ("reference_s2_feasible",     "reference_s2_feasible_120s"),
    ("reference_s3_feasible",     "reference_s3_feasible_120s"),
    ("reference_any_feasible",    "reference_any_feasible_120s"),
    ("reference_all_feasible",    "reference_all_feasible_120s"),
    ("reference_n_routes_s1",     "reference_n_routes_s1_120s"),
    ("reference_n_routes_s2",     "reference_n_routes_s2_120s"),
    ("reference_n_routes_s3",     "reference_n_routes_s3_120s"),
    ("reference_ari_s1s2",        "reference_ari_s1s2_120s"),
    ("reference_ari_s1s3",        "reference_ari_s1s3_120s"),
    ("reference_ari_s2s3",        "reference_ari_s2s3_120s"),
    ("reference_ari_min",         "reference_ari_min_120s"),
    ("reference_obj_unstable",    "reference_obj_unstable_120s"),
)


def _v11_struct_unstable(any_feasible: bool, ari_min: float) -> bool | None:
    """PREREG v1.1 rule: None when no feasible seed; else ari_min < 0.90."""
    if not any_feasible:
        return None
    if ari_min is None or (isinstance(ari_min, float) and math.isnan(ari_min)):
        return False
    return bool(ari_min < ARI_STRUCT_UNSTABLE_THRESHOLD)


def _failure_kind(any_feasible: bool, all_feasible: bool) -> str:
    if all_feasible:
        return "none"
    if not any_feasible:
        return "all_infeasible"
    return "any_infeasible"


def _obj_best_feasible(
    s1_obj: float, s2_obj: float, s3_obj: float,
    s1_feas: bool, s2_feas: bool, s3_feas: bool,
) -> float | None:
    finite = [
        o for o, f in (
            (s1_obj, s1_feas), (s2_obj, s2_feas), (s3_obj, s3_feas),
        )
        if f and o is not None and math.isfinite(float(o)) and float(o) > 0
    ]
    return float(min(finite)) if finite else None


def build_consolidated_wide(
    stage_a_wide: pd.DataFrame, recoll: pd.DataFrame,
) -> pd.DataFrame:
    """Overlay 120s reference columns on the 256 re-collected cells."""
    # Sanity: recoll covers exactly the 256 unstable cells, completely solved.
    assert recoll["recollect_complete"].all(), "recoll has incomplete rows"
    assert len(recoll) == 256, f"recoll has {len(recoll)} rows, expected 256"

    recoll_keyed = recoll.set_index(["instance_id", "perturbation_id"])
    recoll_keys = set(recoll_keyed.index)

    out = stage_a_wide.copy()

    # Provenance columns (defaults for the 640 non-re-collected cells)
    out["reference_recollected"] = False
    out["reference_ari_min_60s"] = pd.NA
    out["reference_time_limit_s"] = 60

    # Promote reference_struct_unstable to nullable boolean so we can store
    # None on the 7 §8.3 cells (v1.1 amendment).
    out["reference_struct_unstable"] = out["reference_struct_unstable"].astype("boolean")

    # Per-cell index for the wide table.
    wide_keyed = out.set_index(["instance_id", "perturbation_id"], drop=False)

    n_updated = 0
    n_struct_undefined = 0
    for key in recoll_keys:
        recoll_row = recoll_keyed.loc[key]
        row_mask = (out["instance_id"] == key[0]) & (out["perturbation_id"] == key[1])
        if not row_mask.any():
            raise RuntimeError(f"Re-collected cell {key} not found in Stage A wide table")

        # Replace primitive reference columns
        for wide_col, recoll_col in REFERENCE_COLS_REPLACE:
            out.loc[row_mask, wide_col] = recoll_row[recoll_col]

        # struct_unstable: apply v1.1 rule
        any_feas = bool(recoll_row["reference_any_feasible_120s"])
        ari_min_120 = float(recoll_row["reference_ari_min_120s"])
        v11_struct = _v11_struct_unstable(any_feas, ari_min_120)
        # nullable boolean column: NA represents undefined
        out.loc[row_mask, "reference_struct_unstable"] = (
            pd.NA if v11_struct is None else bool(v11_struct)
        )
        if v11_struct is None:
            n_struct_undefined += 1

        # Recompute reference_obj_best_feasible from 120s data
        obj_best = _obj_best_feasible(
            float(recoll_row["reference_obj_s1_120s"]),
            float(recoll_row["reference_obj_s2_120s"]),
            float(recoll_row["reference_obj_s3_120s"]),
            bool(recoll_row["reference_s1_feasible_120s"]),
            bool(recoll_row["reference_s2_feasible_120s"]),
            bool(recoll_row["reference_s3_feasible_120s"]),
        )
        out.loc[row_mask, "reference_obj_best_feasible"] = obj_best

        # Recompute reference_failure_kind
        all_feas = bool(recoll_row["reference_all_feasible_120s"])
        fk = _failure_kind(any_feas, all_feas)
        out.loc[row_mask, "reference_failure_kind"] = fk

        # runtime_reference_s = mean of 3 120s seed runtimes
        rt_mean = float(np.mean([
            float(recoll_row["runtime_s1_120s"]),
            float(recoll_row["runtime_s2_120s"]),
            float(recoll_row["runtime_s3_120s"]),
        ]))
        out.loc[row_mask, "runtime_reference_s"] = rt_mean

        # Provenance
        out.loc[row_mask, "reference_recollected"] = True
        out.loc[row_mask, "reference_ari_min_60s"] = float(recoll_row["reference_ari_min_60s"])
        out.loc[row_mask, "reference_time_limit_s"] = 120

        n_updated += int(row_mask.sum())

    print(f"Updated reference columns on {n_updated} wide rows "
          f"({len(recoll_keys)} cells)")
    print(f"  of which struct_unstable=NA (v1.1 undefined): "
          f"{n_struct_undefined} cells × N_action rows")
    return out


def build_consolidated_long(
    stage_a_long: pd.DataFrame, consolidated_wide: pd.DataFrame,
) -> pd.DataFrame:
    """Update long table's reference-derived columns to match the new wide.

    Per task spec, ``loss``, ``band``, ``sufficient_binary`` stay at their
    Stage A values (action portfolio data). Only ``reference_struct_unstable``,
    ``reference_obj_unstable``, and ``reference_valid`` are re-derived.
    """
    out = stage_a_long.copy()
    # Promote nullable boolean.
    out["reference_struct_unstable"] = out["reference_struct_unstable"].astype("boolean")

    # Join wide → long by (iid, pid, action). Per-claim-family rows share
    # the cell-level reference state.
    wide_keyed = consolidated_wide.set_index(
        ["instance_id", "perturbation_id", "action"]
    )

    # Pull reference state from wide (cell-level).
    long_keys = list(zip(out["instance_id"], out["perturbation_id"], out["action"]))
    new_struct = []
    new_obj = []
    new_s1_feas = []
    new_ari_min = []
    new_obj_unst = []
    for key in long_keys:
        try:
            w = wide_keyed.loc[key]
        except KeyError:
            raise RuntimeError(f"Long row {key} not found in consolidated wide")
        # struct_unstable as nullable Boolean
        su = w["reference_struct_unstable"]
        new_struct.append(pd.NA if pd.isna(su) else bool(su))
        new_obj_unst.append(bool(w["reference_obj_unstable"]))
        new_s1_feas.append(bool(w["reference_s1_feasible"]))
        new_obj.append(w["reference_obj_s1"])
        new_ari_min.append(w["reference_ari_min"])

    out["reference_struct_unstable"] = pd.array(new_struct, dtype="boolean")
    out["reference_obj_unstable"] = new_obj_unst

    # Recompute reference_valid per claim family using the same rules as
    # scripts/run_vrptw_scale_check.py:580–595.
    def _ref_s1_valid(s1_feas, obj_s1) -> bool:
        if not s1_feas:
            return False
        if obj_s1 is None:
            return False
        try:
            v = float(obj_s1)
        except (TypeError, ValueError):
            return False
        return math.isfinite(v) and v > 0

    new_ref_valid = []
    families = out["claim_family"].tolist()
    obj_unst_long = new_obj_unst
    struct_unst_long = new_struct
    s1_feas_long = new_s1_feas
    obj_s1_long = new_obj
    for fam, ou, su, s1f, o1 in zip(
        families, obj_unst_long, struct_unst_long, s1_feas_long, obj_s1_long,
    ):
        s1_valid = _ref_s1_valid(s1f, o1)
        if fam == "OBJ":
            rv = s1_valid and not ou
        elif fam == "STRUCT":
            # struct_unstable can be None: treat as not unstable for the
            # purposes of reference_valid? Conservative: if undefined, the
            # cell has no reference partition to compare, so STRUCT
            # reference is NOT valid. Match the §8.3 n/a policy.
            if pd.isna(su):
                rv = False
            else:
                rv = s1_valid and not bool(su)
        elif fam == "PLAN_VALIDITY":
            rv = True
        elif fam == "SCHEDULE":
            rv = s1_valid
        else:
            rv = s1_valid
        new_ref_valid.append(bool(rv))
    out["reference_valid"] = new_ref_valid

    return out


def main() -> int:
    stage_a_wide = pd.read_parquet(STAGE_A_WIDE)
    stage_a_long = pd.read_parquet(STAGE_A_LONG)
    recoll = pd.read_parquet(RECOLL)
    print(f"Stage A wide rows:   {len(stage_a_wide)}")
    print(f"Stage A long rows:   {len(stage_a_long)}")
    print(f"Re-collected cells:  {len(recoll)}")

    wide = build_consolidated_wide(stage_a_wide, recoll)
    long_ = build_consolidated_long(stage_a_long, wide)

    print(f"Consolidated wide rows: {len(wide)}  (expected {len(stage_a_wide)})")
    print(f"Consolidated long rows: {len(long_)}  (expected {len(stage_a_long)})")
    assert len(wide) == len(stage_a_wide)
    assert len(long_) == len(stage_a_long)

    wide.to_parquet(OUT_WIDE, index=False)
    long_.to_parquet(OUT_LONG, index=False)
    print(f"Wrote {OUT_WIDE}  ({OUT_WIDE.stat().st_size} bytes)")
    print(f"Wrote {OUT_LONG}  ({OUT_LONG.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
