"""Methodology metrics for the Homberger-200 probe.

The probe asks four design-level questions:

1. Does reference-anchored evaluation scale? 3-seed ARI ≥ 0.85 on most cells.
2. Does the 5-rung ladder remain operationally meaningful? Per-cell quality
   gap between pyvrp_10s and pyvrp_60s_reference widens vs Solomon-100.
3. Are sufficiency rates non-degenerate per (claim, perturbation) block?
4. Do non-monotone phenomena persist? STRUCT/SCHEDULE cheap=1 py10=0 cells.

Each question maps to one of the output CSVs below. The Stage A
``reference_struct_unstable`` flag and per-seed ARI columns are already
on the wide table, so no re-derivation is needed.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..predictor_baselines.data import CELL_KEYS, instance_class_from_id


#: Probe perturbation grid — for ordering tables consistently.
PROBE_GRID_IDS: tuple[str, ...] = (
    "TT_4", "TT_5", "TW_5", "TW_6", "ST_3", "ST_4", "OC_4", "OC_5",
)

#: Stage A perturbation IDs the probe's upper-half magnitudes match
#: closest, for the methodology-vs-Stage-A delta.
PROBE_TO_STAGE_A_NEAREST: dict[str, str] = {
    "TT_4": "TT_4",  # 1.30 — exact match
    "TT_5": "TT_4",  # 1.50 — Stage A's TT max is TT_4 (soft 1.30)
    "TW_5": "TW_2",  # 0.15 — closest Stage A TW magnitude is TW_2 (soft 0.10)
    "TW_6": "TW_2",  # 0.20 — same as above
    "ST_3": "ST_3",  # exact
    "ST_4": "ST_4",  # exact
    "OC_4": "OC_4",  # exact
    "OC_5": "OC_4",  # 0.25 — Stage A's OC max is OC_4 (0.20)
}


# ---------------------------------------------------------------------------
# Reference stability + methodology summary

def reference_stability_per_cell(
    wide_df: pd.DataFrame,
) -> pd.DataFrame:
    """One row per (instance_id, perturbation_id) — 3-seed ARI summary.

    The wide table has ``reference_ari_s1s2/s1s3/s2s3/min`` already, so
    we just deduplicate over actions (those columns are constant per
    cell × seed-pair).
    """
    keys = ["instance_id", "perturbation_id", "perturbation_family"]
    cols = keys + [
        "reference_ari_s1s2", "reference_ari_s1s3", "reference_ari_s2s3",
        "reference_ari_min", "reference_obj_unstable", "reference_struct_unstable",
        "reference_any_feasible", "reference_all_feasible",
        "reference_obj_best_feasible",
    ]
    cell = wide_df[cols].drop_duplicates(subset=keys).reset_index(drop=True)
    cell["reference_ari_mean"] = cell[
        ["reference_ari_s1s2", "reference_ari_s1s3", "reference_ari_s2s3"]
    ].mean(axis=1)
    cell["stable_at_0_85"] = (cell["reference_ari_min"] >= 0.85).astype(bool)
    cell["instance_class"] = cell["instance_id"].map(instance_class_from_id)
    return cell


def methodology_block_table(
    long_df: pd.DataFrame,
    wide_df: pd.DataFrame,
    stage_a_long_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Per (claim_family × perturbation_family) block summary.

    Columns:
      - n_cells, sufficiency_rate, cheap_feasible_rate
      - reference_ari_mean, reference_unstable_frac
      - sufficiency_rate_stage_a (matched perturbation IDs), delta_sufficiency
    """
    # Cheap-action rows only — sufficiency is defined on the cheap row.
    cheap_long = long_df[long_df["is_cheap_action"]].copy()
    cheap_long = cheap_long.dropna(subset=["sufficient_binary"])
    g = cheap_long.groupby(["claim_family", "perturbation_family"])
    rows: list[dict] = []
    for (cf, pf), sub in g:
        n = len(sub)
        suff_rate = float(sub["sufficient_binary"].mean())
        feasible_rate = float(sub["action_feasible"].astype(int).mean())
        # Per-cell reference stability for this block:
        cells = wide_df[wide_df["perturbation_family"] == pf][
            ["instance_id", "perturbation_id", "reference_ari_min",
             "reference_struct_unstable"]
        ].drop_duplicates(subset=["instance_id", "perturbation_id"])
        ari_mean = float(cells["reference_ari_min"].mean()) if len(cells) else float("nan")
        unstable_frac = float(cells["reference_struct_unstable"].mean()) if len(cells) else float("nan")

        row = {
            "claim_family": cf,
            "perturbation_family": pf,
            "n_cells": int(n),
            "sufficiency_rate": suff_rate,
            "cheap_feasible_rate": feasible_rate,
            "reference_ari_mean": ari_mean,
            "reference_unstable_frac": unstable_frac,
        }
        if stage_a_long_df is not None:
            stage_a_sub = stage_a_long_df[
                (stage_a_long_df["claim_family"] == cf)
                & (stage_a_long_df["perturbation_family"] == pf)
                & (stage_a_long_df["is_cheap_action"])
            ].dropna(subset=["sufficient_binary"])
            if not stage_a_sub.empty:
                row["sufficiency_rate_stage_a"] = float(stage_a_sub["sufficient_binary"].mean())
                row["delta_sufficiency"] = suff_rate - row["sufficiency_rate_stage_a"]
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["claim_family", "perturbation_family"]
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Non-monotone cells (cheap=1, py10=0) — STRUCT and SCHEDULE only.

def nonmonotone_cells(long_df: pd.DataFrame) -> pd.DataFrame:
    """Cells where cheap is sufficient but pyvrp_10s is not.

    Returns long frame with one row per (instance, perturbation, claim)
    that meets the criterion. Plus a summary count per (claim_family,
    perturbation_family).
    """
    cheap = (
        long_df[long_df["is_cheap_action"]]
        [list(CELL_KEYS) + ["perturbation_family", "sufficient_binary"]]
        .rename(columns={"sufficient_binary": "cheap_sufficient"})
    )
    py10 = (
        long_df[long_df["action"] == "pyvrp_10s"]
        [list(CELL_KEYS) + ["sufficient_binary"]]
        .rename(columns={"sufficient_binary": "py10_sufficient"})
    )
    joined = cheap.merge(py10, on=list(CELL_KEYS), how="left")
    nm = joined[
        (joined["cheap_sufficient"] == 1)
        & (joined["py10_sufficient"] == 0)
        & joined["claim_family"].isin(["STRUCT", "SCHEDULE"])
    ].copy()
    return nm.sort_values(list(CELL_KEYS)).reset_index(drop=True)


def nonmonotone_summary(nm_df: pd.DataFrame, total_long_df: pd.DataFrame) -> pd.DataFrame:
    """Per (claim_family × perturbation_family) non-monotone counts."""
    if nm_df.empty:
        return pd.DataFrame(columns=["claim_family", "perturbation_family",
                                     "n_nonmonotone", "n_total_cells",
                                     "nonmonotone_rate"])
    by = nm_df.groupby(["claim_family", "perturbation_family"]).size().rename("n_nonmonotone")
    cheap_total = (
        total_long_df[total_long_df["is_cheap_action"]]
        .dropna(subset=["sufficient_binary"])
        .groupby(["claim_family", "perturbation_family"]).size().rename("n_total_cells")
    )
    out = pd.concat([by, cheap_total], axis=1, join="outer").fillna(0).reset_index()
    out["n_nonmonotone"] = out["n_nonmonotone"].astype(int)
    out["n_total_cells"] = out["n_total_cells"].astype(int)
    out["nonmonotone_rate"] = np.where(
        out["n_total_cells"] > 0,
        out["n_nonmonotone"] / out["n_total_cells"], 0.0,
    )
    return out.sort_values(
        ["claim_family", "perturbation_family"]
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Rung quality gaps — per-cell final_obj differences between consecutive rungs.

#: Action ordering for rung-gap analysis. Cheap actions appear first;
#: pyvrp_60s_reference is the top of the ladder.
RUNG_ORDER: tuple[str, ...] = (
    "reuse_direct",
    "local_repair_insert",
    "construct_feasible",
    "pyvrp_10s",
    "pyvrp_60s_reference",
)


def rung_quality_gaps(wide_df: pd.DataFrame) -> pd.DataFrame:
    """Per (instance, perturbation) pairwise final_obj deltas between rungs.

    A wide row is keyed by (instance_id, perturbation_id, action). For
    each cell we compute Δ obj between (pyvrp_10s, pyvrp_60s_reference),
    (construct_feasible, pyvrp_10s), (reuse_direct, construct_feasible),
    and (reuse_direct, pyvrp_60s_reference) — the all-up reference gap.
    Only feasible rungs contribute to the comparison; infeasible rungs
    yield NaN for the relevant gap.
    """
    rows: list[dict] = []
    for (iid, pid), grp in wide_df.groupby(["instance_id", "perturbation_id"]):
        obj_by_action: dict[str, float] = {}
        feasible_by_action: dict[str, bool] = {}
        for _, r in grp.iterrows():
            obj_by_action[r["action"]] = float(r["action_obj"]) if r["action_feasible"] else float("nan")
            feasible_by_action[r["action"]] = bool(r["action_feasible"])
        rec = {
            "instance_id": iid,
            "perturbation_id": pid,
            "perturbation_family": grp["perturbation_family"].iloc[0],
        }
        for a in RUNG_ORDER:
            rec[f"obj_{a}"] = obj_by_action.get(a, float("nan"))
            rec[f"feas_{a}"] = feasible_by_action.get(a, False)
        # Pairwise relative gaps (next_rung_obj - this_rung_obj) / this_rung_obj.
        def _rel_gap(higher: str, lower: str) -> float:
            hi = obj_by_action.get(higher, float("nan"))
            lo = obj_by_action.get(lower, float("nan"))
            if not np.isfinite(hi) or not np.isfinite(lo) or lo <= 0:
                return float("nan")
            # Higher rung should reduce obj — express as fractional improvement
            # of "lower" relative to "higher": (lower - higher) / higher.
            return (lo - hi) / hi
        rec["rel_gap_pyvrp10s_to_pyvrp60s"] = _rel_gap("pyvrp_60s_reference", "pyvrp_10s")
        rec["rel_gap_construct_to_pyvrp10s"] = _rel_gap("pyvrp_10s", "construct_feasible")
        rec["rel_gap_reuse_to_construct"] = _rel_gap("construct_feasible", "reuse_direct")
        rec["rel_gap_reuse_to_pyvrp60s"] = _rel_gap("pyvrp_60s_reference", "reuse_direct")
        rows.append(rec)
    return pd.DataFrame(rows).sort_values(
        ["perturbation_family", "instance_id", "perturbation_id"]
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Methodology success criteria evaluation.

def evaluate_success_criteria(
    *,
    stability: pd.DataFrame,
    methodology_blocks: pd.DataFrame,
    rung_gaps: pd.DataFrame,
    nonmonotone: pd.DataFrame,
    predictor_eval: pd.DataFrame | None,
) -> pd.DataFrame:
    """Apply the 5 probe success criteria. Returns a long table of verdicts."""
    rows: list[dict] = []

    # 1. Reference stability: ≥70% cells with min-ARI ≥ 0.85.
    if len(stability) > 0:
        stable_frac = float(stability["stable_at_0_85"].mean())
        rows.append({
            "criterion": "1_reference_stability",
            "passes": stable_frac >= 0.70,
            "value": stable_frac,
            "threshold": 0.70,
            "note": f"{int(stability['stable_at_0_85'].sum())}/{len(stability)} cells with ARI_min ≥ 0.85",
        })

    # 2. Sufficiency rates non-degenerate: ≥12 of 16 (claim × pert) blocks
    #    have sufficiency in (0.10, 0.95).
    if not methodology_blocks.empty:
        in_band = methodology_blocks[
            (methodology_blocks["sufficiency_rate"] > 0.10)
            & (methodology_blocks["sufficiency_rate"] < 0.95)
        ]
        rows.append({
            "criterion": "2_sufficiency_non_degenerate",
            "passes": len(in_band) >= 12,
            "value": float(len(in_band)),
            "threshold": 12.0,
            "note": f"{len(in_band)}/{len(methodology_blocks)} (claim × pert) blocks in (0.10, 0.95)",
        })

    # 3. Rung quality gap measurable: median rel_gap_pyvrp10s_to_pyvrp60s ≥ 0.01 (1%).
    if not rung_gaps.empty:
        med_gap = float(rung_gaps["rel_gap_pyvrp10s_to_pyvrp60s"].median())
        rows.append({
            "criterion": "3_rung_gap_measurable",
            "passes": med_gap >= 0.01,
            "value": med_gap,
            "threshold": 0.01,
            "note": "median fractional obj improvement from pyvrp_10s to pyvrp_60s_reference",
        })

    # 4. Non-monotone cells appear: ≥3 STRUCT or SCHEDULE non-monotone cells.
    n_nm = int(len(nonmonotone))
    rows.append({
        "criterion": "4_nonmonotone_persists",
        "passes": n_nm >= 3,
        "value": float(n_nm),
        "threshold": 3.0,
        "note": f"{n_nm} STRUCT/SCHEDULE cells with cheap=1, py10=0",
    })

    # 5. Predictor doesn't collapse: HistGB / C_clean AUROC ≥ 0.65 on ≥2 of 4 families.
    if predictor_eval is not None and not predictor_eval.empty:
        sub = predictor_eval[
            (predictor_eval["model"] == "hist_gradient_boosting")
            & (predictor_eval["feature_set"] == "C_clean")
        ]
        n_above = int((sub["auroc_homberger"] >= 0.65).sum())
        rows.append({
            "criterion": "5_predictor_doesnt_collapse",
            "passes": n_above >= 2,
            "value": float(n_above),
            "threshold": 2.0,
            "note": f"{n_above}/4 claim families with HistGB/C_clean AUROC ≥ 0.65",
        })

    return pd.DataFrame(rows)


def write_methodology_outputs(
    wide_df: pd.DataFrame,
    long_df: pd.DataFrame,
    output_dir: Path,
    *,
    stage_a_long_df: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Compute + write the 4 methodology CSVs; return them keyed by name."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stability = reference_stability_per_cell(wide_df)
    blocks = methodology_block_table(long_df, wide_df, stage_a_long_df=stage_a_long_df)
    nm = nonmonotone_cells(long_df)
    nm_summary = nonmonotone_summary(nm, long_df)
    rungs = rung_quality_gaps(wide_df)

    stability.to_csv(output_dir / "homberger_probe_reference_stability.csv", index=False)
    blocks.to_csv(output_dir / "homberger_probe_methodology.csv", index=False)
    nm.to_csv(output_dir / "homberger_probe_nonmonotone.csv", index=False)
    nm_summary.to_csv(output_dir / "homberger_probe_nonmonotone_summary.csv", index=False)
    rungs.to_csv(output_dir / "homberger_probe_rung_gaps.csv", index=False)

    return {
        "stability": stability,
        "methodology": blocks,
        "nonmonotone": nm,
        "nonmonotone_summary": nm_summary,
        "rung_gaps": rungs,
    }
