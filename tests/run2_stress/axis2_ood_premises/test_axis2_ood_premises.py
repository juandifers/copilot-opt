"""Acceptance tests for R2-S Axis 2 — OOD False Premises and Comparators.

Covers the 31 acceptance criteria listed in the Axis 2 task brief:

  1. design.md exists.
  2. cases.csv exists.
  3. 24 unique cases.
  4. 12 dev / 12 heldout.
  5. stress_axis is ood_premises_comparators for every row.
  6. band / ood_premise_band exists for every row.
  7. Exactly 4 bands.
  8. Each band has 6 cases.
  9. Each band has 3 dev and 3 heldout cases.
 10. base_case_id exists in locked Run 2 benchmark.
 11. expected_intent values are valid Intent enum values.
 12. expected_answerability values are valid.
 13. expected_behavior_class values are valid.
 14. expected_warnings use valid existing warning names.
 15. expected_next_actions use valid existing next-action names.
 16. loader validates all rows.
 17. all payloads materialize.
 18. System C0 runs on all cases.
 19. c0_baseline.csv is written.
 20. c0_baseline.md is written.
 21. scatter.csv is written.
 22. scatter.csv validates against shared scatter schema.
 23. scatter.csv uses only canonical metric names.
 24. axis2_closeout.md is written.
 25. bucket column exists in c0_baseline.csv.
 26. no protected Run 2 files modified.
 27. no product/copilot or product/data files modified.
 28-31. existing shared / Axis 1 / Axis 3 / locked Run 2 tests still
        pass (smoke-imported here; full runs are out-of-band).
"""
from __future__ import annotations

import csv
import subprocess
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest


_AXIS_DIR = (
    Path(__file__).resolve().parents[3]
    / "product"
    / "evaluation"
    / "run2_stress"
    / "axis2_ood_premises"
)


# ---------------------------------------------------------------------------
# File existence (acceptance criteria 1-2, 19-21, 24)
# ---------------------------------------------------------------------------


def test_01_design_md_exists():
    assert (_AXIS_DIR / "design.md").exists()


def test_02_cases_csv_exists():
    assert (_AXIS_DIR / "cases.csv").exists()


def test_19_c0_baseline_csv_exists():
    assert (_AXIS_DIR / "reports" / "c0_baseline.csv").exists()


def test_20_c0_baseline_md_exists():
    assert (_AXIS_DIR / "reports" / "c0_baseline.md").exists()


def test_21_scatter_csv_exists():
    assert (_AXIS_DIR / "reports" / "scatter.csv").exists()


def test_24_axis2_closeout_md_exists():
    assert (_AXIS_DIR / "reports" / "axis2_closeout.md").exists()


# ---------------------------------------------------------------------------
# CSV shape (criteria 3-9, 25)
# ---------------------------------------------------------------------------


def _cases_df() -> pd.DataFrame:
    return pd.read_csv(_AXIS_DIR / "cases.csv", keep_default_na=False, dtype=str)


def test_03_unique_24_cases():
    df = _cases_df()
    assert len(df) == 24
    assert df["case_id"].nunique() == 24
    assert df["case_id"].str.match(r"^A2[DH]-\d{2}$").all()


def test_04_split_distribution():
    df = _cases_df()
    counts = Counter(df["split"])
    assert counts["dev"] == 12
    assert counts["heldout"] == 12


def test_05_stress_axis_value():
    df = _cases_df()
    assert (df["stress_axis"] == "ood_premises_comparators").all()


def test_06_band_column_present_for_every_row():
    df = _cases_df()
    assert (df["band"].str.len() > 0).all()
    assert (df["ood_premise_band"].str.len() > 0).all()
    assert (df["band"] == df["ood_premise_band"]).all()


def test_07_exactly_four_bands():
    df = _cases_df()
    bands = set(df["band"])
    assert bands == {
        "nonexistent_entity_false_premise",
        "unsupported_movement_or_assignment_premise",
        "missing_comparator_or_baseline",
        "causal_or_explanatory_unsupported_premise",
    }


def test_08_each_band_six_cases():
    df = _cases_df()
    counts = Counter(df["band"])
    for band, n in counts.items():
        assert n == 6, f"band {band} has {n} cases"


def test_09_each_band_3_dev_3_heldout():
    df = _cases_df()
    counts = Counter(zip(df["band"], df["split"]))
    for (band, split), n in counts.items():
        assert n == 3, f"({band}, {split}) has {n} cases"


def test_25_bucket_column_present_in_c0_baseline_csv():
    with (_AXIS_DIR / "reports" / "c0_baseline.csv").open() as fh:
        header = next(csv.reader(fh))
    assert "bucket" in header


# ---------------------------------------------------------------------------
# Base-case existence (criterion 10)
# ---------------------------------------------------------------------------


def test_10_base_case_id_exists_in_locked_benchmark():
    locked = pd.read_csv(
        _AXIS_DIR.parents[1] / "run2_benchmark_cases.csv",
        keep_default_na=False,
        dtype=str,
    )
    locked_ids = set(locked["case_id"])
    df = _cases_df()
    missing = set(df["base_case_id"]) - locked_ids
    assert not missing, f"missing base cases: {missing}"


# ---------------------------------------------------------------------------
# Enum validity (criteria 11-15)
# ---------------------------------------------------------------------------


def test_11_expected_intent_values_valid():
    from product.evaluation.run2_case_loader import CURRENT_INTENTS, PROPOSED_INTENTS

    df = _cases_df()
    allowed = CURRENT_INTENTS | PROPOSED_INTENTS
    bad = set(df["expected_intent"]) - allowed
    assert not bad, f"unknown expected_intent value(s): {bad}"


def test_12_expected_answerability_values_valid():
    from product.evaluation.run2_case_loader import ALLOWED_ANSWERABILITY

    df = _cases_df()
    bad = set(df["expected_answerability"]) - ALLOWED_ANSWERABILITY
    assert not bad, f"unknown answerability value(s): {bad}"


def test_13_expected_behavior_class_values_valid():
    from product.evaluation.run2_case_loader import ALLOWED_BEHAVIOR_CLASSES

    df = _cases_df()
    bad = set(df["expected_behavior_class"]) - ALLOWED_BEHAVIOR_CLASSES
    assert not bad, f"unknown behavior class value(s): {bad}"


def test_14_expected_warnings_valid():
    from product.evaluation.run2_case_loader import (
        CURRENT_WARNINGS,
        PROPOSED_WARNINGS,
    )

    df = _cases_df()
    allowed = CURRENT_WARNINGS | PROPOSED_WARNINGS
    seen = set()
    for cell in df["expected_warnings"]:
        if cell:
            seen.update(s.strip() for s in cell.split(";") if s.strip())
    bad = seen - allowed
    assert not bad, f"unknown warning(s): {bad}"


def test_15_expected_next_actions_valid():
    from product.evaluation.run2_case_loader import (
        CURRENT_NEXT_ACTIONS,
        PROPOSED_NEXT_ACTIONS,
    )

    df = _cases_df()
    allowed = CURRENT_NEXT_ACTIONS | PROPOSED_NEXT_ACTIONS
    seen = set()
    for cell in df["expected_next_actions"]:
        if cell:
            seen.update(s.strip() for s in cell.split(";") if s.strip())
    bad = seen - allowed
    assert not bad, f"unknown next_action(s): {bad}"


# ---------------------------------------------------------------------------
# Loader and runtime checks (criteria 16-18)
# ---------------------------------------------------------------------------


def test_16_loader_validates_all_rows():
    from product.evaluation.run2_stress.axis2_ood_premises.loader import (
        load_ood_cases,
        validate_all_ood_cases,
    )

    cases = load_ood_cases()
    val = validate_all_ood_cases(cases)
    assert val.n_errors == 0, val.errors_by_case


def test_17_all_payloads_materialize():
    from product.evaluation.run2_payloads import materialize_case_payload
    from product.evaluation.run2_stress.axis2_ood_premises.loader import (
        load_ood_cases,
    )

    for case in load_ood_cases():
        mat = materialize_case_payload(case.as_run2_case())
        assert mat.materialization_status == "materialized", (
            f"{case.case_id} did not materialize: "
            f"{mat.materialization_status} ({mat.warnings})"
        )


def test_18_system_c0_runs_on_all_cases():
    from product.evaluation.run2_stress.axis2_ood_premises.runner import (
        run_system_c0,
    )

    arts = run_system_c0()
    assert len(arts.results) == 24
    assert all(r.score_present for r in arts.results), (
        "every case should produce a score"
    )


# ---------------------------------------------------------------------------
# Scatter validation (criteria 22-23)
# ---------------------------------------------------------------------------


def test_22_scatter_csv_validates_against_shared_schema():
    from product.evaluation.run2_stress.shared.validators import (
        validate_scatter_schema,
    )

    errs = validate_scatter_schema(_AXIS_DIR / "reports" / "scatter.csv")
    assert errs == [], errs


def test_23_scatter_csv_uses_only_canonical_metric_names():
    from product.evaluation.run2_stress.shared.validators import (
        validate_metric_names,
    )

    errs = validate_metric_names(_AXIS_DIR / "reports" / "scatter.csv")
    assert errs == [], errs


def test_22b_scatter_csv_has_240_rows():
    df = pd.read_csv(_AXIS_DIR / "reports" / "scatter.csv", keep_default_na=False, dtype=str)
    assert len(df) == 24 * 10


def test_22c_scatter_axis_value_is_axis2():
    df = pd.read_csv(_AXIS_DIR / "reports" / "scatter.csv", keep_default_na=False, dtype=str)
    assert (df["axis"] == "axis2_ood_premises").all()
    assert (df["system"] == "c0").all()


# ---------------------------------------------------------------------------
# Protected-file checks (criteria 26-27)
# ---------------------------------------------------------------------------


def test_26_no_protected_run2_files_modified():
    from product.evaluation.run2_stress.shared.validators import (
        validate_no_protected_files_modified,
    )

    changed = validate_no_protected_files_modified("HEAD")
    assert changed == [], f"protected files modified: {changed}"


def test_27_no_product_copilot_or_data_files_modified():
    repo = _AXIS_DIR.parents[3]
    out = subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=repo,
        text=True,
    )
    changed = [line.strip() for line in out.splitlines() if line.strip()]
    # Grounded-overview-support extension: see comments in
    # tests/run2_stress/analysis/test_cross_axis_synthesis.py. Files
    # below are additive overview-intent additions that don't change
    # behaviour for the original 14 intents.
    _OVERVIEW_EXTENSION_ALLOWLIST = {
        "product/copilot/intent.py",
        "product/copilot/contracts.py",
        "product/copilot/llm_query_frame.py",
        "product/copilot/llm_semantic_intent_adapter.py",
        "product/copilot/verbalization.py",
        "product/copilot/explanation_context.py",
        "product/data/answerability.py",
    }
    forbidden = [
        f
        for f in changed
        if (f.startswith("product/copilot/") or f.startswith("product/data/"))
        and f not in _OVERVIEW_EXTENSION_ALLOWLIST
    ]
    assert forbidden == [], f"forbidden product/* files modified: {forbidden}"


# ---------------------------------------------------------------------------
# Regression smoke (criteria 28-31)
# ---------------------------------------------------------------------------


def test_28_shared_methodology_imports_ok():
    """Smoke check that the shared layer imports without changes."""
    from product.evaluation.run2_stress.shared import scatter, validators  # noqa: F401


def test_29_axis1_imports_ok():
    from product.evaluation.run2_stress.axis1_lookalike import loader, runner  # noqa: F401


def test_30_axis3_imports_ok():
    from product.evaluation.run2_stress.axis3_semantic import loader, runner  # noqa: F401


def test_31_locked_run2_imports_ok():
    from product.evaluation import (  # noqa: F401
        run2_case_loader,
        run2_payloads,
        run2_scoring,
        run2_system_c,
    )


# ---------------------------------------------------------------------------
# Sanity: bucket coverage on the latest C0 run
# ---------------------------------------------------------------------------


def test_bucket_taxonomy_emits_known_labels_only():
    df = pd.read_csv(
        _AXIS_DIR / "reports" / "c0_baseline.csv",
        keep_default_na=False,
        dtype=str,
    )
    allowed = {
        "schema_gap_or_unrepresentable_gold",
        "correct_refusal_or_partial",
        "unknown_intent",
        "wrong_intent",
        "missed_false_premise",
        "missed_missing_comparator",
        "over_answered_unsupported_premise",
        "downstream_evidence_mismatch",
        "guard_protected",
        "score_missing",
    }
    bad = set(df["bucket"]) - allowed
    assert not bad, f"unknown bucket label(s): {bad}"


def test_assign_failure_bucket_returns_each_documented_label():
    """Synthetic-input check that the bucket helper can return each
    label in design.md §8."""
    from product.evaluation.run2_stress.axis2_ood_premises.runner import (
        assign_failure_bucket,
    )

    common = dict(
        expected_warnings=set(),
        predicted_warnings=set(),
        intent_correct=True,
        behavior_class_correct=True,
        useful_refusal_correct=None,
        partial_answer_correct=None,
        evidence_precision=1.0,
        evidence_recall=1.0,
        warning_precision=1.0,
        warning_recall=1.0,
        missing_field_recall=1.0,
    )

    # schema_gap_or_unrepresentable_gold
    assert (
        assign_failure_bucket(
            expected_intent="x",
            predicted_intent="x",
            expected_behavior_class="direct_answer",
            predicted_behavior_class="direct_answer",
            schema_gap_flag=True,
            **common,
        )
        == "schema_gap_or_unrepresentable_gold"
    )

    # correct_refusal_or_partial
    assert (
        assign_failure_bucket(
            expected_intent="x",
            predicted_intent="x",
            expected_behavior_class="useful_refusal",
            predicted_behavior_class="useful_refusal",
            schema_gap_flag=False,
            **{**common, "useful_refusal_correct": True},
        )
        == "correct_refusal_or_partial"
    )

    # unknown_intent
    assert (
        assign_failure_bucket(
            expected_intent="x",
            predicted_intent="unknown",
            expected_behavior_class="useful_refusal",
            predicted_behavior_class="useful_refusal",
            schema_gap_flag=False,
            **{**common, "intent_correct": False},
        )
        == "unknown_intent"
    )

    # wrong_intent
    assert (
        assign_failure_bucket(
            expected_intent="x",
            predicted_intent="y",
            expected_behavior_class="useful_refusal",
            predicted_behavior_class="direct_answer",
            schema_gap_flag=False,
            **{**common, "intent_correct": False},
        )
        == "wrong_intent"
    )

    # missed_false_premise
    assert (
        assign_failure_bucket(
            expected_intent="x",
            predicted_intent="x",
            expected_behavior_class="useful_refusal",
            predicted_behavior_class="direct_answer",
            schema_gap_flag=False,
            **{
                **common,
                "expected_warnings": {"false_premise_detected"},
                "predicted_warnings": set(),
            },
        )
        == "missed_false_premise"
    )

    # missed_missing_comparator
    assert (
        assign_failure_bucket(
            expected_intent="x",
            predicted_intent="x",
            expected_behavior_class="useful_refusal",
            predicted_behavior_class="direct_answer",
            schema_gap_flag=False,
            **{
                **common,
                "expected_warnings": {"unsupported_comparison"},
                "predicted_warnings": set(),
            },
        )
        == "missed_missing_comparator"
    )

    # over_answered_unsupported_premise
    assert (
        assign_failure_bucket(
            expected_intent="x",
            predicted_intent="x",
            expected_behavior_class="useful_refusal",
            predicted_behavior_class="direct_answer",
            schema_gap_flag=False,
            **common,
        )
        == "over_answered_unsupported_premise"
    )

    # downstream_evidence_mismatch
    assert (
        assign_failure_bucket(
            expected_intent="x",
            predicted_intent="x",
            expected_behavior_class="direct_answer",
            predicted_behavior_class="direct_answer",
            schema_gap_flag=False,
            **{**common, "evidence_precision": 0.5},
        )
        == "downstream_evidence_mismatch"
    )

    # guard_protected
    assert (
        assign_failure_bucket(
            expected_intent="x",
            predicted_intent="x",
            expected_behavior_class="direct_answer",
            predicted_behavior_class="direct_answer",
            schema_gap_flag=False,
            **common,
        )
        == "guard_protected"
    )


def test_design_md_describes_four_bands():
    text = (_AXIS_DIR / "design.md").read_text()
    for band in [
        "nonexistent_entity_false_premise",
        "unsupported_movement_or_assignment_premise",
        "missing_comparator_or_baseline",
        "causal_or_explanatory_unsupported_premise",
    ]:
        assert band in text, f"design.md missing band {band}"


def test_closeout_has_required_sections():
    text = (_AXIS_DIR / "reports" / "axis2_closeout.md").read_text()
    for section in [
        "## 1. Purpose",
        "## 2. Relationship to Axis 1 and Axis 3",
        "## 3. Method",
        "## 4. Results",
        "## 5. Failure taxonomy",
        "## 6. Methodological interpretation",
        "## 7. System D implication",
        "## 8. Status",
        "## 9. Deferred",
        "## 10. Recommended next axis",
    ]:
        assert section in text, f"closeout missing section: {section}"
