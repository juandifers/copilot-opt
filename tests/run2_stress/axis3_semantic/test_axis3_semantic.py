"""Tests for the R2-S1 semantic-intent stress split (axis 3).

Schema validation, gold-row inheritance from the locked Run 2
benchmark, payload materialization, System C0 execution, scoring,
and report rendering. These tests do not modify or read-for-write
any locked Run 2 artifact.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from product.evaluation.run2_case_loader import (
    CURRENT_INTENTS,
    PROPOSED_INTENTS,
    ALLOWED_ANSWERABILITY,
    ALLOWED_BEHAVIOR_CLASSES,
    load_run2_cases,
)
from product.evaluation.run2_payloads import materialize_case_payload
from product.evaluation.run2_scoring import score_case
from product.evaluation.run2_system_c import run_system_c_on_materialized

from product.evaluation.run2_stress.axis3_semantic.loader import (
    ALLOWED_SPLITS,
    ALLOWED_STRESS_SUBTYPES,
    EXPECTED_COLUMNS,
    EXPECTED_PER_SPLIT,
    EXPECTED_TOTAL_CASES,
    INHERITED_COLUMNS,
    Run2StressCase,
    default_cases_path,
    default_locked_benchmark_path,
    load_stress_cases,
    validate_all_stress_cases,
)
from product.evaluation.run2_stress.axis3_semantic.runner import (
    StressCaseResult,
    build_scatter_rows,
    run_system_c0,
    write_results_csv,
)
from product.evaluation.run2_stress.shared.scatter import (
    SCATTER_COLUMNS as SHARED_SCATTER_COLUMNS,
    write_scatter_csv as shared_write_scatter_csv,
)
from product.evaluation.run2_stress.shared.validators import (
    ALLOWED_METRIC_NAMES as SHARED_METRIC_NAMES,
    validate_metric_names as shared_validate_metric_names,
    validate_scatter_schema as shared_validate_scatter_schema,
)
from product.evaluation.run2_stress.axis3_semantic.report import (
    aggregate_axis3,
    render_markdown,
    write_baseline_markdown,
)


_STRESS_CASE_ID_RE = re.compile(r"^S1[DH]-\d{2}$")


# ---------------------------------------------------------------------------
# Schema and load
# ---------------------------------------------------------------------------


def test_cases_csv_loads_with_expected_header():
    df = pd.read_csv(default_cases_path(), keep_default_na=False, dtype=str)
    assert list(df.columns) == EXPECTED_COLUMNS


def test_load_returns_24_typed_cases():
    cases = load_stress_cases()
    assert len(cases) == EXPECTED_TOTAL_CASES
    assert all(isinstance(c, Run2StressCase) for c in cases)


def test_all_case_ids_unique():
    cases = load_stress_cases()
    ids = [c.case_id for c in cases]
    assert len(set(ids)) == len(ids)


def test_all_case_ids_match_stress_pattern():
    cases = load_stress_cases()
    for case in cases:
        assert _STRESS_CASE_ID_RE.match(case.case_id), case.case_id


def test_all_rows_use_semantic_intent_axis():
    cases = load_stress_cases()
    assert {c.stress_axis for c in cases} == {"semantic_intent"}


def test_stress_subtypes_within_allowed():
    cases = load_stress_cases()
    assert {c.stress_subtype for c in cases}.issubset(ALLOWED_STRESS_SUBTYPES)


def test_dev_heldout_split_is_12_12_exactly():
    cases = load_stress_cases()
    dev = [c for c in cases if c.split == "dev"]
    heldout = [c for c in cases if c.split == "heldout"]
    assert len(dev) == EXPECTED_PER_SPLIT
    assert len(heldout) == EXPECTED_PER_SPLIT
    assert {c.split for c in cases} == ALLOWED_SPLITS
    assert all(c.case_id.startswith("S1D-") for c in dev)
    assert all(c.case_id.startswith("S1H-") for c in heldout)


# ---------------------------------------------------------------------------
# Inheritance from the locked Run 2 benchmark
# ---------------------------------------------------------------------------


def test_all_base_case_ids_exist_in_locked_benchmark():
    locked = {c.case_id for c in load_run2_cases(default_locked_benchmark_path())}
    cases = load_stress_cases()
    for case in cases:
        assert case.base_case_id in locked, (
            f"{case.case_id} references unknown base {case.base_case_id}"
        )


def test_inheritance_against_locked_benchmark():
    locked_df = pd.read_csv(
        default_locked_benchmark_path(), keep_default_na=False, dtype=str
    )
    locked_by_id = {row["case_id"]: dict(row) for _, row in locked_df.iterrows()}
    cases = load_stress_cases()
    for case in cases:
        base = locked_by_id[case.base_case_id]
        for col in INHERITED_COLUMNS:
            stress_val = (
                ";".join(getattr(case, col))
                if col in (
                    "expected_evidence_paths",
                    "expected_missing_fields",
                    "expected_warnings",
                    "expected_next_actions",
                )
                else getattr(case, col)
            )
            assert stress_val == base[col], (
                f"{case.case_id} disagrees with {case.base_case_id} on "
                f"{col!r}: {stress_val!r} vs {base[col]!r}"
            )


def test_canonical_prompt_matches_base_case_prompt():
    locked_df = pd.read_csv(
        default_locked_benchmark_path(), keep_default_na=False, dtype=str
    )
    locked_by_id = {row["case_id"]: dict(row) for _, row in locked_df.iterrows()}
    cases = load_stress_cases()
    for case in cases:
        assert case.canonical_prompt == locked_by_id[case.base_case_id]["prompt_text"]


def test_stress_prompt_differs_from_canonical_prompt():
    cases = load_stress_cases()
    for case in cases:
        assert case.prompt_text.strip() != case.canonical_prompt.strip(), (
            f"{case.case_id}: stress prompt equals canonical — no paraphrase"
        )


# ---------------------------------------------------------------------------
# Enum compliance (no new intent / answerability / behavior-class values)
# ---------------------------------------------------------------------------


def test_expected_intent_values_are_existing_enums():
    cases = load_stress_cases()
    allowed = CURRENT_INTENTS | PROPOSED_INTENTS
    for case in cases:
        assert case.expected_intent in allowed, (
            f"{case.case_id}: intent {case.expected_intent!r} is not in the "
            f"locked benchmark enum"
        )


def test_expected_answerability_values_are_existing_enums():
    cases = load_stress_cases()
    for case in cases:
        assert case.expected_answerability in ALLOWED_ANSWERABILITY


def test_expected_behavior_class_values_are_existing_enums():
    cases = load_stress_cases()
    for case in cases:
        assert case.expected_behavior_class in ALLOWED_BEHAVIOR_CLASSES


def test_validate_all_stress_cases_returns_no_errors():
    cases = load_stress_cases()
    report = validate_all_stress_cases(cases)
    assert report.n_errors == 0, report.errors_by_case


# ---------------------------------------------------------------------------
# Validator catches violations (synthetic mutations)
# ---------------------------------------------------------------------------


def test_validator_rejects_mismatched_inheritance(tmp_path: Path):
    """Mutating the stress CSV so its expected_intent differs from the
    base case's must surface as a loader/validator error."""
    src = default_cases_path()
    df = pd.read_csv(src, keep_default_na=False, dtype=str)
    # Pick the first row and flip its expected_intent to something
    # non-matching but still in the enum set.
    original = df.loc[0, "expected_intent"]
    df.loc[0, "expected_intent"] = (
        "objective_delta" if original != "objective_delta" else "feasibility_status"
    )
    bad_path = tmp_path / "bad_cases.csv"
    df.to_csv(bad_path, index=False)
    cases = load_stress_cases(bad_path)
    report = validate_all_stress_cases(cases)
    assert report.n_errors >= 1
    assert any(
        "inheritance violated" in msg
        for msgs in report.errors_by_case.values()
        for msg in msgs
    )


def test_validator_rejects_unknown_base_case_id(tmp_path: Path):
    src = default_cases_path()
    df = pd.read_csv(src, keep_default_na=False, dtype=str)
    df.loc[0, "base_case_id"] = "R2-999"
    bad_path = tmp_path / "bad_cases.csv"
    df.to_csv(bad_path, index=False)
    cases = load_stress_cases(bad_path)
    report = validate_all_stress_cases(cases)
    assert any(
        "not present in the locked" in msg
        for msgs in report.errors_by_case.values()
        for msg in msgs
    )


# ---------------------------------------------------------------------------
# Runner / scoring / report
# ---------------------------------------------------------------------------


def test_all_stress_payloads_materialize():
    cases = load_stress_cases()
    for case in cases:
        mat = materialize_case_payload(case.as_run2_case())
        assert mat.materialization_status == "materialized", (
            f"{case.case_id}: {mat.materialization_status} ({mat.warnings})"
        )


def test_system_c0_returns_predicted_contract_for_every_case():
    cases = load_stress_cases()
    for case in cases:
        mat = materialize_case_payload(case.as_run2_case())
        pred = run_system_c_on_materialized(case.as_run2_case(), mat)
        assert pred is not None, f"{case.case_id}: System C returned None"
        # The contract response should always populate the predicted_intent
        # field, even if the intent is `unknown`.
        assert pred.predicted_intent != ""


def test_score_case_returns_a_casescore_for_every_case():
    cases = load_stress_cases()
    for case in cases:
        mat = materialize_case_payload(case.as_run2_case())
        pred = run_system_c_on_materialized(case.as_run2_case(), mat)
        score = score_case(case.as_run2_case(), pred)
        assert 0.0 <= score.evidence_precision <= 1.0
        assert 0.0 <= score.evidence_recall <= 1.0


def test_run_system_c0_produces_24_results():
    artifacts = run_system_c0()
    assert len(artifacts.cases) == EXPECTED_TOTAL_CASES
    assert len(artifacts.results) == EXPECTED_TOTAL_CASES
    assert all(isinstance(r, StressCaseResult) for r in artifacts.results)


def test_aggregate_axis3_reports_expected_groups():
    artifacts = run_system_c0()
    aggs = aggregate_axis3(artifacts)
    assert aggs.overall.n == EXPECTED_TOTAL_CASES
    assert set(aggs.by_split.keys()) == {"dev", "heldout"}
    assert aggs.by_split["dev"].n == EXPECTED_PER_SPLIT
    assert aggs.by_split["heldout"].n == EXPECTED_PER_SPLIT
    # All subtypes that appear in cases.csv should appear in the
    # aggregate; the report has at least 4 subtypes.
    assert len(aggs.by_subtype) >= 4


def test_writer_emits_csv_and_markdown(tmp_path: Path):
    artifacts = run_system_c0()
    csv_path = tmp_path / "c0_baseline.csv"
    md_path = tmp_path / "c0_baseline.md"
    write_results_csv(artifacts, csv_path)
    write_baseline_markdown(artifacts, md_path)
    assert csv_path.exists() and csv_path.stat().st_size > 0
    assert md_path.exists() and md_path.stat().st_size > 0

    md_text = md_path.read_text(encoding="utf-8")
    assert "# R2-S1 Semantic Intent Stress" in md_text
    assert "semantic_intent_accuracy" in md_text
    assert "Downstream metrics conditional on intent correct" in md_text


def test_conditional_on_intent_correct_metrics_present():
    """When intent is correct, downstream contract response should be
    high-quality (this is the central claim of the report)."""
    artifacts = run_system_c0()
    aggs = aggregate_axis3(artifacts)
    cond = aggs.conditional_on_intent_correct
    # We do not assert exact thresholds (those drift if C0 changes);
    # we assert that the conditional metric is at least as high as the
    # overall metric. This is the qualitative claim the report makes.
    overall = aggs.overall
    assert cond.answerability_accuracy is not None
    assert overall.answerability_accuracy is not None
    assert cond.answerability_accuracy >= overall.answerability_accuracy
    assert cond.behavior_class_accuracy >= overall.behavior_class_accuracy


# ---------------------------------------------------------------------------
# Shared scatter emission (Path B closeout)
# ---------------------------------------------------------------------------


_AXIS3_SCATTER_PATH = (
    Path("product/evaluation/run2_stress/axis3_semantic/reports/scatter.csv")
)


def test_axis3_scatter_file_exists_and_validates():
    """After the Path B closeout, `reports/scatter.csv` must exist
    under axis3_semantic and must validate against the shared
    scatter schema."""
    assert _AXIS3_SCATTER_PATH.exists(), (
        f"axis3 scatter file missing at {_AXIS3_SCATTER_PATH}"
    )
    assert shared_validate_scatter_schema(_AXIS3_SCATTER_PATH) == []
    assert shared_validate_metric_names(_AXIS3_SCATTER_PATH) == []


def test_axis3_scatter_has_correct_shape():
    """24 cases × 10 metric names = 240 rows. Two metrics
    (`useful_refusal_correct` and `partial_answer_correct`) are
    inapplicable on every axis 3 case, so 48 rows carry null
    scores."""
    import pandas as pd

    df = pd.read_csv(_AXIS3_SCATTER_PATH, keep_default_na=False, dtype=str)
    assert list(df.columns) == SHARED_SCATTER_COLUMNS
    assert len(df) == EXPECTED_TOTAL_CASES * len(SHARED_METRIC_NAMES)
    assert set(df["axis"]) == {"axis3_semantic"}
    assert set(df["system"]) == {"c0"}
    assert set(df["split"]) == {"dev", "heldout"}
    # `band` carries the stress_subtype values.
    assert "schedule_synonym" in set(df["band"])
    # Every metric name in the canonical vocabulary appears.
    assert set(df["metric"]) == SHARED_METRIC_NAMES
    # Inapplicable metrics emit null scores; applicable ones do not.
    null_rows = df[df["score"] == ""]
    assert set(null_rows["metric"]) == {
        "useful_refusal_correct",
        "partial_answer_correct",
    }
    assert len(null_rows) == EXPECTED_TOTAL_CASES * 2


def test_axis3_scatter_carries_payload_chars_for_every_case():
    """`payload_chars` is computed from the materialized payload, so
    every case should carry a positive integer value (the payload
    serialises to non-zero JSON)."""
    import pandas as pd

    df = pd.read_csv(_AXIS3_SCATTER_PATH, keep_default_na=False, dtype=str)
    payload_chars = df["payload_chars"].unique()
    # The empty string would mean "no payload"; none of the 24 cases
    # should be in that state at closeout.
    assert "" not in set(payload_chars), (
        "axis 3 closeout expects every materialized case to carry payload_chars"
    )


def test_build_scatter_rows_returns_canonical_columns(tmp_path: Path):
    """Regenerating the scatter from a fresh run produces the same
    shape as the committed file (round-trip)."""
    artifacts = run_system_c0()
    rows = build_scatter_rows(artifacts)
    out = tmp_path / "scatter.csv"
    shared_write_scatter_csv(rows, out)
    assert shared_validate_scatter_schema(out) == []
    assert shared_validate_metric_names(out) == []


# ---------------------------------------------------------------------------
# Locked-benchmark integrity (no read-for-write)
# ---------------------------------------------------------------------------


def test_locked_benchmark_loader_still_works():
    """Sanity: the existing Run 2 loader is unaffected by axis3 additions."""
    cases = load_run2_cases(default_locked_benchmark_path())
    assert len(cases) >= 24  # Run 2 has 60 cases at HEAD; tolerate growth.
    assert all(c.case_id.startswith("R2-") for c in cases)
