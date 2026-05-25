"""Deterministic intent classification.

Given the prompt text and family, decide which `Intent` (from
product.copilot.contracts) the question maps to. No model calls. Run 1
shows that the four claim families plus the perturbation context are
already enough to distinguish the 11 intents in the contract.
"""
from __future__ import annotations

import re
from typing import Optional


_COMPARATIVE_TOKENS = (
    "changed",
    "change",
    "actually change",
    "still",
    "compared",
    "different",
)
_COMPARATIVE_REGEX = re.compile(r"\b(fewer|more|less)\s+\w+\s+than\b")
_NEW_ORDER_TOKENS = ("new customer", "new order", "added customer")

# full_route_listing matches questions that ask for the full roster of
# customers per route/vehicle (not a single-customer membership lookup).
# Detection must run BEFORE _is_about_new_customer_assignment because
# wording like "List all the customers assigned to each route after the
# new orders came in" would otherwise match the new-customer heuristic
# on the "new orders"+"assigned" tokens.
_FULL_ROUTE_LISTING_PHRASES = (
    "each route",
    "each vehicle",
    "per route",
    "per vehicle",
    "customers on each",
    "customers assigned to each",
    "customers per",
    "route roster",
    "rosters per",
    "list the customers",
    "list all the customers",
    "list all customers",
    "show customers per",
    "customers in each",
)


def _is_full_route_listing(lowered: str) -> bool:
    return any(phrase in lowered for phrase in _FULL_ROUTE_LISTING_PHRASES)
_REFUSAL_PHRASES = (
    "data does not contain",
    "cannot answer",
    "insufficient",
    "not provided",
    "do not have",
)


# ---------------------------------------------------------------------------
# Overview / explanation intent detection
#
# These prompts ask for a payload-derived overview rather than a specific
# field value. Detection must run BEFORE the family-based branches so that
# "what is this perturbation doing?" routes to perturbation_summary even
# when the question is tagged STRUCT or SCHEDULE.
#
# Order within this block matters: route_impact_summary beats
# perturbation_impact_summary when "routes" / "vehicle" appears, because
# the prompt is asking specifically about per-route effects.
# ---------------------------------------------------------------------------

_PERTURBATION_SUMMARY_PHRASES = (
    "what is this perturbation",
    "what's this perturbation",
    "what kind of perturbation",
    "what type of perturbation",
    "what stress",
    "what is being stressed",
    "what does this perturbation",
    "describe this perturbation",
    "describe the perturbation",
    "what is the perturbation doing",
    "what's the perturbation doing",
    "what perturbation",
)

_SCENARIO_SUMMARY_PHRASES = (
    "what am i looking at",
    "what is going on here",
    "what's going on here",
    "summarize this scenario",
    "summarise this scenario",
    "summarize the scenario",
    "summarise the scenario",
    "give me the overview",
    "give me an overview",
    "what is this scenario",
    "what's this scenario",
    "what kind of scenario",
    "what does this scenario represent",
    "scenario overview",
)

_SOLUTION_SUMMARY_PHRASES = (
    "summarize the solution",
    "summarise the solution",
    "summarize the current solution",
    "summarise the current solution",
    "summarize the plan",
    "summarise the plan",
    "how does the plan look",
    "how does this plan look",
    "is this solution okay at a high level",
    "what is the status of the plan",
    "what's the status of the plan",
    "status of the plan",
    "status of the solution",
    "plan status",
    "solution status",
)

_IMPACT_PHRASES = (
    "affecting the solution",
    "affecting the plan",
    "affect the solution",
    "affect the plan",
    "changed because of this perturbation",
    "did this make things worse",
    "did this make the solution worse",
    "did this make the plan worse",
    "what changed because",
    "how did this affect",
    "how did the perturbation affect",
    "how is the perturbation affecting",
    "impact of this perturbation",
    "impact of the perturbation",
    "perturbation impact",
)

_ROUTE_IMPACT_PHRASES = (
    "affecting routes",
    "affecting the routes",
    "affecting the route plan",
    "affect routes",
    "affect the routes",
    "which routes changed",
    "which routes are most affected",
    "which routes were most affected",
    "how did the route plan change",
    "how did the routes change",
    "did the routes change",
    "did any routes change",
    "route impact",
    "routes impacted",
    "routes affected",
    "how is this perturbation affecting routes",
)

_WHAT_TO_WATCH_PHRASES = (
    "what should i pay attention to",
    "what should we pay attention to",
    "anything concerning",
    "anything to worry about",
    "where should i look",
    "where do i look",
    "what should i inspect",
    "what should we inspect",
    "what to watch",
    "what to look for",
)


def _matches_any(lowered: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in lowered for phrase in phrases)


def _detect_overview_intent(lowered: str) -> Optional[str]:
    """Detect overview/explanation intents from prompt language.

    Returns the canonical intent string when a match is found, or ``None``
    otherwise. Order: route-impact > perturbation-impact > perturbation
    > scenario > solution > what-to-watch.
    """
    # Route-impact wins over perturbation-impact when both fire — "how
    # is this perturbation affecting routes?" is a route-impact question.
    if _matches_any(lowered, _ROUTE_IMPACT_PHRASES):
        return "route_impact_summary"
    # Perturbation-impact (general impact framing, not route-specific).
    if _matches_any(lowered, _IMPACT_PHRASES):
        return "perturbation_impact_summary"
    # Perturbation description (no "impact" framing).
    if _matches_any(lowered, _PERTURBATION_SUMMARY_PHRASES):
        return "perturbation_summary"
    # Scenario-level overview.
    if _matches_any(lowered, _SCENARIO_SUMMARY_PHRASES):
        return "scenario_summary"
    # Solution-level summary.
    if _matches_any(lowered, _SOLUTION_SUMMARY_PHRASES):
        return "solution_summary"
    # What-to-watch / where to look first.
    if _matches_any(lowered, _WHAT_TO_WATCH_PHRASES):
        return "what_to_watch"
    return None


def _has_specific_route_number(lowered: str) -> bool:
    return re.search(r"\broute\s+\d+\b", lowered) is not None


def _has_specific_customer_number(lowered: str) -> bool:
    return re.search(r"\bcustomer\s+\d+\b", lowered) is not None


def _is_about_new_customer_assignment(lowered: str) -> bool:
    """The question subject is the new customer's assignment, not a
    specific entity that the new customer happens to interact with."""
    if not any(t in lowered for t in _NEW_ORDER_TOKENS):
        return False
    # Subject-test: a specific route/customer number, or "the driver",
    # means the question is about that entity, not the new customer.
    if _has_specific_route_number(lowered) or _has_specific_customer_number(lowered):
        return False
    if "the driver" in lowered:
        return False
    # Now check that the question asks where the new customer landed.
    return any(
        token in lowered
        for token in ("which route", "what route", "where", "assigned", "end up", "did they")
    )


def _looks_like_refusal(generator_record: Optional[dict]) -> bool:
    if not generator_record:
        return False
    so = generator_record.get("structured_output") or {}
    text = (so.get("answer_text") or generator_record.get("answer_text") or "").lower()
    return any(phrase in text for phrase in _REFUSAL_PHRASES)


def infer_intent(
    prompt_text: str,
    family: str,
    generator_record: Optional[dict] = None,
) -> str:
    """Classify the prompt into one of the contract `Intent` strings."""
    lowered = (prompt_text or "").lower()
    fam = (family or "").upper()
    is_comparative = (
        any(token in lowered for token in _COMPARATIVE_TOKENS)
        or _COMPARATIVE_REGEX.search(lowered) is not None
    )

    # Overview / explanation intents run first. These are family-agnostic
    # operator questions that ask for a payload-derived summary rather than
    # an exact field lookup ("what is this perturbation doing?", "what
    # should I pay attention to?"). Without this check they would
    # otherwise collapse to "unknown" in STRUCT/SCHEDULE families.
    overview = _detect_overview_intent(lowered)
    if overview is not None:
        return overview

    # full_route_listing: per-route roster questions ("list the customers
    # on each route", "customers per vehicle"). Must beat the new-customer
    # heuristic, which would otherwise capture roster questions that
    # happen to mention "after the new orders came in".
    if _is_full_route_listing(lowered):
        return "full_route_listing"

    # New-customer-assignment is family-agnostic but only triggers when
    # the question subject is the new customer itself.
    if _is_about_new_customer_assignment(lowered):
        return "new_customer_assignment"

    if fam == "OBJ":
        if is_comparative:
            return "objective_delta"
        return "objective_value"

    if fam in ("PLAN_VALIDITY", "PV"):
        return "feasibility_status"

    if fam == "STRUCT":
        if "same route" in lowered:
            return "same_route_boolean"
        if is_comparative:
            return "before_after_comparison"
        if any(
            token in lowered
            for token in (
                "number of vehicles",
                "vehicles needed",
                "route count",
                "how many routes",
                "how many vehicles",
                "how many trucks",
            )
        ):
            return "route_count"
        if (
            "which route" in lowered
            or "what route" in lowered
            or _has_specific_customer_number(lowered)
        ):
            return "single_customer_route_membership"
        return "unknown"

    if fam == "SCHEDULE":
        # Customer-arrival check first: a question about a specific
        # customer's arrival time always wins over route-end-time.
        if any(
            token in lowered
            for token in ("when does the driver reach", "when does the driver get to", "arrive at customer", "reach customer", "get to customer")
        ):
            return "customer_arrival"
        if any(token in lowered for token in ("wrap up", "wraps up", "end time", "finish", "complete")) and "route" in lowered:
            return "route_end_time"
        if any(token in lowered for token in ("late", "delivery window", "on time", "delayed", "lateness", "miss")):
            return "lateness_summary"
        if is_comparative:
            return "before_after_comparison"
        # Fallback for "when does X reach Y" style without depot mention
        if "when does" in lowered and _has_specific_customer_number(lowered):
            return "customer_arrival"
        return "unknown"

    if _looks_like_refusal(generator_record):
        return "refusal_or_insufficient_payload"

    return "unknown"


# ---------------------------------------------------------------------------
# System D1 — semantic intent adapter wrapper
# ---------------------------------------------------------------------------


def infer_intent_d1(
    prompt_text: str,
    family: str,
    generator_record: Optional[dict] = None,
) -> str:
    """Intent classifier used by System D1.

    Runs the existing C0 classifier and then defers to the
    deterministic semantic intent adapter
    (`product.copilot.semantic_intent_adapter.decide_d1_intent`) on
    risk-zone outcomes. The adapter never sees the payload or the
    generator record — D1's seam is the language→intent map only.

    The C0 `infer_intent` function above is left untouched: D1 layers
    on top so the canonical C0 path remains available to existing
    runners and tests.
    """
    # Local import keeps `intent.py` import-cycle-free if the adapter
    # ever needs to import from `intent.py` (which it currently does
    # not).
    from product.copilot.semantic_intent_adapter import decide_d1_intent

    c0_intent = infer_intent(
        prompt_text=prompt_text, family=family, generator_record=generator_record
    )
    frame = decide_d1_intent(
        prompt_text=prompt_text, family=family, c0_intent=c0_intent
    )
    return frame.intent


def infer_intent_d1_frame(
    prompt_text: str,
    family: str,
    generator_record: Optional[dict] = None,
):
    """Same as `infer_intent_d1` but returns the full `QueryFrame`.

    Used by the System D1 evaluation harness to record adapter
    provenance (override counts, source distribution, comparison
    type) without altering the downstream contract path. Returns a
    `product.copilot.query_frame.QueryFrame`.
    """
    from product.copilot.semantic_intent_adapter import decide_d1_intent

    c0_intent = infer_intent(
        prompt_text=prompt_text, family=family, generator_record=generator_record
    )
    return decide_d1_intent(
        prompt_text=prompt_text, family=family, c0_intent=c0_intent
    )


# ---------------------------------------------------------------------------
# System D-Final — LLM semantic adapter wrapper
# ---------------------------------------------------------------------------


def infer_intent_d_final(
    prompt_text: str,
    family: str,
    client=None,
    mode: str = "hybrid_guarded",
    generator_record: Optional[dict] = None,
) -> str:
    """Intent classifier used by System D-Final.

    Delegates to the LLM semantic adapter (hybrid_guarded by default)
    then falls back to D1 if the LLM adapter is unavailable (no
    client). Returns only the intent string.

    Parameters
    ----------
    client:
        OpenAI client from
        `product.evaluation.model_clients.openai_client.load_openai_client()`.
        When ``None`` the function falls through to D1 (deterministic
        fallback, no LLM call).
    mode:
        One of "hybrid_guarded" | "llm_only" | "llm_fallback".
        Defaults to "hybrid_guarded".
    """
    frame, _ = infer_intent_d_final_frame(
        prompt_text=prompt_text,
        family=family,
        client=client,
        mode=mode,
        generator_record=generator_record,
    )
    return frame.intent


def infer_intent_d_final_frame(
    prompt_text: str,
    family: str,
    client=None,
    mode: str = "hybrid_guarded",
    generator_record: Optional[dict] = None,
):
    """Same as `infer_intent_d_final` but returns the full ``(QueryFrame, LLMAdapterMetadata)`` tuple.

    Used by the D-Final evaluation harness to record adapter provenance
    (source, confidence, fallback, latency, tokens) without altering the
    downstream contract path.
    """
    from product.copilot.llm_semantic_intent_adapter import infer_intent_d_final_frame as _llm_frame

    if client is None:
        # No client available — fall back to D1 deterministically
        d1_frame = infer_intent_d1_frame(
            prompt_text=prompt_text, family=family, generator_record=generator_record
        )
        from product.copilot.llm_query_frame import LLMAdapterMetadata, ValidationOutcome
        meta = LLMAdapterMetadata(
            mode=mode,
            source="d1",
            accepted=True,
            fallback_used=True,
            fallback_reason="no_llm_client",
            confidence=d1_frame.confidence,
            model_name=None,
            validation_outcome=ValidationOutcome.fallback_to_d1.value,
            d1_intent=d1_frame.intent,
        )
        return d1_frame, meta

    return _llm_frame(
        prompt=prompt_text,
        family=family,
        client=client,
        mode=mode,
    )
