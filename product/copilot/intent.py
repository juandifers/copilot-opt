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


# A-003: OBJ-family default fallthrough used to be unconditional, returning
# `objective_value` for ANY non-comparative OBJ prompt. Adversarial / empty /
# gibberish prompts in an OBJ scenario therefore classified as objective_value
# and produced direct_answer responses (Phase A §3 #4: adversarial_edge LLM-off
# 89% CLASSIFIED_WRONG). Narrow the default by requiring a domain noun.
# PV-family's default stays unchanged because it is load-bearing for operator
# phrasings like "does this still work after...".
_OBJ_DOMAIN_NOUNS = (
    "cost",
    "objective",
    "distance",
    "total",
    "value",
    "score",
    "sum",
    "metric",
    "kpi",
)


def _has_obj_domain_noun(lowered: str) -> bool:
    return any(noun in lowered for noun in _OBJ_DOMAIN_NOUNS)


# A-005: PV-family default narrowing. The pre-A-005 PV branch returned
# feasibility_status unconditionally — Phase A confirmed this over-credits
# orientation queries on PV scenarios (e.g. "walk me through this plan" on a
# PV scenario returned a feasibility flag). The fix uses a positive-match
# check against two lexicons.
#
# The second lexicon (operator-language patterns) is load-bearing: the locked
# Run-2 60-case eval includes operator phrasings like "does this plan still
# work after travel times went up" that do NOT contain feasibility-domain
# nouns but are correctly labeled `feasibility_status` in the golds. A
# pure-noun gate would regress those.
_PV_DOMAIN_NOUNS = (
    "feasible",
    "infeasible",
    "feasibility",
    "violation",
    "violations",
    "unserved",
    "capacity",
    "coverage",
    "windows ok",
    "windows respected",
    "serve",
    "served",
    "reachable",
    "delivered",
    "deliver",
    "assigned",
    "fits",
    "fit",
)

_PV_OPERATOR_PATTERNS = (
    "still work",
    "still works",
    "still hold",
    "holds up",
    "hold up",
    "survive",
    "survives",
    "break",
    "breaks",
    "broken",
    "still ok",
    "still okay",
    "any issues",
    "issues",
    "problems",
    "still doable",
    "doable",
    "still possible",
    # Additions during A-005 calibration against locked Run-2 60-case.
    # Reason and prompt they unblock:
    #   "left out"        — R2-027 "are some going to get left out"
    #   "dropping"        — R2-031 / R2-036 "did we end up dropping any customers"
    #   "dropped"         — past tense companion of "dropping"
    #   "finished within" — R2-035 "can all the stops still be finished within their allowed windows"
    "left out",
    "dropping",
    "dropped",
    "finished within",
)


def _has_pv_feasibility_signal(lowered: str) -> bool:
    if any(noun in lowered for noun in _PV_DOMAIN_NOUNS):
        return True
    if any(phrase in lowered for phrase in _PV_OPERATOR_PATTERNS):
        return True
    return False


# A-006: ranking-prompt detector. Routes prompts like "top 3 customers by
# lateness" or "what's the worst route" to "unknown" before the family
# branches can absorb them into lateness_summary / before_after_comparison.
# The evidence layer's ranking aspect dispatcher (in product.data.evidence)
# then surfaces the ranked items.
#
# Conservative: must contain BOTH a superlative AND a per-entity target
# noun. Bare superlatives ("late") or bare targets ("routes") don't fire.
_RANKING_SUPERLATIVE_RE = re.compile(
    r"\b(worst|best|most|least|biggest|smallest|longest|shortest|"
    r"tightest|widest|heaviest|lightest|top|bottom|rank(?:ing)?|"
    r"closest|furthest|farthest|fastest|slowest|highest|lowest)\b"
)
_RANKING_TARGET_RE = re.compile(
    r"\b(routes?|customers?|vehicles?|deliver(?:y|ies)|stops?|drivers?|"
    r"problems?|issues?|things?|items?|points?|risks?)\b"
)


def _looks_like_ranking_prompt(lowered: str) -> bool:
    return (
        _RANKING_SUPERLATIVE_RE.search(lowered) is not None
        and _RANKING_TARGET_RE.search(lowered) is not None
    )


# A-008: evaluation-prompt detection. Routes "is this acceptable?" /
# "should I worry?" style queries to the new evaluation intents so the
# threshold layer can produce a judgment + grounded numbers.
_ACCEPTABILITY_TOKENS = re.compile(
    r"\b(acceptable|ok|okay|fine|alright|tolerable|reasonable|"
    r"within\s+tolerance|within\s+bounds|within\s+limits|"
    r"good\s+enough|good\s+outcome|live\s+with|comfortable|"
    r"do(?:ne)?\s+well|did\s+we\s+do\s+well|"
    r"on\s+track|in\s+good\s+shape)\b",
    re.IGNORECASE,
)
_CONCERN_TOKENS = re.compile(
    r"\b(worry|worried|concern|concerning|problematic|"
    r"alarming|red\s+flag|should\s+i\s+(?:worry|be\s+worried))\b",
    re.IGNORECASE,
)
_EVALUATION_QUESTION_FORMS = re.compile(
    r"\b(is\s+this|is\s+the|are\s+we|are\s+these|"
    r"should\s+i|should\s+we|"
    r"did\s+we|have\s+we|do\s+i\s+need|"
    r"can\s+i\s+(?:live\s+with|accept))\b",
    re.IGNORECASE,
)

# Dimension tokens used to choose between general plan-acceptability and
# dimension-specific acceptability. Mirrors product/copilot/evaluation.py
# DIMENSION_KEYWORDS — kept here for D1 detection without import cycle.
_EVAL_DIMENSION_TOKENS = re.compile(
    r"\b(late|lateness|delay|tardy|"
    r"cost|objective|expensive|savings|"
    r"feasible|feasibility|infeasible|unserved|"
    r"routes?|vehicles?|structure)\b",
    re.IGNORECASE,
)

# False-positive guard: prompts that mention acceptability/concern in
# meta-conversational contexts (e.g. "is it ok if I ask…") rather than
# evaluating the plan. The guard requires that the prompt also mention
# the *plan* or a dimension keyword.
_EVAL_TARGET_TOKENS = re.compile(
    r"\b(plan|solution|schedule|route|cost|outcome|result|situation|"
    r"perturbation|delivery|deliveries|lateness|"
    r"this(?:\s+(?:one|version|change))?)\b",
    re.IGNORECASE,
)


def _looks_like_evaluation_prompt(lowered: str) -> tuple[bool, bool]:
    """Return ``(is_evaluation, is_dimension_specific)``.

    Detection requires (a) a recognized question form and (b) either an
    acceptability or concern token. The question-form regex is the
    primary false-positive guard — bare "is it" / "is X" without a
    plan-evaluation framing does not match.

    Dimension-specificity is True when the prompt also names a metric
    (lateness/cost/feasibility/routes) — routes to
    ``evaluate_dimension_acceptability``.
    """
    has_question = _EVALUATION_QUESTION_FORMS.search(lowered) is not None
    has_accept = _ACCEPTABILITY_TOKENS.search(lowered) is not None
    has_concern = _CONCERN_TOKENS.search(lowered) is not None
    has_dimension = _EVAL_DIMENSION_TOKENS.search(lowered) is not None
    if not (has_accept or has_concern):
        return (False, False)
    if not has_question:
        return (False, False)
    return (True, has_dimension)




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

# Typo-tolerant regexes for the same phrasings. ``pertu\w+`` matches
# "perturbation", "perturbed", "pertutbation" (real telemetry typo seen
# 2026-05-26), and similar misspellings without over-reaching to other
# words. Anchors the noun via a leading verb so we do not match prompts
# that merely contain "perturbation" incidentally.
_PERTURBATION_SUMMARY_REGEXES = (
    re.compile(r"\bwhat\s+(?:is|does|s)\s+(?:this|the)\s+pertu\w+\b"),
    re.compile(r"\bwhat'?s\s+(?:this|the)\s+pertu\w+\b"),
    re.compile(r"\bwhat\s+(?:kind|type)\s+of\s+pertu\w+\b"),
    re.compile(r"\bwhat\s+pertu\w+\b"),
    re.compile(r"\bdescribe\s+(?:this|the)\s+pertu\w+\b"),
    re.compile(r"\bexplain\s+(?:this|the)\s+pertu\w+\b"),
    re.compile(r"\btell\s+me\s+about\s+(?:this|the)\s+pertu\w+\b"),
    re.compile(r"\bwhat\s+(?:is|'s)\s+(?:the\s+)?pertu\w+\s+doing\b"),
)

_SCENARIO_SUMMARY_PHRASES = (
    "what am i looking at",
    "what is going on here",
    "what's going on here",
    "whats going on",
    "what is going on",
    "what's going on",
    "summarize this scenario",
    "summarise this scenario",
    "summarize the scenario",
    "summarise the scenario",
    "summarize the current situation",
    "summarise the current situation",
    "give me the overview",
    "give me an overview",
    "give me a snapshot",
    "give me the lowdown",
    "set me up",
    "brief me",
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
    "walk me through this plan",
    "walk me through the plan",
    "talk me through this plan",
    "talk me through the plan",
    "walk me through what happened",
    "talk me through what happened",
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
    # Perturbation description (no "impact" framing). Substring set first
    # for the canonical phrasings, then typo-tolerant regexes for variants
    # that the live telemetry surfaced.
    if _matches_any(lowered, _PERTURBATION_SUMMARY_PHRASES):
        return "perturbation_summary"
    if any(p.search(lowered) for p in _PERTURBATION_SUMMARY_REGEXES):
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

    # A-008: evaluation-shaped prompts route to the dedicated evaluation
    # intents. Runs before the family branches so e.g. "is this lateness
    # acceptable?" doesn't get absorbed into lateness_summary.
    is_eval, dim_specific = _looks_like_evaluation_prompt(lowered)
    if is_eval:
        return (
            "evaluate_dimension_acceptability"
            if dim_specific
            else "evaluate_plan_acceptability"
        )

    # A-006: ranking-shaped prompts route to "unknown" so the evidence
    # layer's ranking aspect dispatcher fires. Runs before the family
    # branches because the existing branches would otherwise absorb e.g.
    # "top 3 customers by lateness" as lateness_summary and bypass the
    # ranked output the operator asked for.
    if _looks_like_ranking_prompt(lowered):
        return "unknown"

    if fam == "OBJ":
        if is_comparative:
            return "objective_delta"
        if _has_obj_domain_noun(lowered):
            return "objective_value"
        return "unknown"

    if fam in ("PLAN_VALIDITY", "PV"):
        if _has_pv_feasibility_signal(lowered):
            return "feasibility_status"
        return "unknown"

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
