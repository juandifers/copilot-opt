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
    # Overview / explanation intents.
    #
    # ``perturbation_summary`` / ``scenario_summary`` are answered from
    # perturbation metadata (always derivable from perturbation_id) plus
    # whatever solution-shape signal the payload carries. We list no
    # required payload fields because the perturbation card itself is
    # always producible from the scenario row.
    "perturbation_summary": [],
    "scenario_summary": [],
    # ``solution_summary`` needs at least one solution-shape signal.
    # ``feasible`` is the most common headline; the other signals fall
    # through naturally as additional context.
    "solution_summary": ["feasible"],
    # Impact intents need baseline + diff to give a full answer. When
    # missing, the contract returns partially_answerable and the
    # renderer falls back to a current-state description.
    "perturbation_impact_summary": ["baseline_solution", "diff"],
    "route_impact_summary": ["baseline_solution", "diff"],
    # ``what_to_watch`` is answerable from any solution-shape signal —
    # there's always something to point at.
    "what_to_watch": [],
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

    # Overview-intent graceful degradation.
    #
    # Impact intents (perturbation_impact_summary, route_impact_summary)
    # require baseline_solution + diff for a full answer, but a useful
    # *partial* answer is still possible whenever the payload exposes a
    # current solution — the renderer describes current status and says
    # impact cannot be quantified without comparison data. Treating these
    # as not_answerable here would silence that partial answer, which is
    # the whole point of grounded overview support.
    _OVERVIEW_IMPACT_INTENTS = {
        "perturbation_impact_summary",
        "route_impact_summary",
    }
    if intent in _OVERVIEW_IMPACT_INTENTS and status == "not_answerable":
        if isinstance(payload, dict) and any(
            k in payload
            for k in (
                "feasible",
                "action_objective",
                "routes",
                "customer_schedule",
                "n_routes",
            )
        ):
            status = "partially_answerable"

    # solution_summary degrades to partial when the headline feasibility
    # flag is missing but some other solution-shape signal is present
    # (routes / objective / schedule). Without this, a payload that
    # exposes routes but not feasibility would be reported as
    # not_answerable, suppressing the renderer's natural fallback.
    if intent == "solution_summary" and status == "not_answerable":
        if isinstance(payload, dict) and any(
            k in payload
            for k in ("action_objective", "routes", "customer_schedule", "n_routes")
        ):
            status = "partially_answerable"

    # OBJ-inline escape hatch for perturbation_impact_summary.
    #
    # OBJ-family payloads carry ``baseline_objective`` and
    # ``objective_delta_absolute`` inline rather than as a separate
    # ``baseline_solution`` / ``diff`` block. For the *objective-level*
    # impact question, that inline data is enough to give an actual
    # answer (the renderer cites the delta). The route-level impact
    # intent still needs a route-level diff, so this escape hatch is
    # intent-specific.
    if (
        intent == "perturbation_impact_summary"
        and isinstance(payload, dict)
        and payload.get("baseline_objective") is not None
        and payload.get("objective_delta_absolute") is not None
    ):
        status = "answerable"
        missing = []

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
