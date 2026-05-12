"""Section 4 — capacity-perturbation-only with feasibility.

Subset to ``capacity_reduction``. Splits the reuse_direct results by
``feasible_under_perturbation`` per magnitude, and recomputes the
λ-curve under the penalty=1.0 variant (the strictest interpretation).

Outputs:
  table_capacity_reduction_feasibility_by_magnitude.csv
  figure_capacity_reduction_feasibility_penalized_lambda.png
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
from experiments.phase3_information_sufficiency.robustness.feasibility_penalty import (
    _apply_penalty,
)


CLAIM_LABEL = {
    "objective_resource_delta": "objective",
    "topk_route_ranking": "ranking",
    "assignment_structure": "structure",
}


def write_outputs(
    action_df: pd.DataFrame,
    out_dir: Path,
    *,
    lambdas: list[float],
) -> None:
    log = logging.getLogger("phase3.robustness.capacity_only")
    sub = action_df[action_df["perturbation_family"] == "capacity_reduction"].copy()

    # ---- Per-magnitude feasibility + objective error split ----
    rd_obj = sub[(sub["action"] == "reuse_direct")
                 & (sub["claim_family"] == "objective_resource_delta")
                 & sub["loss"].notna()]
    rows = []
    for mag in sorted(rd_obj["perturbation_magnitude"].unique()):
        smag = rd_obj[rd_obj["perturbation_magnitude"] == mag]
        feas = smag[smag["feasible_under_perturbation"]]
        infeas = smag[~smag["feasible_under_perturbation"]]
        rows.append({
            "magnitude": float(mag),
            "n_cells": int(len(smag)),
            "infeasible_share_pct": float((~smag["feasible_under_perturbation"]).mean() * 100),
            "n_feasible": int(len(feas)),
            "feasible_mean_loss": float(feas["loss"].mean()) if len(feas) else None,
            "feasible_median_loss": float(feas["loss"].median()) if len(feas) else None,
            "feasible_easy_pct": float(((feas["difficulty_label"] == "easy").mean()) * 100) if len(feas) else None,
            "feasible_hard_pct": float(((feas["difficulty_label"] == "hard").mean()) * 100) if len(feas) else None,
            "n_infeasible": int(len(infeas)),
            "infeasible_mean_loss": float(infeas["loss"].mean()) if len(infeas) else None,
            "infeasible_median_loss": float(infeas["loss"].median()) if len(infeas) else None,
            "infeasible_easy_pct": float(((infeas["difficulty_label"] == "easy").mean()) * 100) if len(infeas) else None,
            "infeasible_hard_pct": float(((infeas["difficulty_label"] == "hard").mean()) * 100) if len(infeas) else None,
            "mean_max_overload": float(infeas["max_overload"].mean()) if len(infeas) else None,
        })

    # ---- Best action under penalty=1.0 (most strict) ----
    sub_pen = _apply_penalty(sub, penalty=1.0)
    curves_pen = lambda_sweep(sub_pen, lambdas=lambdas)
    share_rows = []
    for lam in lambdas:
        for fam in CLAIM_FAMILIES:
            ssub = curves_pen[(curves_pen["lambda"] == lam) & (curves_pen["claim_family"] == fam)]
            if ssub.empty:
                continue
            shares = (ssub["best_action"].value_counts(normalize=True) * 100).to_dict()
            share_rows.append({
                "lambda": lam, "claim_family": fam, "n": int(len(ssub)),
                **{f"share_{a}": float(shares.get(a, 0.0)) for a in ACTIONS},
            })

    feas_table = pd.DataFrame(rows)
    pen_share = pd.DataFrame(share_rows)
    feas_table.insert(0, "kind", "feasibility_by_magnitude")
    pen_share.insert(0, "kind", "share_by_lambda_penalty1")
    combined = pd.concat([feas_table, pen_share], ignore_index=True)
    combined.to_csv(
        out_dir / "table_capacity_reduction_feasibility_by_magnitude.csv",
        index=False,
    )
    log.info("wrote table_capacity_reduction_feasibility_by_magnitude.csv (%d rows)",
             len(combined))

    # ---- Figure: λ curves under penalty=1.0 on capacity-only subset ----
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
        ssub = pen_share[pen_share["claim_family"] == fam].sort_values("lambda")
        for a in ACTIONS:
            ax.plot(
                ssub["lambda"], ssub[f"share_{a}"],
                marker="o", linewidth=2, color=color_map[a], label=a,
            )
        ax.set_xscale("symlog", linthresh=1e-4)
        ax.set_title(f"{CLAIM_LABEL[fam]} (capacity_reduction, penalty=1.0)")
        ax.set_xlabel("λ")
        ax.set_ylim(0, 100)
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        if i == 0:
            ax.set_ylabel("best-action share (%)")
    axes[-1].legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    fig.suptitle("Phase 3 robustness: capacity-only λ curves under "
                 "infeasibility penalty=1.0")
    fig.tight_layout()
    fig.savefig(out_dir / "figure_capacity_reduction_feasibility_penalized_lambda.png",
                dpi=140, bbox_inches="tight")
    plt.close(fig)
    log.info("wrote figure_capacity_reduction_feasibility_penalized_lambda.png")
