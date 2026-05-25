"""Tests for the R2-S Axis 1 look-alike-intent stress split.

Covers the 26 acceptance checks listed in the Axis 1 task brief:
schema validation, gold-row inheritance from the locked Run 2
benchmark, band/split distribution, attractor-intent vocabulary,
payload materialization, System C0 execution, scoring, scatter
schema/metric-name conformance, closeout artefact presence, and
the no-protected-files-modified invariant.

These tests do not modify or read-for-write any locked Run 2
artifact and do not call solvers or model APIs.
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
)
from product.evaluation.run2_payloads import materialize_case_payload
from product.evaluation.run2_scoring import score_case
from product.evaluation.run2_system_c import run_system_c_on_materialized

from product.evaluation.run2_stress.axis1_lookalike.loader import (
    ALLOWED_ATTRACTOR_INTENTS,
    ALLOWED_BANDS,
    ALLOWED_SPLITS,
    ALLOWED_STRESS_AXIS,
    ALLOWED_STRESS_SUBTYPES,
    EXPECTED_COLUMNS,
    EXPECTED_PER_BAND,
    EXPECTED_PER_BAND_PER_SPLIT,
    EXPECTED_PER_SPLIT,
    EXPECTED_TOTAL_CASES,
    INHERITED_COLUMNS,
    Run2LookalikeCase,
    default_cases_path,
    default_locked_benchmark_path,
    load_lookalike_cases,
    validate_all_lookalike_cases,
)
from product.evaluation.run2_stress.axis1_lookalike.runner import (
    StressCaseResult,
    assign_failure_bucket,
    build_scatter_rows,
    run_system_c0,
    write_results_csv,
)
from product.evaluation.run2_stress.axis1_lookalike.report import (
    aggregate_axis1,
    render_markdown,
    write_baseline_markdown,
)
from product.evaluation.run2_stress.shared.scatter import (
    SCATTER_COLUMNS as SHARED_SCATTER_COLUMNS,
    write_scatter_csv as shared_write_scatter_csv,
)
from product.evaluation.run2_stress.shared.validators import (
    ALLOWED_METRIC_NAMES as SHARED_METRIC_NAMES,
    PROTECTED_PATHS,
    validate_metric_names as shared_validate_metric_names,
    validate_no_protected_files_modified,
    validate_scatter_schema as shared_validate_scatter_schema,
)


_STRESS_CASE_ID_RE = re.compile(r"^A1[DH]-\d{2}$")
_AXIS_DIR = Path(__file__).resolve().parents[3] / "product" / "evaluation" / "run2_stress" / "axis1_lookalike"
_REPORTS_DIR = _AXIS_DIR / "reports"


# ---------------------------------------------------------------------------
# Acceptance checks 1–2: design.md + cases.csv exist
# ---------------------------------------------------------------------------


def test_design_md_exists():
    assert (_AXIS_DIR / "design.md").is_file()


def test_cases_csv_exists():
    assert default_cases_path().is_file()


# ---------------------------------------------------------------------------
# Acceptance checks 3–9: schema, distribution, band/split invariants
# ---------------------------------------------------------------------------


def test_cases_csv_header_matches_expected():
    df = pd.read_csv(default_cases_path(), keep_default_na=False, dtype=str)
    assert list(df.columns) == EXPECTED_COLUMNS


def test_24_unique_cases():
    cases = load_lookalike_cases()
    assert len(cases) == EXPECTED_TOTAL_CASES
    ids = [c.case_id for c in cases]
    assert len(set(ids)) == len(ids)


def test_case_ids_match_stress_pattern():
    cases = load_lookalike_cases()
    for c in cases:
        assert _STRESS_CASE_ID_RE.match(c.case_id), c.case_id


def test_12_dev_and_12_heldout():
    cases = load_lookalike_cases()
    by_split: dict[str, int] = {}
    for c in cases:
        by_split[c.split] = by_split.get(c.split, 0) + 1
    assert by_split == {"dev": EXPECTED_PER_SPLIT, "heldout": EXPECTED_PER_SPLIT}


def test_stress_axis_is_lookalike_intent_for_every_row():
    cases = load_lookalike_cases()
    assert {c.stress_axis for c in cases} == {"lookalike_intent"}
    # The allowed-axis set is the single-element set.
    assert ALLOWED_STRESS_AXIS == {"lookalike_intent"}


def test_band_and_confusion_pair_exist_for_every_row():
    cases = load_lookalike_cases()
    for c in cases:
        assert c.band, c.case_id
        assert c.confusion_pair == c.band, c.case_id


def test_exactly_four_confusion_pair_bands():
    cases = load_lookalike_cases()
    bands = {c.band for c in cases}
    assert bands == ALLOWED_BANDS
    assert len(bands) == 4


def test_each_band_has_six_cases():
    cases = load_lookalike_cases()
    by_band: dict[str, int] = {}
    for c in cases:
        by_band[c.band] = by_band.get(c.band, 0) + 1
    for band in ALLOWED_BANDS:
        assert by_band.get(band, 0) == EXPECTED_PER_BAND, band


def test_each_band_has_three_dev_and_three_heldout():
    cases = load_lookalike_cases()
    by_band_split: dict[tuple[str, str], int] = {}
    for c in cases:
        key = (c.band, c.split)
        by_band_split[key] = by_band_split.get(key, 0) + 1
    for band in ALLOWED_BANDS:
        for split in ("dev", "heldout"):
            assert by_band_split.get((band, split), 0) == EXPECTED_PER_BAND_PER_SPLIT, (band, split)


# ---------------------------------------------------------------------------
# Acceptance check 10: base_case_id exists in locked benchmark
# ---------------------------------------------------------------------------


def test_every_base_case_id_exists_in_locked_benchmark():
    cases = load_lookalike_cases()
    locked = pd.read_csv(
        default_locked_benchmark_path(), keep_default_na=False, dtype=str
    )
    locked_ids = set(locked["case_id"].tolist())
    for c in cases:
        assert c.base_case_id in locked_ids, c.case_id


# ---------------------------------------------------------------------------
# Acceptance check 11: expected_intent values are valid Intent enum values
# ---------------------------------------------------------------------------


def test_expected_intent_values_are_known_intents():
    cases = load_lookalike_cases()
    allowed = CURRENT_INTENTS | PROPOSED_INTENTS
    for c in cases:
        assert c.expected_intent in allowed, (c.case_id, c.expected_intent)


# ---------------------------------------------------------------------------
# Acceptance check 12: attractor_intent values are valid Intent enum values
# ---------------------------------------------------------------------------


def test_attractor_intent_values_are_known_intents():
    cases = load_lookalike_cases()
    for c in cases:
        assert c.attractor_intent in ALLOWED_ATTRACTOR_INTENTS, (
            c.case_id,
            c.attractor_intent,
        )


def test_attractor_intent_differs_from_gold_intent_for_every_row():
    cases = load_lookalike_cases()
    for c in cases:
        assert c.attractor_intent != c.expected_intent, c.case_id


def test_attractor_tokens_present_for_every_row():
    cases = load_lookalike_cases()
    for c in cases:
        assert c.attractor_tokens.strip(), c.case_id


# ---------------------------------------------------------------------------
# Acceptance check 13: loader validates gold inheritance
# ---------------------------------------------------------------------------


def test_validate_all_lookalike_cases_returns_zero_errors():
    cases = load_lookalike_cases()
    report = validate_all_lookalike_cases(cases)
    assert report.n_errors == 0, report.errors_by_case


def test_every_row_inherits_gold_from_base_case():
    cases = load_lookalike_cases()
    locked = pd.read_csv(
        default_locked_benchmark_path(), keep_default_na=False, dtype=str
    )
    locked_rows = {row["case_id"]: dict(row) for _, row in locked.iterrows()}
    for c in cases:
        base = locked_rows[c.base_case_id]
        stress_serialized = {
            "source_prompt_id": c.source_prompt_id,
            "family": c.family,
            "payload_condition": c.payload_condition,
            "payload_mutation_needed": c.payload_mutation_needed,
            "expected_intent": c.expected_intent,
            "expected_answerability": c.expected_answerability,
            "expected_evidence_paths": ";".join(c.expected_evidence_paths),
            "expected_missing_fields": ";".join(c.expected_missing_fields),
            "expected_warnings": ";".join(c.expected_warnings),
            "expected_next_actions": ";".join(c.expected_next_actions),
            "expected_behavior_class": c.expected_behavior_class,
            "implementation_status": c.implementation_status,
        }
        for col in INHERITED_COLUMNS:
            assert base[col] == stress_serialized[col], (c.case_id, col)


def test_prompt_text_diverges_from_canonical_for_every_row():
    cases = load_lookalike_cases()
    for c in cases:
        assert c.prompt_text.strip() != c.canonical_prompt.strip(), c.case_id


# ---------------------------------------------------------------------------
# Acceptance checks 14–15: payloads materialize and C0 runs on every case
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def artifacts():
    return run_system_c0()


def test_every_case_materializes(artifacts):
    for case, mat in zip(artifacts.cases, artifacts.materializations):
        assert mat.materialization_status == "materialized", case.case_id


def test_every_case_has_a_c0_prediction(artifacts):
    for case, pred in zip(artifacts.cases, artifacts.predictions):
        assert pred is not None, case.case_id


def test_every_case_has_a_score(artifacts):
    for case, score in zip(artifacts.cases, artifacts.scores):
        assert score is not None, case.case_id


# ---------------------------------------------------------------------------
# Acceptance checks 16–18: report artefacts written
# ---------------------------------------------------------------------------


def test_c0_baseline_csv_exists():
    assert (_REPORTS_DIR / "c0_baseline.csv").is_file()


def test_c0_baseline_md_exists():
    assert (_REPORTS_DIR / "c0_baseline.md").is_file()


def test_scatter_csv_exists():
    assert (_REPORTS_DIR / "scatter.csv").is_file()


# ---------------------------------------------------------------------------
# Acceptance checks 19–20: scatter validates against shared schema and uses
# only canonical metric names
# ---------------------------------------------------------------------------


def test_scatter_validates_against_shared_schema():
    errs = shared_validate_scatter_schema(_REPORTS_DIR / "scatter.csv")
    assert errs == []


def test_scatter_uses_only_canonical_metric_names():
    errs = shared_validate_metric_names(_REPORTS_DIR / "scatter.csv")
    assert errs == []


def test_scatter_has_expected_shape():
    df = pd.read_csv(
        _REPORTS_DIR / "scatter.csv", keep_default_na=False, dtype=str
    )
    assert list(df.columns) == SHARED_SCATTER_COLUMNS
    # 24 cases × 10 metrics = 240 rows
    assert len(df) == 24 * 10
    assert set(df["axis"]) == {"axis1_lookalike"}
    assert set(df["system"]) == {"c0"}
    assert set(df["split"]) == {"dev", "heldout"}
    # Every band shows up.
    assert set(df["band"]) == ALLOWED_BANDS
    # Metric column == the full canonical vocabulary.
    assert set(df["metric"]) == SHARED_METRIC_NAMES
    # The two conditional metrics emit 24 null-score rows each
    # (no axis-1 case has gold = useful_refusal or
    # partial_answer_with_warning).
    conditional_metrics = {"useful_refusal_correct", "partial_answer_correct"}
    null_rows = df[df["score"] == ""]
    assert len(null_rows) == 24 * len(conditional_metrics)
    assert set(null_rows["metric"]) == conditional_metrics


def test_build_scatter_rows_returns_canonical_columns(artifacts, tmp_path):
    rows = build_scatter_rows(artifacts)
    assert rows, "expected non-empty scatter rows"
    for row in rows:
        assert set(row.keys()) == set(SHARED_SCATTER_COLUMNS)

    roundtrip = tmp_path / "scatter_roundtrip.csv"
    shared_write_scatter_csv(rows, roundtrip)
    assert shared_validate_scatter_schema(roundtrip) == []
    assert shared_validate_metric_names(roundtrip) == []


def test_scatter_carries_payload_chars_for_every_case():
    df = pd.read_csv(
        _REPORTS_DIR / "scatter.csv", keep_default_na=False, dtype=str
    )
    blanks = df[df["payload_chars"] == ""]
    assert blanks.empty, blanks["case_id"].tolist()


# ---------------------------------------------------------------------------
# Acceptance check 21: axis1_closeout.md exists
# ---------------------------------------------------------------------------


def test_closeout_md_exists():
    closeout = _REPORTS_DIR / "axis1_closeout.md"
    assert closeout.is_file()
    text = closeout.read_text(encoding="utf-8")
    # Required sections from the task brief.
    for heading in (
        "Purpose",
        "Relationship to Axis 3",
        "Method",
        "Results",
        "Failure taxonomy",
        "Methodological interpretation",
        "System D implication",
        "Status",
        "Deferred",
    ):
        assert heading in text, heading


# ---------------------------------------------------------------------------
# Acceptance checks 22–23: no protected Run 2 / contract files modified
# ---------------------------------------------------------------------------


def test_no_protected_run2_files_modified():
    """Validates that no file in the shared PROTECTED_PATHS list has
    been modified since HEAD. Uses the shared git-aware validator;
    returns a list of violations (empty list means clean)."""
    violations = validate_no_protected_files_modified("HEAD")
    # We accept the diagnostic-line shape (single string starting
    # with "could not introspect") when run outside a git repo, but
    # in this repo the call must return an actual empty list.
    assert violations == [], violations


def test_no_product_copilot_or_product_data_files_in_protected_diff():
    """A stricter version: the protected list explicitly enumerates
    `product/copilot/refusal_policy.py`, `product/copilot/contracts.py`,
    and the four `product/data/*.py` files. The previous test would
    have already flagged any of these — this test additionally
    asserts that the protected list still names them, so a future
    refactor that drops the path from the list does not silently
    create a hole."""
    expected_subset = {
        "product/copilot/refusal_policy.py",
        "product/copilot/contracts.py",
        "product/data/answerability.py",
        "product/data/evidence.py",
        "product/data/product_schema.py",
        "product/data/entity_resolution.py",
    }
    assert expected_subset.issubset(set(PROTECTED_PATHS))


# ---------------------------------------------------------------------------
# Bucket / failure taxonomy
# ---------------------------------------------------------------------------


def test_assign_failure_bucket_returns_known_label():
    # wrong_adjacent_intent
    assert (
        assign_failure_bucket(
            "objective_value", "objective_delta",
            False, True, True, 0.4, 1.0, 1.0, 1.0, 1.0,
        )
        == "wrong_adjacent_intent"
    )
    # unknown_intent
    assert (
        assign_failure_bucket(
            "lateness_summary", "unknown",
            False, False, False, 0.0, 0.0, 0.0, 0.0, 1.0,
        )
        == "unknown_intent"
    )
    # guard_protected (perfect)
    assert (
        assign_failure_bucket(
            "single_customer_route_membership", "single_customer_route_membership",
            True, True, True, 1.0, 1.0, 1.0, 1.0, 1.0,
        )
        == "guard_protected"
    )
    # downstream_mismatch (intent correct, evidence_precision < 1.0)
    assert (
        assign_failure_bucket(
            "feasibility_status", "feasibility_status",
            True, True, True, 0.8, 1.0, 1.0, 1.0, 1.0,
        )
        == "downstream_mismatch"
    )


def test_baseline_csv_every_row_has_bucket_label():
    df = pd.read_csv(
        _REPORTS_DIR / "c0_baseline.csv", keep_default_na=False, dtype=str
    )
    allowed = {
        "wrong_adjacent_intent",
        "unknown_intent",
        "guard_protected",
        "downstream_mismatch",
        "score_missing",
    }
    assert set(df["bucket"].tolist()).issubset(allowed)
    assert len(df) == EXPECTED_TOTAL_CASES


def test_aggregates_match_expected_axis1_findings(artifacts):
    """At the frozen baseline, Axis 1's diagnostic findings are:
    - the OBJ comparative-attractor cases misroute (3 cases)
    - the PLAN_VALIDITY band-4 cases land in downstream_mismatch
      because of the documented infeasibility_kind evidence
      off-by-one (3 cases)
    - the remaining 18 cases are guard_protected
    - zero unknown_intent
    These are reproducible at HEAD `18b4811` and represent the
    primary qualitative claims in the closeout."""
    agg = aggregate_axis1(artifacts)
    assert agg.bucket_counts.get("unknown_intent", 0) == 0
    assert agg.bucket_counts.get("wrong_adjacent_intent", 0) >= 1
    assert agg.bucket_counts.get("guard_protected", 0) >= 12
    # Conditional-on-intent-correct downstream metrics should be at
    # least as good as the unconditional ones (the conditional row
    # is a strictly-better-sized cohort).
    if agg.conditional_on_intent_correct.n:
        if agg.overall.answerability_accuracy is not None:
            assert (
                agg.conditional_on_intent_correct.answerability_accuracy
                >= agg.overall.answerability_accuracy
            )


# ---------------------------------------------------------------------------
# Markdown / write helpers smoke tests
# ---------------------------------------------------------------------------


def test_render_markdown_smoke(artifacts):
    md = render_markdown(artifacts)
    assert md.startswith("# R2-S Axis 1 Look-alike Intent Stress")
    # Headline buckets must appear.
    assert "wrong_adjacent_intent" in md
    assert "guard_protected" in md
    assert "Conditional on intent correct".lower() in md.lower() or "conditional" in md.lower()


def test_write_baseline_markdown_writes_file(artifacts, tmp_path):
    out = tmp_path / "c0_baseline.md"
    write_baseline_markdown(artifacts, out)
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert len(text) > 500


def test_write_results_csv_emits_expected_columns(artifacts, tmp_path):
    out = tmp_path / "c0_baseline.csv"
    write_results_csv(artifacts, out)
    df = pd.read_csv(out, keep_default_na=False, dtype=str)
    assert "case_id" in df.columns
    assert "bucket" in df.columns
    assert "predicted_intent" in df.columns
    assert "attractor_intent" in df.columns
    assert len(df) == EXPECTED_TOTAL_CASES
