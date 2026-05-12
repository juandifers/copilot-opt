"""Phase 3 plots and tables.

Reads:
  artifacts/phase3_reuse_direct_results.csv
  artifacts/phase3_estimation_results.csv
  artifacts/phase3_lambda_curves.csv

Writes (under artifacts/):
  table_1_reuse_direct_by_claim_family.csv
  table_2_estimation_by_claim_family.csv
  table_3_lambda_action_shares.csv
  figure_1_reuse_vs_estimation_errors.png
  figure_2_lambda_curves_by_claim_family.png
  figure_3_best_action_heatmap.png

The plots use matplotlib's default style — no seaborn — so they render
without extra deps. Each plot saves to PNG (not displayed).
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display backend in headless CI / scripts
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402


CLAIM_FAMILIES = (
    "objective_resource_delta",
    "topk_route_ranking",
    "assignment_structure",
)
CLAIM_LABEL = {
    "objective_resource_delta": "objective",
    "topk_route_ranking": "ranking",
    "assignment_structure": "structure",
}
ACTIONS = ("reuse_direct", "nearest_neighbor", "clarke_wright", "pyvrp_10s", "pyvrp_60s")


def make_table_1(reuse_csv: Path, out: Path) -> None:
    df = pd.read_csv(reuse_csv)
    rows: list[dict] = []
    for fam in CLAIM_FAMILIES:
        sub = df[(df["claim_family"] == fam) & df["error"].notna()]
        if sub.empty:
            continue
        # By perturbation_family.
        for pfam in sorted(sub["perturbation_family"].unique()):
            ssub = sub[sub["perturbation_family"] == pfam]
            labels = ssub["difficulty_label"].fillna("unknown").value_counts(normalize=True) * 100
            rows.append({
                "claim_family": fam,
                "perturbation_family": pfam,
                "n": len(ssub),
                "mean_error": float(ssub["error"].mean()),
                "median_error": float(ssub["error"].median()),
                "easy_pct": float(labels.get("easy", 0.0)),
                "medium_pct": float(labels.get("medium", 0.0)),
                "hard_pct": float(labels.get("hard", 0.0)),
                "infeasible_share": float((ssub["feasible_under_perturbation"] == False).mean()),
            })
    pd.DataFrame(rows).to_csv(out, index=False)


def make_table_2(estimation_csv: Path, out: Path) -> None:
    df = pd.read_csv(estimation_csv)
    rows: list[dict] = []
    for action in df["action"].unique().tolist():
        for fam in CLAIM_FAMILIES:
            sub = df[(df["action"] == action) & (df["claim_family"] == fam) & df["error"].notna()]
            if sub.empty:
                continue
            labels = sub["difficulty_label"].fillna("unknown").value_counts(normalize=True) * 100
            rows.append({
                "action": action,
                "claim_family": fam,
                "n": len(sub),
                "mean_error": float(sub["error"].mean()),
                "median_error": float(sub["error"].median()),
                "p90_error": float(sub["error"].quantile(0.9)),
                "easy_pct": float(labels.get("easy", 0.0)),
                "medium_pct": float(labels.get("medium", 0.0)),
                "hard_pct": float(labels.get("hard", 0.0)),
                "mean_runtime_sec": float(sub["runtime_sec"].mean()),
                "median_runtime_sec": float(sub["runtime_sec"].median()),
            })
    pd.DataFrame(rows).to_csv(out, index=False)


def make_table_3(curves_csv: Path, out: Path) -> None:
    df = pd.read_csv(curves_csv)
    rows: list[dict] = []
    for lam in sorted(df["lambda"].unique()):
        for fam in CLAIM_FAMILIES:
            sub = df[(df["lambda"] == lam) & (df["claim_family"] == fam)]
            if sub.empty:
                continue
            shares = (sub["best_action"].value_counts(normalize=True) * 100).to_dict()
            rows.append({
                "lambda": lam,
                "claim_family": fam,
                "n": len(sub),
                **{f"share_{a}": float(shares.get(a, 0.0)) for a in ACTIONS},
                "mean_objective": float(sub["objective_value"].mean()),
            })
    pd.DataFrame(rows).to_csv(out, index=False)


def figure_1(estimation_csv: Path, out: Path) -> None:
    """Boxplot: claim error distribution per (action, claim_family).

    Three vertical panels for the three claim families. Within each panel,
    boxplots side-by-side for the cheap-estimation actions plus reuse_direct.
    PyVRP 10s and 60s are excluded from this figure — they're shown in the
    lambda curves instead.
    """
    df = pd.read_csv(estimation_csv)
    show_actions = ["reuse_direct", "nearest_neighbor", "clarke_wright"]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=False)
    for i, fam in enumerate(CLAIM_FAMILIES):
        ax = axes[i]
        data = []
        labels = []
        for a in show_actions:
            sub = df[(df["action"] == a) & (df["claim_family"] == fam)]["error"].dropna()
            data.append(sub.tolist() if not sub.empty else [0.0])
            labels.append(a.replace("_", "\n"))
        bp = ax.boxplot(data, tick_labels=labels, showmeans=True, patch_artist=True)
        for patch, color in zip(bp["boxes"], ("#bdd7e7", "#fdbe85", "#cab2d6")):
            patch.set_facecolor(color)
        ax.set_title(f"{CLAIM_LABEL[fam]} claim error")
        ax.set_ylabel("claim error (lower is better)")
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        ax.set_ylim(bottom=0.0)
    fig.suptitle("Phase 3 Exp 2: per-claim-family errors of cheap actions vs PyVRP 60s reference")
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def figure_2(curves_csv: Path, out: Path) -> None:
    """Best-action share as a function of lambda, per claim family."""
    df = pd.read_csv(curves_csv)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)

    color_map = {
        "reuse_direct": "#1f78b4",
        "nearest_neighbor": "#ff7f00",
        "clarke_wright": "#6a3d9a",
        "pyvrp_10s": "#33a02c",
        "pyvrp_60s": "#e31a1c",
    }

    lambdas = sorted(df["lambda"].unique())
    for i, fam in enumerate(CLAIM_FAMILIES):
        ax = axes[i]
        # Build share[lambda][action]
        for a in ACTIONS:
            ys = []
            for lam in lambdas:
                sub = df[(df["lambda"] == lam) & (df["claim_family"] == fam)]
                if sub.empty:
                    ys.append(np.nan)
                else:
                    ys.append((sub["best_action"] == a).mean() * 100.0)
            ax.plot(
                lambdas, ys,
                marker="o", linewidth=2, color=color_map[a], label=a,
            )
        ax.set_xscale("symlog", linthresh=1e-4)
        ax.set_title(f"{CLAIM_LABEL[fam]} claim")
        ax.set_xlabel("λ (compute penalty)")
        ax.set_ylim(0, 100)
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        if i == 0:
            ax.set_ylabel("best-action share (%)")
    axes[-1].legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    fig.suptitle("Phase 3 Exp 3: best-action share by λ (loss + λ·runtime)")
    fig.tight_layout()
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)


def figure_3(curves_csv: Path, out: Path) -> None:
    """Heatmap of best action by (perturbation magnitude × lambda),
    one panel per claim family. Color-coded by action."""
    df = pd.read_csv(curves_csv)
    lambdas = sorted(df["lambda"].unique())

    # Build perturbation×magnitude axis
    df["pert_label"] = (
        df["perturbation_family"].astype(str) + "@" +
        df["perturbation_magnitude"].astype(str)
    )
    pert_labels = sorted(df["pert_label"].unique(),
                         key=lambda s: (s.split("@")[0], float(s.split("@")[1])))

    # Map actions to integer codes for imshow.
    action_to_code = {a: i for i, a in enumerate(ACTIONS)}
    cmap = matplotlib.colors.ListedColormap([
        "#1f78b4",  # reuse_direct
        "#ff7f00",  # nearest_neighbor
        "#6a3d9a",  # clarke_wright
        "#33a02c",  # pyvrp_10s
        "#e31a1c",  # pyvrp_60s
    ])

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.5), sharey=True)
    for i, fam in enumerate(CLAIM_FAMILIES):
        ax = axes[i]
        # For each (pert, lambda) the modal best_action across instances.
        grid = np.full((len(pert_labels), len(lambdas)), np.nan)
        for r, pl in enumerate(pert_labels):
            for c, lam in enumerate(lambdas):
                sub = df[(df["lambda"] == lam) & (df["claim_family"] == fam) & (df["pert_label"] == pl)]
                if sub.empty:
                    continue
                modal = sub["best_action"].mode()
                if modal.empty:
                    continue
                grid[r, c] = action_to_code[modal.iloc[0]]
        ax.imshow(grid, aspect="auto", cmap=cmap, vmin=-0.5, vmax=len(ACTIONS) - 0.5,
                  interpolation="nearest")
        ax.set_xticks(range(len(lambdas)))
        ax.set_xticklabels([f"{x:g}" for x in lambdas], rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(len(pert_labels)))
        if i == 0:
            ax.set_yticklabels(pert_labels, fontsize=8)
        ax.set_title(f"{CLAIM_LABEL[fam]} claim — modal best action")
        ax.set_xlabel("λ")
    # Build a custom legend for the actions.
    handles = [plt.Rectangle((0, 0), 1, 1, color=cmap(action_to_code[a])) for a in ACTIONS]
    fig.legend(handles, ACTIONS, loc="center right", bbox_to_anchor=(1.0, 0.5),
               fontsize=8, frameon=True)
    fig.suptitle("Phase 3 Exp 3: modal best action over instances")
    fig.tight_layout(rect=(0, 0, 0.85, 1.0))
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("phase3.plots")

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--config",
        default="experiments/phase3_information_sufficiency/phase3_config.yaml",
    )
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()

    repo = Path(args.repo_root).resolve()
    cfg = yaml.safe_load(Path(args.config).read_text())
    out_dir = repo / cfg["outputs"]["results_dir"]

    reuse = out_dir / cfg["outputs"]["reuse_direct_results_csv"]
    estimation = out_dir / cfg["outputs"]["estimation_results_csv"]
    curves = out_dir / cfg["outputs"]["lambda_curves_csv"]

    make_table_1(reuse, out_dir / cfg["outputs"]["table_1"])
    make_table_2(estimation, out_dir / cfg["outputs"]["table_2"])
    make_table_3(curves, out_dir / cfg["outputs"]["table_3"])
    log.info("tables written to %s", out_dir)

    figure_1(estimation, out_dir / cfg["outputs"]["figure_1"])
    figure_2(curves, out_dir / cfg["outputs"]["figure_2"])
    figure_3(curves, out_dir / cfg["outputs"]["figure_3"])
    log.info("figures written to %s", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
