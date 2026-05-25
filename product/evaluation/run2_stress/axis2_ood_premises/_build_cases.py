"""Deterministic case generator for R2-S Axis 2 (OOD false premises
and comparators).

Run once to regenerate `cases.csv` from the (StressSpec) tables below.
Idempotent — same input -> same output (header order fixed, row order
fixed, line endings via `csv` module).

Axis 2 cases do NOT inherit gold verbatim from the base case (unlike
Axis 1 / Axis 3). Each stress case authors its own gold contract
response per `design.md` §4. The `base_case_id` column is used for:

  - payload materialization (via the base case's `source_prompt_id`
    looked up against the locked Run 2 benchmark CSV);
  - traceability in reports.

Usage:

    python -m product.evaluation.run2_stress.axis2_ood_premises._build_cases

writes/overwrites `cases.csv` next to this file. No other side effects.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


HERE = Path(__file__).resolve().parent
LOCKED_BENCHMARK = HERE.parents[1] / "run2_benchmark_cases.csv"


# ---------------------------------------------------------------------------
# Stress spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StressSpec:
    """One authored stress case. Gold is set per case (Axis 2 does
    not inherit from the base case)."""

    case_id: str
    split: str  # dev | heldout
    band: str
    stress_subtype: str
    premise_type: str
    expected_failure_mode: str
    base_case_id: str
    base_family: str

    prompt_text: str
    canonical_supported_prompt: str
    payload_condition: str

    expected_intent: str
    expected_answerability: str
    expected_evidence_paths: list[str]
    expected_missing_fields: list[str]
    expected_warnings: list[str]
    expected_next_actions: list[str]
    expected_behavior_class: str
    implementation_status: str
    difficulty: str
    label_rationale: str
    ambiguity_notes: str

    false_entity_type: str = ""
    false_entity_value: str = ""
    comparator_type: str = ""
    missing_support_field: str = ""
    unsupported_assumption: str = ""
    notes: str = ""


STRESS_AXIS = "ood_premises_comparators"


# ---------------------------------------------------------------------------
# Band 1 — nonexistent_entity_false_premise
# ---------------------------------------------------------------------------


BAND1 = [
    StressSpec(
        case_id="A2D-01",
        split="dev",
        band="nonexistent_entity_false_premise",
        stress_subtype="nonexistent_customer_in_customer_arrival",
        premise_type="nonexistent_entity",
        expected_failure_mode="should_detect_false_premise",
        base_case_id="R2-007",
        base_family="SCHEDULE",
        prompt_text=(
            "When does the driver get to customer 4242 in this updated schedule?"
        ),
        canonical_supported_prompt=(
            "When does the driver reach customer 42 after the new orders came in?"
        ),
        payload_condition="false_premise_customer",
        expected_intent="customer_arrival",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        expected_warnings=["false_premise_detected"],
        expected_next_actions=["clarify_false_premise"],
        expected_behavior_class="useful_refusal",
        implementation_status="target_extension",
        difficulty="medium",
        label_rationale=(
            "customer_arrival is a _CUSTOMER_BOUND_INTENT, so "
            "entity_resolution.prompt_references_unknown_customer fires on "
            "the OOD customer ID 4242 (absent from prompt 007's payload). "
            "Per the R2-3 false-premise extension, the contract should "
            "refuse with false_premise_detected and clarify_false_premise. "
            "implementation_status is target_extension because the "
            "false_premise_detected warning is a proposed R2-1 extension."
        ),
        ambiguity_notes=(
            "Identical contract shape to locked R2-008 / R2-058; the "
            "OOD piece is the surface paraphrase ('get to' instead of "
            "'reach', 'updated schedule' instead of the canonical "
            "'after the new orders came in')."
        ),
        false_entity_type="customer",
        false_entity_value="4242",
        unsupported_assumption=(
            "Customer 4242 exists in the current plan's schedule."
        ),
        notes="C0 should detect via entity_resolution.",
    ),
    StressSpec(
        case_id="A2D-02",
        split="dev",
        band="nonexistent_entity_false_premise",
        stress_subtype="nonexistent_customer_in_membership",
        premise_type="nonexistent_entity",
        expected_failure_mode="should_detect_false_premise",
        base_case_id="R2-039",
        base_family="STRUCT",
        prompt_text=(
            "Which route is customer 4242 assigned to in this revised plan?"
        ),
        canonical_supported_prompt=(
            "Which route is customer 42 on after a new order came in?"
        ),
        payload_condition="false_premise_customer",
        expected_intent="single_customer_route_membership",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        expected_warnings=["false_premise_detected"],
        expected_next_actions=["clarify_false_premise"],
        expected_behavior_class="useful_refusal",
        implementation_status="target_extension",
        difficulty="medium",
        label_rationale=(
            "single_customer_route_membership is a _CUSTOMER_BOUND_INTENT; "
            "the OOD customer ID 4242 is absent from prompt 029's payload. "
            "Per R2-3, the contract refuses and the struct_membership "
            "warning is dominated by false_premise_detected per the "
            "refusal_policy build_warnings dedupe rule."
        ),
        ambiguity_notes=(
            "OOD only in surface wording ('assigned to in this revised "
            "plan') — contract shape mirrors R2-047."
        ),
        false_entity_type="customer",
        false_entity_value="4242",
        unsupported_assumption="Customer 4242 is a known customer in the plan.",
        notes="C0 should detect.",
    ),
    StressSpec(
        case_id="A2D-03",
        split="dev",
        band="nonexistent_entity_false_premise",
        stress_subtype="nonexistent_customer_in_lateness",
        premise_type="nonexistent_entity",
        expected_failure_mode="should_detect_false_premise",
        base_case_id="R2-051",
        base_family="SCHEDULE",
        prompt_text=(
            "Did customer 9999 end up running late in this plan?"
        ),
        canonical_supported_prompt=(
            "Is anyone going to be late after travel times went up 50%?"
        ),
        payload_condition="false_premise_customer",
        expected_intent="lateness_summary",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        expected_warnings=["false_premise_detected"],
        expected_next_actions=["clarify_false_premise"],
        expected_behavior_class="useful_refusal",
        implementation_status="target_extension",
        difficulty="hard",
        label_rationale=(
            "C0's false-premise check is gated to _CUSTOMER_BOUND_INTENTS "
            "(customer_arrival, single_customer_route_membership, "
            "same_route_boolean). lateness_summary is NOT in that set, so "
            "the existing contract will treat the question as answerable "
            "against the late_customer_ids list, silently ignoring that "
            "customer 9999 is not in the payload at all. The faithful "
            "gold is useful_refusal with false_premise_detected; this is "
            "target_extension because the contract does not yet do this."
        ),
        ambiguity_notes=(
            "Predicted C0 outcome: lateness_summary + answerable + "
            "direct_answer (false-premise check not applied). Expected "
            "bucket: missed_false_premise."
        ),
        false_entity_type="customer",
        false_entity_value="9999",
        unsupported_assumption=(
            "Customer 9999 exists and could plausibly be late."
        ),
        notes=(
            "C0 should MISS this — false-premise check not wired for "
            "lateness_summary intent."
        ),
    ),
    StressSpec(
        case_id="A2H-01",
        split="heldout",
        band="nonexistent_entity_false_premise",
        stress_subtype="nonexistent_route_in_route_end",
        premise_type="nonexistent_entity",
        expected_failure_mode="should_detect_false_premise",
        base_case_id="R2-053",
        base_family="SCHEDULE",
        prompt_text=(
            "What time does Route 75 wrap up after the perturbation?"
        ),
        canonical_supported_prompt=(
            "Is anyone going to be late after travel times went up 10%?"
        ),
        payload_condition="false_premise_route",
        expected_intent="route_end_time",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        expected_warnings=["false_premise_detected"],
        expected_next_actions=["clarify_false_premise"],
        expected_behavior_class="useful_refusal",
        implementation_status="target_extension",
        difficulty="medium",
        label_rationale=(
            "route_end_time is a _ROUTE_BOUND_INTENT; "
            "entity_resolution.prompt_references_unknown_route fires on "
            "Route 75 (absent from prompt 053's payload, which has only a "
            "small handful of routes). Mirrors R2-015 / R2-059 contract "
            "shape."
        ),
        ambiguity_notes=(
            "OOD wording 'after the perturbation' substitutes for the "
            "canonical 'after the service time change'."
        ),
        false_entity_type="route",
        false_entity_value="75",
        unsupported_assumption="Route 75 is a route in the current plan.",
        notes="C0 should detect.",
    ),
    StressSpec(
        case_id="A2H-02",
        split="heldout",
        band="nonexistent_entity_false_premise",
        stress_subtype="nonexistent_customer_in_feasibility",
        premise_type="nonexistent_entity",
        expected_failure_mode="should_detect_false_premise",
        base_case_id="R2-027",
        base_family="PLAN_VALIDITY",
        prompt_text=(
            "Is the plan feasible if customer 8888 is added to the new orders?"
        ),
        canonical_supported_prompt=(
            "After adding the new customers, can the existing routes handle "
            "all of them, or are some going to get left out?"
        ),
        payload_condition="false_premise_customer",
        expected_intent="feasibility_status",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        expected_warnings=["false_premise_detected"],
        expected_next_actions=["clarify_false_premise"],
        expected_behavior_class="useful_refusal",
        implementation_status="target_extension",
        difficulty="hard",
        label_rationale=(
            "feasibility_status is not a _CUSTOMER_BOUND_INTENT, so the "
            "C0 false-premise check is never run. The contract will "
            "treat this as a normal answerable PV question, citing "
            "feasible + feasibility_breakdown. The faithful gold is "
            "useful_refusal because the named customer does not exist."
        ),
        ambiguity_notes=(
            "Predicted C0 outcome: feasibility_status + answerable + "
            "direct_answer. Expected bucket: missed_false_premise."
        ),
        false_entity_type="customer",
        false_entity_value="8888",
        unsupported_assumption="Customer 8888 is among the new orders.",
        notes="C0 should MISS — false-premise check not wired for PV.",
    ),
    StressSpec(
        case_id="A2H-03",
        split="heldout",
        band="nonexistent_entity_false_premise",
        stress_subtype="nonexistent_customer_in_same_route",
        premise_type="nonexistent_entity",
        expected_failure_mode="should_detect_false_premise",
        base_case_id="R2-009",
        base_family="STRUCT",
        prompt_text=(
            "Is customer 7777 on the same route as customer 42 in this plan?"
        ),
        canonical_supported_prompt=(
            "Are customers 12 and 17 still on the same route after the new "
            "orders came in?"
        ),
        payload_condition="false_premise_customer",
        expected_intent="same_route_boolean",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        expected_warnings=["false_premise_detected"],
        expected_next_actions=["clarify_false_premise"],
        expected_behavior_class="useful_refusal",
        implementation_status="target_extension",
        difficulty="medium",
        label_rationale=(
            "same_route_boolean is a _CUSTOMER_BOUND_INTENT; customer "
            "7777 is absent from the payload. Mirrors R2-008's contract "
            "shape, applied to same_route_boolean."
        ),
        ambiguity_notes=(
            "Two-customer prompt; only customer 7777 is the false "
            "premise. The contract refuses regardless because any "
            "unknown customer in the pair makes the question "
            "not_answerable."
        ),
        false_entity_type="customer",
        false_entity_value="7777",
        unsupported_assumption="Customer 7777 is on a route.",
        notes="C0 should detect (same_route_boolean is customer-bound).",
    ),
]


# ---------------------------------------------------------------------------
# Band 2 — unsupported_movement_or_assignment_premise
# ---------------------------------------------------------------------------


BAND2_DETECT_GOLD = dict(
    expected_intent="before_after_comparison",
    expected_answerability="not_answerable",
    expected_evidence_paths=[],
    expected_missing_fields=[],
    expected_warnings=["unsupported_comparison"],
    expected_next_actions=["build_baseline_comparison_payload"],
    expected_behavior_class="useful_refusal",
    implementation_status="current",
)


BAND2_MISS_GOLD = dict(
    expected_intent="before_after_comparison",
    expected_answerability="not_answerable",
    expected_evidence_paths=[],
    expected_missing_fields=[],
    expected_warnings=["unsupported_comparison"],
    expected_next_actions=["build_baseline_comparison_payload"],
    expected_behavior_class="useful_refusal",
    implementation_status="target_extension",
)


BAND2 = [
    StressSpec(
        case_id="A2D-04",
        split="dev",
        band="unsupported_movement_or_assignment_premise",
        stress_subtype="comparative_movement",
        premise_type="unsupported_movement",
        expected_failure_mode="should_detect_missing_comparator",
        base_case_id="R2-042",
        base_family="STRUCT",
        prompt_text=(
            "Did customer 42's route assignment actually change after the "
            "perturbation?"
        ),
        canonical_supported_prompt=(
            "Does the current plan use the same number of vehicles as "
            "before the service time changes?"
        ),
        payload_condition="unsupported_comparison",
        **BAND2_DETECT_GOLD,
        difficulty="medium",
        label_rationale=(
            "Prompt contains 'actually change', a _COMPARATIVE_TOKEN, so "
            "intent.py routes STRUCT to before_after_comparison. With "
            "unsupported_comparison mutation (baseline_solution + diff "
            "removed), answerability returns not_answerable; refusal "
            "policy fires unsupported_comparison + "
            "build_baseline_comparison_payload via compose_suggestions."
        ),
        ambiguity_notes=(
            "Mirrors R2-042's contract shape exactly; OOD piece is the "
            "specific-customer wording instead of a vehicle-count "
            "wording."
        ),
        comparator_type="movement_implicit",
        missing_support_field="baseline_solution",
        unsupported_assumption=(
            "A prior route assignment for customer 42 is recorded in "
            "the payload."
        ),
        notes="C0 should detect via comparative-token routing.",
    ),
    StressSpec(
        case_id="A2D-05",
        split="dev",
        band="unsupported_movement_or_assignment_premise",
        stress_subtype="comparative_movement",
        premise_type="unsupported_movement",
        expected_failure_mode="should_detect_missing_comparator",
        base_case_id="R2-042",
        base_family="STRUCT",
        prompt_text=(
            "Has customer 17 been moved to a different vehicle since the "
            "previous run?"
        ),
        canonical_supported_prompt=(
            "Does the current plan use the same number of vehicles as "
            "before the service time changes?"
        ),
        payload_condition="unsupported_comparison",
        **BAND2_DETECT_GOLD,
        difficulty="medium",
        label_rationale=(
            "Contains 'different', a _COMPARATIVE_TOKEN, so STRUCT routes "
            "to before_after_comparison. Same contract shape as A2D-04 "
            "and R2-042."
        ),
        ambiguity_notes=(
            "OOD wording 'moved to a different vehicle since the previous "
            "run' — the contract response shape is unchanged."
        ),
        comparator_type="movement_implicit",
        missing_support_field="baseline_solution",
        unsupported_assumption="Customer 17 was moved between routes.",
        notes="C0 should detect.",
    ),
    StressSpec(
        case_id="A2D-06",
        split="dev",
        band="unsupported_movement_or_assignment_premise",
        stress_subtype="non_comparative_movement",
        premise_type="unsupported_movement",
        expected_failure_mode="should_detect_missing_comparator",
        base_case_id="R2-042",
        base_family="STRUCT",
        prompt_text=(
            "Where was customer 42 before this round of reassignments?"
        ),
        canonical_supported_prompt=(
            "Does the current plan use the same number of vehicles as "
            "before the service time changes?"
        ),
        payload_condition="unsupported_comparison",
        **BAND2_MISS_GOLD,
        difficulty="hard",
        label_rationale=(
            "'before this round of reassignments' carries no token in "
            "_COMPARATIVE_TOKENS ('changed', 'change', 'actually change', "
            "'still', 'compared', 'different'); 'before' alone is not in "
            "the set. STRUCT branch then hits 'customer 42' and routes "
            "to single_customer_route_membership — the question's "
            "movement premise is not surfaced. Faithful gold is "
            "before_after_comparison useful_refusal; this is "
            "target_extension because the current intent classifier "
            "cannot route non-comparative movement wording correctly."
        ),
        ambiguity_notes=(
            "Predicted C0 outcome: single_customer_route_membership + "
            "answerable + direct_answer_with_warning + "
            "struct_membership_ambiguity. Expected bucket: wrong_intent."
        ),
        comparator_type="movement_implicit",
        missing_support_field="baseline_solution",
        unsupported_assumption="A prior assignment for customer 42 exists.",
        notes="C0 should MISS — no comparative token to route.",
    ),
    StressSpec(
        case_id="A2H-04",
        split="heldout",
        band="unsupported_movement_or_assignment_premise",
        stress_subtype="comparative_movement",
        premise_type="unsupported_movement",
        expected_failure_mode="should_detect_missing_comparator",
        base_case_id="R2-042",
        base_family="STRUCT",
        prompt_text=(
            "Has anything actually changed about the route plan from before?"
        ),
        canonical_supported_prompt=(
            "Does the current plan use the same number of vehicles as "
            "before the service time changes?"
        ),
        payload_condition="unsupported_comparison",
        **BAND2_DETECT_GOLD,
        difficulty="medium",
        label_rationale=(
            "'actually changed' is a _COMPARATIVE_TOKEN, so STRUCT routes "
            "to before_after_comparison and the unsupported_comparison "
            "mutation yields the expected refusal contract."
        ),
        ambiguity_notes=(
            "OOD piece is the very general wording about 'the route "
            "plan' rather than a specific entity."
        ),
        comparator_type="general_change",
        missing_support_field="baseline_solution",
        unsupported_assumption="A baseline route plan is recorded.",
        notes="C0 should detect.",
    ),
    StressSpec(
        case_id="A2H-05",
        split="heldout",
        band="unsupported_movement_or_assignment_premise",
        stress_subtype="non_comparative_movement",
        premise_type="unsupported_movement",
        expected_failure_mode="should_detect_missing_comparator",
        base_case_id="R2-042",
        base_family="STRUCT",
        prompt_text=(
            "Which route did customer 17 swap from in this revision?"
        ),
        canonical_supported_prompt=(
            "Does the current plan use the same number of vehicles as "
            "before the service time changes?"
        ),
        payload_condition="unsupported_comparison",
        **BAND2_MISS_GOLD,
        difficulty="hard",
        label_rationale=(
            "'swap' is not in _COMPARATIVE_TOKENS. STRUCT branch matches "
            "'which route' + customer number → "
            "single_customer_route_membership; movement premise is "
            "silently dropped. Faithful gold remains "
            "before_after_comparison useful_refusal."
        ),
        ambiguity_notes=(
            "Predicted C0 outcome: single_customer_route_membership + "
            "direct_answer_with_warning. Expected bucket: wrong_intent."
        ),
        comparator_type="movement_implicit",
        missing_support_field="baseline_solution",
        unsupported_assumption="Customer 17 was previously on a different route.",
        notes="C0 should MISS — non-comparative wording.",
    ),
    StressSpec(
        case_id="A2H-06",
        split="heldout",
        band="unsupported_movement_or_assignment_premise",
        stress_subtype="non_comparative_reassignment_listing",
        premise_type="unsupported_movement",
        expected_failure_mode="should_detect_missing_comparator",
        base_case_id="R2-042",
        base_family="STRUCT",
        prompt_text=(
            "Were any customers reassigned away from Route 1 in this update?"
        ),
        canonical_supported_prompt=(
            "Does the current plan use the same number of vehicles as "
            "before the service time changes?"
        ),
        payload_condition="unsupported_comparison",
        **BAND2_MISS_GOLD,
        difficulty="hard",
        label_rationale=(
            "STRUCT branch: no 'same route', no _COMPARATIVE_TOKEN, no "
            "vehicle-count token, no 'which route' / customer-number "
            "anchor. Falls through to intent=unknown. Faithful gold is "
            "before_after_comparison useful_refusal (the question is a "
            "diff-listing prompt and the schema has no "
            "reassignment_listing intent — see design.md §9)."
        ),
        ambiguity_notes=(
            "Predicted C0 outcome: unknown + useful_refusal + "
            "[route_indexing_ambiguity, narrow_question_to_available_field]. "
            "Expected bucket: unknown_intent."
        ),
        comparator_type="reassignment_listing",
        missing_support_field="diff",
        unsupported_assumption="A prior assignment table exists.",
        notes="C0 should MISS — falls to unknown.",
    ),
]


# ---------------------------------------------------------------------------
# Band 3 — missing_comparator_or_baseline
# ---------------------------------------------------------------------------


BAND3_OBJ_DETECT_EV = [
    "baseline_objective",
    "action_objective",
    "objective_delta_absolute",
    "objective_delta_percent",
    "units.objective",
]


BAND3 = [
    StressSpec(
        case_id="A2D-07",
        split="dev",
        band="missing_comparator_or_baseline",
        stress_subtype="obj_delta_ambiguous_referent",
        premise_type="missing_comparator",
        expected_failure_mode="should_detect_missing_comparator",
        base_case_id="R2-013",
        base_family="OBJ",
        prompt_text=(
            "How much worse is this objective compared with a full re-solve "
            "at higher budget?"
        ),
        canonical_supported_prompt=(
            "What did this end up costing compared to running a full "
            "re-solve?"
        ),
        payload_condition="missing_reference_solution",
        expected_intent="objective_delta",
        expected_answerability="partially_answerable",
        expected_evidence_paths=BAND3_OBJ_DETECT_EV,
        expected_missing_fields=["reference_solution.objective"],
        expected_warnings=["comparison_referent_ambiguity"],
        expected_next_actions=["expose_reference_solution_objective"],
        expected_behavior_class="partial_answer_with_warning",
        implementation_status="target_extension",
        difficulty="medium",
        label_rationale=(
            "Prompt has 'compared' (_COMPARATIVE_TOKEN) → objective_delta; "
            "'full re-solve' is matched by _AMBIGUOUS_REFERENT_PATTERNS, "
            "so answerability adds reference_solution.objective to "
            "missing and the warning + next-action fire."
        ),
        ambiguity_notes="Mirrors R2-013's contract shape with OOD wording.",
        comparator_type="full_resolve",
        missing_support_field="reference_solution.objective",
        unsupported_assumption=(
            "A reference solution's objective is available for comparison."
        ),
        notes="C0 should detect.",
    ),
    StressSpec(
        case_id="A2D-08",
        split="dev",
        band="missing_comparator_or_baseline",
        stress_subtype="obj_implicit_comparator",
        premise_type="missing_comparator",
        expected_failure_mode="should_detect_missing_comparator",
        base_case_id="R2-013",
        base_family="OBJ",
        prompt_text=(
            "Is this objective better than what an optimum solver would find?"
        ),
        canonical_supported_prompt=(
            "What did this end up costing compared to running a full "
            "re-solve?"
        ),
        payload_condition="missing_reference_solution",
        expected_intent="objective_delta",
        expected_answerability="partially_answerable",
        expected_evidence_paths=BAND3_OBJ_DETECT_EV,
        expected_missing_fields=["reference_solution.objective"],
        expected_warnings=["comparison_referent_ambiguity"],
        expected_next_actions=["expose_reference_solution_objective"],
        expected_behavior_class="partial_answer_with_warning",
        implementation_status="target_extension",
        difficulty="hard",
        label_rationale=(
            "Prompt phrasing 'better than … optimum' has no "
            "_COMPARATIVE_TOKEN (the 'fewer/more/less … than' regex does "
            "not match 'better than'), so OBJ routes to objective_value, "
            "not objective_delta. The faithful gold is objective_delta "
            "with comparison_referent_ambiguity, but C0 will route to "
            "objective_value and answer directly — a wrong_intent "
            "failure."
        ),
        ambiguity_notes=(
            "Predicted C0 outcome: objective_value + answerable + "
            "direct_answer. Expected bucket: wrong_intent."
        ),
        comparator_type="optimum",
        missing_support_field="reference_solution.objective",
        unsupported_assumption="An optimum-solver objective is known.",
        notes="C0 should MISS — no comparative token, intent stays value.",
    ),
    StressSpec(
        case_id="A2D-09",
        split="dev",
        band="missing_comparator_or_baseline",
        stress_subtype="struct_before_after",
        premise_type="missing_baseline",
        expected_failure_mode="should_detect_missing_baseline",
        base_case_id="R2-042",
        base_family="STRUCT",
        prompt_text=(
            "Which routes look different from the original plan?"
        ),
        canonical_supported_prompt=(
            "Does the current plan use the same number of vehicles as "
            "before the service time changes?"
        ),
        payload_condition="unsupported_comparison",
        expected_intent="before_after_comparison",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        expected_warnings=["unsupported_comparison"],
        expected_next_actions=["build_baseline_comparison_payload"],
        expected_behavior_class="useful_refusal",
        implementation_status="current",
        difficulty="medium",
        label_rationale=(
            "'different' is a _COMPARATIVE_TOKEN; STRUCT routes to "
            "before_after_comparison and the unsupported_comparison "
            "mutation yields the canonical refusal."
        ),
        ambiguity_notes="Mirrors R2-042's contract shape.",
        comparator_type="original_plan",
        missing_support_field="baseline_solution",
        unsupported_assumption="An original baseline route plan exists.",
        notes="C0 should detect.",
    ),
    StressSpec(
        case_id="A2H-07",
        split="heldout",
        band="missing_comparator_or_baseline",
        stress_subtype="obj_delta_ambiguous_referent",
        premise_type="missing_comparator",
        expected_failure_mode="should_detect_missing_comparator",
        base_case_id="R2-024",
        base_family="OBJ",
        prompt_text=(
            "Compared with re-running this from scratch, what does the "
            "plan cost?"
        ),
        canonical_supported_prompt=(
            "How much more does this plan cost compared to running a full "
            "re-solve from scratch?"
        ),
        payload_condition="missing_reference_solution",
        expected_intent="objective_delta",
        expected_answerability="partially_answerable",
        expected_evidence_paths=BAND3_OBJ_DETECT_EV,
        expected_missing_fields=["reference_solution.objective"],
        expected_warnings=["comparison_referent_ambiguity"],
        expected_next_actions=["expose_reference_solution_objective"],
        expected_behavior_class="partial_answer_with_warning",
        implementation_status="target_extension",
        difficulty="medium",
        label_rationale=(
            "'Compared' is a _COMPARATIVE_TOKEN; 'from scratch' / "
            "'re-?run from scratch' both match _AMBIGUOUS_REFERENT_PATTERNS. "
            "OBJ delta + ambiguous referent → R2-3 partial-answer contract."
        ),
        ambiguity_notes="OOD wording of R2-024's contract shape.",
        comparator_type="from_scratch",
        missing_support_field="reference_solution.objective",
        unsupported_assumption=(
            "A from-scratch re-solve objective is available."
        ),
        notes="C0 should detect.",
    ),
    StressSpec(
        case_id="A2H-08",
        split="heldout",
        band="missing_comparator_or_baseline",
        stress_subtype="obj_implicit_comparator",
        premise_type="missing_comparator",
        expected_failure_mode="should_detect_missing_comparator",
        base_case_id="R2-024",
        base_family="OBJ",
        prompt_text=(
            "How does this plan rank against a stronger solver?"
        ),
        canonical_supported_prompt=(
            "How much more does this plan cost compared to running a full "
            "re-solve from scratch?"
        ),
        payload_condition="missing_reference_solution",
        expected_intent="objective_delta",
        expected_answerability="partially_answerable",
        expected_evidence_paths=BAND3_OBJ_DETECT_EV,
        expected_missing_fields=["reference_solution.objective"],
        expected_warnings=["comparison_referent_ambiguity"],
        expected_next_actions=["expose_reference_solution_objective"],
        expected_behavior_class="partial_answer_with_warning",
        implementation_status="target_extension",
        difficulty="hard",
        label_rationale=(
            "'rank against' has no _COMPARATIVE_TOKEN, so OBJ routes to "
            "objective_value. Even though 'stronger solver' IS in "
            "_AMBIGUOUS_REFERENT_PATTERNS, the comparator check fires only "
            "after the intent is objective_delta — which it is not here."
        ),
        ambiguity_notes=(
            "Predicted C0 outcome: objective_value + direct_answer. "
            "Expected bucket: wrong_intent."
        ),
        comparator_type="stronger_solver",
        missing_support_field="reference_solution.objective",
        unsupported_assumption="A stronger-solver objective is known.",
        notes="C0 should MISS — intent stays value.",
    ),
    StressSpec(
        case_id="A2H-09",
        split="heldout",
        band="missing_comparator_or_baseline",
        stress_subtype="struct_implicit_comparator",
        premise_type="missing_baseline",
        expected_failure_mode="should_detect_missing_baseline",
        base_case_id="R2-042",
        base_family="STRUCT",
        prompt_text=(
            "Did the route structure shift versus the prior schedule?"
        ),
        canonical_supported_prompt=(
            "Does the current plan use the same number of vehicles as "
            "before the service time changes?"
        ),
        payload_condition="unsupported_comparison",
        expected_intent="before_after_comparison",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        expected_warnings=["unsupported_comparison"],
        expected_next_actions=["build_baseline_comparison_payload"],
        expected_behavior_class="useful_refusal",
        implementation_status="target_extension",
        difficulty="hard",
        label_rationale=(
            "'shift', 'versus', 'prior' are not in _COMPARATIVE_TOKENS. "
            "STRUCT falls through every branch and returns intent=unknown. "
            "Faithful gold is before_after_comparison + useful_refusal "
            "with unsupported_comparison."
        ),
        ambiguity_notes=(
            "Predicted C0 outcome: unknown + useful_refusal + "
            "[narrow_question_to_available_field]. Expected bucket: "
            "unknown_intent."
        ),
        comparator_type="prior_schedule",
        missing_support_field="baseline_solution",
        unsupported_assumption="A prior schedule is available.",
        notes="C0 should MISS — STRUCT falls to unknown.",
    ),
]


# ---------------------------------------------------------------------------
# Band 4 — causal_or_explanatory_unsupported_premise
# ---------------------------------------------------------------------------


BAND4 = [
    StressSpec(
        case_id="A2D-10",
        split="dev",
        band="causal_or_explanatory_unsupported_premise",
        stress_subtype="causal_with_citable_facts",
        premise_type="causal_explanation",
        expected_failure_mode="should_partial_answer_current_status_only",
        base_case_id="R2-051",
        base_family="SCHEDULE",
        prompt_text=(
            "Why is route 1 running late in this updated schedule?"
        ),
        canonical_supported_prompt=(
            "Is anyone going to be late after travel times went up 50%?"
        ),
        payload_condition="clean",
        expected_intent="lateness_summary",
        expected_answerability="answerable",
        expected_evidence_paths=["n_late_customers", "late_customer_ids"],
        expected_missing_fields=[],
        expected_warnings=["route_indexing_ambiguity"],
        expected_next_actions=[],
        expected_behavior_class="direct_answer_with_warning",
        implementation_status="current",
        difficulty="medium",
        label_rationale=(
            "SCHEDULE + 'late' → lateness_summary. The contract has no "
            "causal layer, but the lateness facts are cite-able. The "
            "'route 1' integer triggers route_indexing_ambiguity per "
            "refusal_policy. Faithful gold says: answer the citable "
            "facts with the integer-route warning."
        ),
        ambiguity_notes=(
            "The 'why' aspect of the question is implicitly unaddressed; "
            "the schema has no causal_mechanism_unsupported warning. The "
            "case is graded against the closest supported behavior. See "
            "design.md §9."
        ),
        unsupported_assumption=(
            "A causal mechanism for route 1's lateness is recorded."
        ),
        notes="C0 should match gold (cite facts, integer-route warning).",
    ),
    StressSpec(
        case_id="A2D-11",
        split="dev",
        band="causal_or_explanatory_unsupported_premise",
        stress_subtype="causal_with_citable_facts",
        premise_type="causal_explanation",
        expected_failure_mode="should_partial_answer_current_status_only",
        base_case_id="R2-001",
        base_family="OBJ",
        prompt_text=(
            "What's pushing the objective higher in this plan?"
        ),
        canonical_supported_prompt=(
            "What's the total cost on this plan after the time windows "
            "got tighter?"
        ),
        payload_condition="clean",
        expected_intent="objective_value",
        expected_answerability="answerable",
        expected_evidence_paths=["action_objective", "units.objective"],
        expected_missing_fields=[],
        expected_warnings=[],
        expected_next_actions=[],
        expected_behavior_class="direct_answer",
        implementation_status="current",
        difficulty="medium",
        label_rationale=(
            "OBJ family with no comparative token → objective_value. The "
            "contract cites the objective value; the 'pushing higher' "
            "causal framing is implicitly unaddressed."
        ),
        ambiguity_notes=(
            "Schema gap: no causal-mechanism-unsupported warning. Graded "
            "against the closest supported behavior. See design.md §9."
        ),
        unsupported_assumption=(
            "A causal decomposition of the objective is in the payload."
        ),
        notes="C0 should match gold.",
    ),
    StressSpec(
        case_id="A2D-12",
        split="dev",
        band="causal_or_explanatory_unsupported_premise",
        stress_subtype="causal_with_citable_facts",
        premise_type="causal_explanation",
        expected_failure_mode="should_partial_answer_current_status_only",
        base_case_id="R2-053",
        base_family="SCHEDULE",
        prompt_text=(
            "What caused customer 42 to miss its delivery window in this "
            "plan?"
        ),
        canonical_supported_prompt=(
            "Is anyone going to be late after travel times went up 10%?"
        ),
        payload_condition="clean",
        expected_intent="lateness_summary",
        expected_answerability="answerable",
        expected_evidence_paths=["n_late_customers", "late_customer_ids"],
        expected_missing_fields=[],
        expected_warnings=[],
        expected_next_actions=[],
        expected_behavior_class="direct_answer",
        implementation_status="current",
        difficulty="medium",
        label_rationale=(
            "'miss' and 'delivery window' are both in the lateness token "
            "set; SCHEDULE → lateness_summary. The contract cites the "
            "lateness facts. The 'what caused' framing is implicitly "
            "unaddressed; lateness_summary is not customer-bound so no "
            "false-premise check runs (even if customer 42 were absent)."
        ),
        ambiguity_notes=(
            "Schema gap: no causal-mechanism-unsupported warning. The "
            "question's customer-specificity is also implicitly "
            "unaddressed (the summary lists all late customers, not just "
            "customer 42)."
        ),
        unsupported_assumption=(
            "A customer-level lateness attribution is in the payload."
        ),
        notes="C0 should match gold.",
    ),
    StressSpec(
        case_id="A2H-10",
        split="heldout",
        band="causal_or_explanatory_unsupported_premise",
        stress_subtype="causal_with_missing_validity",
        premise_type="causal_explanation",
        expected_failure_mode="should_refuse_causal_explanation",
        base_case_id="R2-033",
        base_family="PLAN_VALIDITY",
        prompt_text=(
            "Why is this plan failing to satisfy the constraints after the "
            "perturbation?"
        ),
        canonical_supported_prompt=(
            "Does this plan still work after travel times went up 20%?"
        ),
        payload_condition="missing_validity_fields",
        expected_intent="feasibility_status",
        expected_answerability="not_answerable",
        expected_evidence_paths=[],
        expected_missing_fields=["feasible", "feasibility_breakdown"],
        expected_warnings=[],
        expected_next_actions=["use_validity_payload"],
        expected_behavior_class="useful_refusal",
        implementation_status="target_extension",
        difficulty="medium",
        label_rationale=(
            "PV family → feasibility_status. With missing_validity_fields "
            "mutation, the required fields feasible + feasibility_breakdown "
            "are both absent → not_answerable. compose_suggestions maps "
            "both missing fields to use_validity_payload. The 'why' framing "
            "is unaddressed but the refusal is correctly grounded in the "
            "missing-field shape."
        ),
        ambiguity_notes=(
            "Mirrors R2-033's contract shape; OOD piece is the causal "
            "framing ('why ... failing to satisfy')."
        ),
        missing_support_field="feasibility_breakdown",
        unsupported_assumption=(
            "A causal feasibility breakdown is available."
        ),
        notes="C0 should detect (PV refusal correctly fires).",
    ),
    StressSpec(
        case_id="A2H-11",
        split="heldout",
        band="causal_or_explanatory_unsupported_premise",
        stress_subtype="causal_with_citable_facts",
        premise_type="causal_explanation",
        expected_failure_mode="should_partial_answer_current_status_only",
        base_case_id="R2-038",
        base_family="STRUCT",
        prompt_text=(
            "What's pushing the route count up in this revision?"
        ),
        canonical_supported_prompt=(
            "How many vehicles are needed for this plan after a new order "
            "came in?"
        ),
        payload_condition="clean",
        expected_intent="route_count",
        expected_answerability="answerable",
        expected_evidence_paths=["n_routes"],
        expected_missing_fields=[],
        expected_warnings=[],
        expected_next_actions=[],
        expected_behavior_class="direct_answer",
        implementation_status="current",
        difficulty="medium",
        label_rationale=(
            "STRUCT branch: no 'same route', no _COMPARATIVE_TOKEN ('push', "
            "'up', 'revision' all absent from the set; no 'fewer/more/less "
            "… than'); 'route count' token matches → route_count. The "
            "contract cites n_routes; the causal 'pushing up' aspect is "
            "implicitly unaddressed."
        ),
        ambiguity_notes=(
            "Schema gap: no causal-mechanism-unsupported warning."
        ),
        unsupported_assumption=(
            "A causal decomposition of route-count change is recorded."
        ),
        notes="C0 should match gold.",
    ),
    StressSpec(
        case_id="A2H-12",
        split="heldout",
        band="causal_or_explanatory_unsupported_premise",
        stress_subtype="causal_with_citable_facts",
        premise_type="causal_explanation",
        expected_failure_mode="should_partial_answer_current_status_only",
        base_case_id="R2-051",
        base_family="SCHEDULE",
        prompt_text=(
            "Why did the lateness counts jump up after the time windows "
            "tightened?"
        ),
        canonical_supported_prompt=(
            "Is anyone going to be late after travel times went up 50%?"
        ),
        payload_condition="clean",
        expected_intent="lateness_summary",
        expected_answerability="answerable",
        expected_evidence_paths=["n_late_customers", "late_customer_ids"],
        expected_missing_fields=[],
        expected_warnings=[],
        expected_next_actions=[],
        expected_behavior_class="direct_answer",
        implementation_status="current",
        difficulty="medium",
        label_rationale=(
            "SCHEDULE + 'lateness' → lateness_summary. The contract cites "
            "lateness facts. The 'why' and 'jump up' framings are "
            "implicitly unaddressed; no integer-route token in the prompt, "
            "so route_indexing_ambiguity does not fire."
        ),
        ambiguity_notes=(
            "Schema gap: no causal-mechanism-unsupported warning."
        ),
        unsupported_assumption=(
            "A causal explanation for the lateness change is recorded."
        ),
        notes="C0 should match gold.",
    ),
]


ALL_SPECS: list[StressSpec] = BAND1 + BAND2 + BAND3 + BAND4


# ---------------------------------------------------------------------------
# CSV column order — must match loader.EXPECTED_COLUMNS
# ---------------------------------------------------------------------------


GOLD_COLS: list[str] = [
    "case_id",
    "source_prompt_id",
    "family",
    "prompt_text",
    "payload_condition",
    "payload_mutation_needed",
    "expected_intent",
    "expected_answerability",
    "expected_evidence_paths",
    "expected_missing_fields",
    "expected_warnings",
    "expected_next_actions",
    "expected_behavior_class",
    "implementation_status",
    "difficulty",
    "label_rationale",
    "ambiguity_notes",
]


STRESS_COLS: list[str] = [
    "stress_axis",
    "stress_subtype",
    "split",
    "band",
    "ood_premise_band",
    "premise_type",
    "expected_failure_mode",
    "base_case_id",
    "base_family",
    "canonical_supported_prompt",
    "false_entity_type",
    "false_entity_value",
    "comparator_type",
    "missing_support_field",
    "unsupported_assumption",
    "notes",
]


CSV_COLUMNS: list[str] = GOLD_COLS + STRESS_COLS


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def _load_locked_lookup() -> dict[str, dict[str, str]]:
    df = pd.read_csv(LOCKED_BENCHMARK, keep_default_na=False, dtype=str)
    return {row["case_id"]: dict(row) for _, row in df.iterrows()}


def _payload_mutation_needed(payload_condition: str) -> str:
    """Mirror the locked-benchmark wording — short, deterministic, and
    matches the mutation that `run2_payloads._apply_mutation` performs."""
    return {
        "clean": "none",
        "false_premise_customer": (
            "Use seed payload as-is; the prompt names a customer absent "
            "from the payload."
        ),
        "false_premise_route": (
            "Use seed payload as-is; the prompt names a route absent "
            "from the payload."
        ),
        "unsupported_comparison": (
            "Remove baseline_solution and diff from the seed payload."
        ),
        "missing_reference_solution": (
            "Use seed payload as-is; the payload does not include "
            "reference_solution.objective."
        ),
        "missing_validity_fields": (
            "Remove feasible and feasibility_breakdown from the seed "
            "payload."
        ),
    }[payload_condition]


def _row_from_spec(
    spec: StressSpec, locked: dict[str, dict[str, str]]
) -> dict[str, str]:
    base = locked[spec.base_case_id]
    return {
        "case_id": spec.case_id,
        "source_prompt_id": base["source_prompt_id"],
        "family": spec.base_family,
        "prompt_text": spec.prompt_text,
        "payload_condition": spec.payload_condition,
        "payload_mutation_needed": _payload_mutation_needed(
            spec.payload_condition
        ),
        "expected_intent": spec.expected_intent,
        "expected_answerability": spec.expected_answerability,
        "expected_evidence_paths": ";".join(spec.expected_evidence_paths),
        "expected_missing_fields": ";".join(spec.expected_missing_fields),
        "expected_warnings": ";".join(spec.expected_warnings),
        "expected_next_actions": ";".join(spec.expected_next_actions),
        "expected_behavior_class": spec.expected_behavior_class,
        "implementation_status": spec.implementation_status,
        "difficulty": spec.difficulty,
        "label_rationale": spec.label_rationale,
        "ambiguity_notes": spec.ambiguity_notes,
        "stress_axis": STRESS_AXIS,
        "stress_subtype": spec.stress_subtype,
        "split": spec.split,
        "band": spec.band,
        "ood_premise_band": spec.band,
        "premise_type": spec.premise_type,
        "expected_failure_mode": spec.expected_failure_mode,
        "base_case_id": spec.base_case_id,
        "base_family": spec.base_family,
        "canonical_supported_prompt": spec.canonical_supported_prompt,
        "false_entity_type": spec.false_entity_type,
        "false_entity_value": spec.false_entity_value,
        "comparator_type": spec.comparator_type,
        "missing_support_field": spec.missing_support_field,
        "unsupported_assumption": spec.unsupported_assumption,
        "notes": spec.notes,
    }


def build_rows() -> list[dict[str, str]]:
    locked = _load_locked_lookup()
    return [_row_from_spec(spec, locked) for spec in ALL_SPECS]


def write_csv(path: Path = HERE / "cases.csv") -> Path:
    rows = build_rows()
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_MINIMAL
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> None:
    out = write_csv()
    print(f"wrote {out} ({len(ALL_SPECS)} cases)")


if __name__ == "__main__":
    main()
