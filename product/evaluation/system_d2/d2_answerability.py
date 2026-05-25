"""System D2 — answerability extension wrapper.

Wraps `product.data.answerability.compute_answerability` with a
minimal widening: when the prompt explicitly references a customer
ID that is absent from the payload, treat the question as
`not_answerable` (with empty missing_fields, per the
false-premise §12 rule already used by `_CUSTOMER_BOUND_INTENTS`),
even when the intent is `lateness_summary` or `feasibility_status`.

D2 does not modify `product/data/answerability.py` in place; this
keeps the C0 and D1 baselines reproducible from their existing
runners. The widening only fires when a customer ID actually
appears in the prompt — generic lateness / feasibility questions
are untouched.
"""
from __future__ import annotations

from typing import Optional

from product.copilot.contracts import AnswerabilityResult
from product.data import entity_resolution
from product.data.answerability import compute_answerability


D2_WIDENED_CUSTOMER_BOUND_INTENTS = frozenset({
    "lateness_summary",
    "feasibility_status",
})


def _d2_widened_false_premise_fires(
    intent: str, payload: Optional[dict], prompt_text: str
) -> bool:
    """True iff D2's widened false-premise check should fire.

    Conditions:
      - intent is one of D2's widened set (lateness_summary,
        feasibility_status), AND
      - the prompt explicitly names a customer ID that the payload
        does not contain.

    A generic ``Is anyone going to be late?`` prompt names no
    customer and therefore does not trigger D2's widening.
    """
    if intent not in D2_WIDENED_CUSTOMER_BOUND_INTENTS:
        return False
    return entity_resolution.prompt_references_unknown_customer(payload, prompt_text)


def compute_answerability_d2(
    prompt_text: str,
    family: str,
    payload: Optional[dict],
    intent: str,
    generator_record: Optional[dict] = None,
) -> AnswerabilityResult:
    """D2-extended answerability.

    Defers to the locked `compute_answerability` for the canonical
    decision, then applies the D2 widening only when the prompt
    explicitly references an unknown customer under a
    lateness_summary / feasibility_status intent.
    """
    base = compute_answerability(
        prompt_text=prompt_text,
        family=family,
        payload=payload,
        intent=intent,
        generator_record=generator_record,
    )
    if _d2_widened_false_premise_fires(intent, payload, prompt_text):
        return base.model_copy(
            update={"status": "not_answerable", "missing_fields": []}
        )
    return base


__all__ = [
    "D2_WIDENED_CUSTOMER_BOUND_INTENTS",
    "compute_answerability_d2",
]
