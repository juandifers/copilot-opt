"""Tests for product/evaluation/run2_system_c.py.

The adapter calls into the existing product-layer functions; the
tests below verify that it produces sensible predictions on the
calibration cases without crashing on any of them. Skip if Run 1
artifacts are not available.
"""
from __future__ import annotations

import pytest

from product.evaluation.run2_case_loader import (
    default_cases_path,
    load_run2_cases,
)
from product.evaluation.run2_payloads import (
    _find_generator_jsonl,
    materialize_all_cases,
    materialize_case_payload,
)
from product.evaluation.run2_system_c import (
    _infer_behavior_class,
    run_system_c_on_case,
    run_system_c_on_materialized,
)
from product.copilot.contracts import AnswerabilityResult


try:
    _find_generator_jsonl("full-run-v1")
except FileNotFoundError as exc:
    pytest.skip(
        f"Run 1 generator JSONL not found: {exc}", allow_module_level=True
    )


def _by_id():
    cases = load_run2_cases(default_cases_path())
    return {c.case_id: c for c in cases}


# ---------------------------------------------------------------------------
# behavior_class projection (pure)
# ---------------------------------------------------------------------------


def _ans(status: str) -> AnswerabilityResult:
    return AnswerabilityResult(status=status, intent="objective_value")


def test_infer_behavior_class_answerable_no_warnings():
    assert _infer_behavior_class(_ans("answerable"), [], []) == "direct_answer"


def test_infer_behavior_class_answerable_with_warnings():
    assert (
        _infer_behavior_class(_ans("answerable"), [], ["x"])
        == "direct_answer_with_warning"
    )


def test_infer_behavior_class_partial_with_evidence():
    class _E:
        pass

    items = [_E()]
    cls = _infer_behavior_class(_ans("partially_answerable"), items, [])
    assert cls == "partial_answer_with_warning"


def test_infer_behavior_class_partial_without_evidence():
    cls = _infer_behavior_class(_ans("partially_answerable"), [], [])
    assert cls == "useful_refusal"


def test_infer_behavior_class_not_answerable():
    cls = _infer_behavior_class(_ans("not_answerable"), [], [])
    assert cls == "useful_refusal"


# ---------------------------------------------------------------------------
# Adapter integration — current cases
# ---------------------------------------------------------------------------


def test_R2_001_predicts_objective_value_answerable():
    case = _by_id()["R2-001"]
    mat = materialize_case_payload(case)
    pred = run_system_c_on_case(case, mat.payload, mat.generator_record)
    assert pred.predicted_intent == "objective_value"
    assert pred.predicted_answerability == "answerable"
    assert "action_objective" in pred.predicted_evidence_paths


def test_R2_002_predicts_objective_delta_answerable_via_escape_hatch():
    case = _by_id()["R2-002"]
    mat = materialize_case_payload(case)
    pred = run_system_c_on_case(case, mat.payload, mat.generator_record)
    assert pred.predicted_intent == "objective_delta"
    # OBJ escape hatch applies → answerable
    assert pred.predicted_answerability == "answerable"
    assert pred.predicted_warnings == []  # no warning under current contract
    assert pred.predicted_behavior_class == "direct_answer"


def test_R2_003_predicts_partial_with_missing_new_customer_ids():
    case = _by_id()["R2-003"]
    mat = materialize_case_payload(case)
    pred = run_system_c_on_case(case, mat.payload, mat.generator_record)
    assert pred.predicted_intent == "new_customer_assignment"
    assert pred.predicted_answerability == "partially_answerable"
    assert "new_customer_ids" in pred.predicted_missing_fields
    assert "missing_new_customer_attribution" in pred.predicted_warnings


def test_R2_004_predicts_single_customer_membership_with_struct_warning():
    case = _by_id()["R2-004"]
    mat = materialize_case_payload(case)
    pred = run_system_c_on_case(case, mat.payload, mat.generator_record)
    assert pred.predicted_intent == "single_customer_route_membership"
    assert pred.predicted_answerability == "answerable"
    assert "struct_membership_ambiguity" in pred.predicted_warnings


def test_R2_005_predicts_unsupported_comparison_refusal():
    case = _by_id()["R2-005"]
    mat = materialize_case_payload(case)
    pred = run_system_c_on_case(case, mat.payload, mat.generator_record)
    assert pred.predicted_intent == "before_after_comparison"
    assert pred.predicted_answerability == "not_answerable"
    assert "unsupported_comparison" in pred.predicted_warnings
    assert pred.predicted_behavior_class == "useful_refusal"


def test_R2_011_pv_clean_predicts_feasibility_status_answerable():
    case = _by_id()["R2-011"]
    mat = materialize_case_payload(case)
    pred = run_system_c_on_case(case, mat.payload, mat.generator_record)
    assert pred.predicted_intent == "feasibility_status"
    assert pred.predicted_answerability == "answerable"
    assert any(
        p.startswith("feasibility_breakdown") or p == "feasible"
        for p in pred.predicted_evidence_paths
    )


# ---------------------------------------------------------------------------
# Adapter integration — target_extension cases
# ---------------------------------------------------------------------------


def test_R2_008_false_premise_emits_warning_after_R2_3_extension():
    # R2-3 STEP 4: customer false-premise extension. The contract now
    # detects that customer_id=999 is absent from the payload and
    # refuses with false_premise_detected (was target_extension at R2-1).
    case = _by_id()["R2-008"]
    mat = materialize_case_payload(case)
    pred = run_system_c_on_case(case, mat.payload, mat.generator_record)
    assert pred.predicted_intent == "customer_arrival"
    assert pred.predicted_answerability == "not_answerable"
    assert "false_premise_detected" in pred.predicted_warnings
    assert "clarify_false_premise" in pred.predicted_next_actions


def test_R2_013_comparison_referent_emits_warning_after_R2_3_extension():
    # R2-3 STEP 6: comparison_referent_ambiguity extension. The
    # contract now detects that "a full re-solve" does not match what
    # baseline_objective describes, lists reference_solution.objective
    # as missing, and emits the warning.
    case = _by_id()["R2-013"]
    mat = materialize_case_payload(case)
    pred = run_system_c_on_case(case, mat.payload, mat.generator_record)
    assert pred.predicted_intent == "objective_delta"
    assert pred.predicted_answerability == "partially_answerable"
    assert "comparison_referent_ambiguity" in pred.predicted_warnings
    assert "reference_solution.objective" in pred.predicted_missing_fields
    assert "expose_reference_solution_objective" in pred.predicted_next_actions


def test_R2_010_full_route_listing_routes_correctly_after_R2_3_extension():
    # R2-3 STEP 3: full_route_listing intent extension. The contract
    # now routes "List all the customers assigned to each route..." to
    # full_route_listing — the listing matcher runs BEFORE the
    # new-customer-assignment heuristic so "new orders" + "assigned"
    # tokens no longer hijack roster questions.
    case = _by_id()["R2-010"]
    mat = materialize_case_payload(case)
    assert mat.materialization_status == "materialized"
    pred = run_system_c_on_materialized(case, mat)
    assert pred is not None
    assert pred.predicted_intent == "full_route_listing"
    assert pred.predicted_answerability == "answerable"
    # Evidence cites routes[].customer_ids (the contract emits one
    # item per route with a route_idx predicate that the scorer
    # normalises to the field-family form).
    assert any(
        "routes[" in p and "customer_ids" in p
        for p in pred.predicted_evidence_paths
    )


# ---------------------------------------------------------------------------
# Whole-set integration
# ---------------------------------------------------------------------------


def test_system_c_runs_on_every_materialized_case():
    cases = load_run2_cases(default_cases_path())
    mats, _ = materialize_all_cases(cases)
    by_id = {c.case_id: c for c in cases}
    n_predictions = 0
    for mat in mats:
        pred = run_system_c_on_materialized(by_id[mat.case_id], mat)
        if pred is None:
            continue
        n_predictions += 1
        assert pred.predicted_intent  # non-empty
        assert pred.predicted_answerability in (
            "answerable",
            "partially_answerable",
            "not_answerable",
        )
        assert pred.predicted_behavior_class in (
            "direct_answer",
            "direct_answer_with_warning",
            "partial_answer_with_warning",
            "useful_refusal",
        )
    assert n_predictions >= 10
