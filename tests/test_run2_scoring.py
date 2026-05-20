"""Tests for product/evaluation/run2_scoring.py."""
from __future__ import annotations

import math

from product.evaluation.run2_case_loader import Run2Case
from product.evaluation.run2_scoring import (
    aggregate_scores,
    normalize_field_path,
    normalize_paths,
    score_case,
    set_precision,
    set_recall,
)
from product.evaluation.run2_system_c import PredictedContract


# ---------------------------------------------------------------------------
# Path normalisation
# ---------------------------------------------------------------------------


def test_normalize_strips_route_idx_predicate():
    assert (
        normalize_field_path("routes[route_idx=4].customer_ids")
        == "routes[].customer_ids"
    )


def test_normalize_strips_customer_id_predicate():
    assert (
        normalize_field_path("customer_schedule[customer_id=42].arrival")
        == "customer_schedule[].arrival"
    )


def test_normalize_keeps_plain_paths_unchanged():
    assert normalize_field_path("action_objective") == "action_objective"
    assert normalize_field_path("units.objective") == "units.objective"
    assert (
        normalize_field_path("routes[].customer_ids") == "routes[].customer_ids"
    )


def test_normalize_paths_deduplicates_after_stripping():
    paths = {
        "routes[route_idx=4].customer_ids",
        "routes[route_idx=2].customer_ids",
    }
    assert normalize_paths(paths) == {"routes[].customer_ids"}


# ---------------------------------------------------------------------------
# set_precision / set_recall edge cases
# ---------------------------------------------------------------------------


def test_set_precision_both_empty_is_one():
    assert set_precision(set(), set()) == 1.0


def test_set_precision_predicted_empty_gold_non_empty_is_zero():
    assert set_precision(set(), {"a"}) == 0.0


def test_set_precision_gold_empty_predicted_non_empty_is_zero():
    assert set_precision({"a"}, set()) == 0.0


def test_set_precision_partial_overlap():
    assert math.isclose(set_precision({"a", "b"}, {"a"}), 0.5)


def test_set_recall_both_empty_is_one():
    assert set_recall(set(), set()) == 1.0


def test_set_recall_gold_empty_is_one():
    assert set_recall({"a"}, set()) == 1.0


def test_set_recall_partial_overlap():
    assert math.isclose(set_recall({"a"}, {"a", "b"}), 0.5)


# ---------------------------------------------------------------------------
# Per-case scoring
# ---------------------------------------------------------------------------


def _gold(case_kwargs):
    base = dict(
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
        label_rationale="t",
        ambiguity_notes="",
    )
    base.update(case_kwargs)
    return Run2Case(**base)


def _pred(**kwargs):
    base = dict(
        case_id="R2-999",
        predicted_intent="objective_value",
        predicted_answerability="answerable",
        predicted_evidence_paths=["action_objective"],
        predicted_missing_fields=[],
        predicted_warnings=[],
        predicted_next_actions=[],
        predicted_behavior_class="direct_answer",
    )
    base.update(kwargs)
    return PredictedContract(**base)


def test_exact_match_scores_perfect():
    case = _gold({})
    pred = _pred()
    s = score_case(case, pred)
    assert s.intent_correct
    assert s.answerability_correct
    assert s.evidence_precision == 1.0
    assert s.evidence_recall == 1.0
    assert s.behavior_class_correct
    assert s.useful_refusal_correct is None  # not applicable
    assert s.partial_answer_correct is None


def test_intent_mismatch_is_flagged():
    case = _gold({})
    pred = _pred(predicted_intent="objective_delta")
    s = score_case(case, pred)
    assert not s.intent_correct


def test_evidence_paths_are_normalized_before_matching():
    case = _gold(
        {
            "expected_intent": "customer_arrival",
            "family": "SCHEDULE",
            "expected_evidence_paths": [
                "customer_schedule[].customer_id",
                "customer_schedule[].arrival",
            ],
        }
    )
    pred = _pred(
        predicted_intent="customer_arrival",
        predicted_evidence_paths=[
            "customer_schedule[customer_id=42].customer_id",
            "customer_schedule[customer_id=42].arrival",
        ],
    )
    s = score_case(case, pred)
    assert s.evidence_precision == 1.0
    assert s.evidence_recall == 1.0


def test_useful_refusal_correct_only_evaluated_when_gold_is_useful_refusal():
    case = _gold(
        {
            "expected_answerability": "not_answerable",
            "expected_evidence_paths": [],
            "expected_missing_fields": ["baseline_solution", "diff"],
            "expected_warnings": ["unsupported_comparison"],
            "expected_next_actions": ["build_baseline_comparison_payload"],
            "expected_behavior_class": "useful_refusal",
        }
    )
    pred = _pred(
        predicted_answerability="not_answerable",
        predicted_evidence_paths=[],
        predicted_missing_fields=["baseline_solution", "diff"],
        predicted_warnings=["unsupported_comparison"],
        predicted_next_actions=["build_baseline_comparison_payload"],
        predicted_behavior_class="useful_refusal",
    )
    s = score_case(case, pred)
    assert s.useful_refusal_correct is True
    assert s.partial_answer_correct is None


def test_useful_refusal_correct_allows_empty_missing_when_gold_is_empty():
    # Schema §12 false-premise exception.
    case = _gold(
        {
            "family": "SCHEDULE",
            "payload_condition": "false_premise_customer",
            "expected_intent": "customer_arrival",
            "expected_answerability": "not_answerable",
            "expected_evidence_paths": [],
            "expected_missing_fields": [],
            "expected_warnings": ["false_premise_detected"],
            "expected_next_actions": ["clarify_false_premise"],
            "expected_behavior_class": "useful_refusal",
            "implementation_status": "target_extension",
        }
    )
    pred = _pred(
        predicted_intent="customer_arrival",
        predicted_answerability="not_answerable",
        predicted_evidence_paths=[],
        predicted_missing_fields=[],
        predicted_warnings=["false_premise_detected"],
        predicted_next_actions=["clarify_false_premise"],
        predicted_behavior_class="useful_refusal",
    )
    s = score_case(case, pred)
    assert s.useful_refusal_correct is True


def test_partial_answer_correct_evaluated_distinctly():
    case = _gold(
        {
            "expected_intent": "objective_delta",
            "expected_answerability": "partially_answerable",
            "expected_evidence_paths": ["action_objective"],
            "expected_missing_fields": ["reference_solution.objective"],
            "expected_warnings": ["comparison_referent_ambiguity"],
            "expected_next_actions": ["expose_reference_solution_objective"],
            "expected_behavior_class": "partial_answer_with_warning",
            "implementation_status": "target_extension",
            "difficulty": "hard",
        }
    )
    pred = _pred(
        predicted_intent="objective_delta",
        predicted_answerability="partially_answerable",
        predicted_evidence_paths=["action_objective"],
        predicted_missing_fields=["reference_solution.objective"],
        predicted_warnings=["comparison_referent_ambiguity"],
        predicted_next_actions=["expose_reference_solution_objective"],
        predicted_behavior_class="partial_answer_with_warning",
    )
    s = score_case(case, pred)
    assert s.partial_answer_correct is True
    assert s.useful_refusal_correct is None


def test_predicted_concrete_next_action_string_normalises_to_semantic_code():
    # The current contract emits the literal "Expose perturbation.new_customer_ids
    # in the product payload." string. Gold uses the semantic code
    # `expose_new_customer_ids`. The scorer must match them.
    case = _gold(
        {
            "family": "STRUCT",
            "expected_intent": "new_customer_assignment",
            "expected_answerability": "partially_answerable",
            "expected_evidence_paths": [],
            "expected_missing_fields": ["new_customer_ids"],
            "expected_warnings": ["missing_new_customer_attribution"],
            "expected_next_actions": ["expose_new_customer_ids"],
            "expected_behavior_class": "useful_refusal",
        }
    )
    pred = _pred(
        predicted_intent="new_customer_assignment",
        predicted_answerability="partially_answerable",
        predicted_evidence_paths=[],
        predicted_missing_fields=["new_customer_ids"],
        predicted_warnings=["missing_new_customer_attribution"],
        # Literal contract string — what refusal_policy.py actually emits.
        predicted_next_actions=[
            "Expose perturbation.new_customer_ids in the product payload."
        ],
        predicted_behavior_class="useful_refusal",
    )
    s = score_case(case, pred)
    assert s.useful_refusal_correct is True


def test_warning_precision_recall_when_system_emits_unexpected_warning():
    case = _gold({})
    pred = _pred(
        predicted_warnings=["route_indexing_ambiguity"],
        predicted_behavior_class="direct_answer_with_warning",
    )
    s = score_case(case, pred)
    # Predicted: {route_indexing_ambiguity}, gold: {}
    # → precision 0.0, recall 1.0 (gold empty)
    assert s.warning_precision == 0.0
    assert s.warning_recall == 1.0


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_aggregate_splits_by_implementation_status():
    cur = score_case(_gold({}), _pred())
    tgt = score_case(
        _gold({"implementation_status": "target_extension"}),
        _pred(predicted_intent="objective_delta"),  # wrong
    )
    agg = aggregate_scores([cur, tgt])
    assert agg["overall"]["n"] == 2
    assert agg["by_implementation_status"]["current"]["n"] == 1
    assert agg["by_implementation_status"]["target_extension"]["n"] == 1
    assert agg["by_implementation_status"]["current"]["intent_accuracy"] == 1.0
    assert agg["by_implementation_status"]["target_extension"]["intent_accuracy"] == 0.0


def test_aggregate_returns_empty_when_no_scores():
    agg = aggregate_scores([])
    assert agg == {
        "overall": {},
        "by_implementation_status": {},
        "by_family": {},
        "by_behavior_class": {},
        "by_difficulty": {},
    }


def test_aggregate_does_not_include_composite():
    cur = score_case(_gold({}), _pred())
    agg = aggregate_scores([cur])
    # No top-level "composite" or "headline" key
    forbidden = {"composite", "composite_score", "headline", "aggregate_composite"}
    for group in agg.values():
        if isinstance(group, dict):
            assert not (set(group.keys()) & forbidden), group
