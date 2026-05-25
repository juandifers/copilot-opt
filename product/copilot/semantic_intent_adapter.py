"""System D1 — Deterministic semantic intent adapter.

D1 layers a deterministic semantic adapter on top of the existing
C0 keyword classifier. The adapter recognises three families of
intent-mediated failures identified in the R2-S cross-axis
synthesis (`product/evaluation/run2_stress/analysis/cross_axis_synthesis.md`,
§4):

1. OBJ value/delta disambiguation
   - Recover `objective_value` on "what's the total cost" prompts
     whose incidental wording ("compared with the rate card",
     "still a single total", "actually changed in the report
     format") would otherwise drag C0 to `objective_delta`.
   - Promote prompts with an explicit comparator clause
     (`better than the optimum`, `rank against a stronger solver`)
     to `objective_delta` so downstream `reference_solution.objective`
     missing-field logic and `comparison_referent_ambiguity` can
     fire.

2. STRUCT movement / reassignment / before-after
   - Map non-comparative movement wording (`swap from`,
     `reassigned away from`, `before this round of reassignments`,
     `shift versus the prior`) to `before_after_comparison` so the
     contract's `unsupported_comparison` useful-refusal can fire.

3. SCHEDULE / STRUCT paraphrase tail
   - Map paraphrases of completion (`close out`, `done for the day`,
     `complete its run`) to `route_end_time`.
   - Map lateness paraphrases (`fall behind schedule`,
     `served after their allowed time`) to `lateness_summary`.
   - Map route-listing paraphrases (`show me every route`,
     `list the complete route plan`, `full set of vehicle runs`)
     to `full_route_listing`.

The adapter is deterministic, side-effect-free, and consumes only
the prompt text + family. It does NOT touch downstream
answerability, evidence, warning, useful-refusal, or refusal-policy
logic. The downstream contract pipeline reads only the canonical
`intent` field of the returned `QueryFrame`.

Routing policy (`infer_intent_d1`):

  1. Run the existing C0 `infer_intent`.
  2. If C0 returned a high-confidence non-risk intent, keep it.
  3. Otherwise consult `classify_semantic`; if it returns a
     supported intent, override C0.
  4. On any adapter exception, ambiguous result, or unsupported
     intent, fall back to C0 (or `unknown` if C0 also returned
     `unknown`).

The adapter never invents an intent value outside the existing
`Intent` enum (`product/copilot/contracts.py`).

No model call. No solver call. No payload access. No prompt-engineering
against heldout case text — the rule families are organised around
semantic categories, not case-by-case strings.
"""
from __future__ import annotations

import re
from typing import Optional

from product.copilot.query_frame import (
    AmbiguitySignal,
    ComparisonType,
    QueryFrame,
    QueryFrameEntities,
)


# ---------------------------------------------------------------------------
# Supported intents (mirrors the Intent literal in contracts.py)
# ---------------------------------------------------------------------------


SUPPORTED_INTENTS: frozenset[str] = frozenset({
    "objective_value",
    "objective_delta",
    "feasibility_status",
    "route_count",
    "single_customer_route_membership",
    "same_route_boolean",
    "route_end_time",
    "customer_arrival",
    "lateness_summary",
    "before_after_comparison",
    "new_customer_assignment",
    "full_route_listing",
    "refusal_or_insufficient_payload",
    "unknown",
})


# ---------------------------------------------------------------------------
# Semantic phrase banks
# ---------------------------------------------------------------------------


# OBJ value question — "what's the total cost", "what does X cost".
_OBJ_VALUE_PHRASES: tuple[str, ...] = (
    "what's the total cost",
    "what is the total cost",
    "whats the total cost",
    "what's the final cost",
    "what is the final cost",
    "what's the current cost",
    "what is the current cost",
    "total cost on this plan",
    "total cost of this plan",
    "what does this plan cost",
    "what does the plan cost",
    "what does this plan end up costing",
    "what does the plan end up costing",
    "what does this end up costing",
    "what does it cost",
    "what is the cost",
    "what's the cost",
    "how much does this plan cost",
    "how much does the plan cost",
    "what does this plan come to",
    "what does this come to",
    "end up costing",
    "single total",
    "one total cost",
)

# OBJ explicit delta phrasing — these always indicate a delta question.
_OBJ_DELTA_HOW_MUCH_RE = re.compile(
    r"\bhow much\s+(?:more|less|fewer|cheaper|costlier|better|worse|further)\b"
)
_OBJ_DELTA_PHRASES: tuple[str, ...] = (
    "compared to before",
    "compared with before",
    "compared to the baseline",
    "compared with the baseline",
    "compared to the previous",
    "compared with the previous",
    "compared to the original",
    "compared with the original",
    "compared to a full re-solve",
    "compared with a full re-solve",
    "compared to running a full re-solve",
    "compared with running a full re-solve",
    "compared to re-running",
    "compared with re-running",
    "is the cost up or down compared",
    "how much did the total distance change",
    "how much did the cost change",
    "did the objective change",
)

# Comparator words used in implicit-delta detection
_OBJ_DELTA_COMPARATOR_TOKENS: tuple[str, ...] = (
    "compared to",
    "compared with",
    "versus",
    " vs ",
    " vs.",
    "relative to",
    "rank against",
    "stack up against",
    "stack up to",
    "stacks up against",
    "rank against",
    "better than",
    "worse than",
    "stronger than",
    "weaker than",
)

# Comparator referents — phrases the comparator might point at.
# Splitting them lets us decide whether "compared with X" actually
# describes a plan/objective baseline (→ delta) or an incidental
# external reference like a rate card (→ value).
_OBJ_DELTA_REFERENT_TOKENS: tuple[str, ...] = (
    "baseline",
    "previous solution",
    "previous plan",
    "previous version",
    "previous run",
    "previous re-solve",
    "prior solution",
    "prior plan",
    "prior schedule",
    "prior run",
    "old solution",
    "old plan",
    "from before",
    "before the perturbation",
    "before service",
    "before travel",
    "the optimum",
    "an optimum",
    "optimum solver",
    "optimal solver",
    "stronger solver",
    "different solver",
    "another solver",
    "better solver",
    "full re-solve",
    "fuller re-solve",
    "re-solve from scratch",
    "rerunning",
    "re-running",
    "from scratch",
)


# STRUCT before/after movement / reassignment indicators.
# Each entry is intended to be specific enough that triggering it on
# a non-comparative current-state question is unlikely.
_STRUCT_MOVEMENT_PHRASES: tuple[str, ...] = (
    "swap from",
    "swapped from",
    "swap to",
    "swapped to",
    "reassigned away",
    "reassigned to",
    "reassignment",
    "reassignments",
    "round of reassignments",
    "moved away from",
    "moved to a different",
    "moved off of",
    "moved off",
    "shifted away",
    "shift versus",
    "shifted versus",
    "shift from",
    "shifted from",
    "in this revision",
    "in this update",
    "in this round",
    "versus the prior",
    "versus the previous",
    "from the previous",
    "from the prior",
    "before this round",
    "before the reassignments",
    "before the reassignment",
)

# A "where was X before" / "did X get moved" style question — past
# tense plus a temporal-before marker — should trigger before_after.
_STRUCT_PAST_BEFORE_RE = re.compile(
    r"\b(?:where|which route)\s+(?:was|did)\b.*\bbefore\b"
)
_STRUCT_SHIFT_VERSUS_RE = re.compile(
    r"\bshift\b.*\b(?:versus|vs\.?|against|relative to)\b.*\b(?:prior|previous|baseline|old|original)\b"
)


# SCHEDULE route_end_time paraphrases — completion verbs + an entity
# noun (vehicle/truck/route/run/driver). The C0 branch requires the
# literal word "route" to co-occur with one of its tokens; the
# adapter relaxes this to any of {route, vehicle, truck, driver, run}.
_SCHEDULE_END_COMPLETION_VERBS: tuple[str, ...] = (
    "close out",
    "closes out",
    "closing out",
    "done for the day",
    "done with the run",
    "done with its run",
    "complete its run",
    "completes its run",
    "completed its run",
    "complete the run",
    "completes the run",
    "ends its run",
    "end its run",
    "wraps up",
    "wrap up",
    "wraps up the day",
    "wraps its day",
    "wraps its run",
    "finish window",
    "last stop time",
    "finished for the day",
)

_SCHEDULE_END_ENTITY_RE = re.compile(
    r"\b(?:route|vehicle|truck|driver|run|tour)\s*\d+\b",
    re.IGNORECASE,
)

# Bare "is X finished" / "when is X finished" where X is a vehicle.
_SCHEDULE_END_BARE_FINISH_RE = re.compile(
    r"\b(?:is|when is|what time is|at what time is)\s+"
    r"(?:route|vehicle|truck|driver|run|tour)\s*\d+\s+"
    r"(?:finished|done|complete|completed|wrapped up|wrapped|closed out)\b",
    re.IGNORECASE,
)


# SCHEDULE lateness paraphrases — beyond the C0 token set
# ("late", "delivery window", "on time", "delayed", "lateness",
# "miss").
_SCHEDULE_LATENESS_PHRASES: tuple[str, ...] = (
    "behind schedule",
    "fall behind",
    "falling behind",
    "served after their allowed time",
    "served after the allowed time",
    "served after their time window",
    "served after the time window",
    "after their time window",
    "after the time window",
    "miss promised window",
    "miss their promised window",
    "miss the promised window",
    "promised window",
    "not on time",
    "running late",
    "show up late",
    "served late",
)


# STRUCT full_route_listing paraphrases — beyond C0's phrase set.
_FULL_ROUTE_LISTING_PHRASES_D1: tuple[str, ...] = (
    "every route",
    "every vehicle",
    "show me every route",
    "show me every vehicle",
    "list the complete route plan",
    "complete route plan",
    "full route plan",
    "full set of routes",
    "full set of vehicle runs",
    "full set of routes",
    "vehicle runs",
    "route roster",
    "rosters per",
    "full route list",
    "all the routes",
    "all routes in the plan",
    "all the vehicles in the plan",
    "list all the vehicles",
    "list every route",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_CUSTOMER_NUMBER_RE = re.compile(r"\bcustomer\s+\d+\b", re.IGNORECASE)
_ROUTE_NUMBER_RE = re.compile(r"\broute\s+\d+\b", re.IGNORECASE)


def _has_customer_number(lowered: str) -> bool:
    return _CUSTOMER_NUMBER_RE.search(lowered) is not None


def _has_route_number(lowered: str) -> bool:
    return _ROUTE_NUMBER_RE.search(lowered) is not None


def _any_phrase(lowered: str, phrases: tuple[str, ...]) -> Optional[str]:
    for p in phrases:
        if p in lowered:
            return p
    return None


# ---------------------------------------------------------------------------
# Semantic classifier — per-family
# ---------------------------------------------------------------------------


def _classify_obj(lowered: str) -> Optional[QueryFrame]:
    """OBJ family: disambiguate value vs delta."""
    value_match = _any_phrase(lowered, _OBJ_VALUE_PHRASES)
    explicit_delta_match = _any_phrase(lowered, _OBJ_DELTA_PHRASES)
    how_much_delta = _OBJ_DELTA_HOW_MUCH_RE.search(lowered)
    comparator_token = _any_phrase(lowered, _OBJ_DELTA_COMPARATOR_TOKENS)
    referent_token = _any_phrase(lowered, _OBJ_DELTA_REFERENT_TOKENS)

    notes: list[str] = []
    comparison_type: ComparisonType = "none"

    # 1. Clear explicit delta phrasing wins.
    if explicit_delta_match or how_much_delta:
        notes.append(
            "explicit_delta_phrase=" + (explicit_delta_match or "how-much-than")
        )
        if referent_token:
            comparison_type = _referent_to_comparison_type(referent_token)
        else:
            comparison_type = "baseline"
        return QueryFrame(
            intent="objective_delta",
            source="semantic_adapter",
            confidence=0.95,
            requires_baseline=True,
            comparison_type=comparison_type,
            adapter_notes=notes,
        )

    # 2. Implicit comparator + delta referent → delta.
    if comparator_token and referent_token:
        notes.append(
            f"implicit_delta_comparator={comparator_token.strip()!r} "
            f"referent={referent_token!r}"
        )
        return QueryFrame(
            intent="objective_delta",
            source="semantic_adapter",
            confidence=0.85,
            requires_baseline=True,
            comparison_type=_referent_to_comparison_type(referent_token),
            adapter_notes=notes,
        )

    # 3. Value-question wording with no genuine delta comparator → value.
    if value_match:
        if comparator_token and not referent_token:
            notes.append(
                f"value_question={value_match!r} comparator={comparator_token.strip()!r} "
                "but no recognised delta referent — incidental comparative"
            )
        else:
            notes.append(f"value_question={value_match!r}")
        return QueryFrame(
            intent="objective_value",
            source="semantic_adapter",
            confidence=0.9,
            comparison_type="none",
            adapter_notes=notes,
        )

    # 4. Comparator without referent and without value framing → leave
    # to C0 (likely keyword-driven delta in the family branch).
    return None


def _referent_to_comparison_type(token: str) -> ComparisonType:
    t = token.lower()
    if "solver" in t or "re-solve" in t or "rerunning" in t or "re-running" in t or "from scratch" in t:
        return "reference_solver"
    if "optimum" in t or "optimal" in t:
        return "reference_solver"
    if "baseline" in t:
        return "baseline"
    if "previous" in t or "prior" in t or "old" in t:
        return "previous_solution"
    if "before" in t:
        return "baseline"
    return "implicit"


def _classify_struct_movement(lowered: str) -> Optional[QueryFrame]:
    """STRUCT: detect movement / before-after questions even when a
    specific customer / route number is present (the C0
    customer-number guard would otherwise route to
    `single_customer_route_membership`)."""
    movement_phrase = _any_phrase(lowered, _STRUCT_MOVEMENT_PHRASES)
    past_before = _STRUCT_PAST_BEFORE_RE.search(lowered) is not None
    shift_versus = _STRUCT_SHIFT_VERSUS_RE.search(lowered) is not None

    if not (movement_phrase or past_before or shift_versus):
        return None

    notes: list[str] = []
    if movement_phrase:
        notes.append(f"struct_movement_phrase={movement_phrase!r}")
    if past_before:
        notes.append("struct_past_tense_before")
    if shift_versus:
        notes.append("struct_shift_versus_prior")

    return QueryFrame(
        intent="before_after_comparison",
        source="semantic_adapter",
        confidence=0.9,
        requires_baseline=True,
        comparison_type="previous_solution",
        adapter_notes=notes,
    )


def _classify_schedule_end(lowered: str) -> Optional[QueryFrame]:
    """SCHEDULE route_end_time paraphrase tail."""
    if _SCHEDULE_END_BARE_FINISH_RE.search(lowered):
        return QueryFrame(
            intent="route_end_time",
            source="semantic_adapter",
            confidence=0.9,
            adapter_notes=["schedule_end_bare_finish"],
        )

    verb_match = _any_phrase(lowered, _SCHEDULE_END_COMPLETION_VERBS)
    has_entity = _SCHEDULE_END_ENTITY_RE.search(lowered) is not None
    if verb_match and has_entity:
        return QueryFrame(
            intent="route_end_time",
            source="semantic_adapter",
            confidence=0.9,
            adapter_notes=[f"schedule_completion_verb={verb_match!r}"],
        )
    return None


def _classify_schedule_lateness(lowered: str) -> Optional[QueryFrame]:
    """SCHEDULE lateness paraphrase tail."""
    match = _any_phrase(lowered, _SCHEDULE_LATENESS_PHRASES)
    if match is None:
        return None
    return QueryFrame(
        intent="lateness_summary",
        source="semantic_adapter",
        confidence=0.9,
        adapter_notes=[f"schedule_lateness_phrase={match!r}"],
    )


def _classify_full_route_listing(lowered: str) -> Optional[QueryFrame]:
    """STRUCT full_route_listing paraphrase tail.

    Defers to single_customer_route_membership if a specific customer
    number appears (C0 customer-number guard precedence)."""
    if _has_customer_number(lowered):
        return None
    match = _any_phrase(lowered, _FULL_ROUTE_LISTING_PHRASES_D1)
    if match is None:
        return None
    return QueryFrame(
        intent="full_route_listing",
        source="semantic_adapter",
        confidence=0.9,
        adapter_notes=[f"full_route_listing_phrase={match!r}"],
    )


# ---------------------------------------------------------------------------
# Top-level semantic classifier
# ---------------------------------------------------------------------------


def classify_semantic(
    prompt_text: str,
    family: str,
) -> Optional[QueryFrame]:
    """Run the deterministic semantic adapter over (prompt, family).

    Returns a `QueryFrame` with `source == 'semantic_adapter'` when a
    rule fires, else `None`. The caller decides whether to override
    C0 with the result. Never raises; an unrecognised family returns
    `None`.
    """
    if not prompt_text:
        return None
    lowered = prompt_text.lower()
    fam = (family or "").upper()

    if fam == "OBJ":
        frame = _classify_obj(lowered)
        if frame is not None:
            return frame

    if fam == "STRUCT":
        # STRUCT — try movement first; full_route_listing second.
        # Movement signal is stronger because the C0
        # customer-number guard could otherwise mis-claim it as
        # single_customer_route_membership.
        frame = _classify_struct_movement(lowered)
        if frame is not None:
            return frame
        frame = _classify_full_route_listing(lowered)
        if frame is not None:
            return frame

    if fam == "SCHEDULE":
        # Order matters: route_end is stricter than lateness phrasing.
        frame = _classify_schedule_end(lowered)
        if frame is not None:
            return frame
        frame = _classify_schedule_lateness(lowered)
        if frame is not None:
            return frame
        # Some SCHEDULE prompts paraphrase movement of routes
        # (e.g. "did the schedule shift versus the prior").
        frame = _classify_struct_movement(lowered)
        if frame is not None:
            return frame

    # Cross-family rescues for prompts that C0 returned unknown on
    # but whose paraphrase tail is clear from the prompt alone.
    # E.g. an Axis 3 SCHEDULE/STRUCT crossover where the family
    # column was mis-set. The adapter is conservative: it only fires
    # the SCHEDULE/STRUCT paraphrase rules and never invents an OBJ
    # intent in this branch.
    if fam not in ("OBJ", "STRUCT", "SCHEDULE", "PLAN_VALIDITY", "PV"):
        frame = _classify_schedule_end(lowered)
        if frame is not None:
            return frame
        frame = _classify_schedule_lateness(lowered)
        if frame is not None:
            return frame
        frame = _classify_full_route_listing(lowered)
        if frame is not None:
            return frame

    return None


# ---------------------------------------------------------------------------
# Routing policy decisions
# ---------------------------------------------------------------------------


# C0 intents where comparator/movement/listing wording can flip the
# correct intent. The adapter is called whenever C0 lands here and
# a semantic signal is present.
_C0_RISK_ZONE_INTENTS: frozenset[str] = frozenset({
    "objective_value",
    "objective_delta",
    "single_customer_route_membership",
    "unknown",
})

# Lightweight pre-check: does the prompt contain any signal that the
# adapter could act on? Avoids calling the adapter on prompts that
# can't possibly be re-routed.
_ANY_SIGNAL_TOKENS: tuple[str, ...] = (
    # OBJ
    "compared", "versus", " vs ", "vs.", "relative to", "rank against",
    "stack up", "better than", "worse than", "stronger than", "weaker than",
    "still", "actually change", "actually changed", "actually changes",
    "single total", "end up costing", "total cost on this plan",
    "what's the total cost", "what is the total cost",
    # STRUCT movement
    "swap", "reassigned", "reassignment", "reassignments", "moved", "shift",
    "in this update", "in this revision", "in this round", "before this round",
    "from the previous", "from the prior", "versus the prior", "versus the previous",
    # SCHEDULE route end
    "close out", "closes out", "done for the day", "complete its run",
    "completes its run", "wraps up", "wrap up", "ends its run", "finish window",
    "finished", "complete the run",
    # SCHEDULE lateness
    "behind schedule", "fall behind", "after their allowed time",
    "after the allowed time", "promised window", "running late",
    # full route listing
    "every route", "every vehicle", "complete route plan", "full route plan",
    "vehicle runs", "route roster", "list the complete", "all the routes",
    "full set of routes", "full set of vehicle runs",
)


def _prompt_has_any_signal(lowered: str) -> bool:
    return any(tok in lowered for tok in _ANY_SIGNAL_TOKENS)


def _should_consult_adapter(c0_intent: str, lowered: str) -> bool:
    """Decide whether the adapter should be called for this prompt.

    Conservative — return True only when:
      - C0 returned `unknown` (any signal worth a try); OR
      - C0 returned a risk-zone intent AND the prompt contains at
        least one adapter signal token.
    """
    if c0_intent == "unknown":
        return True
    if c0_intent in _C0_RISK_ZONE_INTENTS and _prompt_has_any_signal(lowered):
        return True
    return False


def _validate_adapter_frame(frame: QueryFrame) -> bool:
    """The adapter only ever emits one of the supported `Intent`
    enum values. Defensive guard in case a future change slips a
    novel string through."""
    return frame.intent in SUPPORTED_INTENTS and frame.intent != "unknown"


def decide_d1_intent(
    prompt_text: str,
    family: str,
    c0_intent: str,
) -> QueryFrame:
    """Apply the D1 routing policy.

    Returns a `QueryFrame` whose `intent` field is what the
    downstream contract should see. `source` tells the evaluation
    harness which classifier supplied the intent (c0 vs
    semantic_adapter vs fallback).
    """
    lowered = (prompt_text or "").lower()
    c0_frame = QueryFrame(
        intent=c0_intent,
        source="c0",
        confidence=1.0,
        c0_intent=c0_intent,
        overridden=False,
    )

    if not _should_consult_adapter(c0_intent, lowered):
        return c0_frame

    try:
        candidate = classify_semantic(prompt_text, family)
    except Exception as exc:  # noqa: BLE001
        c0_frame.adapter_notes.append(f"adapter_exception={exc!r} -> c0_fallback")
        return c0_frame

    if candidate is None:
        c0_frame.adapter_notes.append("adapter_no_match -> c0_fallback")
        return c0_frame

    if not _validate_adapter_frame(candidate):
        c0_frame.adapter_notes.append(
            f"adapter_invalid_intent={candidate.intent!r} -> c0_fallback"
        )
        return c0_frame

    if candidate.intent == c0_intent:
        # Confirming the C0 choice — record source as semantic_adapter
        # for telemetry but don't mark `overridden`.
        candidate.c0_intent = c0_intent
        candidate.overridden = False
        return candidate

    candidate.c0_intent = c0_intent
    candidate.overridden = True
    return candidate


__all__ = [
    "SUPPORTED_INTENTS",
    "classify_semantic",
    "decide_d1_intent",
]
