"""System C pipeline using D1 intent adapter + D2 downstream extensions.

Mirrors `product.evaluation.system_d1.d1_system_c.run_system_d1_on_case`
verbatim, except `compute_answerability` is replaced by
`compute_answerability_d2` and `build_warnings` / `build_useful_refusal`
are replaced by their D2 counterparts. Intent classification is
unchanged from D1 (semantic adapter).

This file is the only place where D2 hooks the contract pipeline.
No protected file is modified.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from product.copilot.contracts import EvidenceItem
from product.copilot.intent import infer_intent_d1_frame
from product.copilot.query_frame import QueryFrame
from product.copilot.refusal_policy import compose_suggestions
from product.data import evidence as evidence_mod
from product.data import product_schema

from product.evaluation.run2_case_loader import Run2Case
from product.evaluation.run2_payloads import MaterializedPayload
from product.evaluation.run2_system_c import PredictedContract, _infer_behavior_class
from product.evaluation.system_d2.d2_answerability import compute_answerability_d2
from product.evaluation.system_d2.d2_refusal_policy import (
    build_useful_refusal_d2,
    build_warnings_d2,
)


@dataclass
class PredictedContractD2(PredictedContract):
    """D2's predicted contract — same as System C, plus the D1 query
    frame so the evaluation harness can report adapter provenance."""

    query_frame: Optional[QueryFrame] = None


def _evidence_paths(items: list[EvidenceItem]) -> list[str]:
    return [it.field_path for it in items]


def run_system_d2_on_case(
    case: Run2Case,
    payload: Optional[dict],
    generator_record: Optional[dict] = None,
) -> PredictedContractD2:
    """Run the full Stage-2 contract on a Run 2 case using D1 for
    intent classification and D2 for the answerability + warning
    extensions."""
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

    answerability = compute_answerability_d2(
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

    warnings = build_warnings_d2(
        prompt_id=case.case_id,
        intent=intent,
        payload=augmented,
        answerability=answerability,
        prompt_text=case.prompt_text,
        answer_text="",
    )

    useful_refusal = build_useful_refusal_d2(
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

    return PredictedContractD2(
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


def run_system_d2_on_materialized(
    case: Run2Case, mat: MaterializedPayload
) -> Optional[PredictedContractD2]:
    if mat.materialization_status != "materialized":
        return None
    return run_system_d2_on_case(
        case=case,
        payload=mat.payload,
        generator_record=mat.generator_record,
    )


__all__ = [
    "PredictedContractD2",
    "run_system_d2_on_case",
    "run_system_d2_on_materialized",
]
