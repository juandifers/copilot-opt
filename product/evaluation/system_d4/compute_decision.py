"""System D4 — ComputeDecision contract + deterministic policy.

Public surface:

- ``ComputeDecision``   — pydantic response model attached to D4 responses.
- ``ComputeMode``       — Literal of the six allowed mode strings.
- ``RecommendedAction`` — Literal of the nine allowed action strings.
- ``QueryFamily``       — Literal of the six allowed query-family strings.
- ``decide_compute(...)`` — pure policy function; returns a ``ComputeDecision``.
- ``intent_to_query_family(intent, warnings)`` — projection used by the policy.

The policy is deterministic. It never calls a solver, never imports
``vrp_copilot_bench``, and never touches a learned model.

Precedence (highest first):

    unsupported
      > needs_recompute
      > needs_comparison_payload
      > partial_from_payload
      > clarification_needed
      > answer_from_payload

This file is the single source of truth for the D4 contract.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from product.copilot.sufficiency_gate import (
    DEFAULT_CORRECTNESS_FLOOR,
    DEFAULT_RECOMPUTE_ACTION,
    FORBIDDEN_RECOMPUTE_ACTIONS,
    SUPPORTED_FAMILIES as _GATE_SUPPORTED_FAMILIES,
    SufficiencyGateResult,
    gate_enabled,
    predict_sufficiency,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

ComputeMode = Literal[
    "answer_from_payload",
    "partial_from_payload",
    "needs_comparison_payload",
    "needs_recompute",
    "clarification_needed",
    "unsupported",
]

RecommendedAction = Literal[
    "none",
    "build_comparison_payload",
    "load_baseline_payload",
    "run_reuse_direct",
    "run_nearest_neighbor",
    "run_clarke_wright",
    "run_pyvrp_10s",
    "ask_clarification",
    "unsupported",
]

QueryFamily = Literal[
    "OBJ",
    "PLAN_VALIDITY",
    "STRUCT",
    "SCHEDULE",
    "CAUSAL",
    "OVERVIEW",
    "UNKNOWN",
]


ALL_MODES: frozenset[str] = frozenset(
    [
        "answer_from_payload",
        "partial_from_payload",
        "needs_comparison_payload",
        "needs_recompute",
        "clarification_needed",
        "unsupported",
    ]
)

ALL_ACTIONS: frozenset[str] = frozenset(
    [
        "none",
        "build_comparison_payload",
        "load_baseline_payload",
        "run_reuse_direct",
        "run_nearest_neighbor",
        "run_clarke_wright",
        "run_pyvrp_10s",
        "ask_clarification",
        "unsupported",
    ]
)

ALL_QUERY_FAMILIES: frozenset[str] = frozenset(
    ["OBJ", "PLAN_VALIDITY", "STRUCT", "SCHEDULE", "CAUSAL", "OVERVIEW", "UNKNOWN"]
)

# Deployable actions per benchmark §7. ``pyvrp_60s`` is intentionally
# omitted; it was the reference-label generator, not a deployable rung.
DEPLOYABLE_RECOMPUTE_ACTIONS: frozenset[str] = frozenset(
    [
        "run_reuse_direct",
        "run_nearest_neighbor",
        "run_clarke_wright",
        "run_pyvrp_10s",
    ]
)

POLICY_SOURCE: str = "deterministic_d4_v1"


# ---------------------------------------------------------------------------
# Compute decision pydantic shape
# ---------------------------------------------------------------------------


class ComputeDecision(BaseModel):
    """Recomputation-aware decision attached to the D4 response.

    The model validates against the closed mode/action/family enums. The
    free-form ``reason`` is a single sentence intended for operator
    display. ``required_fields`` and ``available_fields`` are derived
    from the payload shape; ``missing_for_full_answer`` is their set
    difference (with stable ordering).
    """

    mode: ComputeMode
    requires_recompute: bool
    recommended_action: RecommendedAction
    query_family: QueryFamily
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    required_fields: list[str] = Field(default_factory=list)
    available_fields: list[str] = Field(default_factory=list)
    missing_for_full_answer: list[str] = Field(default_factory=list)
    expected_runtime_seconds: Optional[float] = None
    policy_source: str = POLICY_SOURCE
    # Advisory output from the learned Stage A sufficiency gate (when
    # enabled). The gate does not own answerability, evidence, or warning
    # decisions; it only nudges the compute-decision mode/action.
    sufficiency_gate: Optional[SufficiencyGateResult] = None


# ---------------------------------------------------------------------------
# Intent → query-family projection
# ---------------------------------------------------------------------------

_OBJ_INTENTS = frozenset({"objective_value", "objective_delta"})
_PV_INTENTS = frozenset({"feasibility_status"})
_STRUCT_INTENTS = frozenset(
    {
        "route_count",
        "single_customer_route_membership",
        "same_route_boolean",
        "full_route_listing",
        "new_customer_assignment",
        "before_after_comparison",
    }
)
_SCHEDULE_INTENTS = frozenset(
    {"route_end_time", "customer_arrival", "lateness_summary"}
)
_OVERVIEW_INTENTS = frozenset(
    {
        "perturbation_summary",
        "scenario_summary",
        "solution_summary",
        "perturbation_impact_summary",
        "route_impact_summary",
        "what_to_watch",
    }
)


def intent_to_query_family(
    intent: Optional[str],
    warnings: Optional[list[str]] = None,
) -> QueryFamily:
    """Project an intent + warnings list onto the D4 query-family enum.

    The CAUSAL family is an overlay: it is selected when D3 emitted
    ``causal_mechanism_unsupported`` regardless of the underlying
    intent. This matches the spec's "CAUSAL: causal explanation prompts
    detected by D3 warning causal_mechanism_unsupported."

    OVERVIEW intents are the new "grounded overview" family — high-level
    explanation prompts that read a payload-derived context card rather
    than perform an exact field lookup. They never trigger needs_recompute.
    """
    warnings = warnings or []
    if "causal_mechanism_unsupported" in warnings:
        return "CAUSAL"
    if intent in _OVERVIEW_INTENTS:
        return "OVERVIEW"
    if intent in _OBJ_INTENTS:
        return "OBJ"
    if intent in _PV_INTENTS:
        return "PLAN_VALIDITY"
    if intent in _STRUCT_INTENTS:
        return "STRUCT"
    if intent in _SCHEDULE_INTENTS:
        return "SCHEDULE"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Trigger phrase tables
#
# Triggers are conservative and lexical. Each table is exposed as a
# module-level frozenset so tests can introspect / extend.
# ---------------------------------------------------------------------------

UNSUPPORTED_TRIGGERS: frozenset[str] = frozenset(
    [
        "driver preference",
        "driver preferences",
        "labor rule",
        "labor rules",
        "labour rule",
        "labour rules",
        "fuel price",
        "fuel cost",
        "emissions",
        "co2",
        "depot staffing",
        "depot staff",
        "carbon",
    ]
)

# Hypothetical / optimization / repair language.
RECOMPUTE_TRIGGERS: frozenset[str] = frozenset(
    [
        "what if",
        "what would happen",
        "suppose",
        "add customer",
        "add a customer",
        "insert customer",
        "insert this customer",
        "insert a customer",
        "remove customer",
        "remove a customer",
        "drop customer",
        "change demand",
        "capacity drops",
        "capacity drop",
        "capacity falls",
        "if capacity",
        "tighten time window",
        "tighten the time window",
        "relax time window",
        "relax the time window",
        "make customer",
        "make him on time",
        "make them on time",
        "on time",
        "find a better plan",
        "find a better solution",
        "better plan",
        "better solution",
        "improve the plan",
        "improve the solution",
        "reroute",
        "rerouting",
        "re-route",
        "re-routing",
        "repair",
        "reoptimize",
        "re-optimize",
        "re-optimise",
        "reoptimise",
        "fresh solve",
        "fresh solution",
        "fresh run",
        "rerun the solver",
        "re-run the solver",
        "run the solver",
        "stronger solver",
        "stronger solve",
        "stronger optimization",
        "stronger optimisation",
        "reduce lateness",
        # Cheap-replan / heuristic-by-name language. D5 wires these
        # through to ``run_clarke_wright`` via ``_CW_HINTS``.
        "replan",
        "cheap heuristic",
        "fast heuristic",
        "savings heuristic",
        "savings algorithm",
        "clarke wright",
        "clarke-wright",
        "rebuild the routes",
        "rebuild the route",
        "alternative route plan",
        "alternative plan",
    ]
)

# Comparison-only triggers. Comparative-shape prompts that do NOT also
# ask to construct/repair the new plan.
COMPARISON_TRIGGERS: frozenset[str] = frozenset(
    [
        "compared to",
        "compared with",
        "vs the baseline",
        "vs baseline",
        "vs. baseline",
        "previous plan",
        "previous solution",
        "prior plan",
        "prior solution",
        "old plan",
        "old solution",
        "baseline plan",
        "baseline solution",
        "the baseline",
        "before and after",
        "before/after",
        "changed routes",
        "routes changed",
        "moved from",
        "reassigned from",
        "reassigned to a different",
        "switched routes",
        "shifted from",
        "did it move",
        "did they move",
    ]
)

# Hedged "should I act on this?" language. These ALWAYS win over the
# recompute path because they are explicitly inquiry-shaped — "Can you
# improve this?" is not a directive to improve.
CLARIFICATION_TRIGGERS: frozenset[str] = frozenset(
    [
        "can you improve this",
        "can we improve this",
        "is this plan okay",
        "is this route okay",
        "is this plan ok",
        "is this route ok",
        "is this ok",
        "is this okay",
        "what should we do",
        "what should i do",
        "anything wrong",
    ]
)

# Action-selection sub-triggers for needs_recompute.
_REUSE_HINTS = frozenset(
    [
        "reuse current",
        "reuse the current",
        "still feasible",
        "without resolving",
        "without re-solving",
        "without recomputing",
        "stays feasible",
        "is it still feasible",
        "current solution still",
    ]
)
_NN_HINTS = frozenset(["nearest neighbor", "nearest-neighbor", "nn heuristic"])
_CW_HINTS = frozenset(
    [
        "clarke wright",
        "clarke-wright",
        "clarke and wright",
        "cw heuristic",
        "quick heuristic",
        "cheap heuristic",
        "cheap solve",
        "fast heuristic",
        # Phrased-by-effect cheap-replan hints. D5 maps these to
        # ``run_clarke_wright`` (the savings heuristic rung) rather
        # than the stronger ``run_pyvrp_10s`` default.
        "savings heuristic",
        "savings algorithm",
        "cheap replan",
        "quick replan",
        "rebuild the routes",
        "rebuild the route",
        "alternative route plan",
        "alternative plan",
    ]
)
_FRESH_HINTS = frozenset(
    [
        "fresh solve",
        "fresh solution",
        "fresh run",
        "stronger solver",
        "stronger solve",
        "better plan",
        "better solution",
        "find a better",
        "reoptimize",
        "re-optimize",
        "reoptimise",
        "improve the plan",
        "improve the solution",
        "improve this",
        "rerun the solver",
        "run the solver",
        "reduce lateness",
        "repair",
        "reroute",
    ]
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _contains_any(haystack: str, needles: frozenset[str]) -> bool:
    return any(needle in haystack for needle in needles)


def _detect_comparison(prompt_lower: str) -> bool:
    """True if the prompt contains a comparison referent."""
    if _contains_any(prompt_lower, COMPARISON_TRIGGERS):
        return True
    # "did ... change" / "did ... move" comparative patterns
    if re.search(r"\bdid\s+\w+\s+(change|move|switch|shift)\b", prompt_lower):
        return True
    # "how many ... changed" comparative pattern
    if re.search(r"how many\s+\w+\s+(changed|moved|switched|shifted)", prompt_lower):
        return True
    # "is this (plan|solution|run|result) better/worse"
    if re.search(
        r"\bis\s+this\s+(plan|solution|run|result)\s+(better|worse)\b",
        prompt_lower,
    ):
        return True
    # "has the objective/plan/solution improved" — needs an explicit
    # comparative-aspect predicate. Suppress on "why" framings: those
    # are causal questions, not comparison requests.
    if re.search(r"\bwhy\b", prompt_lower):
        return False
    if re.search(
        r"\b(did|has|have)\s+(lateness|the\s+objective|the\s+plan|"
        r"the\s+solution|the\s+lateness)\s+"
        r"(improve|improved|change|changed|increase|increased|decrease|"
        r"decreased|drop|dropped|rise|risen|reduce|reduced)\b",
        prompt_lower,
    ):
        return True
    return False


def _detect_recompute(prompt_lower: str) -> bool:
    return _contains_any(prompt_lower, RECOMPUTE_TRIGGERS)


def _detect_unsupported(prompt_lower: str) -> bool:
    return _contains_any(prompt_lower, UNSUPPORTED_TRIGGERS)


def _detect_clarification(prompt_lower: str) -> bool:
    if _contains_any(prompt_lower, CLARIFICATION_TRIGGERS):
        return True
    # "Is route N okay/ok/fine/good?" — the route-by-number clarification
    # framing. Tighter than a bare "is route" substring.
    if re.search(r"\bis\s+route\s+\d+\s+(okay|ok|fine|good)\b", prompt_lower):
        return True
    # "What should we do about route N?" — explicit clarification framing.
    if re.search(r"\bwhat\s+should\s+(we|i)\s+do\s+about\b", prompt_lower):
        return True
    return False


# Causal-framing detector — lexical fallback for cases where D3 has
# not emitted ``causal_mechanism_unsupported``. D3 excludes
# ``before_after_comparison`` and ``unknown`` from its factual-intent
# set, so prompts like "Why did the route count change?" do not
# receive the warning at the D3 layer; D4 still needs to mark them as
# partial because the operator is asking for a cause.
_CAUSAL_FALLBACK_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\bwhy\s+(is|are|did|does|was|were|do|don't|am)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+caused\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'s| is)\s+causing\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+made\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'s| is)\s+driving\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+drove\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'s| is)\s+behind\b", re.IGNORECASE),
    re.compile(r"\bwhat'?s\s+the\s+reason\b", re.IGNORECASE),
    re.compile(r"\breason\s+(?:for|behind|why)\b", re.IGNORECASE),
)


def _detect_causal(prompt_lower: str) -> bool:
    return any(p.search(prompt_lower) for p in _CAUSAL_FALLBACK_PATTERNS)


def _select_recompute_action(prompt_lower: str) -> RecommendedAction:
    """Pick the rung of the deployable ladder.

    Ordering: reuse-direct > NN > CW > fresh-solve, with pyvrp_10s as
    the safe default for ambiguous recompute prompts.
    """
    if _contains_any(prompt_lower, _REUSE_HINTS):
        return "run_reuse_direct"
    if _contains_any(prompt_lower, _NN_HINTS):
        return "run_nearest_neighbor"
    if _contains_any(prompt_lower, _CW_HINTS):
        return "run_clarke_wright"
    if _contains_any(prompt_lower, _FRESH_HINTS):
        return "run_pyvrp_10s"
    return "run_pyvrp_10s"


_RUNTIME_BY_ACTION: dict[str, Optional[float]] = {
    "run_reuse_direct": 0.5,
    "run_nearest_neighbor": 0.5,
    "run_clarke_wright": 1.0,
    "run_pyvrp_10s": 10.0,
    "build_comparison_payload": None,
    "load_baseline_payload": None,
    "ask_clarification": None,
    "unsupported": None,
    "none": None,
}


# ---------------------------------------------------------------------------
# Field-availability extraction
# ---------------------------------------------------------------------------


# Payload keys / nested keys we surface to the operator. Order is the
# canonical display order used in reports.
_PAYLOAD_TOP_KEYS: tuple[str, ...] = (
    "solution",
    "current_solution",
    "routes",
    "route_end_times",
    "route_finish_times",
    "customer_schedule",
    "customer_arrival_times",
    "objective",
    "action_objective",
    "baseline_objective",
    "baseline_solution",
    "baseline_routes",
    "baseline_schedule",
    "diff",
    "objective_delta",
    "objective_delta_absolute",
    "objective_delta_percent",
    "lateness_summary",
    "late_customers",
    "feasible",
    "feasibility",
    "validity",
    "units",
    "reference_solution",
    "perturbed_solution",
    "recomputed_solution",
    "assignment",
    "new_customer_ids",
)


def extract_available_fields(payload: Optional[dict]) -> list[str]:
    """Return a sorted, stable list of available top-level payload keys."""
    if not isinstance(payload, dict):
        return []
    present: list[str] = []
    for k in _PAYLOAD_TOP_KEYS:
        if k in payload and payload[k] not in (None, "", [], {}):
            present.append(k)
    # Include any extra top-level keys not in our canonical list — we
    # still surface them, just sorted alphabetically and after the
    # canonical block, so the operator sees the canonical names first.
    extras = sorted(
        k for k in payload.keys()
        if k not in _PAYLOAD_TOP_KEYS and isinstance(k, str)
    )
    return present + extras


# Per-intent required-field hints. Intent-level is finer than family-
# level so `route_end_time` asks for `route_end_times`, not the SCHEDULE
# family's umbrella set.
_REQUIRED_BY_INTENT_ANSWER: dict[str, tuple[str, ...]] = {
    "objective_value": ("objective",),
    "objective_delta": ("objective_delta",),
    "feasibility_status": ("feasible",),
    "route_count": ("routes",),
    "single_customer_route_membership": ("assignment",),
    "same_route_boolean": ("assignment",),
    "full_route_listing": ("routes",),
    "new_customer_assignment": ("assignment", "new_customer_ids"),
    "before_after_comparison": ("baseline_solution", "diff"),
    "route_end_time": ("route_end_times",),
    "customer_arrival": ("customer_schedule",),
    "lateness_summary": ("late_customers",),
    # Overview intents. Descriptive intents need no payload field
    # (perturbation metadata is always derivable from perturbation_id).
    # Impact intents need baseline/diff for a *full* answer — when
    # missing, D4 returns partial_from_payload rather than recommending
    # a recompute, because the operator is asking about the state of
    # the world, not asking us to change it.
    "perturbation_summary": (),
    "scenario_summary": (),
    "solution_summary": ("feasible",),
    "perturbation_impact_summary": ("baseline_solution", "diff"),
    "route_impact_summary": ("baseline_solution", "diff"),
    "what_to_watch": (),
}

# Family-level fallbacks for cases where the intent doesn't map cleanly
# (e.g. CAUSAL overlay).
_REQUIRED_BY_FAMILY_ANSWER: dict[str, tuple[str, ...]] = {
    "OBJ": ("objective",),
    "PLAN_VALIDITY": ("feasible",),
    "STRUCT": ("routes",),
    "SCHEDULE": ("customer_schedule",),
    "CAUSAL": ("causal_attribution",),
    "OVERVIEW": (),
    "UNKNOWN": (),
}

_REQUIRED_BY_FAMILY_COMPARE: dict[str, tuple[str, ...]] = {
    "OBJ": ("baseline_objective", "action_objective", "objective_delta"),
    "PLAN_VALIDITY": ("baseline_solution", "diff"),
    "STRUCT": ("baseline_solution", "diff"),
    "SCHEDULE": ("baseline_schedule", "diff"),
    "CAUSAL": ("baseline_solution", "diff", "causal_attribution"),
    "OVERVIEW": ("baseline_solution", "diff"),
    "UNKNOWN": ("baseline_solution", "diff"),
}

_REQUIRED_FOR_RECOMPUTE: tuple[str, ...] = ("perturbed_solution",)


def _required_fields(
    mode: ComputeMode,
    family: QueryFamily,
    intent: Optional[str] = None,
) -> list[str]:
    if mode == "needs_recompute":
        return list(_REQUIRED_FOR_RECOMPUTE)
    if mode == "needs_comparison_payload":
        return list(_REQUIRED_BY_FAMILY_COMPARE.get(family, ()))
    if mode == "partial_from_payload":
        return ["causal_attribution"] if family == "CAUSAL" else []
    if mode == "answer_from_payload":
        if intent and intent in _REQUIRED_BY_INTENT_ANSWER:
            return list(_REQUIRED_BY_INTENT_ANSWER[intent])
        return list(_REQUIRED_BY_FAMILY_ANSWER.get(family, ()))
    return []


def _missing_for_full_answer(
    required: list[str], available: list[str]
) -> list[str]:
    avail_set = set(available)
    return [r for r in required if r not in avail_set]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def decide_compute(
    *,
    prompt_text: str,
    intent: Optional[str],
    answerability_status: Optional[str],
    warnings: Optional[list[str]] = None,
    payload: Optional[dict] = None,
    answerability_missing_fields: Optional[list[str]] = None,
    perturbation_context: Optional[dict] = None,
    action_context: Optional[dict] = None,
    use_learned_sufficiency_gate: Optional[bool] = None,
    correctness_floor: float = DEFAULT_CORRECTNESS_FLOOR,
) -> ComputeDecision:
    """Run the deterministic D4 policy.

    Parameters
    ----------
    prompt_text:
        The operator-facing prompt. Lower-cased internally; phrase
        triggers are run against the lower-cased copy.
    intent:
        D1/D3 intent string. Maps to the D4 query family via
        ``intent_to_query_family``.
    answerability_status:
        D2/D3 answerability status (``answerable`` /
        ``partially_answerable`` / ``not_answerable``).
    warnings:
        D3 warnings list. The ``causal_mechanism_unsupported`` warning
        causes the query family to flip to ``CAUSAL``.
    payload:
        Optional materialized payload. Used only to derive
        ``available_fields``.
    answerability_missing_fields:
        Optional D2 missing-field list. Surfaced verbatim in the
        ``missing_for_full_answer`` slot when the resolved required-
        field list is empty (e.g. partial-from-payload).

    Returns
    -------
    ComputeDecision
        Fully populated decision object. Never raises for valid
        argument shapes; unknown intents collapse to ``UNKNOWN`` family.
    """
    warnings = warnings or []
    prompt = (prompt_text or "").lower()
    family = intent_to_query_family(intent, warnings)
    available = extract_available_fields(payload)

    has_unsupported = _detect_unsupported(prompt)
    has_clarification = _detect_clarification(prompt)
    has_recompute = _detect_recompute(prompt)
    has_comparison = _detect_comparison(prompt)
    has_causal_warning = "causal_mechanism_unsupported" in warnings
    # Lexical fallback for causal framing. D3 does not emit its causal
    # warning for ``before_after_comparison`` / ``unknown`` intents, so
    # prompts like "Why did the route count change?" reach D4 with no
    # warning. D4 still marks them partial — the operator is asking for
    # a cause, not a fact.
    if not has_causal_warning and _detect_causal(prompt):
        has_causal_warning = True
        family = "CAUSAL"

    # Overview intents own their own decision path: they explicitly ask
    # for a payload-derived overview, so the standard trigger ladder
    # (clarification / recompute / comparison) must not hijack them.
    # "How does the plan look?" should answer from payload; "How is this
    # perturbation affecting routes?" without a diff should partial-
    # answer-with-comparison-payload-recommendation, not recompute.
    if intent in _OVERVIEW_INTENTS:
        return _build_overview_decision(
            intent=intent,
            family=family,
            available=available,
            answerability_status=answerability_status,
            extra_missing=answerability_missing_fields,
            unsupported=has_unsupported,
        )

    # Rule precedence — explicit, top to bottom.
    #   unsupported
    # > clarification (hedged "can you improve this?" / "is route N okay?")
    # > recompute  (directive: "improve the plan", "what if")
    # > comparison (explicit referent: "compared to", "baseline", …)
    # > causal     (D3 warning fires)
    # > partial    (D3 partially_answerable status)
    # > not_answerable → fall back to clarification ask
    # > answer_from_payload (default)
    #
    # Clarification beats recompute because hedged inquiry-shaped
    # prompts ("Can you improve this?") should not trigger a solver
    # recommendation — the operator has not asked for action yet.

    if has_unsupported:
        return _build(
            mode="unsupported",
            recommended_action="unsupported",
            family=family,
            reason=(
                "The prompt asks for data outside the current copilot "
                "schema (driver preferences, fuel cost, labor rules, "
                "emissions, or similar)."
            ),
            confidence=0.95,
            available=available,
            extra_missing=answerability_missing_fields,
            intent=intent,
        )

    if has_clarification:
        return _build(
            mode="clarification_needed",
            recommended_action="ask_clarification",
            family=family,
            reason=(
                "The prompt is ambiguous between a status query and an "
                "optimization request."
            ),
            confidence=0.7,
            available=available,
            extra_missing=answerability_missing_fields,
            intent=intent,
        )

    if has_recompute:
        action = _select_recompute_action(prompt)
        return _build(
            mode="needs_recompute",
            recommended_action=action,
            family=family,
            reason=(
                "The prompt asks about a changed scenario or "
                "optimization that is not materialized in the current "
                "payload."
            ),
            confidence=0.9,
            available=available,
            extra_missing=answerability_missing_fields,
            intent=intent,
        )

    if has_comparison:
        # If the baseline/diff is already in the payload, the
        # comparison is answerable from payload — no rebuild.
        baseline_present = any(
            k in available for k in (
                "baseline_objective", "baseline_solution", "baseline_routes",
                "baseline_schedule", "diff", "objective_delta",
            )
        )
        if baseline_present and answerability_status == "answerable":
            return _build(
                mode="answer_from_payload",
                recommended_action="none",
                family=family,
                reason=(
                    "The prompt is comparative; the payload already "
                    "carries the baseline/diff fields needed."
                ),
                confidence=0.9,
                available=available,
                extra_missing=answerability_missing_fields,
                intent=intent,
            )
        return _build(
            mode="needs_comparison_payload",
            recommended_action="build_comparison_payload",
            family=family,
            reason=(
                "The prompt asks about a comparison against a baseline "
                "or previous plan, but the payload does not contain "
                "baseline/diff fields."
            ),
            confidence=0.9,
            available=available,
            extra_missing=answerability_missing_fields,
            intent=intent,
        )

    if has_causal_warning:
        return _build(
            mode="partial_from_payload",
            recommended_action="none",
            family=family,
            reason=(
                "The prompt asks for a causal explanation. The factual "
                "evidence can be cited but the cause cannot be "
                "grounded in the current payload."
            ),
            confidence=0.85,
            available=available,
            extra_missing=answerability_missing_fields,
            intent=intent,
        )

    if answerability_status == "partially_answerable":
        return _build(
            mode="partial_from_payload",
            recommended_action="none",
            family=family,
            reason=(
                "The payload supports a partial answer; the requested "
                "scope is not fully grounded by the available fields."
            ),
            confidence=0.8,
            available=available,
            extra_missing=answerability_missing_fields,
            intent=intent,
        )

    if answerability_status == "not_answerable":
        # The contract has already said this case is not answerable.
        # D4's job is to suggest the next thing the operator can do.
        # If the prompt is none of the above triggers, default to
        # clarification so the operator can refine the question.
        return _build(
            mode="clarification_needed",
            recommended_action="ask_clarification",
            family=family,
            reason=(
                "The contract reports the prompt is not answerable from "
                "the current payload; D4 recommends asking the "
                "operator to refine the question."
            ),
            confidence=0.6,
            available=available,
            extra_missing=answerability_missing_fields,
            intent=intent,
        )

    base_decision = _build(
        mode="answer_from_payload",
        recommended_action="none",
        family=family,
        reason=(
            "The contract reports the prompt is answerable from the "
            "current payload."
        ),
        confidence=1.0,
        available=available,
        extra_missing=answerability_missing_fields,
        intent=intent,
    )

    # Advisory learned sufficiency gate. Consulted only when D4 was
    # already about to accept the current payload — never overrides the
    # hard contract branches above (unsupported, clarification, explicit
    # recompute/comparison, causal, partial, not_answerable).
    return _apply_sufficiency_gate(
        decision=base_decision,
        intent=intent,
        family=family,
        payload=payload,
        perturbation_context=perturbation_context,
        action_context=action_context,
        use_gate=use_learned_sufficiency_gate,
        correctness_floor=correctness_floor,
    )


def _apply_sufficiency_gate(
    *,
    decision: ComputeDecision,
    intent: Optional[str],
    family: QueryFamily,
    payload: Optional[dict],
    perturbation_context: Optional[dict],
    action_context: Optional[dict],
    use_gate: Optional[bool],
    correctness_floor: float,
) -> ComputeDecision:
    """Optionally consult the learned gate and attach its result.

    Safety invariants enforced here:

    * Gate is consulted **only** when the deterministic branch landed on
      ``answer_from_payload`` for a family the gate is calibrated for
      (OBJ / PLAN_VALIDITY / STRUCT / SCHEDULE). Hard contract branches
      (unsupported, clarification, comparison, recompute, partial,
      causal) are never re-litigated by the gate.
    * Gate output is attached to ``decision.sufficiency_gate`` so the
      caller can audit what happened — including when the gate abstains.
    * Gate may flip ``answer_from_payload`` -> ``needs_recompute`` with
      ``run_pyvrp_10s``. It never recommends ``pyvrp_60s`` and never
      changes the query family, evidence, warnings, or missing-fields.
    """
    if use_gate is None:
        use_gate = gate_enabled()
    if not use_gate:
        return decision
    if decision.mode != "answer_from_payload":
        return decision
    if family not in _GATE_SUPPORTED_FAMILIES:
        return decision

    result = predict_sufficiency(
        family=family,
        payload_snapshot=payload,
        action_context=action_context,
        perturbation_context=perturbation_context,
        correctness_floor=correctness_floor,
        force_enabled=True,
    )
    # Attach the gate result regardless of decision so the audit trail
    # always carries the gate's view, even when it abstains.
    annotated = decision.model_copy(update={"sufficiency_gate": result})

    if result.decision != "recommend_recompute":
        return annotated

    rec_action = result.recommended_action or DEFAULT_RECOMPUTE_ACTION
    if rec_action in FORBIDDEN_RECOMPUTE_ACTIONS:
        rec_action = DEFAULT_RECOMPUTE_ACTION
    if rec_action not in DEPLOYABLE_RECOMPUTE_ACTIONS:
        rec_action = DEFAULT_RECOMPUTE_ACTION

    return ComputeDecision(
        mode="needs_recompute",
        requires_recompute=True,
        recommended_action=rec_action,
        query_family=family,
        reason=(
            "A bounded recomputation is recommended because the current "
            "action is predicted insufficient for this claim "
            f"(p_sufficient={result.p_sufficient:.3f} < "
            f"threshold={result.threshold:.2f})."
        ),
        confidence=max(0.0, min(1.0, 1.0 - (result.p_sufficient or 0.0))),
        required_fields=list(_REQUIRED_FOR_RECOMPUTE),
        available_fields=decision.available_fields,
        missing_for_full_answer=decision.missing_for_full_answer,
        expected_runtime_seconds=_RUNTIME_BY_ACTION.get(rec_action),
        policy_source=POLICY_SOURCE,
        sufficiency_gate=result,
    )


def _build_overview_decision(
    *,
    intent: str,
    family: QueryFamily,
    available: list[str],
    answerability_status: Optional[str],
    extra_missing: Optional[list[str]],
    unsupported: bool,
) -> ComputeDecision:
    """Decision routing for OVERVIEW-family intents.

    Mapping (per thesis spec):

      perturbation_summary           -> answer_from_payload
      scenario_summary               -> answer_from_payload
      solution_summary               -> answer_from_payload / partial
      perturbation_impact_summary    -> answer_from_payload (with diff)
                                      / needs_comparison_payload (without)
      route_impact_summary           -> answer_from_payload (with route diff)
                                      / needs_comparison_payload (without)
      what_to_watch                  -> answer_from_payload / partial

    Recompute is NEVER recommended for overview intents — these are
    status / explanation questions, not optimization requests.
    """
    # An ``unsupported`` lexical trigger is genuine (driver preference,
    # fuel cost, etc.) — surface it even for overview prompts.
    if unsupported:
        return _build(
            mode="unsupported",
            recommended_action="unsupported",
            family=family,
            reason=(
                "The prompt mixes an overview question with a field "
                "outside the current copilot schema."
            ),
            confidence=0.9,
            available=available,
            extra_missing=extra_missing,
            intent=intent,
        )

    _diff_available = any(
        k in available for k in ("diff", "baseline_solution", "baseline_routes",
                                 "baseline_schedule", "objective_delta",
                                 "objective_delta_absolute", "objective_delta_percent",
                                 "baseline_objective")
    )

    if intent in ("perturbation_summary", "scenario_summary"):
        return _build(
            mode="answer_from_payload",
            recommended_action="none",
            family=family,
            reason=(
                "The prompt asks for a payload-derived overview. The "
                "perturbation context card is always producible from the "
                "scenario metadata."
            ),
            confidence=0.95,
            available=available,
            extra_missing=extra_missing,
            intent=intent,
        )

    if intent == "solution_summary":
        if answerability_status == "answerable":
            return _build(
                mode="answer_from_payload",
                recommended_action="none",
                family=family,
                reason=(
                    "The prompt asks for a current-solution summary; the "
                    "payload exposes the relevant status fields."
                ),
                confidence=0.95,
                available=available,
                extra_missing=extra_missing,
                intent=intent,
            )
        return _build(
            mode="partial_from_payload",
            recommended_action="none",
            family=family,
            reason=(
                "The payload supports a partial solution summary; some "
                "status fields are absent but the rest can be reported."
            ),
            confidence=0.85,
            available=available,
            extra_missing=extra_missing,
            intent=intent,
        )

    if intent in ("perturbation_impact_summary", "route_impact_summary"):
        if _diff_available and answerability_status == "answerable":
            return _build(
                mode="answer_from_payload",
                recommended_action="none",
                family=family,
                reason=(
                    "The prompt asks for an impact summary and the payload "
                    "carries comparison data."
                ),
                confidence=0.9,
                available=available,
                extra_missing=extra_missing,
                intent=intent,
            )
        return _build(
            mode="needs_comparison_payload",
            recommended_action="build_comparison_payload",
            family=family,
            reason=(
                "The prompt asks about the perturbation's impact, but the "
                "payload does not carry baseline/diff fields. The contract "
                "describes the current state and recommends building a "
                "comparison payload."
            ),
            confidence=0.85,
            available=available,
            extra_missing=extra_missing,
            intent=intent,
        )

    # what_to_watch
    if answerability_status == "answerable":
        return _build(
            mode="answer_from_payload",
            recommended_action="none",
            family=family,
            reason=(
                "The prompt asks where the operator should look first; the "
                "payload exposes enough status signals to point at."
            ),
            confidence=0.9,
            available=available,
            extra_missing=extra_missing,
            intent=intent,
        )
    return _build(
        mode="partial_from_payload",
        recommended_action="none",
        family=family,
        reason=(
            "The prompt asks where the operator should look first; the "
            "payload exposes some status signals."
        ),
        confidence=0.8,
        available=available,
        extra_missing=extra_missing,
        intent=intent,
    )


def _build(
    *,
    mode: ComputeMode,
    recommended_action: RecommendedAction,
    family: QueryFamily,
    reason: str,
    confidence: float,
    available: list[str],
    extra_missing: Optional[list[str]],
    intent: Optional[str] = None,
) -> ComputeDecision:
    required = _required_fields(mode, family, intent=intent)
    missing = _missing_for_full_answer(required, available)
    # If the contract already supplied missing fields and ours is empty,
    # surface the contract's list so the API consumer has something to
    # display.
    if not missing and extra_missing:
        missing = list(extra_missing)
    return ComputeDecision(
        mode=mode,
        requires_recompute=(mode == "needs_recompute"),
        recommended_action=recommended_action,
        query_family=family,
        reason=reason,
        confidence=confidence,
        required_fields=required,
        available_fields=available,
        missing_for_full_answer=missing,
        expected_runtime_seconds=_RUNTIME_BY_ACTION.get(recommended_action),
        policy_source=POLICY_SOURCE,
    )


__all__ = [
    "ComputeDecision",
    "ComputeMode",
    "QueryFamily",
    "RecommendedAction",
    "ALL_MODES",
    "ALL_ACTIONS",
    "ALL_QUERY_FAMILIES",
    "DEPLOYABLE_RECOMPUTE_ACTIONS",
    "POLICY_SOURCE",
    "UNSUPPORTED_TRIGGERS",
    "RECOMPUTE_TRIGGERS",
    "COMPARISON_TRIGGERS",
    "CLARIFICATION_TRIGGERS",
    "SufficiencyGateResult",
    "decide_compute",
    "intent_to_query_family",
    "extract_available_fields",
]
