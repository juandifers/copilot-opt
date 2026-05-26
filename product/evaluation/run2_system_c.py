"""System C adapter — runs the existing product contract on a Run 2 case.

The Stage 2 orchestrator (`product/copilot/response_builder.py`)
expects to look up a Run 1 prompt by `prompt_id` and read the full
bundle from disk. Run 2 cases may rewrite the prompt text and mutate
the payload, so this adapter calls the lower-level product modules
directly with the Run 2 inputs:

    infer_intent(prompt_text, family, generator_record)
    compute_answerability(prompt_text, family, payload, intent, generator_record)
    compose_suggestions(intent, missing_fields)
    build_evidence_items(intent, payload, generator_record, row)
    build_warnings(prompt_id, intent, payload, answerability, prompt_text, answer_text)
    build_useful_refusal(answerability)
    infer_visual_actions(intent, evidence_items)
    augment_payload_for_product(payload)

No model calls. No solver calls. No mutation of production code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from product.copilot.contracts import AnswerabilityResult, EvidenceItem
from product.copilot.intent import infer_intent
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


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------


@dataclass
class PredictedContract:
    """The System C contract response in Run 2-comparable shape.

    Field paths in `predicted_evidence_paths` are reported as-emitted
    by the product layer; the scoring layer normalises predicate
    qualifiers (`[route_idx=K]` → `[]`) before matching against gold.
    """

    case_id: str
    predicted_intent: str
    predicted_answerability: str
    predicted_evidence_paths: list[str] = field(default_factory=list)
    predicted_missing_fields: list[str] = field(default_factory=list)
    predicted_warnings: list[str] = field(default_factory=list)
    predicted_next_actions: list[str] = field(default_factory=list)
    predicted_behavior_class: str = ""
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _evidence_paths(items: list[EvidenceItem]) -> list[str]:
    return [it.field_path for it in items]


def _infer_behavior_class(
    answerability: AnswerabilityResult,
    evidence_items: list[EvidenceItem],
    warnings: list[str],
) -> str:
    """Project the contract response onto the four-valued behavior_class
    enum used by Run 2 (schema §7).

    Decision tree:
      - answerable + no warnings        → direct_answer
      - answerable + warnings           → direct_answer_with_warning
      - partial + evidence cited        → partial_answer_with_warning
      - partial + no evidence cited     → useful_refusal
      - not_answerable                  → useful_refusal
    """
    status = answerability.status
    has_evidence = bool(evidence_items)
    has_warnings = bool(warnings)
    if status == "answerable":
        return "direct_answer_with_warning" if has_warnings else "direct_answer"
    if status == "partially_answerable":
        return (
            "partial_answer_with_warning" if has_evidence else "useful_refusal"
        )
    return "useful_refusal"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_system_c_on_case(
    case: Run2Case,
    payload: Optional[dict],
    generator_record: Optional[dict] = None,
) -> PredictedContract:
    """Run the full System C contract pipeline on a Run 2 case.

    `payload` is the materialized (already-mutated) payload from
    `run2_payloads.materialize_case_payload`. `generator_record` is
    optional Run 1 structured-output context, used by the evidence
    extractor to pin route/customer membership claims and by
    `intent.py` to detect refusal-shaped answers. It is **not** an
    oracle of the answer — Run 2 evaluates the contract, not the
    Run 1 answer text.
    """
    notes: list[str] = []
    if payload is None:
        notes.append("payload is None (materialization did not produce a payload)")

    augmented = product_schema.augment_payload_for_product(payload)

    intent = infer_intent(
        prompt_text=case.prompt_text,
        family=case.family,
        generator_record=generator_record,
    )

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
        row={
            "prompt_text": case.prompt_text,
            "family": case.family or "",
            "perturbation_id": getattr(case, "perturbation_id", "") or "",
        },
    )

    # `build_warnings` was authored against Run 1 prompt IDs; for
    # Run 2 we pass the case_id (a stable string identifier).
    # This means the `_KNOWN_ROUTE_INDEXING_PROMPTS = {040, 041}` and
    # `_KNOWN_STRUCT_MEMBERSHIP_PROMPTS = {029}` hand-flagged sets
    # do NOT trigger for Run 2 cases — the warning logic falls back
    # to its regex / intent rules, which is correct for an
    # evaluation set whose IDs are R2-NNN.
    warnings = build_warnings(
        prompt_id=case.case_id,
        intent=intent,
        payload=augmented,
        answerability=answerability,
        prompt_text=case.prompt_text,
        # No model generator is invoked at R2-1: we evaluate the
        # contract in contract-only mode per design §5
        # ("Contract-only mode for System C"). answer_text is "".
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

    return PredictedContract(
        case_id=case.case_id,
        predicted_intent=intent,
        predicted_answerability=answerability.status,
        predicted_evidence_paths=_evidence_paths(evidence_items),
        predicted_missing_fields=list(answerability.missing_fields),
        predicted_warnings=list(warnings),
        predicted_next_actions=list(next_actions),
        predicted_behavior_class=behavior_class,
        notes=notes,
    )


def run_system_c_on_materialized(
    case: Run2Case, mat: MaterializedPayload
) -> Optional[PredictedContract]:
    """Convenience wrapper that handles skipped-materialization cases.

    Returns None when the payload could not be materialized; callers
    should record this as an evaluation-step skip rather than calling
    System C on a None payload.
    """
    if mat.materialization_status != "materialized":
        return None
    return run_system_c_on_case(
        case=case,
        payload=mat.payload,
        generator_record=mat.generator_record,
    )
