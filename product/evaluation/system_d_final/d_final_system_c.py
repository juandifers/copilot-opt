"""System D-Final — LLM semantic adapter + D2/D3/D4 deterministic contract.

D-Final wraps the full D4 pipeline. The only seam changed is the intent
classifier: `infer_intent_d1_frame` is replaced by
`infer_intent_d_final_frame`. Every downstream module — D2 answerability,
D3 causal warnings, D4 compute decision — is called unchanged.

The LLM call is optional: when ``client=None``, the intent falls back to
D1 deterministically, preserving full D4 semantics without any LLM cost.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from product.copilot.contracts import EvidenceItem
from product.copilot.llm_query_frame import LLMAdapterMetadata
from product.copilot.query_frame import QueryFrame
from product.copilot.refusal_policy import compose_suggestions
from product.data import evidence as evidence_mod
from product.data import product_schema

from product.evaluation.run2_case_loader import Run2Case
from product.evaluation.run2_payloads import MaterializedPayload
from product.evaluation.run2_system_c import PredictedContract, _infer_behavior_class
from product.evaluation.system_d2.d2_answerability import compute_answerability_d2
from product.evaluation.system_d3.d3_refusal_policy import (
    build_useful_refusal_d3,
    build_warnings_d3,
)
from product.evaluation.system_d4.compute_decision import decide_compute


@dataclass
class PredictedContractDFinal(PredictedContract):
    """D4 contract enriched with D-Final adapter metadata."""

    query_frame: Optional[QueryFrame] = None
    compute_decision: Optional[Any] = None
    adapter_metadata: Optional[LLMAdapterMetadata] = None


def _evidence_paths(items: list[EvidenceItem]) -> list[str]:
    return [it.field_path for it in items]


def run_system_d_final_on_case(
    case: Run2Case,
    payload: Optional[dict],
    generator_record: Optional[dict] = None,
    client: Optional[Any] = None,
    mode: str = "hybrid_guarded",
) -> PredictedContractDFinal:
    """Run the D-Final pipeline on a single case.

    Parameters
    ----------
    client:
        OpenAI client. When ``None``, falls back to D1 deterministically
        (no LLM call, full D4 output preserved).
    mode:
        Adapter mode: "hybrid_guarded" | "llm_only" | "llm_fallback".
    """
    from product.copilot.intent import infer_intent_d_final_frame

    notes: list[str] = []
    if payload is None:
        notes.append("payload is None (materialization did not produce a payload)")

    augmented = product_schema.augment_payload_for_product(payload)

    # Intent via D-Final adapter (LLM + guardrails, or D1 fallback)
    frame, adapter_meta = infer_intent_d_final_frame(
        prompt_text=case.prompt_text,
        family=case.family,
        client=client,
        mode=mode,
        generator_record=generator_record,
    )
    intent = frame.intent

    # D2 answerability
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

    # D3 warnings
    warnings = build_warnings_d3(
        prompt_id=case.case_id,
        intent=intent,
        payload=augmented,
        answerability=answerability,
        prompt_text=case.prompt_text,
        answer_text="",
    )

    useful_refusal = build_useful_refusal_d3(
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

    # D4 compute decision
    decision = decide_compute(
        prompt_text=case.prompt_text,
        intent=intent,
        answerability_status=answerability.status,
        warnings=list(warnings),
        payload=payload,
        answerability_missing_fields=list(answerability.missing_fields),
    )

    return PredictedContractDFinal(
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
        compute_decision=decision,
        adapter_metadata=adapter_meta,
    )


def run_system_d_final_on_materialized(
    case: Run2Case,
    mat: MaterializedPayload,
    client: Optional[Any] = None,
    mode: str = "hybrid_guarded",
) -> Optional[PredictedContractDFinal]:
    if mat.materialization_status != "materialized":
        return None
    return run_system_d_final_on_case(
        case=case,
        payload=mat.payload,
        generator_record=mat.generator_record,
        client=client,
        mode=mode,
    )


__all__ = [
    "PredictedContractDFinal",
    "run_system_d_final_on_case",
    "run_system_d_final_on_materialized",
]
