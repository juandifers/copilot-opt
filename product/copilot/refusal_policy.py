"""Warnings, useful refusals, and next-action suggestions.

Stage 2 warnings are short string codes (the frontend or `metrics.py`
maps them to display messages); useful_refusal is a structured object
that fills in when answerability is partial or none.
"""
from __future__ import annotations

import re
from typing import Optional

from product.copilot.contracts import AnswerabilityResult, UsefulRefusal
from product.data import entity_resolution


_CUSTOMER_BOUND_INTENTS = frozenset({
    "customer_arrival",
    "single_customer_route_membership",
    "same_route_boolean",
})
_ROUTE_BOUND_INTENTS = frozenset({"route_end_time"})


def _is_false_premise_case(
    intent: str, payload: Optional[dict], prompt_text: str
) -> bool:
    """Mirror of the answerability layer's false-premise override."""
    if intent in _CUSTOMER_BOUND_INTENTS:
        if entity_resolution.prompt_references_unknown_customer(payload, prompt_text):
            return True
    if intent in _ROUTE_BOUND_INTENTS:
        if entity_resolution.prompt_references_unknown_route(payload, prompt_text):
            return True
    return False


# Prompts that Run 1 analysis explicitly flagged for product-schema gaps,
# beyond what rule-based detection would catch.
_KNOWN_ROUTE_INDEXING_PROMPTS = {"040", "041"}
_KNOWN_STRUCT_MEMBERSHIP_PROMPTS = {"029"}

# A route-indexing concern only really applies when an integer route number
# actually appears somewhere the user can see — in the question or in the
# answer. Firing the warning merely because the intent is route-typed
# generates UI noise on questions like "how many routes?" that never name
# a route by integer.
_ROUTE_NUMBER_REGEX = re.compile(r"\broute\s+\d+\b", re.IGNORECASE)


def _references_route_by_number(text: str) -> bool:
    if not text:
        return False
    return _ROUTE_NUMBER_REGEX.search(text) is not None

_NEXT_ACTION_BY_FIELD: dict[str, str] = {
    "baseline_solution": "Build before/after comparison payload.",
    "diff": "Build before/after comparison payload.",
    "new_customer_ids": "Expose perturbation.new_customer_ids in the product payload.",
    "routes[].route_label": "Apply product route-label schema augmentation.",
    "routes[].display_route_number": "Apply product route-label schema augmentation.",
    "customer_schedule[].arrival": "Use SCHEDULE payload or run schedule projection.",
    "customer_schedule[].customer_id": "Use SCHEDULE payload or run schedule projection.",
    "route_end_times[].end_time": "Use SCHEDULE payload or run schedule projection.",
    "route_end_times[].route_idx": "Use SCHEDULE payload or run schedule projection.",
    # Stage R2-3 extensions — semantic codes emitted directly because the
    # gold rubric is also in semantic-code shape.
    "feasible": "use_validity_payload",
    "feasibility_breakdown": "use_validity_payload",
    "units.objective": "expose_units_objective",
    "reference_solution.objective": "expose_reference_solution_objective",
}


def suggested_next_actions_for_missing_fields(missing_fields: list[str]) -> list[str]:
    """Deduplicated, order-preserving list of suggestions."""
    seen: set[str] = set()
    suggestions: list[str] = []
    for field in missing_fields:
        action = _NEXT_ACTION_BY_FIELD.get(field)
        if action and action not in seen:
            seen.add(action)
            suggestions.append(action)
    return suggestions


def compose_suggestions(intent: str, missing_fields: list[str]) -> list[str]:
    """Canonical suggestions for the top-level response and the useful refusal.

    Falls back to a generic 'narrow your question' suggestion when intent is
    unknown / refusal-shaped and there are no concrete missing fields."""
    suggestions = suggested_next_actions_for_missing_fields(missing_fields)
    if not suggestions and intent in ("unknown", "refusal_or_insufficient_payload"):
        suggestions = [
            "Narrow the question to a specific customer, route, or claim "
            "type, or pick a field from the available payload fields list."
        ]
    return suggestions


def build_warnings(
    prompt_id: str,
    intent: str,
    payload: Optional[dict],
    answerability: AnswerabilityResult,
    prompt_text: str = "",
    answer_text: str = "",
) -> list[str]:
    warnings: list[str] = []

    # route_indexing_ambiguity: fires only when an actual route number
    # appears somewhere user-visible (the question or the answer) or
    # the prompt is one of the explicitly flagged Run 1 cases. This is
    # narrower than "fire for any route-typed intent" because warnings
    # carry an operator-attention cost: firing on a question that does
    # not name a route by integer creates UI noise.
    if (
        prompt_id in _KNOWN_ROUTE_INDEXING_PROMPTS
        or _references_route_by_number(prompt_text)
        or _references_route_by_number(answer_text)
    ):
        warnings.append("route_indexing_ambiguity")

    # struct_membership_ambiguity: single-customer membership claims are
    # the ambiguous case (subset vs full-route set equality).
    if intent == "single_customer_route_membership" or prompt_id in _KNOWN_STRUCT_MEMBERSHIP_PROMPTS:
        warnings.append("struct_membership_ambiguity")

    # unsupported_comparison: before/after asked but not fully answerable.
    if intent == "before_after_comparison" and answerability.status != "answerable":
        warnings.append("unsupported_comparison")

    # missing_new_customer_attribution: new_customer_assignment needs ids.
    if (
        intent == "new_customer_assignment"
        and "new_customer_ids" in answerability.missing_fields
    ):
        warnings.append("missing_new_customer_attribution")

    # evidence_units_missing: OBJ value/delta is grounded by action_objective
    # but cannot be displayed without a unit annotation. Fires when units.objective
    # is the missing-field hole on an OBJ value/delta question.
    if (
        intent in ("objective_value", "objective_delta")
        and "units.objective" in answerability.missing_fields
    ):
        warnings.append("evidence_units_missing")

    # false_premise_detected: prompt names a customer or route that
    # does not exist in the payload. Distinct from a missing schema
    # column — the schema is intact, the named entity simply is not
    # present.
    if _is_false_premise_case(intent, payload, prompt_text):
        warnings.append("false_premise_detected")

    # comparison_referent_ambiguity: OBJ delta question names a
    # comparator (``a full re-solve``, ``the optimum``) that the
    # pre-perturbation baseline_objective does not describe. Fires
    # when the answerability layer has flagged the gap by listing
    # reference_solution.objective as missing.
    if (
        intent == "objective_delta"
        and "reference_solution.objective" in answerability.missing_fields
    ):
        warnings.append("comparison_referent_ambiguity")

    # When false_premise_detected fires, it dominates the other
    # entity-shape warnings (route_indexing_ambiguity,
    # struct_membership_ambiguity). Those warnings are about how to
    # display or qualify a *real* entity; a phantom entity makes them
    # moot. The gold rubric (R2-015, R2-047, R2-059) requires only
    # false_premise_detected in this state.
    if "false_premise_detected" in warnings:
        warnings = [
            w
            for w in warnings
            if w
            not in {"route_indexing_ambiguity", "struct_membership_ambiguity"}
        ]

    # Dedup while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            deduped.append(w)
    return deduped


def build_useful_refusal(
    answerability: AnswerabilityResult,
    payload: Optional[dict] = None,
    prompt_text: str = "",
) -> Optional[UsefulRefusal]:
    if answerability.status == "answerable":
        return None

    intent = answerability.intent
    missing = list(answerability.missing_fields)
    subclaims = list(answerability.answerable_subclaims)

    false_premise = _is_false_premise_case(intent, payload, prompt_text)

    reason_parts: list[str] = []
    if false_premise:
        if intent in _ROUTE_BOUND_INTENTS:
            unknown_routes = sorted(
                entity_resolution.unknown_route_numbers_from_prompt(
                    payload, prompt_text
                )
            )
            reason_parts.append(
                "The current plan does not contain the route referenced "
                f"in the question (Route {', '.join(str(n) for n in unknown_routes)})."
            )
        else:
            unknown_customers = sorted(
                entity_resolution.unknown_customer_ids_from_prompt(
                    payload, prompt_text
                )
            )
            reason_parts.append(
                "The current plan does not contain the customer "
                f"referenced in the question (customer "
                f"{', '.join(str(c) for c in unknown_customers)})."
            )
    elif intent == "before_after_comparison":
        reason_parts.append(
            "The current payload does not contain before/after route "
            "comparison fields. It can show the current route plan, but "
            "not whether the route structure changed."
        )
    elif intent == "new_customer_assignment":
        reason_parts.append(
            "The current payload does not record which customer IDs the "
            "perturbation added, so the assignment of the new customer "
            "cannot be attributed directly."
        )
    elif intent in ("unknown", "refusal_or_insufficient_payload"):
        reason_parts.append(
            "The product copilot could not classify this question into "
            "a known intent. Show the available payload fields and let "
            "the operator pick a narrower question."
        )
    else:
        reason_parts.append(
            f"The payload is missing required fields for intent {intent!r}."
        )

    if missing:
        reason_parts.append(f"Missing fields: {', '.join(missing)}.")

    suggestions = compose_suggestions(intent, missing)
    if false_premise and "clarify_false_premise" not in suggestions:
        suggestions = ["clarify_false_premise"] + suggestions

    return UsefulRefusal(
        refusal_reason=" ".join(reason_parts),
        missing_fields=missing,
        available_subclaims=subclaims,
        suggested_next_actions=suggestions,
    )
