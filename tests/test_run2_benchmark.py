"""Tests for the 60-case Run 2 benchmark CSV.

These tests run against the canonical
`product/evaluation/run2_benchmark_cases.csv` and pin the R2-2
acceptance criteria from the expansion plan: 60 rows, 0 schema
errors, 60/60 materialize, no rationale-text seed inference, and
the planned family / behavior_class / impl_status distribution.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from product.evaluation.run2_case_loader import (
    Run2Case,
    load_run2_cases,
    validate_all_cases,
)
from product.evaluation.run2_payloads import (
    _find_generator_jsonl,
    materialize_all_cases,
)
from product.evaluation.run2_scoring import aggregate_scores, score_case
from product.evaluation.run2_system_c import run_system_c_on_materialized


def _benchmark_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "product"
        / "evaluation"
        / "run2_benchmark_cases.csv"
    )


try:
    _find_generator_jsonl("full-run-v1")
except FileNotFoundError as exc:
    pytest.skip(
        f"Run 1 generator JSONL not found: {exc}", allow_module_level=True
    )


# ---------------------------------------------------------------------------
# Load + schema
# ---------------------------------------------------------------------------


def test_benchmark_loads_60_rows():
    cases = load_run2_cases(_benchmark_path())
    assert len(cases) == 60
    assert all(isinstance(c, Run2Case) for c in cases)


def test_benchmark_validates_with_zero_errors():
    cases = load_run2_cases(_benchmark_path())
    report = validate_all_cases(cases)
    assert report.n_errors == 0, f"unexpected errors: {report.errors_by_case}"
    assert report.n_cases == 60


def test_benchmark_family_distribution_matches_plan():
    cases = load_run2_cases(_benchmark_path())
    report = validate_all_cases(cases)
    assert report.distributions["family"] == {
        "OBJ": 15,
        "PLAN_VALIDITY": 12,
        "STRUCT": 18,
        "SCHEDULE": 15,
    }


def test_benchmark_implementation_status_within_target_bands():
    cases = load_run2_cases(_benchmark_path())
    report = validate_all_cases(cases)
    dist = report.distributions["implementation_status"]
    # Plan target: current 35-40, target_extension 20-25
    assert 35 <= dist["current"] <= 40, dist
    assert 20 <= dist["target_extension"] <= 25, dist
    assert dist["current"] + dist["target_extension"] == 60


def test_benchmark_behavior_class_distribution_reasonable():
    cases = load_run2_cases(_benchmark_path())
    report = validate_all_cases(cases)
    dist = report.distributions["expected_behavior_class"]
    assert sum(dist.values()) == 60
    # Every class is represented
    assert set(dist.keys()) == {
        "direct_answer",
        "direct_answer_with_warning",
        "partial_answer_with_warning",
        "useful_refusal",
    }
    # No class dominates (no class > 35)
    assert max(dist.values()) <= 35


def test_benchmark_difficulty_distribution_within_target_bands():
    cases = load_run2_cases(_benchmark_path())
    report = validate_all_cases(cases)
    dist = report.distributions["difficulty"]
    assert 18 <= dist["easy"] <= 22, dist  # target 18-20, ±2 slack
    assert 23 <= dist["medium"] <= 30, dist  # target 25-28, ±2 slack
    assert 10 <= dist["hard"] <= 17, dist  # target 12-15, ±2 slack
    assert sum(dist.values()) == 60


# ---------------------------------------------------------------------------
# Source-prompt-id coverage
# ---------------------------------------------------------------------------


def test_benchmark_every_case_has_explicit_source_prompt_id():
    """R2-2 acceptance criterion: no rationale-text source inference.
    Every case must bind to a seed via the CSV column directly."""
    cases = load_run2_cases(_benchmark_path())
    empty = [c.case_id for c in cases if not c.source_prompt_id]
    assert empty == [], f"cases without source_prompt_id: {empty}"


def test_benchmark_source_prompt_ids_all_resolve_to_run1_prompts():
    """All seeds must be among the 48 Run 1 prompt IDs (001..048).
    Catches typos like '047a' or '01' that would silently load nothing."""
    cases = load_run2_cases(_benchmark_path())
    valid = {f"{i:03d}" for i in range(1, 49)}
    bad = [c.case_id for c in cases if c.source_prompt_id not in valid]
    assert bad == [], f"cases with non-Run-1 source_prompt_id: {bad}"


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------


def test_benchmark_all_60_cases_materialize():
    cases = load_run2_cases(_benchmark_path())
    mats, summary = materialize_all_cases(cases)
    assert summary.counts.get("materialized", 0) == 60
    assert summary.counts.get("skipped_no_seed", 0) == 0
    assert summary.counts.get("error", 0) == 0


def test_benchmark_has_no_rationale_inferred_seeds():
    """R2-2 acceptance criterion: the rationale-text inference path
    is not exercised by any benchmark case."""
    cases = load_run2_cases(_benchmark_path())
    mats, _ = materialize_all_cases(cases)
    inferred = [
        m.case_id
        for m in mats
        if any("seed inferred from" in w for w in m.warnings)
    ]
    assert inferred == [], f"rationale-inferred cases: {inferred}"


# ---------------------------------------------------------------------------
# Proposed-code constraints (schema §13) survive expansion
# ---------------------------------------------------------------------------


def test_benchmark_proposed_codes_only_appear_with_target_extension():
    cases = load_run2_cases(_benchmark_path())
    PROPOSED_INTENTS = {"full_route_listing"}
    PROPOSED_WARNINGS = {
        "false_premise_detected",
        "comparison_referent_ambiguity",
        "evidence_units_missing",
    }
    PROPOSED_ACTIONS = {
        "clarify_false_premise",
        "use_validity_payload",
        "expose_reference_solution_objective",
        "expose_units_objective",
    }
    bad: list[str] = []
    for c in cases:
        if c.implementation_status == "target_extension":
            continue
        if c.expected_intent in PROPOSED_INTENTS:
            bad.append(f"{c.case_id}: proposed intent on current row")
        if set(c.expected_warnings) & PROPOSED_WARNINGS:
            bad.append(f"{c.case_id}: proposed warning on current row")
        if set(c.expected_next_actions) & PROPOSED_ACTIONS:
            bad.append(f"{c.case_id}: proposed action on current row")
    assert bad == [], bad


# ---------------------------------------------------------------------------
# System C: current rows must be regression-free
# ---------------------------------------------------------------------------


def test_benchmark_current_rows_score_perfectly_on_component_metrics():
    """The R2-2 expansion gate: no current row may fail intent /
    answerability / behavior_class. evidence_recall and warning_recall
    must be 1.0 on every current row (gold + contract are aligned)."""
    cases = load_run2_cases(_benchmark_path())
    mats, _ = materialize_all_cases(cases)
    mats_by = {m.case_id: m for m in mats}
    failures: list[str] = []
    for c in cases:
        if c.implementation_status != "current":
            continue
        pred = run_system_c_on_materialized(c, mats_by[c.case_id])
        assert pred is not None, c.case_id
        s = score_case(c, pred)
        reasons: list[str] = []
        if not s.intent_correct:
            reasons.append("intent")
        if not s.answerability_correct:
            reasons.append("answerability")
        if not s.behavior_class_correct:
            reasons.append("behavior_class")
        if s.evidence_recall < 1.0 and c.expected_evidence_paths:
            reasons.append("evidence_recall")
        if (
            c.expected_behavior_class in {"direct_answer", "direct_answer_with_warning"}
            and s.warning_recall < 1.0
        ):
            reasons.append("warning_recall")
        if reasons:
            failures.append(f"{c.case_id} ({', '.join(reasons)})")
    assert failures == [], f"current-row failures: {failures}"


def test_benchmark_aggregate_split_by_implementation_status():
    """Aggregation surface preserved: current vs target_extension
    are always reported separately and no composite is added."""
    cases = load_run2_cases(_benchmark_path())
    mats, _ = materialize_all_cases(cases)
    mats_by = {m.case_id: m for m in mats}
    scores = []
    for c in cases:
        pred = run_system_c_on_materialized(c, mats_by[c.case_id])
        if pred is not None:
            scores.append(score_case(c, pred))
    agg = aggregate_scores(scores)
    # Both partitions must exist
    assert "current" in agg["by_implementation_status"]
    assert "target_extension" in agg["by_implementation_status"]
    # No composite key
    forbidden = {"composite", "composite_score", "headline", "aggregate_composite"}
    for group in agg.values():
        if isinstance(group, dict):
            assert not (set(group.keys()) & forbidden), group
