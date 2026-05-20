"""Orchestrator: assembles a `ProductCopilotResponse` from Run 1 artifacts.

This is the only module that imports from every other product module.
All cross-module composition lives here so the leaves stay pure.
"""
from __future__ import annotations

from typing import Any, Optional

from product.copilot.contracts import (
    AnswerabilityResult,
    GeneratorAnswer,
    MetricsFlags,
    ProductCopilotResponse,
    PromptMetadata,
)
from product.copilot.intent import infer_intent
from product.copilot.refusal_policy import (
    build_useful_refusal,
    build_warnings,
    compose_suggestions,
)
from product.data import evidence as evidence_mod
from product.data import loaders, payloads, product_schema
from product.data.answerability import compute_answerability


# ---------------------------------------------------------------------------
# Adapters (bundle row → typed sub-models)
# ---------------------------------------------------------------------------


def _generator_answer_from_record(record: Optional[dict]) -> GeneratorAnswer:
    if not record:
        return GeneratorAnswer(answer_text="")
    so = record.get("structured_output") or {}
    return GeneratorAnswer(
        answer_text=so.get("answer_text") or record.get("answer_text") or "",
        claimed_objective=so.get("claimed_objective"),
        claimed_feasible=so.get("claimed_feasible"),
        claimed_route_count=so.get("claimed_route_count"),
        claimed_route_membership=so.get("claimed_route_membership"),
        claimed_late_customers=so.get("claimed_late_customers"),
        claimed_customer_timings=so.get("claimed_customer_timings"),
    )


def _prompt_metadata_from_bundle(bundle: dict) -> PromptMetadata:
    prompt_row = bundle.get("prompt_row") or {}
    joined_row = bundle.get("joined_row") or {}

    def pick(key: str) -> Any:
        value = prompt_row.get(key)
        if value is None:
            value = joined_row.get(key)
        return value

    return PromptMetadata(
        prompt_id=bundle["prompt_id"],
        family=str(pick("family") or ""),
        source=str(pick("source") or ""),
        instance_id=str(pick("instance_id") or ""),
        perturbation_id=str(pick("perturbation_id") or ""),
        perturbation_family=pick("perturbation_family"),
        instance_class=pick("instance_class"),
        dataset=pick("dataset"),
        quadrant=pick("quadrant"),
        sufficiency_label=pick("sufficiency_label"),
        policy_decision=pick("policy_decision"),
        action_taken=str(pick("action_taken") or ""),
        template_id=pick("template_id"),
        prompt_text=str(pick("prompt_text") or ""),
    )


# ---------------------------------------------------------------------------
# Metric flag computation
# ---------------------------------------------------------------------------


def _compute_metrics_flags(
    joined_row: dict,
    answerability: AnswerabilityResult,
    evidence_items: list,
    warnings: list[str],
    useful_refusal_present: bool,
    intent: str,
    augmented_payload: Optional[dict],
) -> MetricsFlags:
    score = joined_row.get("faithfulness_score")
    try:
        score_f = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_f = None
    grounded = (
        score_f is not None
        and score_f >= 4.0
        and answerability.status == "answerable"
    )

    evidence_shown = bool(evidence_items) or bool(answerability.missing_fields) or useful_refusal_present

    unsupported_comparison_detected = "unsupported_comparison" in warnings

    # route_label_ambiguity_resolved: True if intent involves routes AND
    # the augmented payload now exposes display_route_number on its
    # route-like sub-objects.
    def _routes_have_display(payload: Optional[dict]) -> bool:
        if not payload:
            return False
        for key in ("routes", "route_end_times", "customer_schedule"):
            lst = payload.get(key)
            if isinstance(lst, list) and lst and isinstance(lst[0], dict):
                if "display_route_number" in lst[0]:
                    return True
        return False

    route_intents = {
        "route_end_time",
        "single_customer_route_membership",
        "same_route_boolean",
        "route_count",
    }
    if intent in route_intents:
        route_label_resolved = _routes_have_display(augmented_payload)
    else:
        route_label_resolved = True  # not applicable; treat as resolved

    return MetricsFlags(
        grounded_answer_available=grounded,
        evidence_shown=evidence_shown,
        unsupported_comparison_detected=unsupported_comparison_detected,
        route_label_ambiguity_resolved=route_label_resolved,
        useful_refusal_available=useful_refusal_present,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def build_replay_response(
    prompt_id: str, run_id: str = "full-run-v1"
) -> ProductCopilotResponse:
    """Stage 2 orchestrator. Loads → augments → infers → assembles."""
    bundle = loaders.load_prompt_bundle(prompt_id, run_id=run_id)

    raw_payload = payloads.parse_payload_snapshot(bundle.get("generator_record"))
    augmented_payload = product_schema.augment_payload_for_product(raw_payload)

    prompt = _prompt_metadata_from_bundle(bundle)
    generator_answer = _generator_answer_from_record(bundle.get("generator_record"))

    intent = infer_intent(
        prompt_text=prompt.prompt_text,
        family=prompt.family,
        generator_record=bundle.get("generator_record"),
    )

    answerability = compute_answerability(
        prompt_text=prompt.prompt_text,
        family=prompt.family,
        payload=augmented_payload,
        intent=intent,
        generator_record=bundle.get("generator_record"),
    )

    # Compose the canonical suggestions list once and reuse for both the
    # AnswerabilityResult, the useful_refusal, and the top-level response.
    suggestions = compose_suggestions(intent, answerability.missing_fields)
    answerability = answerability.model_copy(update={"suggested_next_actions": suggestions})

    evidence_items = evidence_mod.build_evidence_items(
        intent=intent,
        payload=augmented_payload,
        generator_record=bundle.get("generator_record"),
        row=bundle.get("joined_row"),
    )

    visual_actions = evidence_mod.infer_visual_actions(intent, evidence_items)

    warnings = build_warnings(
        prompt_id=prompt.prompt_id,
        intent=intent,
        payload=augmented_payload,
        answerability=answerability,
        prompt_text=prompt.prompt_text,
        answer_text=generator_answer.answer_text,
    )

    useful_refusal = build_useful_refusal(
        answerability,
        payload=augmented_payload,
        prompt_text=prompt.prompt_text,
    )

    metrics_flags = _compute_metrics_flags(
        joined_row=bundle.get("joined_row") or {},
        answerability=answerability,
        evidence_items=evidence_items,
        warnings=warnings,
        useful_refusal_present=useful_refusal is not None,
        intent=intent,
        augmented_payload=augmented_payload,
    )

    return ProductCopilotResponse(
        prompt_id=prompt.prompt_id,
        run_id=run_id,
        question=prompt.prompt_text,
        answer_text=generator_answer.answer_text,
        family=prompt.family,
        source=prompt.source,
        quadrant=prompt.quadrant,
        action_taken=prompt.action_taken,
        intent=intent,
        answerability=answerability,
        evidence=evidence_items,
        missing_fields=answerability.missing_fields,
        warnings=warnings,
        useful_refusal=useful_refusal,
        suggested_next_actions=suggestions,
        visual_actions=visual_actions,
        payload_augmented=augmented_payload,
        metrics_flags=metrics_flags,
        warnings_loader=list(bundle.get("warnings") or []),
    )
