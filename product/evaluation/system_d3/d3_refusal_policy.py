"""System D3 — causal-unsupported warning wrapper.

Layers on top of D2's `build_warnings_d2`. Emits the v2 warning
`causal_mechanism_unsupported` when the prompt asks a "why / what
caused" question targeting a factually-answerable intent.

The detector is deterministic — no model call, no payload
introspection beyond the answerability status produced upstream.

D3 does not modify `product/copilot/refusal_policy.py` and does
not modify D2's wrapper. It only adds the v2 causal warning.
"""
from __future__ import annotations

import re
from typing import Optional

from product.copilot.contracts import AnswerabilityResult, UsefulRefusal
from product.evaluation.system_d2.d2_refusal_policy import (
    build_useful_refusal_d2,
    build_warnings_d2,
)


# Intents that can yield citable facts. before_after_comparison is
# its own paraphrase class and already handled by D1/D2; unknown
# and refusal_or_insufficient_payload have no factual surface to
# cite, so the causal warning would just be noise.
_D3_FACTUAL_INTENTS = frozenset({
    "objective_value",
    "objective_delta",
    "feasibility_status",
    "route_count",
    "single_customer_route_membership",
    "same_route_boolean",
    "route_end_time",
    "customer_arrival",
    "lateness_summary",
    "new_customer_assignment",
    "full_route_listing",
})


# A small, conservative phrase bank. Each pattern targets a
# discrete causal framing. The bank is keyed off semantic
# categories (why-question, causation verb, push/drive metaphor),
# not against any specific heldout case text.
#
# `what's X` and `what is X` are both spelled as the alternation
# `what(?:'s| is)` — the apostrophe branch carries no extra
# whitespace, the `is` branch does.
_CAUSAL_PHRASE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\bwhy\s+(is|are|did|does|was|were|do|don't|am)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+caused\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'s| is)\s+causing\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+made\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'s| is)\s+pushing\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'s| is)\s+driving\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+drove\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'s| is)\s+behind\b", re.IGNORECASE),
    re.compile(r"\bwhat'?s\s+the\s+reason\b", re.IGNORECASE),
    re.compile(r"\breason\s+(?:for|behind|why)\b", re.IGNORECASE),
)


def is_causal_prompt(prompt_text: str) -> bool:
    if not prompt_text:
        return False
    return any(p.search(prompt_text) for p in _CAUSAL_PHRASE_PATTERNS)


def _should_emit_causal_warning(
    intent: str,
    answerability: AnswerabilityResult,
    prompt_text: str,
    existing_warnings: list[str],
) -> bool:
    if intent not in _D3_FACTUAL_INTENTS:
        return False
    if answerability.status == "not_answerable":
        # The case is a refusal; the operator's causal framing is
        # secondary to the missing-entity / missing-field issue. D2
        # has already explained the refusal.
        return False
    if "false_premise_detected" in existing_warnings:
        # A phantom entity dominates the causal framing.
        return False
    return is_causal_prompt(prompt_text)


def build_warnings_d3(
    prompt_id: str,
    intent: str,
    payload: Optional[dict],
    answerability: AnswerabilityResult,
    prompt_text: str = "",
    answer_text: str = "",
) -> list[str]:
    """D3-extended warnings.

    Delegates to `build_warnings_d2` for everything D2 already
    handles, then adds `causal_mechanism_unsupported` when the
    causal-prompt trigger fires.
    """
    warnings = list(
        build_warnings_d2(
            prompt_id=prompt_id,
            intent=intent,
            payload=payload,
            answerability=answerability,
            prompt_text=prompt_text,
            answer_text=answer_text,
        )
    )
    if _should_emit_causal_warning(intent, answerability, prompt_text, warnings):
        if "causal_mechanism_unsupported" not in warnings:
            warnings.append("causal_mechanism_unsupported")
    return warnings


def build_useful_refusal_d3(
    answerability: AnswerabilityResult,
    payload: Optional[dict] = None,
    prompt_text: str = "",
) -> Optional[UsefulRefusal]:
    """D3 useful refusal — unchanged from D2.

    The causal warning is non-refusal; it never produces a
    useful_refusal of its own, so this wrapper exists only to keep
    the surface symmetric with `build_warnings_d3`.
    """
    return build_useful_refusal_d2(
        answerability=answerability,
        payload=payload,
        prompt_text=prompt_text,
    )


__all__ = [
    "build_useful_refusal_d3",
    "build_warnings_d3",
    "is_causal_prompt",
]
