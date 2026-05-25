"""System C contract pipeline with the D1 semantic intent adapter.

Mirrors `product.evaluation.run2_system_c.run_system_c_on_case`
verbatim, except the intent classifier seam is replaced with
`product.copilot.intent.infer_intent_d1_frame`. Every downstream
module — `compute_answerability`, `compose_suggestions`,
`build_evidence_items`, `build_warnings`, `build_useful_refusal` —
is called unchanged.

This file is the only place where D1 hooks the contract pipeline.
No protected file is modified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from product.copilot.contracts import AnswerabilityResult, EvidenceItem
from product.copilot.intent import infer_intent_d1_frame
from product.copilot.query_frame import QueryFrame
from product.copilot.refusal_policy import (
    build_useful_refusal,
    build_warnings,
    compose_suggestions,
)
from product.data import evidence as evidence_mod
from product.data import product_schema
from product.data.answerability import compute_answerability

from product.evaluation.run2_case_loader import Run2Case
from product.evaluation.run2_payloads import MaterializedPayload
from product.evaluation.run2_system_c import PredictedContract, _infer_behavior_class


@dataclass
class PredictedContractD1(PredictedContract):
    """D1's predicted contract — same as System C, plus the D1 query
    frame so the evaluation harness can report adapter provenance."""

    query_frame: Optional[QueryFrame] = None


def _evidence_paths(items: list[EvidenceItem]) -> list[str]:
    return [it.field_path for it in items]


def run_system_d1_on_case(
    case: Run2Case,
    payload: Optional[dict],
    generator_record: Optional[dict] = None,
) -> PredictedContractD1:
    """Run the full Stage-2 contract on a Run 2 case using D1 for
    intent classification."""
    notes: list[str] = []
    if payload is None:
        notes.append("payload is None (materialization did not produce a payload)")

    augmented = product_schema.augment_payload_for_product(payload)

    frame = infer_intent_d1_frame(
        prompt_text=case.prompt_text,
        family=case.family,
        generator_record=generator_record,
    )
    intent = frame.intent

    answerability = compute_answerability(
        prompt_text=case.prompt_text,
        family=case.family,
        payload=augmented,
        intent=intent,
        generator_record=generator_record,
    )

    suggestions = compose_suggestions(intent, answerability.missing_fields)
    answerability = answerability.model_copy(
        update={"suggested_next_actions": suggestions}
    )

    evidence_items = evidence_mod.build_evidence_items(
        intent=intent,
        payload=augmented,
        generator_record=generator_record,
        row={"prompt_text": case.prompt_text},
    )

    warnings = build_warnings(
        prompt_id=case.case_id,
        intent=intent,
        payload=augmented,
        answerability=answerability,
        prompt_text=case.prompt_text,
        answer_text="",
    )

    useful_refusal = build_useful_refusal(
        answerability,
        payload=augmented,
        prompt_text=case.prompt_text,
    )

    next_actions = (
        useful_refusal.suggested_next_actions
        if useful_refusal is not None
        else suggestions
    )

    behavior_class = _infer_behavior_class(answerability, evidence_items, warnings)

    return PredictedContractD1(
        case_id=case.case_id,
        predicted_intent=intent,
        predicted_answerability=answerability.status,
        predicted_evidence_paths=_evidence_paths(evidence_items),
        predicted_missing_fields=list(answerability.missing_fields),
        predicted_warnings=list(warnings),
        predicted_next_actions=list(next_actions),
        predicted_behavior_class=behavior_class,
        notes=notes,
        query_frame=frame,
    )


def run_system_d1_on_materialized(
    case: Run2Case, mat: MaterializedPayload
) -> Optional[PredictedContractD1]:
    """Convenience wrapper that handles skipped-materialization cases."""
    if mat.materialization_status != "materialized":
        return None
    return run_system_d1_on_case(
        case=case,
        payload=mat.payload,
        generator_record=mat.generator_record,
    )


__all__ = [
    "PredictedContractD1",
    "run_system_d1_on_case",
    "run_system_d1_on_materialized",
]
