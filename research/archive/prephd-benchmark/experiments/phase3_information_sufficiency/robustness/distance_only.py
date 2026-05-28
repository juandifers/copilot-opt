"""Section 3 — distance-perturbation-only clean cut.

Subset to ``regional_distance_inflation`` only. This is the cleanest
case for the thesis: the perturbation modifies edge costs but does not
affect capacity or demand, so the fixed solution always remains
feasible — every infeasibility we observed in Phase 3 came from
capacity reductions, not from this family.

Outputs:
  table_distance_only_reuse_direct.csv
  figure_distance_only_lambda_curve.png
"""
from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from experiments.phase3_information_sufficiency.robustness._action_table import (
    ACTIONS,
    CLAIM_FAMILIES,
    lambda_sweep,
)


CLAIM_LABEL = {
    "objective_resource_delta": "objective",
    "topk_route_ranking": "ranking",
    "assignment_structure": "structure",
}


def _share_per_label(s: pd.Series, label: str) -> float:
    if s.empty:
        return 0.0
    return 100.0 * (s == label).sum() / len(s)


def write_outputs(
    action_df: pd.DataFrame,
    out_dir: Path,
    *,
    lambdas: list[float],
) -> None:
    log = logging.getLogger("phase3.robustness.distance_only")
    sub = action_df[action_df["perturbation_family"] == "regional_distance_inflation"].copy()

    # ---- Table: reuse_direct error / difficulty share + best-action share by λ ----
    rd = sub[sub["action"] == "reuse_direct"]
    rd_rows = []
    for fam in CLAIM_FAMILIES:
        s = rd[(rd["claim_family"] == fam) & rd["loss"].notna()]
        if s.empty:
            continue
        rd_rows.append({
            "claim_family": fam,
            "n_cells": int(len(s)),
            "mean_loss": float(s["loss"].mean()),
            "median_loss": float(s["loss"].median()),
            "p90_loss": float(s["loss"].quantile(0.9)),
            "easy_pct": _share_per_label(s["difficulty_label"], "easy"),
            "medium_pct": _share_per_label(s["difficulty_label"], "medium"),
            "hard_pct": _share_per_label(s["difficulty_label"], "hard"),
            "infeasible_share_pct": float(((s["feasible_under_perturbation"] == False).mean()) * 100),
        })
    rd_table = pd.DataFrame(rd_rows)

    # Best-action shares by λ on the distance-only subset.
    curves = lambda_sweep(sub, lambdas=lambdas)
    share_rows = []
    for lam in lambdas:
        for fam in CLAIM_FAMILIES:
            ssub = curves[(curves["lambda"] == lam) & (curves["claim_family"] == fam)]
            if ssub.empty:
                continue
            shares = (ssub["best_action"].value_counts(normalize=True) * 100).to_dict()
            share_rows.append({
                "lambda": lam, "claim_family": fam, "n": int(len(ssub)),
                **{f"share_{a}": float(shares.get(a, 0.0)) for a in ACTIONS},
            })
    share_df = pd.DataFrame(share_rows)

    # Combine into one CSV with two sections labelled by 'kind'.
    rd_table.insert(0, "kind", "error_summary")
    share_df.insert(0, "kind", "share_by_lambda")
    combined = pd.concat([rd_table, share_df], ignore_index=True)
    combined.to_csv(out_dir / "table_distance_only_reuse_direct.csv", index=False)
    log.info("wrote table_distance_only_reuse_direct.csv (%d rows)", len(combined))

    # ---- Figure: best-action share vs λ for distance-only subset ----
    color_map = {
        "reuse_direct": "#1f78b4",
        "nearest_neighbor": "#ff7f00",
        "clarke_wright": "#6a3d9a",
        "pyvrp_10s": "#33a02c",
        "pyvrp_60s": "#e31a1c",
    }
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)
    for i, fam in enumerate(CLAIM_FAMILIES):
        ax = axes[i]
        ssub = share_df[share_df["claim_family"] == fam].sort_values("lambda")
        for a in ACTIONS:
            ax.plot(
                ssub["lambda"], ssub[f"share_{a}"],
                marker="o", linewidth=2, color=color_map[a], label=a,
            )
        ax.set_xscale("symlog", linthresh=1e-4)
        ax.set_title(f"{CLAIM_LABEL[fam]} (regional_distance only)")
        ax.set_xlabel("λ")
        ax.set_ylim(0, 100)
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        if i == 0:
            ax.set_ylabel("best-action share (%)")
    axes[-1].legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    fig.suptitle("Phase 3 robustness: distance-only λ curves "
                 "(no capacity perturbations, no infeasibility)")
    fig.tight_layout()
    fig.savefig(out_dir / "figure_distance_only_lambda_curve.png",
                dpi=140, bbox_inches="tight")
    plt.close(fig)
    log.info("wrote figure_distance_only_lambda_curve.png")
