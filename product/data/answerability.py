"""Answerability computation.

Given an intent (computed by `product.copilot.intent`) and a payload,
determine which required fields are present and produce an
`AnswerabilityResult`. Pure function — no model calls, no I/O. The
orchestrator (product.copilot.response_builder) populates the
`suggested_next_actions` field afterwards by calling refusal_policy.
"""
from __future__ import annotations

from typing import Optional

from product.copilot.contracts import AnswerabilityResult
from product.data import entity_resolution, evidence, payloads


# Intents whose answerability depends on a specific customer or route
# named in the prompt. For these, the contract must additionally check
# that the named entity is actually in the augmented payload — a
# customer_arrival question about ``customer 999`` cannot be answered
# from a payload whose customer IDs are 1..30 even if the
# customer_schedule schema is fully present.
_CUSTOMER_BOUND_INTENTS = frozenset({
    "customer_arrival",
    "single_customer_route_membership",
    "same_route_boolean",
})
_ROUTE_BOUND_INTENTS = frozenset({"route_end_time"})


_REQUIRED_FIELDS: dict[str, list[str]] = {
    "objective_value": ["action_objective", "units.objective"],
    "objective_delta": [
        "baseline_objective",
        "action_objective",
        "objective_delta_absolute",
        "objective_delta_percent",
    ],
    "feasibility_status": ["feasible", "feasibility_breakdown"],
    "route_count": ["n_routes"],
    "single_customer_route_membership": ["routes[].customer_ids"],
    "same_route_boolean": ["routes[].customer_ids"],
    "route_end_time": ["route_end_times[].route_idx", "route_end_times[].end_time"],
    "customer_arrival": [
        "customer_schedule[].customer_id",
        "customer_schedule[].arrival",
    ],
    "lateness_summary": ["n_late_customers", "late_customer_ids"],
    "before_after_comparison": ["baseline_solution", "diff"],
    "new_customer_assignment": ["new_customer_ids", "routes[].customer_ids"],
    "full_route_listing": ["routes[].customer_ids"],
    "refusal_or_insufficient_payload": [],
    "unknown": [],
}


def required_fields_for_intent(intent: str, family: str = "") -> list[str]:
    return list(_REQUIRED_FIELDS.get(intent, []))


def _obj_delta_already_covered(payload: Optional[dict]) -> bool:
    """The OBJ payload exposes baseline_objective + delta inline, so
    a before/after comparison restricted to objective values does not
    actually require a separate baseline_solution / diff."""
    if not payload:
        return False
    return (
        "baseline_objective" in payload
        and "action_objective" in payload
        and "objective_delta_absolute" in payload
    )


def _answerable_subclaims(
    intent: str, payload: Optional[dict], missing: list[str]
) -> list[str]:
    """List narrower claims that are still answerable when not everything
    is. Stage-2 minimal: for before_after_comparison over OBJ, we can
    still report the current and baseline objective values."""
    if intent == "before_after_comparison" and _obj_delta_already_covered(payload):
        return ["objective_value", "objective_delta"]
    return []


def compute_answerability(
    prompt_text: str,
    family: str,
    payload: Optional[dict],
    intent: str,
    generator_record: Optional[dict] = None,
) -> AnswerabilityResult:
    required = required_fields_for_intent(intent, family)
    available = payloads.available_payload_fields(payload)

    missing = [path for path in required if not evidence.field_path_exists(payload, path)]

    # OBJ escape hatch: before/after questions about cost are answerable
    # from baseline_objective + objective_delta_* without a separate
    # baseline_solution structure.
    if intent == "before_after_comparison" and (family or "").upper() == "OBJ":
        if _obj_delta_already_covered(payload):
            missing = []

    if not required:
        # Unknown / refusal intents have no required-fields key — treat
        # them as not-answerable so the refusal layer surfaces a useful
        # message instead of silently passing.
        if intent in ("unknown", "refusal_or_insufficient_payload"):
            status = "not_answerable"
        else:
            status = "answerable"
    elif not missing:
        status = "answerable"
    elif len(missing) < len(required):
        status = "partially_answerable"
    else:
        status = "not_answerable"

    # False-premise override (schema §12): if the prompt names a
    # customer or route that does not exist in the payload, the
    # question is not_answerable regardless of which schema fields are
    # present. Missing-fields stays empty — the issue is a phantom
    # entity, not an absent column.
    if intent in _CUSTOMER_BOUND_INTENTS and entity_resolution.prompt_references_unknown_customer(
        payload, prompt_text
    ):
        status = "not_answerable"
        missing = []
    elif intent in _ROUTE_BOUND_INTENTS and entity_resolution.prompt_references_unknown_route(
        payload, prompt_text
    ):
        status = "not_answerable"
        missing = []

    # Comparison-referent ambiguity (OBJ delta): if the prompt names a
    # comparator that baseline_objective does not describe (e.g. ``full
    # re-solve``, ``optimum``) and reference_solution.objective is
    # absent, the OBJ escape hatch no longer covers the full question.
    # The contract can still cite the inline OBJ fields but should
    # surface reference_solution.objective as the missing piece for the
    # named comparator's subclaim.
    if (
        intent == "objective_delta"
        and entity_resolution.prompt_has_ambiguous_comparison_referent(prompt_text)
        and not evidence.field_path_exists(payload, "reference_solution.objective")
    ):
        if "reference_solution.objective" not in missing:
            missing = list(missing) + ["reference_solution.objective"]
        status = "partially_answerable"

    return AnswerabilityResult(
        status=status,
        intent=intent,
        required_fields=required,
        available_fields=available,
        missing_fields=missing,
        answerable_subclaims=_answerable_subclaims(intent, payload, missing),
        suggested_next_actions=[],  # filled in by orchestrator
    )
