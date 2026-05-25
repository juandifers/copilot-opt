"""Deterministic prior for System A (R2-6).

Wires the existing product-layer functions (intent classifier,
answerability checker, warning policy, next-action policy) into a
single `build_system_a_prior(case, payload)` helper. The result is a
JSON-serialisable dict the System A prompt builder embeds in the
model's context.

System A intentionally calls these functions with
`generator_record=None`: a fresh evaluator only has the prompt text +
materialised payload; it does not get to peek at Run 1's structured
output. C-extended uses `generator_record` for claim-aware pinning,
but System A's purpose is to be a *thin* prior — so we use the same
inputs an external evaluator would.

The prior layer does NOT call `run_system_c_on_case`. Doing so would
collapse A into "C with one extra step" and defeat the experiment.
"""
from __future__ import annotations

from typing import Any, Optional

from product.copilot.intent import infer_intent
from product.copilot.refusal_policy import (
    build_warnings,
    suggested_next_actions_for_missing_fields,
)
from product.data import payloads as payloads_mod
from product.data import product_schema
from product.data.answerability import (
    compute_answerability,
    required_fields_for_intent,
)

from product.evaluation.run2_case_loader import Run2Case


# ---------------------------------------------------------------------------
# Locked fields — the prompt instructs the model to copy these verbatim
# unless it flags `prior_disagreement=true` and explains in
# `adapter_notes`.
# ---------------------------------------------------------------------------

PRIOR_LOCKED_FIELDS: list[str] = [
    "predicted_intent",
    "predicted_answerability",
    "predicted_missing_fields",
    "predicted_warnings",
    "predicted_next_actions",
    "predicted_behavior_class",
]


# ---------------------------------------------------------------------------
# Semantic next-action mapping (mirror of run2_scoring._to_semantic_action)
# ---------------------------------------------------------------------------

# `suggested_next_actions_for_missing_fields` returns the concrete
# strings the product UI displays. The gold rubric and the System B
# prompt both use semantic codes. We map concrete -> semantic for the
# prior so the model sees the same code it is expected to emit.

_CONCRETE_TO_SEMANTIC: dict[str, str] = {
    "Build before/after comparison payload.": "build_baseline_comparison_payload",
    "Expose perturbation.new_customer_ids in the product payload.": "expose_new_customer_ids",
    "Apply product route-label schema augmentation.": "apply_route_label_augmentation",
    "Use SCHEDULE payload or run schedule projection.": "use_schedule_payload",
    "Narrow the question to a specific customer, route, or claim type, "
    "or pick a field from the available payload fields list.": "narrow_question_to_available_field",
    # R2-3 extension codes (already semantic in refusal_policy._NEXT_ACTION_BY_FIELD)
    "use_validity_payload": "use_validity_payload",
    "expose_units_objective": "expose_units_objective",
    "expose_reference_solution_objective": "expose_reference_solution_objective",
}


def _to_semantic(action: str) -> str:
    if action in _CONCRETE_TO_SEMANTIC:
        return _CONCRETE_TO_SEMANTIC[action]
    # Anything else: if it already looks like a snake_case semantic code,
    # pass through; otherwise keep verbatim and let the scorer sort it.
    if " " not in action and "." not in action:
        return action
    return action


# ---------------------------------------------------------------------------
# Behavior class projection
# ---------------------------------------------------------------------------


def _project_behavior_class(
    answerability: str, warnings: list[str], has_missing: bool
) -> str:
    """Mirror of `run2_system_c._infer_behavior_class`, but on the prior's
    shape (we do not have EvidenceItem objects at prior-build time).

    For partially_answerable cases the discriminator C uses is "is there
    any evidence cited?" — the prior cannot know that until the model
    has picked evidence paths. We approximate:

    - answerable + no warnings           → direct_answer
    - answerable + warnings              → direct_answer_with_warning
    - partially_answerable + missing     → partial_answer_with_warning
    - partially_answerable, no missing   → useful_refusal (rare edge)
    - not_answerable                     → useful_refusal
    """
    if answerability == "answerable":
        return "direct_answer_with_warning" if warnings else "direct_answer"
    if answerability == "partially_answerable":
        return "partial_answer_with_warning" if has_missing else "useful_refusal"
    return "useful_refusal"


# ---------------------------------------------------------------------------
# Next-action prior assembly
# ---------------------------------------------------------------------------


def _next_actions_prior(
    intent: str, missing_fields: list[str], warnings: list[str]
) -> list[str]:
    """Semantic codes derived from missing fields and (where applicable)
    fired warnings. Mirrors `refusal_policy.build_useful_refusal` in
    that `clarify_false_premise` is prepended when
    `false_premise_detected` is in warnings."""
    concrete = suggested_next_actions_for_missing_fields(missing_fields)
    actions: list[str] = []
    seen: set[str] = set()
    for c in concrete:
        sem = _to_semantic(c)
        if sem not in seen:
            seen.add(sem)
            actions.append(sem)
    if "false_premise_detected" in warnings and "clarify_false_premise" not in seen:
        actions = ["clarify_false_premise"] + actions
    return actions


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_system_a_prior(
    case: Run2Case, payload: Optional[dict]
) -> dict[str, Any]:
    """Compute the System A prior for one case.

    All keys in the result are JSON-serialisable. The model receives
    this dict (rendered as JSON) in its prompt; the prompt builder
    decides how to surface "locked" vs "informational" fields. The
    `prior_locked_fields` key documents which output keys the model
    is forbidden to override unless it flags disagreement.
    """
    augmented = product_schema.augment_payload_for_product(payload)

    intent = infer_intent(
        prompt_text=case.prompt_text,
        family=case.family,
        generator_record=None,
    )

    answerability = compute_answerability(
        prompt_text=case.prompt_text,
        family=case.family,
        payload=augmented,
        intent=intent,
        generator_record=None,
    )

    warnings = build_warnings(
        prompt_id=case.case_id,
        intent=intent,
        payload=augmented,
        answerability=answerability,
        prompt_text=case.prompt_text,
        # No model answer at prior-build time; warnings that fire from
        # answer_text (e.g. route_indexing_ambiguity by lexical match
        # on the answer) will only see the prompt side.
        answer_text="",
    )

    missing_fields = list(answerability.missing_fields)
    next_actions = _next_actions_prior(intent, missing_fields, warnings)

    behavior_class = _project_behavior_class(
        answerability.status,
        warnings=warnings,
        has_missing=bool(missing_fields),
    )

    return {
        "intent_prior": intent,
        "answerability_prior": answerability.status,
        "required_fields": list(answerability.required_fields),
        "available_fields": list(answerability.available_fields),
        "missing_fields_prior": missing_fields,
        "warnings_prior": list(warnings),
        "next_actions_prior": list(next_actions),
        "behavior_class_prior": behavior_class,
        "prior_locked_fields": list(PRIOR_LOCKED_FIELDS),
        # Bookkeeping the prompt does not surface to the model:
        "_answerable_subclaims": list(answerability.answerable_subclaims),
    }


__all__ = [
    "PRIOR_LOCKED_FIELDS",
    "build_system_a_prior",
]
