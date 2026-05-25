"""Tests for product/evaluation/run2_model_output_adapter.py.

Covers the parse-status branches that the runner relies on:
- happy path (`parsed`)
- markdown-fence forgiveness (`parsed` + note)
- invalid JSON (`invalid_json`)
- missing required keys (`missing_required_fields`)
- invalid enum (`invalid_enum`)
- predicate-pinned path normalisation
- concrete next-action string mapped back to semantic code
"""
from __future__ import annotations

import json

from product.evaluation.run2_model_output_adapter import (
    parse_model_contract_json,
    parsed_output_to_dict,
    parsed_output_from_dict,
)


def _good_payload() -> dict:
    return {
        "predicted_intent": "objective_value",
        "predicted_answerability": "answerable",
        "predicted_evidence_paths": ["action_objective", "units.objective"],
        "predicted_missing_fields": [],
        "predicted_warnings": [],
        "predicted_next_actions": [],
        "predicted_behavior_class": "direct_answer",
        "answer_text": "The total cost is 423.7 in solomon_distance units.",
    }


def test_parses_clean_json():
    raw = json.dumps(_good_payload())
    parsed = parse_model_contract_json(raw, case_id="R2-001")
    assert parsed.parse_status == "parsed"
    assert parsed.predicted is not None
    assert parsed.predicted.predicted_intent == "objective_value"
    assert parsed.predicted.predicted_answerability == "answerable"
    assert parsed.predicted.predicted_behavior_class == "direct_answer"
    assert "action_objective" in parsed.predicted.predicted_evidence_paths
    assert parsed.answer_text.startswith("The total cost")


def test_strips_markdown_fence_and_notes_it():
    body = json.dumps(_good_payload())
    raw = "```json\n" + body + "\n```"
    parsed = parse_model_contract_json(raw, case_id="R2-001")
    assert parsed.parse_status == "parsed"
    assert "stripped_markdown_fence" in parsed.parser_notes


def test_invalid_json_returns_invalid_json_status():
    raw = "not a json object {{{"
    parsed = parse_model_contract_json(raw, case_id="R2-001")
    assert parsed.parse_status == "invalid_json"
    assert parsed.predicted is None
    assert any("json_decode_error" in n for n in parsed.parser_notes)


def test_missing_required_field_returns_missing_required_fields():
    payload = _good_payload()
    payload.pop("predicted_behavior_class")
    parsed = parse_model_contract_json(json.dumps(payload), case_id="R2-001")
    assert parsed.parse_status == "missing_required_fields"
    assert parsed.predicted is None
    assert any("predicted_behavior_class" in n for n in parsed.parser_notes)


def test_invalid_intent_enum_marked_invalid_enum_but_predicted_populated():
    payload = _good_payload()
    payload["predicted_intent"] = "not_a_real_intent"
    parsed = parse_model_contract_json(json.dumps(payload), case_id="R2-001")
    assert parsed.parse_status == "invalid_enum"
    # We still surface the model's claim for downstream scoring/inspection.
    assert parsed.predicted is not None
    assert parsed.predicted.predicted_intent == "not_a_real_intent"
    assert any("predicted_intent" in n for n in parsed.parser_notes)


def test_invalid_warning_code_marked_invalid_enum():
    payload = _good_payload()
    payload["predicted_warnings"] = ["mystery_warning"]
    parsed = parse_model_contract_json(json.dumps(payload), case_id="R2-099")
    assert parsed.parse_status == "invalid_enum"
    assert "mystery_warning" in parsed.predicted.predicted_warnings


def test_predicate_pinned_evidence_path_is_normalised():
    payload = _good_payload()
    payload["predicted_intent"] = "customer_arrival"
    payload["predicted_evidence_paths"] = [
        "customer_schedule[customer_id=42].arrival"
    ]
    payload["predicted_behavior_class"] = "direct_answer"
    parsed = parse_model_contract_json(json.dumps(payload), case_id="R2-007")
    assert parsed.parse_status == "parsed"
    assert (
        "customer_schedule[].arrival"
        in parsed.predicted.predicted_evidence_paths
    )


def test_concrete_next_action_string_mapped_to_semantic_code():
    payload = _good_payload()
    payload["predicted_intent"] = "new_customer_assignment"
    payload["predicted_answerability"] = "partially_answerable"
    payload["predicted_behavior_class"] = "useful_refusal"
    payload["predicted_missing_fields"] = ["new_customer_ids"]
    payload["predicted_warnings"] = ["missing_new_customer_attribution"]
    payload["predicted_evidence_paths"] = []
    payload["predicted_next_actions"] = [
        "Expose perturbation.new_customer_ids in the product payload."
    ]
    parsed = parse_model_contract_json(json.dumps(payload), case_id="R2-003")
    assert parsed.parse_status == "parsed"
    assert (
        "expose_new_customer_ids"
        in parsed.predicted.predicted_next_actions
    )


def test_semantic_next_action_passes_through():
    payload = _good_payload()
    payload["predicted_intent"] = "customer_arrival"
    payload["predicted_answerability"] = "not_answerable"
    payload["predicted_behavior_class"] = "useful_refusal"
    payload["predicted_warnings"] = ["false_premise_detected"]
    payload["predicted_evidence_paths"] = []
    payload["predicted_next_actions"] = ["clarify_false_premise"]
    parsed = parse_model_contract_json(json.dumps(payload), case_id="R2-008")
    assert parsed.parse_status == "parsed"
    assert parsed.predicted.predicted_next_actions == ["clarify_false_premise"]


def test_semicolon_string_coerced_to_list_with_note():
    payload = _good_payload()
    payload["predicted_evidence_paths"] = "action_objective;units.objective"
    parsed = parse_model_contract_json(json.dumps(payload), case_id="R2-001")
    assert parsed.parse_status == "parsed"
    assert "action_objective" in parsed.predicted.predicted_evidence_paths
    assert "units.objective" in parsed.predicted.predicted_evidence_paths
    assert any(
        "string with ';' coerced" in n for n in parsed.parser_notes
    )


def test_roundtrip_through_jsonl_dict():
    raw = json.dumps(_good_payload())
    parsed = parse_model_contract_json(raw, case_id="R2-001")
    row = parsed_output_to_dict(parsed)
    # Roundtrip via json to mimic JSONL write/read.
    row2 = json.loads(json.dumps(row))
    rebuilt = parsed_output_from_dict(row2)
    assert rebuilt.parse_status == "parsed"
    assert rebuilt.predicted is not None
    assert rebuilt.predicted.predicted_intent == "objective_value"
    assert rebuilt.answer_text.startswith("The total cost")


# ---------------------------------------------------------------------------
# System A optional fields
# ---------------------------------------------------------------------------


def test_system_b_output_without_prior_fields_parses_with_defaults():
    """System B never emits prior_disagreement / adapter_notes; parser
    defaults them to False / "" without warning."""
    raw = json.dumps(_good_payload())
    parsed = parse_model_contract_json(raw, case_id="R2-001")
    assert parsed.parse_status == "parsed"
    assert parsed.prior_disagreement is False
    assert parsed.adapter_notes == ""


def test_system_a_output_with_prior_disagreement_true_parses():
    payload = _good_payload()
    payload["prior_disagreement"] = True
    payload["adapter_notes"] = "prior locked feasibility_status but payload missing both fields"
    parsed = parse_model_contract_json(json.dumps(payload), case_id="R2-012")
    assert parsed.parse_status == "parsed"
    assert parsed.prior_disagreement is True
    assert parsed.adapter_notes.startswith("prior locked")


def test_system_a_output_with_prior_disagreement_false_parses():
    payload = _good_payload()
    payload["prior_disagreement"] = False
    payload["adapter_notes"] = ""
    parsed = parse_model_contract_json(json.dumps(payload), case_id="R2-008")
    assert parsed.parse_status == "parsed"
    assert parsed.prior_disagreement is False
    assert parsed.adapter_notes == ""


def test_system_a_string_prior_disagreement_coerced_with_note():
    payload = _good_payload()
    payload["prior_disagreement"] = "true"
    parsed = parse_model_contract_json(json.dumps(payload), case_id="R2-008")
    assert parsed.parse_status == "parsed"
    assert parsed.prior_disagreement is True
    assert any("prior_disagreement" in n for n in parsed.parser_notes)


def test_system_a_invalid_enum_still_rejected_with_prior_fields_present():
    payload = _good_payload()
    payload["predicted_intent"] = "not_a_real_intent"
    payload["prior_disagreement"] = True
    payload["adapter_notes"] = "model disagreed"
    parsed = parse_model_contract_json(json.dumps(payload), case_id="R2-012")
    assert parsed.parse_status == "invalid_enum"
    # The disagreement flag is preserved even when the enum is invalid,
    # so downstream analysis can see what the model attempted.
    assert parsed.prior_disagreement is True
    assert parsed.adapter_notes == "model disagreed"


def test_system_a_roundtrip_preserves_prior_fields():
    payload = _good_payload()
    payload["prior_disagreement"] = True
    payload["adapter_notes"] = "payload contradicts prior"
    parsed = parse_model_contract_json(json.dumps(payload), case_id="R2-008")
    row = parsed_output_to_dict(parsed)
    row2 = json.loads(json.dumps(row))
    rebuilt = parsed_output_from_dict(row2)
    assert rebuilt.prior_disagreement is True
    assert rebuilt.adapter_notes == "payload contradicts prior"
