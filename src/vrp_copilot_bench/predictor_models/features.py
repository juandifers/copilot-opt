"""Feature-set construction with explicit leakage guards.

Feature sets exposed via :data:`FEATURE_SETS` and consumed by
:func:`build_feature_matrix`. Every column that touches the label, the
reference solve, or any escalation/recompute rung is held in
:data:`LEAKAGE_COLUMNS`; the builder refuses to surface them so a typo
in a feature list can't silently pull in label-derived signal.

Set C is per-claim-family. The headline definition (``C_clean``) drops
the columns that definitionally encode each family's label. The
pre-Run-2 unified definition is retained as ``C_leaky`` for the
ablation table only.
"""
from __future__ import annotations

from typing import Sequence

import pandas as pd

#: Categorical columns common across feature sets. Listed explicitly so
#: downstream encoders can target them without sniffing dtypes.
CATEGORICAL_COLUMNS_A: tuple[str, ...] = (
    "perturbation_family",
    "cheap_action",
    "instance_class",
)

#: Feature set A: categorical / block only. Includes the cheap-action
#: tier name and the perturbation magnitude (from the ``_N`` suffix) so
#: the predictor at least has access to what the categorical block-rule
#: baseline has.
FEATURE_SET_A: tuple[str, ...] = (
    "perturbation_family",
    "perturbation_magnitude",
    "cheap_action",
    "instance_class",
)

#: Pre-cheap instance + perturbation descriptors. These are available
#: before the cheap action runs, so a deployed gate could use them.
FEATURE_SET_B_EXTRA: tuple[str, ...] = (
    "baseline_n_routes",
    "baseline_obj",
    "baseline_generalized_cost",
    "baseline_total_wait",
    "baseline_min_route_slack",
    "baseline_mean_route_slack",
    "baseline_n_tight_customers",
    "n_affected_customers",
    "affected_route_share",
    "affected_demand_share",
    "affected_service_time_share",
    "affected_min_slack",
    "affected_mean_slack",
    "affected_total_wait",
)
FEATURE_SET_B: tuple[str, ...] = FEATURE_SET_A + FEATURE_SET_B_EXTRA

#: Post-cheap action diagnostics. These describe what the cheap action
#: did after running it.
FEATURE_SET_C_EXTRA: tuple[str, ...] = (
    "action_feasible",
    "infeasibility_kind",
    "action_obj_delta_pct",
    "action_generalized_delta_pct",
    "action_time_warp",
    "action_total_wait",
    "action_total_duration",
    "action_n_late_customers",
    "action_max_lateness",
)
#: ``C_leaky`` — pre-Run-2 unified Set C. PV × C_leaky is a tautology
#: (``action_feasible`` is essentially the PLAN_VALIDITY label) and
#: SCHEDULE × C_leaky has a partial leak via the lateness columns.
#: Retained for the ablation table only.
FEATURE_SET_C_LEAKY: tuple[str, ...] = FEATURE_SET_B + FEATURE_SET_C_EXTRA

#: Columns dropped from ``C_leaky`` to form ``C_clean`` per claim family.
#: PV drops the four definitional columns (feasibility itself plus the
#: kind, plus the lateness columns which co-encode infeasibility);
#: SCHEDULE drops the lateness columns which are the SCHEDULE loss
#: signal by construction.
C_CLEAN_DROPS_PER_CLAIM: dict[str, frozenset[str]] = {
    "OBJ": frozenset(),
    "PLAN_VALIDITY": frozenset(
        {
            "action_feasible",
            "action_n_late_customers",
            "action_max_lateness",
            "infeasibility_kind",
        }
    ),
    "STRUCT": frozenset(),
    "SCHEDULE": frozenset({"action_n_late_customers", "action_max_lateness"}),
}


def _c_clean_columns(claim_family: str) -> tuple[str, ...]:
    drops = C_CLEAN_DROPS_PER_CLAIM[claim_family]
    return tuple(c for c in FEATURE_SET_C_LEAKY if c not in drops)


#: Categoricals added in feature set C. Forwarded to the encoder.
CATEGORICAL_COLUMNS_C_EXTRA: tuple[str, ...] = ("infeasibility_kind",)

#: Public registry of feature sets. Values are static for A and B; for
#: per-family sets (``C_clean``) we register the unified column list and
#: resolve per-claim in :func:`build_feature_matrix`.
FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "A_categorical": FEATURE_SET_A,
    "B_pre_cheap": FEATURE_SET_B,
    "C_clean": FEATURE_SET_C_LEAKY,  # placeholder; resolved per-family
    "C_leaky": FEATURE_SET_C_LEAKY,
}

#: Feature sets whose column list depends on ``claim_family``.
PER_FAMILY_FEATURE_SETS: frozenset[str] = frozenset({"C_clean"})


#: Columns the predictor is forbidden from using as inputs.
LEAKAGE_COLUMNS: frozenset[str] = frozenset(
    {
        "sufficient_binary",
        "loss",
        "band",
        "reference_valid",
        "reference_struct_unstable",
        "reference_obj_unstable",
        "is_cheap_action",
        "is_reference_action",
        "is_middle_action",
        "cheap_action_for_cell",
        "claim_family",
    }
)


def perturbation_magnitude(perturbation_id: str) -> int:
    """Parse the ``_N`` suffix of a perturbation id into an integer 1–4.

    Returns ``0`` for ids without a numeric suffix so the caller can
    treat them as missing without raising.
    """
    if not isinstance(perturbation_id, str) or "_" not in perturbation_id:
        return 0
    tail = perturbation_id.rsplit("_", 1)[-1]
    try:
        return int(tail)
    except ValueError:
        return 0


def _derive_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the synthetic feature columns (magnitude, cheap_action alias)."""
    out = df.copy()
    if "perturbation_magnitude" not in out.columns:
        out["perturbation_magnitude"] = out["perturbation_id"].map(
            perturbation_magnitude
        )
    if "cheap_action" not in out.columns:
        out["cheap_action"] = out["action"].astype(str)
    if "action_feasible" in out.columns and out["action_feasible"].dtype == bool:
        out["action_feasible"] = out["action_feasible"].astype(int)
    return out


def _assert_no_leakage(columns: Sequence[str]) -> None:
    bad = sorted(set(columns) & LEAKAGE_COLUMNS)
    if bad:
        raise ValueError(
            f"leakage columns present in feature list: {bad}. "
            "Predictor inputs must not touch reference / loss / band / label."
        )


def feature_set_columns(feature_set: str, claim_family: str | None = None) -> tuple[str, ...]:
    """Resolve a feature_set name to its column tuple, per claim if needed."""
    if feature_set not in FEATURE_SETS:
        raise KeyError(
            f"unknown feature_set {feature_set!r}; expected one of "
            f"{sorted(FEATURE_SETS)}"
        )
    if feature_set in PER_FAMILY_FEATURE_SETS:
        if claim_family is None:
            raise ValueError(
                f"feature_set {feature_set!r} is per-claim-family; "
                "pass claim_family to resolve its column list."
            )
        if claim_family not in C_CLEAN_DROPS_PER_CLAIM:
            raise KeyError(f"unknown claim_family {claim_family!r}")
        return _c_clean_columns(claim_family)
    return FEATURE_SETS[feature_set]


def build_feature_matrix(
    cheap_df: pd.DataFrame,
    feature_set: str,
    claim_family: str | None = None,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Return ``(X, numeric_columns, categorical_columns)``.

    For per-family feature sets (``C_clean``) the column list is
    resolved against ``claim_family``. ``X`` is row-aligned to
    ``cheap_df``. Numeric columns are cast to float64 (NaN-preserving);
    categorical columns are cast to ``str``.
    """
    columns = feature_set_columns(feature_set, claim_family)
    _assert_no_leakage(columns)

    derived = _derive_columns(cheap_df)
    missing = [c for c in columns if c not in derived.columns]
    if missing:
        raise KeyError(f"missing required feature columns: {missing}")

    cat_cols: list[str] = []
    num_cols: list[str] = []
    for c in columns:
        if c in CATEGORICAL_COLUMNS_A or c in CATEGORICAL_COLUMNS_C_EXTRA:
            cat_cols.append(c)
        else:
            num_cols.append(c)

    X = derived[list(columns)].copy()
    for c in num_cols:
        X[c] = X[c].astype(float)
    for c in cat_cols:
        X[c] = X[c].astype(str)
    return X, num_cols, cat_cols


def numeric_features_for(feature_set: str, claim_family: str | None = None) -> list[str]:
    """Numeric columns belonging to ``feature_set`` (per-family if needed)."""
    columns = feature_set_columns(feature_set, claim_family)
    return [
        c for c in columns
        if c not in CATEGORICAL_COLUMNS_A and c not in CATEGORICAL_COLUMNS_C_EXTRA
    ]


def categorical_features_for(feature_set: str, claim_family: str | None = None) -> list[str]:
    """Categorical columns belonging to ``feature_set`` (per-family if needed)."""
    columns = feature_set_columns(feature_set, claim_family)
    return [
        c for c in columns
        if c in CATEGORICAL_COLUMNS_A or c in CATEGORICAL_COLUMNS_C_EXTRA
    ]
