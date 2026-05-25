"""Zero-shot evaluation of the Stage A learned predictors on Homberger cells.

The Run 2 predictors are trained on the Solomon-100 Stage A cells; we
re-fit them on the full Stage A cheap_df (no fold split) and score the
Homberger cheap rows. This is exactly the pattern the escalation probe
uses — see ``predictor_models.runner._escalation_probe_eval``. We
broaden it to cover the deployment-relevant (model, feature_set)
combinations and add a threshold sweep so the report can quote routing
metrics, not just classifier AUROC.

Per the probe spec we skip ``logistic_regression_platt`` (already shown
to underperform on Stage A) and ``A_categorical`` (uninformative for
the probe's interpretability question).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

from ..predictor_baselines.data import (
    CLAIM_FAMILIES,
    build_cheap_eval_frame,
    build_escalation_frame,
    instance_class_from_id,
    load_long_table,
)
from ..predictor_models.evaluation import (
    ThresholdConfig,
    threshold_sweep,
)
from ..predictor_models.features import (
    build_feature_matrix,
    perturbation_magnitude,
)
from ..predictor_models.models import make_model


#: (model, feature_set) combos to score zero-shot. Skips Platt LR
#: (calibration degrades Stage A non-monotone preservation) and the
#: A_categorical feature set (uninformative on Homberger since it
#: encodes Stage A's perturbation grid, not the probe's).
PROBE_PREDICTORS: tuple[tuple[str, str], ...] = (
    ("hist_gradient_boosting", "C_clean"),
    ("hist_gradient_boosting", "B_pre_cheap"),
    ("decision_tree", "C_clean"),
    ("logistic_regression", "C_clean"),
)


def _train_final_pipeline(
    cheap_df: pd.DataFrame,
    *,
    model_name: str,
    feature_set: str,
    claim_family: str,
):
    """Fit one (model, feature_set, claim_family) pipeline on full Stage A."""
    fam_df = cheap_df[cheap_df["claim_family"] == claim_family].copy()
    fam_df = fam_df.dropna(subset=["sufficient_binary"]).reset_index(drop=True)
    X, num_cols, cat_cols = build_feature_matrix(fam_df, feature_set, claim_family)
    y = fam_df["sufficient_binary"].astype(int).to_numpy()
    pipe = make_model(model_name, numeric_columns=num_cols, categorical_columns=cat_cols)
    pipe.fit(X, y)
    return pipe


def _safe_pos_proba(pipe, X) -> np.ndarray:
    """Probability for class 1, NaN if the pipeline degenerated."""
    proba = pipe.predict_proba(X)
    if proba.ndim == 1 or proba.shape[1] == 1:
        return np.full(len(X), float("nan"), dtype=float)
    classes_ = getattr(pipe.named_steps["clf"], "classes_", np.array([0, 1]))
    pos_idx = int(np.where(classes_ == 1)[0][0]) if 1 in classes_ else 1
    return proba[:, pos_idx]


def _prepare_homberger_cheap(long_df: pd.DataFrame) -> pd.DataFrame:
    """Filter to cheap-action rows, drop NaN labels, attach helpers."""
    cheap = build_cheap_eval_frame(long_df, keep_nan_labels=True)
    cheap = cheap.dropna(subset=["sufficient_binary"]).reset_index(drop=True)
    if "instance_class" not in cheap.columns:
        cheap["instance_class"] = cheap["instance_id"].map(instance_class_from_id)
    if "perturbation_magnitude" not in cheap.columns:
        cheap["perturbation_magnitude"] = cheap["perturbation_id"].map(perturbation_magnitude)
    # Many predictors expect categorical "instance_class" to take one of
    # {C, R, RC, ?}. Homberger uses the same Solomon-letter convention, so
    # ``instance_class_from_id`` does the right thing.
    return cheap


def predictor_zero_shot_eval(
    stage_a_long_parquet: Path,
    homberger_long_parquet: Path,
    *,
    predictors: Iterable[tuple[str, str]] = PROBE_PREDICTORS,
    threshold_grid: tuple[float, ...] = ThresholdConfig().grid,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Train on Stage A, score on Homberger.

    Returns three frames:
      - ``metrics``: per (model, feature_set, claim_family) AUROC/AUPRC/Brier
        on Homberger cheap-action rows.
      - ``oof_long``: cell-level pred_proba per (model, feature_set), in the
        same long-form schema the runner produces.
      - ``sweep``: threshold sweep — final_correctness, avg compute, etc.
    """
    stage_a_long = load_long_table(stage_a_long_parquet)
    stage_a_cheap = build_cheap_eval_frame(stage_a_long, keep_nan_labels=True)
    stage_a_cheap = stage_a_cheap.dropna(subset=["sufficient_binary"]).reset_index(drop=True)

    homberger_long = load_long_table(homberger_long_parquet)
    homberger_cheap = _prepare_homberger_cheap(homberger_long)
    pyvrp_10s_df = build_escalation_frame(homberger_long, "pyvrp_10s")

    metric_rows: list[dict] = []
    oof_pieces: list[pd.DataFrame] = []
    for model_name, feature_set in predictors:
        for cf in CLAIM_FAMILIES:
            fam_probe = homberger_cheap[homberger_cheap["claim_family"] == cf]
            if len(fam_probe) < 5 or fam_probe["sufficient_binary"].nunique() < 2:
                continue
            pipe = _train_final_pipeline(
                stage_a_cheap, model_name=model_name,
                feature_set=feature_set, claim_family=cf,
            )
            X_probe, _, _ = build_feature_matrix(fam_probe, feature_set, cf)
            p = _safe_pos_proba(pipe, X_probe)
            y = fam_probe["sufficient_binary"].astype(int).to_numpy()
            try:
                auroc = float(roc_auc_score(y, p))
            except ValueError:
                auroc = float("nan")
            try:
                auprc = float(average_precision_score(y, p))
            except ValueError:
                auprc = float("nan")
            brier = float(brier_score_loss(y, p))
            metric_rows.append(
                {
                    "model": model_name,
                    "feature_set": feature_set,
                    "claim_family": cf,
                    "n_rows": int(len(fam_probe)),
                    "pos_rate": float(y.mean()),
                    "auroc_homberger": auroc,
                    "auprc_homberger": auprc,
                    "brier_homberger": brier,
                }
            )
            oof = fam_probe[
                ["instance_id", "perturbation_id", "perturbation_family",
                 "claim_family", "instance_class", "action",
                 "sufficient_binary", "action_feasible", "action_runtime_s"]
            ].copy()
            oof["fold"] = 0  # zero-shot — no fold; downstream code expects the column
            oof["model"] = model_name
            oof["feature_set"] = feature_set
            oof["pred_proba"] = p
            oof_pieces.append(oof)

    if metric_rows:
        metrics = pd.DataFrame(metric_rows).sort_values(
            ["model", "feature_set", "claim_family"]
        ).reset_index(drop=True)
    else:
        metrics = pd.DataFrame(columns=[
            "model", "feature_set", "claim_family", "n_rows", "pos_rate",
            "auroc_homberger", "auprc_homberger", "brier_homberger",
        ])
    oof_long = pd.concat(oof_pieces, ignore_index=True) if oof_pieces else pd.DataFrame()

    if not oof_long.empty:
        sweep = threshold_sweep(oof_long, pyvrp_10s_df, grid=threshold_grid)
    else:
        sweep = pd.DataFrame()

    return metrics, oof_long, sweep


def write_predictor_eval_outputs(
    stage_a_long_parquet: Path,
    homberger_long_parquet: Path,
    output_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run eval and persist CSVs. Returns the three frames."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics, oof_long, sweep = predictor_zero_shot_eval(
        stage_a_long_parquet, homberger_long_parquet,
    )
    metrics.to_csv(output_dir / "homberger_probe_predictor_eval.csv", index=False)
    if not oof_long.empty:
        oof_long.to_csv(output_dir / "homberger_probe_predictor_oof.csv", index=False)
    if not sweep.empty:
        sweep.to_csv(output_dir / "homberger_probe_predictor_threshold_sweep.csv", index=False)
    return metrics, oof_long, sweep
