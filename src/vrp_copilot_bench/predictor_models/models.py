"""Model factories: regularised LR, Platt-calibrated LR, HistGB, decision tree.

All four are wrapped in an sklearn :class:`Pipeline` whose first stage
is a :class:`ColumnTransformer` that imputes numerics with the median
and one-hot encodes categoricals. The hyperparameters are deliberately
conservative — the per-claim training sets are ~889 rows.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

#: Canonical ordering of trained models. Run 2 swaps isotonic for Platt
#: (``logistic_regression_platt``) and adds a shallow decision tree for
#: interpretability.
MODEL_NAMES: tuple[str, ...] = (
    "logistic_regression",
    "logistic_regression_platt",
    "hist_gradient_boosting",
    "decision_tree",
)


def _make_preprocessor(
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    *,
    scale: bool,
) -> ColumnTransformer:
    numeric_steps: list[tuple[str, object]] = [
        ("impute", SimpleImputer(strategy="median")),
    ]
    if scale:
        numeric_steps.append(("scale", StandardScaler()))
    numeric_pipeline = Pipeline(numeric_steps)
    categorical_pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="most_frequent")),
            (
                "encode",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            ),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, list(numeric_columns)),
            ("cat", categorical_pipeline, list(categorical_columns)),
        ],
        remainder="drop",
    )


def _make_logistic_regression(
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
) -> Pipeline:
    pre = _make_preprocessor(numeric_columns, categorical_columns, scale=True)
    clf = LogisticRegression(
        penalty="l2",
        C=1.0,
        solver="lbfgs",
        max_iter=2000,
        class_weight=None,
    )
    return Pipeline([("pre", pre), ("clf", clf)])


def _make_platt_logistic_regression(
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
) -> Pipeline:
    """Platt (sigmoid) calibration on top of a regularised LR.

    Run 1 used isotonic; on ~230-row inner folds the nonparametric
    isotonic step compressed probability tails and collapsed
    non-monotone preservation. Platt has one free parameter against
    isotonic's nonparametric many and should be more robust at this
    sample size.
    """
    pre = _make_preprocessor(numeric_columns, categorical_columns, scale=True)
    base = LogisticRegression(
        penalty="l2",
        C=1.0,
        solver="lbfgs",
        max_iter=2000,
    )
    cal = CalibratedClassifierCV(estimator=base, method="sigmoid", cv=3)
    return Pipeline([("pre", pre), ("clf", cal)])


def _make_hist_gradient_boosting(
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
) -> Pipeline:
    """Native-NaN HistGB with conservative depth and learning rate."""
    pre = _make_preprocessor(numeric_columns, categorical_columns, scale=False)
    clf = HistGradientBoostingClassifier(
        max_iter=200,
        learning_rate=0.05,
        max_depth=4,
        min_samples_leaf=20,
        l2_regularization=1.0,
        random_state=0,
    )
    return Pipeline([("pre", pre), ("clf", clf)])


def _make_decision_tree(
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
) -> Pipeline:
    """Shallow decision tree for interpretability.

    Depth 4 keeps the tree small enough to read directly in the thesis
    appendix. Uses the same preprocessor as HistGB (no scaling) so the
    one-hot expansion of categoricals produces splittable features.
    """
    pre = _make_preprocessor(numeric_columns, categorical_columns, scale=False)
    clf = DecisionTreeClassifier(
        max_depth=4,
        min_samples_leaf=20,
        class_weight=None,
        random_state=0,
    )
    return Pipeline([("pre", pre), ("clf", clf)])


_FACTORIES = {
    "logistic_regression": _make_logistic_regression,
    "logistic_regression_platt": _make_platt_logistic_regression,
    "hist_gradient_boosting": _make_hist_gradient_boosting,
    "decision_tree": _make_decision_tree,
}


def make_model(
    name: str,
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
) -> Pipeline:
    """Build a fresh sklearn pipeline for the named model."""
    if name not in _FACTORIES:
        raise KeyError(f"unknown model {name!r}; expected one of {MODEL_NAMES}")
    return _FACTORIES[name](numeric_columns, categorical_columns)


def expanded_feature_names(pipeline: Pipeline) -> list[str]:
    """Feature names after the ``pre`` ColumnTransformer expands one-hots."""
    pre: ColumnTransformer = pipeline.named_steps["pre"]
    names: list[str] = []
    for name, trans, cols in pre.transformers_:
        if name == "remainder":
            continue
        if name == "num":
            names.extend(cols)
            continue
        ohe: OneHotEncoder = trans.named_steps["encode"]
        for src_col, cats in zip(cols, ohe.categories_):
            names.extend(f"{src_col}={c}" for c in cats)
    return names


def extract_coefficients_or_importance(pipeline: Pipeline) -> tuple[str, np.ndarray]:
    """Return ``(kind, values)`` where kind is ``"coef"`` or ``"importance"``.

    - LR / DecisionTree → their native attributes.
    - Platt-calibrated LR → mean coefficient across the inner-CV
      calibrators (one weight per feature).
    - HistGB → no native attribute in sklearn 1.6; permutation
      importance is computed downstream in :mod:`evaluation`.
    """
    clf = pipeline.named_steps["clf"]
    if hasattr(clf, "coef_"):
        coef = np.asarray(clf.coef_).ravel()
        return "coef", coef
    if isinstance(clf, CalibratedClassifierCV):
        coefs = []
        for cc in clf.calibrated_classifiers_:
            inner = cc.estimator
            if hasattr(inner, "coef_"):
                coefs.append(np.asarray(inner.coef_).ravel())
        if coefs:
            return "coef", np.mean(np.vstack(coefs), axis=0)
    if isinstance(clf, DecisionTreeClassifier):
        if hasattr(clf, "feature_importances_"):
            return "importance", np.asarray(clf.feature_importances_)
    if isinstance(clf, HistGradientBoostingClassifier):
        if hasattr(clf, "feature_importances_"):
            return "importance", np.asarray(clf.feature_importances_)
        return "importance", np.full(len(expanded_feature_names(pipeline)), np.nan)
    return "importance", np.full(len(expanded_feature_names(pipeline)), np.nan)
