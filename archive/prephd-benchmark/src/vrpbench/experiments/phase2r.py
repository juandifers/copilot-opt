"""Phase 2R difficulty-revision analysis.

Re-labels Phase 2 required corpus (n=210) with three independent claim-family
difficulty labels using frozen cutoffs:

  objective    : easy |gap|<0.05; medium 0.05<=|gap|<0.15; hard |gap|>=0.15
  assignment   : easy ARI>0.75;   medium 0.50<ARI<=0.75;   hard ARI<=0.50
  ranking      : easy overlap>=0.67; medium overlap==0.33; hard overlap==0.00
                 (rows excluded when either backend has <3 routes -> 'na')

Reads only Phase 2 outputs. Writes per_family_difficulty.csv and
cross_family_confusion.csv under data/processed/phase2r/. Does not rerun any
solver. Budget-consistency check is a separate runner (phase2r_budget.py).
"""
from __future__ import annotations

import argparse
import logging
import math
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


REQUIRED_FAMILIES = ("capacity_reduction", "regional_distance_inflation")


def label_objective(gap: float | None) -> str | None:
    if gap is None or (isinstance(gap, float) and math.isnan(gap)):
        return None
    g = abs(float(gap))
    if g < 0.05:
        return "easy"
    if g < 0.15:
        return "medium"
    return "hard"


def label_assignment(ari: float | None) -> str | None:
    if ari is None or (isinstance(ari, float) and math.isnan(ari)):
        return None
    a = float(ari)
    if a > 0.75:
        return "easy"
    if a > 0.50:
        return "medium"
    return "hard"


def label_ranking(
    overlap: float | None,
    routes_a: int | None,
    routes_b: int | None,
) -> str | None:
    """Ranking label or 'na' when fewer than three routes on either side."""
    if routes_a is None or routes_b is None:
        return "na"
    if int(routes_a) < 3 or int(routes_b) < 3:
        return "na"
    if overlap is None or (isinstance(overlap, float) and math.isnan(overlap)):
        return "na"
    o = float(overlap)
    # Cutoffs (frozen): easy >=0.67 (= 2 or 3 matches), medium ==0.33 (1 match),
    # hard ==0 (no matches). Overlap is intersection/3 so values are {0,1/3,2/3,1};
    # the "0.67" cutoff is the rounded form of 2/3, so 2/3 is bucketed easy per
    # the parenthetical "(2 or 3 of top 3 match)".
    if o >= 2 / 3 - 1e-9:
        return "easy"
    if abs(o - 1 / 3) < 1e-3:
        return "medium"
    if o == 0.0:
        return "hard"
    return "na"


def build_per_family_table(cmp_df: pd.DataFrame) -> pd.DataFrame:
    req = cmp_df[cmp_df["family"].isin(REQUIRED_FAMILIES)].copy()
    req = req.rename(columns={
        "adjusted_rand_assignment": "adjusted_rand",
    })
    req["objective_difficulty"] = req["objective_gap_rel"].apply(label_objective)
    req["assignment_difficulty"] = req["adjusted_rand"].apply(label_assignment)
    req["ranking_difficulty"] = [
        label_ranking(o, ra, rb) for o, ra, rb in zip(
            req["top_k_route_overlap"],
            req["route_count_a"],
            req["route_count_b"],
        )
    ]
    out_cols = [
        "instance_id", "family", "magnitude", "cheap_backend",
        "objective_gap_rel", "adjusted_rand", "top_k_route_overlap",
        "route_count_a", "route_count_b",
        "objective_difficulty", "assignment_difficulty", "ranking_difficulty",
    ]
    return req[out_cols].sort_values(
        ["instance_id", "family", "cheap_backend", "magnitude"]
    ).reset_index(drop=True)


def distribution_table(
    df: pd.DataFrame,
    label_col: str,
    family_label: str,
    include_na: bool = False,
) -> pd.DataFrame:
    """Stratify by (cheap_backend, perturbation family) and tally bands."""
    bands = ["easy", "medium", "hard"]
    rows = []
    for (cb, fam), sub in df.groupby(["cheap_backend", "family"]):
        n = len(sub)
        counts = {b: int((sub[label_col] == b).sum()) for b in bands}
        na_count = int((sub[label_col] == "na").sum())
        # For pct denominator use n minus na (ranking only excludes na).
        denom = n - na_count if include_na else n
        denom = denom if denom > 0 else 1
        row = {
            "claim_family": family_label,
            "cheap_backend": cb,
            "family": fam,
            "n": n,
            "easy": counts["easy"],
            "medium": counts["medium"],
            "hard": counts["hard"],
            "easy_pct": round(100.0 * counts["easy"] / denom, 2),
            "medium_pct": round(100.0 * counts["medium"] / denom, 2),
            "hard_pct": round(100.0 * counts["hard"] / denom, 2),
        }
        if include_na:
            row["na"] = na_count
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["cheap_backend", "family"]).reset_index(drop=True)


def confusion_long(
    df: pd.DataFrame,
    fam_a: str,
    col_a: str,
    fam_b: str,
    col_b: str,
) -> pd.DataFrame:
    """Long-form confusion matrix; 'na' is kept as its own row when present."""
    bands_a = sorted(df[col_a].dropna().unique().tolist())
    bands_b = sorted(df[col_b].dropna().unique().tolist())
    rows = []
    for ba in bands_a:
        for bb in bands_b:
            n = int(((df[col_a] == ba) & (df[col_b] == bb)).sum())
            rows.append({
                "family_a": fam_a,
                "family_b": fam_b,
                "label_a": ba,
                "label_b": bb,
                "n": n,
            })
    return pd.DataFrame(rows)


def perturbation_grid(
    df: pd.DataFrame,
    label_col: str,
    family_label: str,
) -> pd.DataFrame:
    rows = []
    for (fam, mag, cb), sub in df.groupby(["family", "magnitude", "cheap_backend"]):
        n = len(sub)
        easy = int((sub[label_col] == "easy").sum())
        med = int((sub[label_col] == "medium").sum())
        hard = int((sub[label_col] == "hard").sum())
        na = int((sub[label_col] == "na").sum())
        rows.append({
            "claim_family": family_label,
            "perturbation_family": fam,
            "magnitude": mag,
            "cheap_backend": cb,
            "n": n,
            "easy": easy,
            "medium": med,
            "hard": hard,
            "na": na,
        })
    return pd.DataFrame(rows).sort_values(
        ["perturbation_family", "magnitude", "cheap_backend"]
    ).reset_index(drop=True)


def compute_all(repo_root: Path) -> dict:
    cmp_path = repo_root / "data/processed/phase2/backend_comparisons.csv"
    cmp_df = pd.read_csv(cmp_path)

    pf = build_per_family_table(cmp_df)

    out_dir = repo_root / "data/processed/phase2r"
    out_dir.mkdir(parents=True, exist_ok=True)
    pf.to_csv(out_dir / "per_family_difficulty.csv", index=False)

    obj_dist = distribution_table(pf, "objective_difficulty", "objective")
    asn_dist = distribution_table(pf, "assignment_difficulty", "assignment")
    rnk_dist = distribution_table(pf, "ranking_difficulty", "ranking", include_na=True)

    conf_obj_asn = confusion_long(
        pf, "objective", "objective_difficulty", "assignment", "assignment_difficulty",
    )
    conf_obj_rnk = confusion_long(
        pf, "objective", "objective_difficulty", "ranking", "ranking_difficulty",
    )
    conf_asn_rnk = confusion_long(
        pf, "assignment", "assignment_difficulty", "ranking", "ranking_difficulty",
    )
    conf_all = pd.concat(
        [conf_obj_asn, conf_obj_rnk, conf_asn_rnk], ignore_index=True
    )
    conf_all.to_csv(out_dir / "cross_family_confusion.csv", index=False)

    obj_grid = perturbation_grid(pf, "objective_difficulty", "objective")
    asn_grid = perturbation_grid(pf, "assignment_difficulty", "assignment")
    rnk_grid = perturbation_grid(pf, "ranking_difficulty", "ranking")

    # Diagnostic numbers for the report.
    n_total = len(pf)
    diagnostics = {
        "n_total": n_total,
        "obj_easy": int((pf["objective_difficulty"] == "easy").sum()),
        "obj_medium": int((pf["objective_difficulty"] == "medium").sum()),
        "obj_hard": int((pf["objective_difficulty"] == "hard").sum()),
        "asn_easy": int((pf["assignment_difficulty"] == "easy").sum()),
        "asn_medium": int((pf["assignment_difficulty"] == "medium").sum()),
        "asn_hard": int((pf["assignment_difficulty"] == "hard").sum()),
        "rnk_easy": int((pf["ranking_difficulty"] == "easy").sum()),
        "rnk_medium": int((pf["ranking_difficulty"] == "medium").sum()),
        "rnk_hard": int((pf["ranking_difficulty"] == "hard").sum()),
        "rnk_na": int((pf["ranking_difficulty"] == "na").sum()),
        "max_ari": float(pf["adjusted_rand"].max()),
        "min_abs_gap": float(pf["objective_gap_rel"].abs().min()),
        "max_overlap": float(pf["top_k_route_overlap"].max()),
    }

    return {
        "per_family": pf,
        "distributions": {
            "objective": obj_dist,
            "assignment": asn_dist,
            "ranking": rnk_dist,
        },
        "confusions": {
            "obj_asn": conf_obj_asn,
            "obj_rnk": conf_obj_rnk,
            "asn_rnk": conf_asn_rnk,
        },
        "grids": {
            "objective": obj_grid,
            "assignment": asn_grid,
            "ranking": rnk_grid,
        },
        "diagnostics": diagnostics,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    out = compute_all(Path(args.repo_root).resolve())
    pf = out["per_family"]
    diag = out["diagnostics"]
    print(f"per_family rows: {len(pf)}")
    print("diagnostics:", diag)


if __name__ == "__main__":
    main()
