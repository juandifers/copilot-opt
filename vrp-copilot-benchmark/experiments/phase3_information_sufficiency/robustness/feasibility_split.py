"""Section 1 — split reuse_direct results by feasibility.

Outputs (under artifacts/robustness/):
  phase3_reuse_direct_feasibility_split.csv    long-form per-cell rows
  table_reuse_direct_objective_feasible_vs_infeasible.csv   summary

Long form: one row per (instance × scenario × claim) for the reuse_direct
action. Summary: aggregate by (claim_family × perturbation_family ×
feasible_under_perturbation).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from experiments.phase3_information_sufficiency.robustness._action_table import (
    CLAIM_FAMILIES,
)


def _label_share(s: pd.Series, label: str) -> float:
    if s.empty:
        return 0.0
    return 100.0 * (s == label).sum() / len(s)


def write_outputs(action_df: pd.DataFrame, out_dir: Path) -> None:
    log = logging.getLogger("phase3.robustness.feasibility_split")
    rd = action_df[action_df["action"] == "reuse_direct"].copy()

    # Long form keeps every cell × claim row.
    long_cols = [
        "instance_id", "scenario_id", "perturbation_family",
        "perturbation_magnitude", "claim_family",
        "feasible_under_perturbation", "loss", "difficulty_label",
        "max_overload", "candidate_status",
    ]
    long_df = rd[long_cols].copy()
    long_df.to_csv(out_dir / "phase3_reuse_direct_feasibility_split.csv", index=False)
    log.info("wrote phase3_reuse_direct_feasibility_split.csv (%d rows)", len(long_df))

    # Summary: by claim × perturbation_family × feasibility.
    summary_rows: list[dict] = []
    for fam in CLAIM_FAMILIES:
        for pfam in sorted(rd["perturbation_family"].unique()):
            for feasible in (True, False):
                sub = rd[(rd["claim_family"] == fam)
                         & (rd["perturbation_family"] == pfam)
                         & (rd["feasible_under_perturbation"] == feasible)
                         & rd["loss"].notna()]
                if sub.empty:
                    summary_rows.append({
                        "claim_family": fam, "perturbation_family": pfam,
                        "feasible": feasible, "n": 0,
                        "mean_loss": None, "median_loss": None, "p90_loss": None,
                        "easy_pct": None, "medium_pct": None, "hard_pct": None,
                    })
                    continue
                summary_rows.append({
                    "claim_family": fam,
                    "perturbation_family": pfam,
                    "feasible": feasible,
                    "n": int(len(sub)),
                    "mean_loss": float(sub["loss"].mean()),
                    "median_loss": float(sub["loss"].median()),
                    "p90_loss": float(sub["loss"].quantile(0.9)),
                    "easy_pct": _label_share(sub["difficulty_label"], "easy"),
                    "medium_pct": _label_share(sub["difficulty_label"], "medium"),
                    "hard_pct": _label_share(sub["difficulty_label"], "hard"),
                })
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(
        out_dir / "table_reuse_direct_objective_feasible_vs_infeasible.csv",
        index=False,
    )
    log.info("wrote table_reuse_direct_objective_feasible_vs_infeasible.csv (%d rows)",
             len(summary))

    # Quick-glance numbers.
    obj = rd[(rd["claim_family"] == "objective_resource_delta") & rd["loss"].notna()]
    if not obj.empty:
        feas = obj[obj["feasible_under_perturbation"]]["loss"]
        infeas = obj[~obj["feasible_under_perturbation"]]["loss"]
        log.info(
            "reuse_direct OBJECTIVE: feasible n=%d mean=%.4f easy_share=%.1f%% | infeasible n=%d mean=%.4f easy_share=%.1f%%",
            len(feas),
            float(feas.mean()) if len(feas) else float("nan"),
            _label_share(obj.loc[obj["feasible_under_perturbation"], "difficulty_label"], "easy"),
            len(infeas),
            float(infeas.mean()) if len(infeas) else float("nan"),
            _label_share(obj.loc[~obj["feasible_under_perturbation"], "difficulty_label"], "easy"),
        )
