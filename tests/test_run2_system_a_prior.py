"""Tests for product/evaluation/run2_system_a_prior.py.

Each test takes a real R2-5 case from the frozen benchmark, materialises
its payload via the existing materializer, builds the prior, and asserts
the deterministic priors match the rubric the System A prompt will lock.

Skip if Run 1 generator JSONL is missing (the materializer needs it for
the seed payload_snapshot).
"""
from __future__ import annotations

import pytest

from product.evaluation.run2_case_loader import (
    default_cases_path,
    load_run2_cases,
)
from product.evaluation.run2_payloads import (
    _find_generator_jsonl,
    materialize_case_payload,
)
from product.evaluation.run2_system_a_prior import (
    PRIOR_LOCKED_FIELDS,
    build_system_a_prior,
)


try:
    _find_generator_jsonl("full-run-v1")
except FileNotFoundError as exc:  # pragma: no cover
    pytest.skip(
        f"Run 1 generator JSONL not found: {exc}", allow_module_level=True
    )


# Use the locked benchmark CSV (not the calibration set) so the test
# cases match the IDs the runner / pass^k subset use.
def _by_id():
    cases = load_run2_cases("product/evaluation/run2_benchmark_cases.csv")
    return {c.case_id: c for c in cases}


def _prior(case_id: str) -> dict:
    case = _by_id()[case_id]
    mat = materialize_case_payload(case)
    assert mat.materialization_status == "materialized", (
        f"materialization failed for {case_id}: {mat.warnings}"
    )
    return build_system_a_prior(case, mat.payload)


# ---------------------------------------------------------------------------
# Shape / contract
# ---------------------------------------------------------------------------


def test_prior_has_expected_keys_and_locked_field_list():
    p = _prior("R2-001")
    for k in (
        "intent_prior",
        "answerability_prior",
        "required_fields",
        "available_fields",
        "missing_fields_prior",
        "warnings_prior",
        "next_actions_prior",
        "behavior_class_prior",
        "prior_locked_fields",
    ):
        assert k in p, f"missing key {k} in prior"
    # The locked-field list pins the columns the model must preserve.
    assert "predicted_intent" in PRIOR_LOCKED_FIELDS
    assert "predicted_answerability" in PRIOR_LOCKED_FIELDS
    assert "predicted_missing_fields" in PRIOR_LOCKED_FIELDS


# ---------------------------------------------------------------------------
# Acceptance criteria from the R2-6 spec
# ---------------------------------------------------------------------------


def test_R2_040_prior_gives_single_customer_membership_not_new_customer_assignment():
    p = _prior("R2-040")
    assert p["intent_prior"] == "single_customer_route_membership"
    assert p["answerability_prior"] == "answerable"
    assert "struct_membership_ambiguity" in p["warnings_prior"]
    assert p["behavior_class_prior"] == "direct_answer_with_warning"


def test_R2_051_prior_gives_lateness_summary_not_feasibility_status():
    p = _prior("R2-051")
    assert p["intent_prior"] == "lateness_summary"
    assert p["answerability_prior"] == "answerable"


def test_R2_055_prior_includes_route_indexing_ambiguity():
    p = _prior("R2-055")
    assert p["intent_prior"] == "route_end_time"
    assert "route_indexing_ambiguity" in p["warnings_prior"]
    assert p["behavior_class_prior"] == "direct_answer_with_warning"


def test_R2_060_prior_includes_route_indexing_ambiguity():
    p = _prior("R2-060")
    assert p["intent_prior"] == "route_end_time"
    assert "route_indexing_ambiguity" in p["warnings_prior"]
    assert p["behavior_class_prior"] == "direct_answer_with_warning"


def test_R2_027_prior_uses_plan_validity_required_field_structure():
    p = _prior("R2-027")
    assert p["intent_prior"] == "feasibility_status"
    # PV required-fields skeleton — the prior exposes the family
    # structure the model needs even though the gold rubric splits
    # feasibility_breakdown into per-subkey rows.
    assert "feasible" in p["required_fields"]
    assert "feasibility_breakdown" in p["required_fields"]
    assert p["answerability_prior"] == "answerable"


def test_R2_048_prior_gives_full_route_listing():
    p = _prior("R2-048")
    assert p["intent_prior"] == "full_route_listing"
    assert p["answerability_prior"] == "answerable"
    assert p["behavior_class_prior"] == "direct_answer"


def test_R2_058_prior_gives_useful_refusal_with_false_premise():
    p = _prior("R2-058")
    assert p["intent_prior"] == "customer_arrival"
    assert p["answerability_prior"] == "not_answerable"
    assert "false_premise_detected" in p["warnings_prior"]
    assert "clarify_false_premise" in p["next_actions_prior"]
    assert p["behavior_class_prior"] == "useful_refusal"


def test_R2_008_prior_gives_false_premise_customer_refusal():
    p = _prior("R2-008")
    assert p["intent_prior"] == "customer_arrival"
    assert p["answerability_prior"] == "not_answerable"
    assert "false_premise_detected" in p["warnings_prior"]
    assert "clarify_false_premise" in p["next_actions_prior"]


def test_R2_012_prior_gives_pv_missing_validity_refusal():
    p = _prior("R2-012")
    assert p["intent_prior"] == "feasibility_status"
    assert p["answerability_prior"] == "not_answerable"
    # The PV missing-fields case should suggest use_validity_payload
    # (the R2-3 extension semantic code).
    assert "use_validity_payload" in p["next_actions_prior"]


def test_R2_015_prior_gives_false_premise_route_refusal():
    p = _prior("R2-015")
    assert p["intent_prior"] == "route_end_time"
    assert p["answerability_prior"] == "not_answerable"
    assert "false_premise_detected" in p["warnings_prior"]


# ---------------------------------------------------------------------------
# Generic invariants
# ---------------------------------------------------------------------------


def test_prior_for_answerable_no_warning_case_is_direct_answer():
    p = _prior("R2-001")
    assert p["intent_prior"] == "objective_value"
    assert p["answerability_prior"] == "answerable"
    assert p["behavior_class_prior"] == "direct_answer"
    assert p["warnings_prior"] == []
    assert p["missing_fields_prior"] == []


def test_prior_for_partial_obj_delta_case_has_missing_reference_solution():
    p = _prior("R2-013")
    assert p["intent_prior"] == "objective_delta"
    assert p["answerability_prior"] == "partially_answerable"
    assert "reference_solution.objective" in p["missing_fields_prior"]
    assert "comparison_referent_ambiguity" in p["warnings_prior"]
    assert "expose_reference_solution_objective" in p["next_actions_prior"]
