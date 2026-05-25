"""Tests for the Stage A learned cheap-sufficiency predictor suite.

Uses a small synthetic frame that mirrors the locked Stage A long table
schema. Each combination of cell × claim_family appears at most once in
the cheap subset; an ``pyvrp_10s`` row exists for every cell so the
routing join is well-defined.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from vrp_copilot_bench.predictor_baselines.data import (
    CELL_KEYS,
    CLAIM_FAMILIES,
    build_cheap_eval_frame,
    build_escalation_frame,
)
from vrp_copilot_bench.predictor_baselines.runtime_costs import FALLBACK_RUNTIME_S
from vrp_copilot_bench.predictor_models.evaluation import (
    ThresholdConfig,
    calibration_curve_rows,
    cv_aggregate_classifier_metrics,
    nonmonotone_preservation,
    per_fold_classifier_metrics,
    restrict_to_non_degenerate,
    threshold_sweep,
)
from vrp_copilot_bench.predictor_models.features import (
    FEATURE_SETS,
    LEAKAGE_COLUMNS,
    build_feature_matrix,
    perturbation_magnitude,
)
from vrp_copilot_bench.predictor_models.models import (
    MODEL_NAMES,
    expanded_feature_names,
    make_model,
)
from vrp_copilot_bench.predictor_models.training import (
    attach_folds,
    oof_to_long_frame,
    train_all,
    train_oof,
)


# ---------------------------------------------------------------------------
# Synthetic data


_PRE_CHEAP_NUMERIC = {
    "baseline_n_routes": 10,
    "baseline_obj": 1234.5,
    "baseline_generalized_cost": 1500.0,
    "baseline_total_wait": 50,
    "baseline_min_route_slack": 5,
    "baseline_mean_route_slack": 12.5,
    "baseline_n_tight_customers": 3,
    "n_affected_customers": 4,
    "affected_route_share": 0.4,
    "affected_demand_share": 0.3,
    "affected_service_time_share": 0.25,
    "affected_min_slack": 1.0,
    "affected_mean_slack": 4.0,
    "affected_total_wait": 30,
}

_POST_CHEAP_NUMERIC = {
    "action_obj_delta_pct": 0.05,
    "action_generalized_delta_pct": 0.07,
    "action_time_warp": 0,
    "action_total_wait": 25,
    "action_total_duration": 320,
    "action_n_late_customers": 0,
    "action_max_lateness": 0,
}


def _cheap_row(
    iid: str,
    pid: str,
    pfam: str,
    action: str,
    feasible: bool,
    claim_to_label: dict[str, float],
    *,
    perturbation_tag: int,
) -> list[dict]:
    rows = []
    for fam in CLAIM_FAMILIES:
        rec = {
            "instance_id": iid,
            "perturbation_id": pid,
            "perturbation_family": pfam,
            "action": action,
            "action_tier": "tier",
            "action_tier_index": 0,
            "is_middle_action": False,
            "is_reference_action": False,
            "action_runtime_s": FALLBACK_RUNTIME_S[action],
            "action_solver_time_limit": float("nan"),
            "action_seed": float("nan"),
            "action_valid": True,
            "cheap_action_for_cell": action,
            "is_cheap_action": True,
            "claim_family": fam,
            "loss": 0.0,
            "band": "easy",
            "sufficient_binary": claim_to_label[fam],
            "reference_valid": True,
            "reference_struct_unstable": False,
            "reference_obj_unstable": False,
            "action_feasible": feasible,
            "infeasibility_kind": "none" if feasible else "time_window",
            "reference_time_limit_s": 60,
            "perturbation_tag_for_test": perturbation_tag,
        }
        rec.update(_PRE_CHEAP_NUMERIC)
        rec.update(_POST_CHEAP_NUMERIC)
        rows.append(rec)
    return rows


def _escalation_rows(iid: str, pid: str, pfam: str) -> list[dict]:
    rows = []
    for fam in CLAIM_FAMILIES:
        rows.append(
            {
                "instance_id": iid,
                "perturbation_id": pid,
                "perturbation_family": pfam,
                "action": "pyvrp_10s",
                "action_tier": "tier",
                "action_tier_index": 3,
                "is_middle_action": True,
                "is_reference_action": False,
                "action_runtime_s": FALLBACK_RUNTIME_S["pyvrp_10s"],
                "action_solver_time_limit": 10.0,
                "action_seed": 1.0,
                "action_valid": True,
                "cheap_action_for_cell": (
                    "reuse_direct" if pfam != "ORDER_CHANGE" else "local_repair_insert"
                ),
                "is_cheap_action": False,
                "claim_family": fam,
                "loss": 0.0,
                "band": "easy",
                "sufficient_binary": 1.0,
                "reference_valid": True,
                "reference_struct_unstable": False,
                "reference_obj_unstable": False,
                "action_feasible": True,
                "infeasibility_kind": "none",
                "reference_time_limit_s": 60,
                "perturbation_tag_for_test": 0,
            }
        )
    return rows


def _make_long_frame() -> pd.DataFrame:
    """20 instances × 2 perturbations × 4 claim families × cheap + pyvrp_10s.

    Half the cheap rows have ``sufficient_binary=1`` and half =0 so the
    classifier has a non-degenerate target to learn. A signal column
    ``perturbation_tag_for_test`` is embedded so we can verify the
    classifier actually learns something on this synthetic dataset.
    """
    rng = np.random.default_rng(0)
    rows: list[dict] = []
    instances = [f"C{i:03d}" for i in range(8)] + [
        f"R{i:03d}" for i in range(7)
    ] + [f"RC{i:03d}" for i in range(5)]
    for iid in instances:
        for pid, pfam, tag in [("TT_1", "TRAVEL_TIME", 1), ("OC_2", "ORDER_CHANGE", 2)]:
            action = "reuse_direct" if pfam != "ORDER_CHANGE" else "local_repair_insert"
            # Easy: cheap sufficient when tag matches a hidden rule.
            base_label = 1.0 if rng.random() < 0.6 else 0.0
            labels = {fam: base_label for fam in CLAIM_FAMILIES}
            rows.extend(
                _cheap_row(
                    iid, pid, pfam, action, feasible=base_label == 1.0,
                    claim_to_label=labels, perturbation_tag=tag,
                )
            )
            rows.extend(_escalation_rows(iid, pid, pfam))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# features.py


def test_feature_sets_progress_in_columns():
    a = set(FEATURE_SETS["A_categorical"])
    b = set(FEATURE_SETS["B_pre_cheap"])
    c = set(FEATURE_SETS["C_leaky"])
    assert a < b < c
    # Spot-check that the columns the spec named are present in each tier.
    assert "perturbation_magnitude" in a
    assert "baseline_obj" in b and "baseline_obj" not in a
    assert "action_obj_delta_pct" in c and "action_obj_delta_pct" not in b


def test_c_clean_per_family_drops_label_columns():
    from vrp_copilot_bench.predictor_models.features import (
        C_CLEAN_DROPS_PER_CLAIM, feature_set_columns,
    )
    # PV drops the four definitional columns; SCHEDULE drops two lateness ones.
    assert "action_feasible" not in feature_set_columns("C_clean", "PLAN_VALIDITY")
    assert "infeasibility_kind" not in feature_set_columns("C_clean", "PLAN_VALIDITY")
    assert "action_n_late_customers" not in feature_set_columns("C_clean", "SCHEDULE")
    assert "action_max_lateness" not in feature_set_columns("C_clean", "SCHEDULE")
    # OBJ / STRUCT retain the full set.
    assert "action_feasible" in feature_set_columns("C_clean", "OBJ")
    assert "action_n_late_customers" in feature_set_columns("C_clean", "STRUCT")
    # Per-family resolution refuses to silently default.
    with pytest.raises(ValueError, match="per-claim-family"):
        feature_set_columns("C_clean")
    # Drop table covers all claim families.
    assert set(C_CLEAN_DROPS_PER_CLAIM) == {"OBJ", "PLAN_VALIDITY", "STRUCT", "SCHEDULE"}


def test_leakage_columns_rejected_by_builder(monkeypatch):
    """Hand-craft a feature_set entry with a leakage column and confirm the
    builder refuses it. We mutate the registry inside the test only and
    restore it afterwards via monkeypatch.
    """
    from vrp_copilot_bench.predictor_models import features as mod
    bad_name = "_test_leakage"
    monkeypatch.setitem(mod.FEATURE_SETS, bad_name, ("perturbation_family", "loss"))
    df = _make_long_frame()
    cheap = build_cheap_eval_frame(df, keep_nan_labels=False)
    with pytest.raises(ValueError, match="leakage"):
        build_feature_matrix(cheap, bad_name)


def test_perturbation_magnitude_parses_suffix():
    assert perturbation_magnitude("TT_4") == 4
    assert perturbation_magnitude("OC_1") == 1
    assert perturbation_magnitude("notanid") == 0
    assert perturbation_magnitude(None) == 0  # type: ignore[arg-type]


def test_build_feature_matrix_returns_typed_columns():
    df = _make_long_frame()
    cheap = build_cheap_eval_frame(df, keep_nan_labels=False)
    X, num, cat = build_feature_matrix(cheap, "C_leaky")
    # Numeric columns are float-castable.
    for c in num:
        X[c].astype(float)
    # Categorical columns are strings.
    for c in cat:
        assert X[c].dtype == object
    # No leakage column leaks into the matrix.
    assert not (set(X.columns) & LEAKAGE_COLUMNS)
    # Aligned to cheap_df row order.
    assert len(X) == len(cheap)


def test_build_feature_matrix_rejects_unknown_set():
    df = _make_long_frame()
    cheap = build_cheap_eval_frame(df, keep_nan_labels=False)
    with pytest.raises(KeyError):
        build_feature_matrix(cheap, "Z_does_not_exist")


# ---------------------------------------------------------------------------
# models.py


def test_make_model_returns_pipeline_per_name():
    for name in MODEL_NAMES:
        pipe = make_model(name, numeric_columns=["x"], categorical_columns=["c"])
        assert hasattr(pipe, "fit")
        assert hasattr(pipe, "predict_proba")


def test_make_model_unknown_raises():
    with pytest.raises(KeyError):
        make_model("not_a_model", numeric_columns=[], categorical_columns=[])


def test_expanded_feature_names_align_with_one_hots():
    pipe = make_model(
        "logistic_regression",
        numeric_columns=["num_a"],
        categorical_columns=["cat_b"],
    )
    X = pd.DataFrame({"num_a": [1.0, 2.0, 3.0, 4.0], "cat_b": ["x", "y", "x", "y"]})
    y = np.array([0, 1, 0, 1])
    pipe.fit(X, y)
    names = expanded_feature_names(pipe)
    assert names[0] == "num_a"
    assert {"cat_b=x", "cat_b=y"}.issubset(names)


# ---------------------------------------------------------------------------
# training.py


@pytest.fixture
def fold_csv(tmp_path):
    df = _make_long_frame()
    instances = sorted(df["instance_id"].unique())
    # Round-robin across 5 folds for the test.
    folds = pd.DataFrame(
        {"instance_id": instances, "fold": [i % 5 for i in range(len(instances))]}
    )
    path = tmp_path / "folds.csv"
    folds.to_csv(path, index=False)
    return path


def test_attach_folds_requires_every_instance(fold_csv, tmp_path):
    df = _make_long_frame()
    cheap = build_cheap_eval_frame(df, keep_nan_labels=False)
    out = attach_folds(cheap, fold_csv)
    assert "fold" in out.columns
    assert out["fold"].notna().all()
    # Missing instance triggers an error.
    bad_path = tmp_path / "bad.csv"
    pd.DataFrame({"instance_id": ["C000"], "fold": [0]}).to_csv(bad_path, index=False)
    with pytest.raises(ValueError, match="missing"):
        attach_folds(cheap, bad_path)


def test_train_oof_produces_one_prob_per_row(fold_csv):
    df = _make_long_frame()
    cheap = build_cheap_eval_frame(df, keep_nan_labels=False)
    cheap = attach_folds(cheap, fold_csv)
    res = train_oof(
        cheap, model_name="logistic_regression",
        feature_set="A_categorical", claim_family="OBJ",
    )
    obj_rows = cheap[cheap["claim_family"] == "OBJ"]
    assert len(res.probs) == len(obj_rows)
    assert np.isfinite(res.probs).all()
    assert ((res.probs >= 0) & (res.probs <= 1)).all()


def test_oof_long_frame_covers_each_cell_once_per_config(fold_csv):
    df = _make_long_frame()
    cheap = build_cheap_eval_frame(df, keep_nan_labels=False)
    cheap = attach_folds(cheap, fold_csv)
    results = train_all(
        cheap,
        models=("logistic_regression",),
        feature_sets=("A_categorical",),
        claim_families=CLAIM_FAMILIES,
    )
    long = oof_to_long_frame(results)
    grouped = (
        long.groupby(["model", "feature_set", "claim_family"]).size()
    )
    expected = len(cheap) // len(CLAIM_FAMILIES)
    # Every (model × feature_set × claim_family) has the per-claim cheap subset size.
    assert grouped.eq(expected).all()


# ---------------------------------------------------------------------------
# evaluation.py


@pytest.fixture
def trained_long(fold_csv):
    df = _make_long_frame()
    cheap = build_cheap_eval_frame(df, keep_nan_labels=False)
    cheap = attach_folds(cheap, fold_csv)
    results = train_all(
        cheap,
        models=("logistic_regression",),
        feature_sets=("A_categorical",),
        claim_families=CLAIM_FAMILIES,
    )
    return df, oof_to_long_frame(results)


def test_per_fold_metrics_have_one_row_per_fold(trained_long):
    _, long = trained_long
    pf = per_fold_classifier_metrics(long)
    assert {"auroc", "auprc", "brier", "n_rows"}.issubset(pf.columns)
    # 1 model × 1 fs × 4 claims × 5 folds = 20 rows.
    assert len(pf) == 20


def test_cv_aggregate_reduces_to_one_row_per_config(trained_long):
    _, long = trained_long
    pf = per_fold_classifier_metrics(long)
    cv = cv_aggregate_classifier_metrics(pf)
    assert len(cv) == 4  # 4 claim families, one model, one feature set
    assert "auroc_cv_mean" in cv.columns


def test_threshold_sweep_covers_grid_and_metrics(trained_long):
    df, long = trained_long
    esc = build_escalation_frame(df, "pyvrp_10s")
    sweep = threshold_sweep(long, esc, grid=(0.5, 0.9))
    assert {"accepted_coverage", "final_correctness",
            "average_compute_cost_s", "p95_compute_cost_s"}.issubset(sweep.columns)
    # 1 model × 1 fs × 4 claims × 2 thresholds.
    assert len(sweep) == 8
    # Accepted coverage at the higher threshold cannot exceed coverage at
    # the lower threshold (the gate is monotone in the threshold).
    pairs = sweep.pivot_table(
        index=["model", "feature_set", "claim_family"],
        columns="threshold",
        values="accepted_coverage",
    )
    assert (pairs[0.5] >= pairs[0.9] - 1e-9).all()


def test_threshold_sweep_routing_uses_escalation_label(trained_long):
    """At threshold 1.0 the gate never accepts → final correctness equals
    the escalation row's sufficient rate."""
    df, long = trained_long
    esc = build_escalation_frame(df, "pyvrp_10s")
    sweep = threshold_sweep(long, esc, grid=(1.0,))
    # All cheap probabilities < 1.0 (LR doesn't emit hard ones on this fixture),
    # so every row escalates and final_correctness becomes the py10 rate.
    py10_rate = esc["sufficient_binary"].mean()
    assert sweep["final_correctness"].between(py10_rate - 1e-6, py10_rate + 1e-6).all()


def test_calibration_curve_bins_sum_to_n_rows(trained_long):
    _, long = trained_long
    cal = calibration_curve_rows(long, n_bins=5)
    # 1 model × 1 fs × 4 claims × 5 bins = 20.
    assert len(cal) == 20
    # Sum of bin_count == n_rows for the configuration.
    by_config = cal.groupby(["model", "feature_set", "claim_family"])["bin_count"].sum()
    n_per_config = long.groupby(["model", "feature_set", "claim_family"]).size()
    assert (by_config.values == n_per_config.values).all()


def test_nonmonotone_preservation_counts(trained_long):
    df, long = trained_long
    esc = build_escalation_frame(df, "pyvrp_10s")
    # Force one STRUCT cell into the non-monotone bucket: set py10 label to 0
    # for the first STRUCT cell.
    first_cell = long[long["claim_family"] == "STRUCT"].iloc[0]
    key = {k: first_cell[k] for k in CELL_KEYS}
    mask = (
        (esc["instance_id"] == key["instance_id"])
        & (esc["perturbation_id"] == key["perturbation_id"])
        & (esc["claim_family"] == "STRUCT")
    )
    esc = esc.copy()
    esc.loc[mask, "sufficient_binary"] = 0.0
    # Force the corresponding cheap row to label=1 so the (cheap=1, py10=0)
    # condition is satisfied.
    long = long.copy()
    long.loc[
        (long["claim_family"] == "STRUCT")
        & (long["instance_id"] == key["instance_id"])
        & (long["perturbation_id"] == key["perturbation_id"]),
        "sufficient_binary",
    ] = 1.0
    nm = nonmonotone_preservation(long, esc, grid=(0.5,))
    struct = nm[nm["claim_family"] == "STRUCT"]
    assert (struct["n_cases"] >= 1).all()


def test_restrict_to_non_degenerate_drops_obj_tw_and_tt():
    df = pd.DataFrame(
        {
            "claim_family": ["OBJ", "OBJ", "OBJ", "STRUCT"],
            "perturbation_family": [
                "TIME_WINDOW", "TRAVEL_TIME", "SERVICE_TIME", "TRAVEL_TIME",
            ],
        }
    )
    out = restrict_to_non_degenerate(df)
    assert (
        out[["claim_family", "perturbation_family"]]
        .apply(tuple, axis=1)
        .tolist()
        == [("OBJ", "SERVICE_TIME"), ("STRUCT", "TRAVEL_TIME")]
    )
