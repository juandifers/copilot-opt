"""Tests for the pass^k aggregation in `run2_passk_report`.

The runner itself makes live API calls and is not exercised here; the
metric layer is pure aggregation over the `scored.jsonl` shape that
`run2_passk_runner._score_replicate` writes.
"""
from __future__ import annotations

from product.evaluation.run2_case_loader import Run2Case
from product.evaluation.run2_passk_report import (
    classify_stability,
    compute_case_reliability,
)


def _direct_answer_case() -> Run2Case:
    return Run2Case(
        case_id="R2-TEST-DA",
        source_prompt_id="001",
        family="OBJ",
        prompt_text="placeholder",
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
        label_rationale="test fixture",
    )


def _useful_refusal_case() -> Run2Case:
    return Run2Case(
        case_id="R2-TEST-UR",
        source_prompt_id="007",
        family="SCHEDULE",
        prompt_text="placeholder",
        payload_condition="false_premise_customer",
        payload_mutation_needed="none",
        expected_intent="customer_arrival",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        expected_warnings=["false_premise_detected"],
        expected_next_actions=["clarify_false_premise"],
        expected_behavior_class="useful_refusal",
        implementation_status="target_extension",
        difficulty="hard",
        label_rationale="test fixture",
    )


def _all_pass_row(case_id: str, rep: int, ur: bool | None = None) -> dict:
    return {
        "case_id": case_id,
        "replicate_id": rep,
        "parse_status": "parsed",
        "intent_correct": True,
        "answerability_correct": True,
        "behavior_class_correct": True,
        "evidence_precision": 1.0,
        "evidence_recall": 1.0,
        "warning_precision": 1.0,
        "warning_recall": 1.0,
        "missing_field_recall": 1.0,
        "useful_refusal_correct": ur,
        "partial_answer_correct": None,
        "all_components_pass": True,
    }


def _fail_intent_row(case_id: str, rep: int) -> dict:
    return {
        "case_id": case_id,
        "replicate_id": rep,
        "parse_status": "parsed",
        "intent_correct": False,
        "answerability_correct": False,
        "behavior_class_correct": False,
        "evidence_precision": 0.5,
        "evidence_recall": 1.0,
        "warning_precision": 0.0,
        "warning_recall": 0.0,
        "missing_field_recall": 1.0,
        "useful_refusal_correct": None,
        "partial_answer_correct": None,
        "all_components_pass": False,
    }


def test_stable_success_classifies_correctly():
    case = _direct_answer_case()
    rows = [_all_pass_row("R2-TEST-DA", i) for i in range(5)]
    rel = compute_case_reliability(case, rows)
    assert rel.n_replicates == 5
    assert rel.n_parsed == 5
    assert rel.intent_correct_rate == 1.0
    assert rel.all_components_pass_rate == 1.0
    assert rel.pass_at_k_any is True
    assert rel.pass_to_the_k_all is True
    assert classify_stability(rel) == "stable_success"


def test_stable_failure_classifies_correctly():
    case = _direct_answer_case()
    rows = [_fail_intent_row("R2-TEST-DA", i) for i in range(5)]
    rel = compute_case_reliability(case, rows)
    assert rel.all_components_pass_rate == 0.0
    assert rel.pass_at_k_any is False
    assert rel.pass_to_the_k_all is False
    assert classify_stability(rel) == "stable_failure"
    assert rel.intent_correct_rate == 0.0


def test_flaky_case_classifies_correctly():
    case = _direct_answer_case()
    rows = [_all_pass_row("R2-TEST-DA", 0), _fail_intent_row("R2-TEST-DA", 1),
            _all_pass_row("R2-TEST-DA", 2), _fail_intent_row("R2-TEST-DA", 3),
            _fail_intent_row("R2-TEST-DA", 4)]
    rel = compute_case_reliability(case, rows)
    assert 0.0 < rel.all_components_pass_rate < 1.0
    assert rel.pass_at_k_any is True
    assert rel.pass_to_the_k_all is False
    assert classify_stability(rel) == "flaky"


def test_useful_refusal_rate_aggregated_when_applicable():
    case = _useful_refusal_case()
    rows = [
        _all_pass_row("R2-TEST-UR", 0, ur=True),
        _all_pass_row("R2-TEST-UR", 1, ur=True),
        _all_pass_row("R2-TEST-UR", 2, ur=False),
    ]
    # Force one row's all_components_pass to False so the composite divides cleanly.
    rows[2]["all_components_pass"] = False
    rel = compute_case_reliability(case, rows)
    # 2 of 3 applicable useful_refusal_correct rows are True.
    assert rel.useful_refusal_correct_rate is not None
    assert abs(rel.useful_refusal_correct_rate - (2 / 3)) < 1e-9


def test_useful_refusal_rate_is_none_for_direct_answer():
    case = _direct_answer_case()
    rows = [_all_pass_row("R2-TEST-DA", i) for i in range(5)]
    rel = compute_case_reliability(case, rows)
    assert rel.useful_refusal_correct_rate is None
    assert rel.partial_answer_correct_rate is None


def test_parse_failures_count_correctly():
    case = _direct_answer_case()
    rows = [_all_pass_row("R2-TEST-DA", i) for i in range(3)]
    rows.append(
        {
            "case_id": "R2-TEST-DA",
            "replicate_id": 3,
            "parse_status": "invalid_json",
            "intent_correct": False,
            "answerability_correct": False,
            "behavior_class_correct": False,
            "evidence_precision": 0.0,
            "evidence_recall": 0.0,
            "warning_precision": 0.0,
            "warning_recall": 0.0,
            "missing_field_recall": 0.0,
            "useful_refusal_correct": None,
            "partial_answer_correct": None,
            "all_components_pass": False,
        }
    )
    rel = compute_case_reliability(case, rows)
    assert rel.n_replicates == 4
    assert rel.n_parsed == 3
    assert rel.all_components_pass_rate == 0.75
    assert rel.pass_to_the_k_all is False
