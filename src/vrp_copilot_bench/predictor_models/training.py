"""Out-of-fold training + prediction over the existing 5-fold layout.

For each ``(model, feature_set, claim_family)`` we fit a fresh pipeline
on the four training folds and predict on the held-out fold; concatenating
yields one OOF probability per row. The OOF frame is the input to all
downstream metric, threshold, calibration, and non-monotone-preservation
tables.

The fold assignments are reused from
``reports/predictor_baselines/fold_assignments.csv`` so the predictor
suite reports apples-to-apples with the baseline suite.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .features import FEATURE_SETS, build_feature_matrix
from .models import (
    MODEL_NAMES,
    expanded_feature_names,
    extract_coefficients_or_importance,
    make_model,
)


@dataclass(frozen=True)
class OOFResult:
    """Per-(model, feature_set, claim_family) out-of-fold artefact."""

    model: str
    feature_set: str
    claim_family: str
    rows: pd.DataFrame  # original cheap_df rows, OOF order
    probs: np.ndarray
    fold: np.ndarray
    feature_importance: pd.DataFrame


def _load_fold_assignments(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if not {"instance_id", "fold"}.issubset(df.columns):
        raise ValueError(f"fold assignment file {path} missing instance_id / fold")
    return df[["instance_id", "fold"]].copy()


def attach_folds(cheap_df: pd.DataFrame, fold_path: Path) -> pd.DataFrame:
    """Left-join ``fold`` onto the cheap-action eval frame."""
    folds = _load_fold_assignments(fold_path)
    out = cheap_df.merge(folds, on="instance_id", how="left")
    if out["fold"].isna().any():
        missing = out.loc[out["fold"].isna(), "instance_id"].unique()
        raise ValueError(
            f"{len(missing)} instances missing from fold map: {sorted(missing)[:5]}…"
        )
    out["fold"] = out["fold"].astype(int)
    return out


def _fold_iter(folds: np.ndarray) -> Iterable[tuple[int, np.ndarray, np.ndarray]]:
    for fold_id in sorted(np.unique(folds)):
        test = folds == fold_id
        yield int(fold_id), ~test, test


def _safe_predict_proba(pipeline, X: pd.DataFrame, classes_: np.ndarray) -> np.ndarray:
    """Return the column of ``predict_proba`` matching the positive class.

    A training fold can in principle be all-positive or all-negative,
    in which case ``predict_proba`` produces a single column. Guard that
    here so the OOF column for those folds is interpretable.
    """
    proba = pipeline.predict_proba(X)
    if proba.ndim == 1 or proba.shape[1] == 1:
        # Single-class training fold: predict the majority probability.
        single = classes_[0] if len(classes_) else 0
        return np.full(proba.shape[0], float(single == 1), dtype=float)
    pos_idx = int(np.where(classes_ == 1)[0][0]) if 1 in classes_ else 1
    return proba[:, pos_idx]


def train_oof(
    eval_df: pd.DataFrame,
    *,
    model_name: str,
    feature_set: str,
    claim_family: str,
) -> OOFResult:
    """Fit the model out-of-fold for one claim family.

    Returns row-aligned OOF probabilities plus a feature-importance
    summary averaged over the trained folds (so the report doesn't need
    to pick a single fold's coefficients arbitrarily).
    """
    fam_df = eval_df[eval_df["claim_family"] == claim_family].copy()
    fam_df = fam_df.dropna(subset=["sufficient_binary"]).reset_index(drop=True)
    if "fold" not in fam_df.columns:
        raise ValueError("eval_df must carry a 'fold' column (call attach_folds first)")

    X, num_cols, cat_cols = build_feature_matrix(fam_df, feature_set, claim_family)
    y = fam_df["sufficient_binary"].astype(int).to_numpy()
    folds = fam_df["fold"].to_numpy()

    oof = np.full(len(fam_df), np.nan, dtype=float)
    importances_per_fold: list[np.ndarray] = []
    importance_kind = "coef"

    for fold_id, train_mask, test_mask in _fold_iter(folds):
        pipeline = make_model(
            model_name,
            numeric_columns=num_cols,
            categorical_columns=cat_cols,
        )
        pipeline.fit(X.iloc[train_mask], y[train_mask])
        classes_ = getattr(
            pipeline.named_steps["clf"], "classes_", np.array([0, 1])
        )
        oof[test_mask] = _safe_predict_proba(pipeline, X.iloc[test_mask], classes_)
        kind, vals = extract_coefficients_or_importance(pipeline)
        importance_kind = kind
        importances_per_fold.append(vals)

    # Average importances across folds; align feature names with the
    # last-fold pipeline (categories are stable across folds because the
    # encoder has access to the full categorical vocabulary on each
    # fold, modulo absent values which OneHotEncoder pads with zeros).
    feature_names = expanded_feature_names(pipeline)
    importance_matrix = np.vstack(importances_per_fold)
    importance_mean = importance_matrix.mean(axis=0)
    importance_std = importance_matrix.std(axis=0)
    importance_df = pd.DataFrame(
        {
            "feature": feature_names,
            "kind": importance_kind,
            "value_mean": importance_mean,
            "value_std": importance_std,
        }
    )

    return OOFResult(
        model=model_name,
        feature_set=feature_set,
        claim_family=claim_family,
        rows=fam_df.reset_index(drop=True),
        probs=oof,
        fold=folds,
        feature_importance=importance_df,
    )


def train_all(
    eval_df: pd.DataFrame,
    *,
    models: Iterable[str] = MODEL_NAMES,
    feature_sets: Iterable[str] = tuple(FEATURE_SETS),
    claim_families: Iterable[str],
) -> list[OOFResult]:
    """Train every ``(model, feature_set, claim_family)`` combination."""
    results: list[OOFResult] = []
    for model in models:
        for fs in feature_sets:
            for cf in claim_families:
                results.append(
                    train_oof(
                        eval_df,
                        model_name=model,
                        feature_set=fs,
                        claim_family=cf,
                    )
                )
    return results


def oof_to_long_frame(results: Iterable[OOFResult]) -> pd.DataFrame:
    """Stack OOF probabilities into a long frame keyed by cell × claim × model × fs."""
    pieces: list[pd.DataFrame] = []
    for r in results:
        df = r.rows[
            ["instance_id", "perturbation_id", "perturbation_family",
             "claim_family", "instance_class", "action", "fold",
             "sufficient_binary", "action_feasible", "action_runtime_s"]
        ].copy()
        df["model"] = r.model
        df["feature_set"] = r.feature_set
        df["pred_proba"] = r.probs
        pieces.append(df)
    return pd.concat(pieces, ignore_index=True)
