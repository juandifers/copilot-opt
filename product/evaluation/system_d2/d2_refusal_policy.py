"""System D2 — warnings + useful-refusal extension wrapper.

Wraps `product.copilot.refusal_policy.build_warnings` and
`build_useful_refusal` to:

1. Fire `route_indexing_ambiguity` on `vehicle N` and `truck N`
   paraphrases in addition to the existing literal `route N`
   detection. The existing literal-route behaviour is preserved
   because the D2 detector is a *strict superset* of the C0/D1
   detector.

2. Add `false_premise_detected` warning + `clarify_false_premise`
   next action + useful-refusal shape when the D2 answerability
   widening fires (lateness_summary / feasibility_status with an
   unknown customer named in the prompt).

The downstream `product/copilot/refusal_policy.py` is NOT modified
in place; this preserves C0 and D1 reproducibility. D2's harness
calls these wrappers directly.

Over-firing rails:
- `vehicle N` / `truck N` patterns require a digit token; ordinal
  phrasings like ``the first vehicle`` or plural ``vehicles 1-4``
  do not trigger.
- The false-premise widening only fires when the prompt explicitly
  names a customer absent from the payload — generic
  ``Is anyone late?`` / ``Is the plan feasible?`` are untouched.
"""
from __future__ import annotations

import re
from typing import Optional

from product.copilot.contracts import AnswerabilityResult, UsefulRefusal
from product.copilot.refusal_policy import (
    _is_false_premise_case as _c0_d1_false_premise_case,
    build_useful_refusal as _c0_d1_build_useful_refusal,
    build_warnings as _c0_d1_build_warnings,
    compose_suggestions,
)
from product.data import entity_resolution

from product.evaluation.system_d2.d2_answerability import (
    D2_WIDENED_CUSTOMER_BOUND_INTENTS,
    _d2_widened_false_premise_fires,
)


# A `vehicle N` / `truck N` paraphrase. `\b\d+\b` enforces a bare
# integer immediately following the noun, so ordinal phrasings
# (``the first vehicle``) and plural ranges (``vehicles 1-4`` —
# matched as `vehicles` not `vehicle`) do not trigger.
_VEHICLE_NUMBER_REGEX = re.compile(r"\b(vehicle|truck)\s+\d+\b", re.IGNORECASE)


def _d2_references_route_alias_by_number(text: str) -> bool:
    if not text:
        return False
    return _VEHICLE_NUMBER_REGEX.search(text) is not None


def build_warnings_d2(
    prompt_id: str,
    intent: str,
    payload: Optional[dict],
    answerability: AnswerabilityResult,
    prompt_text: str = "",
    answer_text: str = "",
) -> list[str]:
    """D2-extended warnings.

    Delegates to the C0/D1 `build_warnings` for the canonical
    decision, then applies the two D2 additions on top.
    """
    warnings = list(
        _c0_d1_build_warnings(
            prompt_id=prompt_id,
            intent=intent,
            payload=payload,
            answerability=answerability,
            prompt_text=prompt_text,
            answer_text=answer_text,
        )
    )

    # D2 rail 1: vehicle N / truck N → route_indexing_ambiguity.
    if (
        _d2_references_route_alias_by_number(prompt_text)
        or _d2_references_route_alias_by_number(answer_text)
    ):
        if "route_indexing_ambiguity" not in warnings:
            warnings.append("route_indexing_ambiguity")

    # D2 rail 2: widened false-premise → false_premise_detected
    # (plus the same dominance rule the C0/D1 layer applies).
    if _d2_widened_false_premise_fires(intent, payload, prompt_text):
        if "false_premise_detected" not in warnings:
            warnings.append("false_premise_detected")

    # Preserve the C0/D1 dominance rule: false_premise_detected
    # dominates entity-shape warnings about a phantom entity.
    if "false_premise_detected" in warnings:
        warnings = [
            w
            for w in warnings
            if w
            not in {"route_indexing_ambiguity", "struct_membership_ambiguity"}
        ]

    # Dedup preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            deduped.append(w)
    return deduped


def build_useful_refusal_d2(
    answerability: AnswerabilityResult,
    payload: Optional[dict] = None,
    prompt_text: str = "",
) -> Optional[UsefulRefusal]:
    """D2-extended useful refusal.

    When the D2-widened false-premise fires (lateness_summary /
    feasibility_status + unknown customer), build a refusal that
    names the missing customer using the same reason text and
    next-action shape as the C0/D1 customer-bound path.
    Otherwise, defer to the C0/D1 builder unchanged.
    """
    if answerability.status == "answerable":
        return None

    intent = answerability.intent
    if _d2_widened_false_premise_fires(intent, payload, prompt_text):
        unknown_customers = sorted(
            entity_resolution.unknown_customer_ids_from_prompt(
                payload, prompt_text
            )
        )
        reason = (
            "The current plan does not contain the customer referenced "
            f"in the question (customer "
            f"{', '.join(str(c) for c in unknown_customers)})."
        )
        suggestions = compose_suggestions(intent, list(answerability.missing_fields))
        if "clarify_false_premise" not in suggestions:
            suggestions = ["clarify_false_premise"] + suggestions
        return UsefulRefusal(
            refusal_reason=reason,
            missing_fields=list(answerability.missing_fields),
            available_subclaims=list(answerability.answerable_subclaims),
            suggested_next_actions=suggestions,
        )

    return _c0_d1_build_useful_refusal(
        answerability=answerability,
        payload=payload,
        prompt_text=prompt_text,
    )


__all__ = [
    "_d2_references_route_alias_by_number",
    "build_useful_refusal_d2",
    "build_warnings_d2",
]
