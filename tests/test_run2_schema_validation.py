"""Tests for validate_case + validate_all_cases.

The canonical 15-row CSV must pass validation with zero errors; every
disallowed-shape rule in run2_gold_schema.md §13 has at least one
negative test below.
"""
from __future__ import annotations

import dataclasses

from product.evaluation.run2_case_loader import (
    Run2Case,
    default_cases_path,
    load_run2_cases,
    validate_all_cases,
    validate_case,
)


# ---------------------------------------------------------------------------
# Whole-file integration check
# ---------------------------------------------------------------------------


def test_calibration_csv_validates_clean():
    cases = load_run2_cases(default_cases_path())
    report = validate_all_cases(cases)
    assert report.n_cases == 15
    assert report.n_errors == 0, f"unexpected errors: {report.errors_by_case}"
    # Distribution sanity (mirrors R2-0 final report)
    assert report.distributions["family"] == {
        "OBJ": 4,
        "PLAN_VALIDITY": 2,
        "STRUCT": 5,
        "SCHEDULE": 4,
    }
    assert report.distributions["implementation_status"] == {
        "current": 9,
        "target_extension": 6,
    }
    assert report.distributions["expected_behavior_class"] == {
        "direct_answer": 6,
        "direct_answer_with_warning": 2,
        "partial_answer_with_warning": 2,
        "useful_refusal": 5,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_direct_answer_case() -> Run2Case:
    return Run2Case(
        case_id="R2-999",
        source_prompt_id="",
        family="OBJ",
        prompt_text="test",
        payload_condition="clean",
        payload_mutation_needed="none",
        expected_intent="objective_value",
        expected_answerability="answerable",
        expected_evidence_paths=["action_objective"],
        expected_missing_fields=[],
        expected_warnings=[],
        expected_next_actions=[],
        expected_behavior_class="direct_answer",
        implementation_status="current",
        difficulty="easy",
        label_rationale="test rationale",
    )


def _mutate(case: Run2Case, **kw) -> Run2Case:
    return dataclasses.replace(case, **kw)


# ---------------------------------------------------------------------------
# Disallowed-shape negative tests
# ---------------------------------------------------------------------------


def test_invalid_case_id_format():
    case = _mutate(_base_direct_answer_case(), case_id="abc")
    errs = validate_case(case)
    assert any("case_id" in e for e in errs)


def test_unknown_family():
    case = _mutate(_base_direct_answer_case(), family="OBJX")
    errs = validate_case(case)
    assert any("family" in e for e in errs)


def test_unknown_payload_condition():
    case = _mutate(_base_direct_answer_case(), payload_condition="bogus")
    errs = validate_case(case)
    assert any("payload_condition" in e for e in errs)


def test_proposed_intent_requires_target_extension():
    case = _mutate(
        _base_direct_answer_case(),
        family="STRUCT",
        expected_intent="full_route_listing",
        # implementation_status still "current" → should error
    )
    errs = validate_case(case)
    assert any("proposed intent" in e for e in errs)


def test_proposed_warning_requires_target_extension():
    case = _mutate(
        _base_direct_answer_case(),
        expected_behavior_class="direct_answer_with_warning",
        expected_intent="objective_delta",
        expected_warnings=["comparison_referent_ambiguity"],
    )
    errs = validate_case(case)
    assert any("proposed warning" in e for e in errs)


def test_proposed_next_action_requires_target_extension():
    case = _mutate(
        _base_direct_answer_case(),
        expected_behavior_class="useful_refusal",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_next_actions=["expose_units_objective"],
    )
    errs = validate_case(case)
    assert any("proposed next_action" in e for e in errs)


def test_answerable_with_missing_fields_rejected():
    case = _mutate(
        _base_direct_answer_case(),
        expected_missing_fields=["something"],
    )
    errs = validate_case(case)
    assert any("answerable rows cannot have non-empty" in e for e in errs)


def test_direct_answer_with_warning_requires_warnings():
    case = _mutate(
        _base_direct_answer_case(),
        expected_behavior_class="direct_answer_with_warning",
    )
    errs = validate_case(case)
    assert any(
        "direct_answer_with_warning requires non-empty expected_warnings" in e
        for e in errs
    )


def test_direct_answer_must_have_no_warnings():
    case = _mutate(
        _base_direct_answer_case(),
        expected_warnings=["route_indexing_ambiguity"],
    )
    errs = validate_case(case)
    assert any("direct_answer requires empty expected_warnings" in e for e in errs)


def test_partial_answer_with_warning_full_shape_required():
    # Only the behavior_class label is set; other required fields missing.
    case = _mutate(
        _base_direct_answer_case(),
        expected_behavior_class="partial_answer_with_warning",
    )
    errs = validate_case(case)
    # Should flag answerability, warnings, missing, next_actions, and evidence
    # presence on partial_answer_with_warning rows.
    joined = " | ".join(errs)
    assert "partial_answer_with_warning requires expected_answerability" in joined
    assert "non-empty expected_warnings" in joined
    assert "non-empty expected_missing_fields" in joined
    assert "non-empty expected_next_actions" in joined


def test_useful_refusal_cannot_be_answerable():
    case = _mutate(
        _base_direct_answer_case(),
        expected_behavior_class="useful_refusal",
        expected_next_actions=["narrow_question_to_available_field"],
        # answerability still "answerable" → should error
    )
    errs = validate_case(case)
    assert any("useful_refusal cannot pair with answerable" in e for e in errs)


def test_useful_refusal_requires_next_actions():
    case = _mutate(
        _base_direct_answer_case(),
        expected_answerability="not_answerable",
        expected_behavior_class="useful_refusal",
    )
    errs = validate_case(case)
    assert any(
        "useful_refusal requires non-empty expected_next_actions" in e for e in errs
    )


def test_false_premise_condition_requires_paired_warning_and_action():
    case = _mutate(
        _base_direct_answer_case(),
        family="SCHEDULE",
        prompt_text="when does the driver reach customer 999?",
        payload_condition="false_premise_customer",
        expected_intent="customer_arrival",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        # warning + next action intentionally left blank
        expected_behavior_class="useful_refusal",
        implementation_status="target_extension",
        difficulty="hard",
    )
    errs = validate_case(case)
    joined = " | ".join(errs)
    assert "false_premise_detected" in joined
    assert "clarify_false_premise" in joined


def test_false_premise_warning_requires_false_premise_condition():
    case = _mutate(
        _base_direct_answer_case(),
        family="SCHEDULE",
        prompt_text="test",
        payload_condition="clean",
        expected_intent="customer_arrival",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_warnings=["false_premise_detected"],
        expected_next_actions=["clarify_false_premise"],
        expected_behavior_class="useful_refusal",
        implementation_status="target_extension",
        difficulty="hard",
    )
    errs = validate_case(case)
    assert any(
        "false_premise_detected requires a false_premise_*" in e for e in errs
    )


def test_comparison_referent_warning_restricted_to_obj_delta():
    case = _mutate(
        _base_direct_answer_case(),
        family="STRUCT",
        expected_intent="route_count",
        expected_warnings=["comparison_referent_ambiguity"],
        implementation_status="target_extension",
        expected_behavior_class="direct_answer_with_warning",
    )
    errs = validate_case(case)
    assert any(
        "comparison_referent_ambiguity requires family=OBJ" in e for e in errs
    )


def test_predicate_pinned_evidence_path_rejected():
    case = _mutate(
        _base_direct_answer_case(),
        expected_evidence_paths=["route_end_times[route_idx=0].end_time"],
    )
    errs = validate_case(case)
    assert any("predicate-pinned evidence path" in e for e in errs)


def test_missing_label_rationale_rejected():
    case = _mutate(_base_direct_answer_case(), label_rationale="")
    errs = validate_case(case)
    assert any("label_rationale" in e for e in errs)


def test_unknown_warning_code_rejected():
    case = _mutate(
        _base_direct_answer_case(),
        expected_behavior_class="direct_answer_with_warning",
        expected_warnings=["totally_made_up_warning"],
    )
    errs = validate_case(case)
    assert any("unknown warning" in e for e in errs)
