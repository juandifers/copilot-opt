"""Section 2 — feasibility-penalized λ curves (3 variants).

For each variant we modify only the reuse_direct rows where
``feasible_under_perturbation == False``:

  V1 (penalty=1.0)        : reuse_direct loss := 1.0 (worst possible).
  V2 (penalty=0.5)        : reuse_direct loss := max(observed_loss, 0.5).
                            Half-credit interpretation — infeasible
                            answers are treated as half-correct at best.
  V3 (mark unanswerable)  : reuse_direct row removed entirely. The cell
                            still gets a best_action over the remaining
                            four actions.

We sweep the same λ grid as Phase 3's main run (read from phase3_config.yaml).

Outputs (under artifacts/robustness/):
  phase3_lambda_curves_feasibility_penalty_1.csv
  phase3_lambda_curves_feasibility_penalty_05.csv
  phase3_lambda_curves_unanswerable_infeasible.csv
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import yaml

from experiments.phase3_information_sufficiency.robustness._action_table import (
    lambda_sweep,
)


def _apply_penalty(action_df: pd.DataFrame, *, penalty: float) -> pd.DataFrame:
    """Replace reuse_direct's loss with ``max(loss, penalty)`` on infeasible cells."""
    df = action_df.copy()
    mask = (df["action"] == "reuse_direct") & (~df["feasible_under_perturbation"]) & df["loss"].notna()
    df.loc[mask, "loss"] = df.loc[mask, "loss"].clip(lower=penalty)
    return df


def _drop_infeasible_reuse(action_df: pd.DataFrame) -> pd.DataFrame:
    """Mark infeasible reuse_direct as unanswerable: drop those rows entirely."""
    df = action_df.copy()
    mask = (df["action"] == "reuse_direct") & (~df["feasible_under_perturbation"])
    return df[~mask].reset_index(drop=True)


def write_outputs(
    action_df: pd.DataFrame,
    out_dir: Path,
    *,
    lambdas: list[float],
) -> dict[str, Path]:
    log = logging.getLogger("phase3.robustness.feasibility_penalty")
    paths: dict[str, Path] = {}

    # V1 — penalty 1.0
    df_v1 = _apply_penalty(action_df, penalty=1.0)
    curves_v1 = lambda_sweep(df_v1, lambdas=lambdas)
    p = out_dir / "phase3_lambda_curves_feasibility_penalty_1.csv"
    curves_v1.to_csv(p, index=False)
    log.info("wrote %s (%d rows)", p.name, len(curves_v1))
    paths["penalty_1"] = p

    # V2 — penalty 0.5
    df_v05 = _apply_penalty(action_df, penalty=0.5)
    curves_v05 = lambda_sweep(df_v05, lambdas=lambdas)
    p = out_dir / "phase3_lambda_curves_feasibility_penalty_05.csv"
    curves_v05.to_csv(p, index=False)
    log.info("wrote %s (%d rows)", p.name, len(curves_v05))
    paths["penalty_05"] = p

    # V3 — drop infeasible reuse_direct
    df_unans = _drop_infeasible_reuse(action_df)
    curves_unans = lambda_sweep(df_unans, lambdas=lambdas)
    p = out_dir / "phase3_lambda_curves_unanswerable_infeasible.csv"
    curves_unans.to_csv(p, index=False)
    log.info("wrote %s (%d rows)", p.name, len(curves_unans))
    paths["unanswerable"] = p

    return paths


def share_table(curves_csv: Path) -> pd.DataFrame:
    """Return a wide table: lambda × claim_family with action share %."""
    df = pd.read_csv(curves_csv)
    rows = []
    for lam in sorted(df["lambda"].unique()):
        for fam in sorted(df["claim_family"].unique()):
            sub = df[(df["lambda"] == lam) & (df["claim_family"] == fam)]
            if sub.empty:
                continue
            shares = (sub["best_action"].value_counts(normalize=True) * 100).to_dict()
            rows.append({
                "lambda": lam, "claim_family": fam, "n": int(len(sub)),
                **{f"share_{a}": float(shares.get(a, 0.0))
                   for a in ("reuse_direct", "nearest_neighbor", "clarke_wright",
                             "pyvrp_10s", "pyvrp_60s")},
            })
    return pd.DataFrame(rows)
