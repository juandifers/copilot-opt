"""LLM-based semantic intent adapter for System D-Final.

The LLM maps a natural-language prompt to a structured query frame.
It does NOT:
  - answer the user;
  - decide answerability, evidence, warnings, missing fields, refusal;
  - decide compute/recompute actions;
  - run or select solvers.

All of those remain owned by the deterministic contract pipeline
(D2/D3/D4/D5).

Three adapter modes are exposed:

  llm_only       — LLM maps prompt → frame, then contract runs.
                   For evaluation only; no D1 fallback.
  llm_fallback   — Try D1 first; call LLM only if D1 returns
                   unknown or a risk-zone intent.
  hybrid_guarded — Run D1 and LLM; accept the safer frame per
                   deterministic guard rules.
                   Recommended for d_final production path.

Confidence thresholds:
  >= 0.80 : accept if no ambiguity
  0.60–0.80: accept only if D1 agrees or D1 is unknown
  < 0.60  : reject / fallback

Local validation rejects LLM output if:
  - JSON/schema invalid
  - intent not in enum
  - confidence below threshold
  - ambiguous without safe clarification path
  - output contains forbidden operational fields
  - entity fields malformed
  - comparison flags contradict selected intent
  - recompute_request=True (semantic flag only; D4 still owns compute_decision)
  - causal_request=True with non-causal-flagged intent
  - any downstream contract field appears in output
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Optional

from pydantic import ValidationError

from product.copilot.llm_query_frame import (
    ALLOWED_COMPARISON_TYPES,
    ALLOWED_INTENTS,
    LLMAdapterMetadata,
    LLMSemanticFrame,
    ValidationOutcome,
)
from product.copilot.query_frame import (
    AmbiguitySignal,
    ComparisonType,
    QueryFrame,
    QueryFrameEntities,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


_LLM_MODEL = "gpt-5.4-mini"

_CONFIDENCE_ACCEPT = 0.80
_CONFIDENCE_CONDITIONAL = 0.60

# Comparison types that require baseline availability
_BASELINE_COMPARISON_TYPES: frozenset[str] = frozenset({
    "baseline",
    "previous_solution",
    "reference_solver",
    "implicit",
})

# Intent values where requires_baseline=True is semantically coherent
_BASELINE_COMPATIBLE_INTENTS: frozenset[str] = frozenset({
    "objective_delta",
    "before_after_comparison",
    # Overview impact intents implicitly need a baseline to quantify
    # change. The contract still answers partially when baseline/diff
    # is missing; this flag just tells the LLM that asking for one is
    # semantically coherent.
    "perturbation_impact_summary",
    "route_impact_summary",
})

# Intents that are coherent with causal_request=True
_CAUSAL_COMPATIBLE_INTENTS: frozenset[str] = frozenset({
    "feasibility_status",
    "lateness_summary",
    "before_after_comparison",
    "objective_delta",
    "route_end_time",
    "customer_arrival",
    # Overview impact intents can carry a causal framing ("why is the
    # objective worse?"). The downstream D3 causal warning still
    # decides whether the payload supports an actual mechanism claim.
    "perturbation_impact_summary",
    "route_impact_summary",
})

# Risk-zone C0/D1 intents where LLM override is worth consulting
_RISK_ZONE_INTENTS: frozenset[str] = frozenset({
    "objective_value",
    "objective_delta",
    "single_customer_route_membership",
    "unknown",
})

# The system prompt sent to the LLM — tells it exactly what to do and
# what not to do. Includes the exact output format to prevent field naming drift.
_SYSTEM_PROMPT = """\
You are a semantic intent parser for a VRPTW operations copilot.
Your job is NOT to answer the user.
Return ONLY a JSON object matching this EXACT format — no extra fields, no missing fields:

{
  "intent": "<one intent from the allowed list, or 'unknown'>",
  "confidence": <float 0.0–1.0>,
  "entities": {
    "customer_ids": [<integers>],
    "route_labels": [<integers>]
  },
  "requires_baseline": <true|false>,
  "comparison_type": "<none|baseline|previous_solution|reference_solver|implicit|unsupported>",
  "causal_request": <true|false>,
  "recompute_request": <true|false>,
  "ambiguity": {
    "is_ambiguous": <true|false>,
    "reason": <null or "string">
  },
  "alternative_intents": []
}

Rules:
- intent: choose exactly one from the allowed list, or "unknown"
- confidence: your certainty 0.0–1.0
- entities.customer_ids: integer customer IDs mentioned (empty list if none)
- entities.route_labels: integer route numbers mentioned (empty list if none)
- requires_baseline: true if prompt asks about before/after, previous plan, comparison, changed routes, moved customers, improvement
- comparison_type: set when requires_baseline=true; otherwise "none"
- causal_request: true only if prompt asks WHY something happened
- recompute_request: true if prompt asks to optimize, improve, re-solve, repair, reroute
- ambiguity.is_ambiguous: true only if intent is genuinely unclear between two alternatives

DO NOT emit: answer_text, evidence_paths, warnings, missing_fields, next_actions, compute_decision, ui_actions.
DO NOT answer the user's question.
DO NOT decide answerability.

Overview intents:
- perturbation_summary: "What is this perturbation doing?", "What kind of perturbation is this?"
- scenario_summary: "What am I looking at?", "Summarize this scenario.", "Give me the overview."
- solution_summary: "Summarize the current solution.", "How does the plan look?", "What's the status of the plan?"
- perturbation_impact_summary: "How is this perturbation affecting the solution?", "Did this make things worse?", "How did it affect the objective?"
- route_impact_summary: "How is this perturbation affecting routes?", "Which routes changed?", "Which routes are most affected?"
- what_to_watch: "What should I pay attention to?", "Anything concerning here?", "Where should I look first?"

For overview intents, set requires_baseline=False unless the prompt explicitly asks about change/impact compared to a baseline. perturbation_impact_summary and route_impact_summary should set requires_baseline=True when the prompt asks about change/impact.

Evaluation intents (A-008):
- evaluate_plan_acceptability: general "Is this plan acceptable?", "Should I be worried?", "Is this OK?", "Can I live with this outcome?", "Did we do well absorbing this?", "Is this a good outcome?"
- evaluate_dimension_acceptability: dimension-specific "Is the lateness reasonable?", "Is the cost change acceptable?", "Are we still feasible enough?", "Is the structural change within bounds?"

For evaluation intents, set requires_baseline=False (the verdict is computed against documented thresholds, not against a baseline). The contract layer runs the actual threshold checks; the LLM's job is only to recognize that the prompt is asking for a judgment, not a value.

DO NOT use evaluation intents for comparison-shaped prompts. These belong to before_after_comparison / objective_delta / perturbation_impact_summary, not evaluation:
- "Did anything improve?" → before_after_comparison (asks what changed)
- "Did things get worse?" → before_after_comparison
- "What got better/worse?" → before_after_comparison
- "How did this affect X?" → perturbation_impact_summary
- "How much did the cost change?" → objective_delta

Evaluation queries ask for a verdict against an implicit standard ("acceptable", "good enough"), not a comparison against the baseline.
"""


def _build_user_message(
    prompt: str,
    available_fields: Optional[dict] = None,
) -> str:
    allowed = sorted(ALLOWED_INTENTS)
    payload = {
        "prompt": prompt,
        "allowed_intents": allowed,
        "intent_descriptions": {
            "objective_value": "What is the total cost / distance?",
            "objective_delta": "How did the cost / distance change vs a baseline?",
            "feasibility_status": "Is the plan feasible? Can we keep using it?",
            "route_count": "How many routes / vehicles are used?",
            "single_customer_route_membership": "Which route does customer X belong to?",
            "same_route_boolean": "Are customers X and Y on the same route?",
            "route_end_time": "When does vehicle/route N finish / return to depot?",
            "customer_arrival": "When does the driver arrive at customer X?",
            "lateness_summary": "Which customers receive late deliveries?",
            "before_after_comparison": "How did routes / assignments change vs before?",
            "new_customer_assignment": "Which route was the new customer assigned to?",
            "full_route_listing": "List all customers assigned to each route.",
            "refusal_or_insufficient_payload": "Payload is insufficient to answer.",
            "unknown": "No supported intent fits the prompt.",
            "perturbation_summary": "What is this perturbation doing? What does this stress?",
            "scenario_summary": "What am I looking at overall? Summarize this scenario.",
            "solution_summary": "Summarize the current solution. How does the plan look?",
            "perturbation_impact_summary": "How is this perturbation affecting the solution? Did it make things worse?",
            "route_impact_summary": "How is this perturbation affecting routes? Which routes changed?",
            "what_to_watch": "What should I pay attention to? Anything concerning here?",
            "evaluate_plan_acceptability": "Is this plan acceptable / OK / good enough / something to worry about? Asks for a judgment, not a value.",
            "evaluate_dimension_acceptability": "Is the lateness / cost / feasibility / structure acceptable? Dimension-scoped judgment.",
        },
        "available_fields": available_fields or {
            "routes": True,
            "customer_schedule": True,
            "route_end_times": True,
            "baseline_solution": False,
            "diff": False,
            "causal_diagnostics": False,
        },
    }
    return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Local validation
# ---------------------------------------------------------------------------


def validate_llm_frame(
    frame: LLMSemanticFrame,
    d1_intent: str,
    mode: str = "hybrid_guarded",
) -> tuple[ValidationOutcome, Optional[str]]:
    """Validate parsed LLM output against semantic guard rules.

    Returns (outcome, rejection_reason). outcome == accepted means the
    frame is safe to use; any other outcome triggers a fallback.
    """
    # 1. Intent must be in enum
    if frame.intent not in ALLOWED_INTENTS:
        return ValidationOutcome.rejected_invalid_enum, f"intent {frame.intent!r} not in enum"

    # 2. comparison_type must be in enum
    if frame.comparison_type not in ALLOWED_COMPARISON_TYPES:
        return (
            ValidationOutcome.rejected_invalid_enum,
            f"comparison_type {frame.comparison_type!r} not in enum",
        )

    # 3. Confidence gate
    if frame.confidence < _CONFIDENCE_CONDITIONAL:
        return ValidationOutcome.rejected_low_confidence, f"confidence {frame.confidence:.2f} < {_CONFIDENCE_CONDITIONAL}"

    if frame.confidence < _CONFIDENCE_ACCEPT:
        # Conditional: accept only if D1 agrees or D1 is unknown
        if d1_intent != "unknown" and d1_intent != frame.intent:
            return (
                ValidationOutcome.rejected_low_confidence,
                f"confidence {frame.confidence:.2f} in conditional zone and D1 disagrees ({d1_intent!r} != {frame.intent!r})",
            )

    # 4. Ambiguity without safe path → reject
    if frame.ambiguity.is_ambiguous:
        return ValidationOutcome.rejected_ambiguous, f"LLM marked ambiguous: {frame.ambiguity.reason}"

    # 5. requires_baseline contradicts intent
    if frame.requires_baseline and frame.intent not in _BASELINE_COMPATIBLE_INTENTS:
        # Warn but don't reject — the downstream contract handles this via
        # comparison_referent_ambiguity. Downgrade comparison_type to none.
        pass  # non-fatal

    # 6. causal_request=True with intent not in compatible set → unsafe
    if frame.causal_request and frame.intent not in _CAUSAL_COMPATIBLE_INTENTS:
        return (
            ValidationOutcome.rejected_unsafe_semantics,
            f"causal_request=True incompatible with intent {frame.intent!r}",
        )

    # 7. Entity sanity
    for cid in frame.entities.customer_ids:
        if not isinstance(cid, int) or cid < 0:
            return (
                ValidationOutcome.rejected_unsafe_semantics,
                f"malformed customer_id: {cid!r}",
            )
    for rl in frame.entities.route_labels:
        if not isinstance(rl, int) or rl < 0:
            return (
                ValidationOutcome.rejected_unsafe_semantics,
                f"malformed route_label: {rl!r}",
            )

    return ValidationOutcome.accepted, None


def _frame_with_retained_llm_entities(
    fallback_frame: QueryFrame,
    llm_frame: LLMSemanticFrame,
    note: str,
) -> QueryFrame:
    """Return a copy of ``fallback_frame`` carrying the LLM-extracted
    entities (customer_ids, route_labels) when the LLM frame is rejected
    but the downstream layer (aspectual fallback) can still use what the
    LLM saw. Only call this when the fallback frame's intent is "unknown"
    so we don't conflate D1's intent with the LLM's entity extraction.
    """
    cust = [int(c) for c in (llm_frame.entities.customer_ids or [])]
    routes = [str(r) for r in (llm_frame.entities.route_labels or [])]
    if not cust and not routes:
        return fallback_frame
    return QueryFrame(
        intent=fallback_frame.intent,
        source=fallback_frame.source,
        confidence=fallback_frame.confidence,
        entities=QueryFrameEntities(customer_ids=cust, route_labels=routes),
        requires_baseline=fallback_frame.requires_baseline,
        comparison_type=fallback_frame.comparison_type,
        ambiguity=fallback_frame.ambiguity,
        adapter_notes=list(fallback_frame.adapter_notes) + [note],
        c0_intent=fallback_frame.c0_intent,
        overridden=fallback_frame.overridden,
        model_name=fallback_frame.model_name,
    )


def _llm_frame_to_query_frame(
    frame: LLMSemanticFrame,
    model_name: str,
    d1_intent: str,
) -> QueryFrame:
    """Convert a validated LLMSemanticFrame to the canonical QueryFrame."""
    ct = frame.comparison_type
    if ct not in ("none", "baseline", "previous_solution", "reference_solver", "implicit"):
        ct = "none"

    return QueryFrame(
        intent=frame.intent,
        source="llm_adapter",
        confidence=frame.confidence,
        entities=QueryFrameEntities(
            customer_ids=list(frame.entities.customer_ids),
            route_labels=[str(r) for r in frame.entities.route_labels],
        ),
        requires_baseline=frame.requires_baseline,
        comparison_type=ct,  # type: ignore[arg-type]
        ambiguity=AmbiguitySignal(
            is_ambiguous=frame.ambiguity.is_ambiguous,
            reason=frame.ambiguity.reason,
        ),
        adapter_notes=[
            f"llm_confidence={frame.confidence:.2f}",
            f"d1_intent={d1_intent!r}",
            f"model={model_name}",
            *(
                [f"causal_request=True"]
                if frame.causal_request
                else []
            ),
            *(
                [f"recompute_request=True"]
                if frame.recompute_request
                else []
            ),
        ],
        c0_intent=d1_intent,
        overridden=(frame.intent != d1_intent),
        model_name=model_name,
    )


# ---------------------------------------------------------------------------
# LLM output normalizer
# ---------------------------------------------------------------------------


def _normalize_llm_raw(raw: dict) -> dict:
    """Reshape common LLM output variants into the canonical schema.

    Handles three known drift patterns:
    1. customer_ids / route_labels at top level → wrap in entities dict
    2. flags dict → flatten to top level
    3. Missing confidence → default 0.80
    4. Missing alternative_intents → default []
    5. ambiguity without reason key → add reason=null
    """
    out = dict(raw)

    # 1. Hoist entities fields if flat
    entities = out.get("entities")
    if not isinstance(entities, dict):
        entities = {}
    if "customer_ids" in out and "customer_ids" not in entities:
        entities.setdefault("customer_ids", out.pop("customer_ids", []))
    else:
        out.pop("customer_ids", None)
    if "route_labels" in out and "route_labels" not in entities:
        entities.setdefault("route_labels", out.pop("route_labels", []))
    else:
        out.pop("route_labels", None)
    entities.setdefault("customer_ids", [])
    entities.setdefault("route_labels", [])
    out["entities"] = entities

    # 2. Flatten a nested "flags" dict if present
    flags = out.pop("flags", None)
    if isinstance(flags, dict):
        for k in ("requires_baseline", "comparison_type", "causal_request", "recompute_request"):
            if k in flags and k not in out:
                out[k] = flags[k]

    # 3. Default missing scalar fields
    out.setdefault("confidence", 0.80)
    out.setdefault("requires_baseline", False)
    out.setdefault("comparison_type", "none")
    out.setdefault("causal_request", False)
    out.setdefault("recompute_request", False)
    out.setdefault("alternative_intents", [])

    # 3b. Coerce bare-string alternative_intents into LLMAlternativeIntent
    # shape. Observed via telemetry 2026-05-26: gpt-5.4-mini frequently
    # emits ``alternative_intents: ["objective_value", "route_count"]``
    # rather than the schema-required ``[{"intent": ..., "reason": ...}]``.
    # We coerce defensively rather than tightening the prompt — the
    # contract validation still happens downstream.
    alts = out.get("alternative_intents")
    if isinstance(alts, list):
        coerced: list = []
        for entry in alts:
            if isinstance(entry, str):
                coerced.append({"intent": entry, "reason": ""})
            elif isinstance(entry, dict):
                coerced.append(entry)
            # else: drop silently (validation would have flagged it anyway)
        out["alternative_intents"] = coerced

    # 4. Normalize ambiguity block
    ambiguity = out.get("ambiguity")
    if not isinstance(ambiguity, dict):
        ambiguity = {"is_ambiguous": False, "reason": None}
    ambiguity.setdefault("is_ambiguous", False)
    ambiguity.setdefault("reason", None)
    out["ambiguity"] = ambiguity

    return out


# ---------------------------------------------------------------------------
# A-008.5 R2 — LLM self-correction retry on Pydantic ValidationError
# ---------------------------------------------------------------------------
#
# Stage 0/A-002 telemetry noted that the gpt-5.4-mini emitter occasionally
# drifts from the LLMSemanticFrame contract (extra keys, wrong types,
# missing required fields). The Stage-3 corpus retains a small residual
# rate of schema-validation failures even after the _normalize_llm_raw
# defensive coercion. R2 issues a single retry with feedback referencing
# the offending fields; the recovered frame still flows through every
# semantic guard (counterfactual, ranking, evaluation) before acceptance.
#
# Scope: retry fires ONLY on Pydantic ValidationError after _normalize_llm_raw.
# Other failure classes (low confidence, ambiguous, guard-fired) are by
# design and never trigger a retry. JSON-decode errors are out of scope
# for this initial implementation — they typically indicate a deeper
# model malfunction that one extra round-trip will not fix.

_RETRY_DISABLE_ENV = "COPILOT_DISABLE_LLM_RETRY"


def _retry_enabled() -> bool:
    """Return True iff the LLM retry-on-validation-error path is active."""
    val = os.environ.get(_RETRY_DISABLE_ENV, "").strip().lower()
    return val not in ("1", "true", "yes", "on")


def _classify_validation_error(exc: ValidationError) -> str:
    """Map a Pydantic ValidationError into a coarse retry_reason category.

    Categories are used for telemetry / morning-summary bucketing only.
    Pydantic v2 type tags this classifier recognises:
      - ``missing`` / ``*_required`` → missing_required_field
      - ``*_parsing`` / ``*_type`` (bool_type/int_type/etc.) → wrong_type
      - ``extra_forbidden``, ``value_error``, range checks → schema_validation_error
    """
    try:
        errors = exc.errors()
    except Exception:  # noqa: BLE001 — pydantic version safety
        return "schema_validation_error"
    if not errors:
        return "schema_validation_error"
    types = {str(e.get("type", "")) for e in errors}
    if any(t == "missing" or t.endswith("_required") for t in types):
        return "missing_required_field"
    if any(
        t.endswith("_parsing")
        or t.endswith("_type")
        or t.startswith("type_error")
        for t in types
    ):
        return "wrong_type"
    return "schema_validation_error"


def _build_retry_feedback(
    original_user_message: str,
    previous_raw_response: str,
    validation_error: ValidationError,
) -> list[dict]:
    """Build the messages list for the corrective retry round-trip.

    Includes the original user message verbatim (so the model has the full
    parser-task context), the previous failed JSON response, and per-error
    correction instructions derived from the Pydantic error structure.
    """
    try:
        errors = validation_error.errors()
    except Exception:  # noqa: BLE001 — pydantic version safety
        errors = []
    instruction_lines: list[str] = []
    for err in errors[:5]:  # cap at 5 to keep retry prompt tight
        loc_path = ".".join(str(p) for p in err.get("loc", ()) if p != "__root__")
        msg = str(err.get("msg", "")).strip()
        etype = str(err.get("type", "")).strip()
        if etype == "missing" or etype.endswith("_required"):
            instruction_lines.append(
                f"- include the required field: '{loc_path or 'root'}'"
            )
        elif "extra_forbidden" in etype:
            instruction_lines.append(
                f"- remove the unexpected field: '{loc_path or 'root'}' "
                "(the schema rejects extra keys)"
            )
        elif etype:
            instruction_lines.append(
                f"- field '{loc_path or 'root'}' is invalid: {msg} (error: {etype})"
            )
        else:
            instruction_lines.append(
                f"- field '{loc_path or 'root'}' is invalid: {msg}"
            )
    if not instruction_lines:
        instruction_lines.append(
            "- the previous JSON did not validate against the LLMSemanticFrame schema"
        )
    correction_block = "\n".join(instruction_lines)

    retry_text = (
        "Your previous JSON response failed schema validation. "
        "Return ONLY a corrected JSON object matching the LLMSemanticFrame "
        "schema described in the system prompt — no other text, no "
        "explanations, no markdown fences.\n\n"
        f"Previous response:\n{previous_raw_response}\n\n"
        f"Validation issues to fix:\n{correction_block}\n\n"
        "Return the corrected JSON now."
    )

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": original_user_message},
        {"role": "assistant", "content": previous_raw_response or ""},
        {"role": "user", "content": retry_text},
    ]


def _retry_with_feedback(
    client: Any,
    model: str,
    original_user_message: str,
    previous_raw_response: str,
    validation_error: ValidationError,
) -> tuple[Optional[LLMSemanticFrame], Optional[ValidationError], Optional[str]]:
    """Issue ONE corrective retry round-trip to the LLM.

    Returns ``(frame_or_none, retry_validation_error_or_none, call_error_or_none)``.
    ``frame_or_none`` is set when the retry produced a schema-valid frame.
    ``retry_validation_error_or_none`` is set when the retry response also
    failed Pydantic validation. ``call_error_or_none`` is set when the
    underlying OpenAI client returned an error or the JSON could not be
    decoded.
    """
    from product.evaluation.model_clients.openai_client import (
        call_openai_contract_model,
    )

    messages = _build_retry_feedback(
        original_user_message, previous_raw_response, validation_error
    )
    try:
        result = call_openai_contract_model(
            client=client,
            model=model,
            messages=messages,
            temperature=0.0,
            max_output_tokens=512,
            response_format_json_object=True,
            max_retries=1,
        )
    except Exception as exc:  # noqa: BLE001 — defensive
        return None, None, f"retry_call_exception: {type(exc).__name__}: {exc}"

    if result.error:
        return None, None, f"retry_call_error: {result.error}"

    try:
        raw = json.loads(result.raw_response_text)
    except json.JSONDecodeError as exc:
        return None, None, f"retry_json_decode_error: {exc}"

    raw = _normalize_llm_raw(raw)

    try:
        frame = LLMSemanticFrame.model_validate(raw)
        return frame, None, None
    except ValidationError as exc:
        return None, exc, None


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


def _call_llm(
    client: Any,
    prompt: str,
    available_fields: Optional[dict] = None,
    model: str = _LLM_MODEL,
) -> tuple[Optional[LLMSemanticFrame], LLMAdapterMetadata]:
    """Call the LLM and parse structured output.

    Returns (frame_or_None, metadata). Parses and validates JSON;
    does NOT apply semantic guardrails (that is validate_llm_frame's job).
    """
    from product.evaluation.model_clients.openai_client import (
        call_openai_contract_model,
    )

    meta = LLMAdapterMetadata(
        mode="hybrid_guarded",
        source="llm",
        model_name=model,
    )

    user_message = _build_user_message(prompt, available_fields)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    t0 = time.monotonic()
    result = call_openai_contract_model(
        client=client,
        model=model,
        messages=messages,
        temperature=0.0,
        max_output_tokens=512,
        response_format_json_object=True,
        max_retries=1,
    )
    meta.latency_ms = (time.monotonic() - t0) * 1000
    meta.tokens_prompt = result.prompt_tokens
    meta.tokens_completion = result.completion_tokens

    if result.error:
        meta.validation_outcome = ValidationOutcome.rejected_invalid_schema.value
        meta.fallback_used = True
        meta.fallback_reason = f"llm_call_error: {result.error}"
        return None, meta

    # Parse JSON
    try:
        raw = json.loads(result.raw_response_text)
    except json.JSONDecodeError as exc:
        meta.validation_outcome = ValidationOutcome.rejected_invalid_schema.value
        meta.fallback_used = True
        meta.fallback_reason = f"json_decode_error: {exc}"
        return None, meta

    # Normalize common LLM output shape variations before Pydantic validation.
    # Models occasionally place customer_ids/route_labels at the top level
    # or wrap flags in a nested dict despite explicit schema instructions.
    raw = _normalize_llm_raw(raw)
    raw_response_text = result.raw_response_text or ""

    # Schema validation via Pydantic
    try:
        frame = LLMSemanticFrame.model_validate(raw)
        meta.schema_valid = True
    except ValidationError as exc:
        meta.schema_valid = False
        try:
            errs = exc.errors()
        except Exception:  # noqa: BLE001 — pydantic version safety
            errs = []
        meta.validation_error_details = [
            {
                "loc": list(e.get("loc", ())),
                "msg": str(e.get("msg", "")),
                "type": str(e.get("type", "")),
            }
            for e in errs[:3]
        ]

        # A-008.5 R2: attempt a single corrective retry with feedback.
        # The recovered frame still flows through every semantic guard
        # below, so guard interactions remain identical to a first-try
        # validated frame.
        if _retry_enabled():
            meta.retry_fired = True
            meta.retry_reason = _classify_validation_error(exc)
            t_retry = time.monotonic()
            retry_frame, retry_exc, call_err = _retry_with_feedback(
                client=client,
                model=model,
                original_user_message=user_message,
                previous_raw_response=raw_response_text,
                validation_error=exc,
            )
            meta.retry_latency_ms = int((time.monotonic() - t_retry) * 1000)
            if retry_frame is not None:
                meta.retry_success = True
                meta.schema_valid = True
                frame = retry_frame
                # Fall through to semantic guards below — DO NOT return here.
            else:
                meta.retry_success = False
                meta.validation_outcome = (
                    ValidationOutcome.rejected_invalid_schema.value
                )
                meta.fallback_used = True
                if call_err is not None:
                    meta.fallback_reason = call_err
                else:
                    err_count = (
                        retry_exc.error_count() if retry_exc is not None else "?"
                    )
                    meta.fallback_reason = (
                        f"schema_validation_error_after_retry: {err_count} error(s)"
                    )
                return None, meta
        else:
            meta.validation_outcome = (
                ValidationOutcome.rejected_invalid_schema.value
            )
            meta.fallback_used = True
            meta.fallback_reason = (
                f"schema_validation_error: {exc.error_count()} error(s)"
            )
            return None, meta

    meta.llm_intent = frame.intent
    meta.confidence = frame.confidence

    # A-008 evaluation guard: redirect mis-classified comparison prompts
    # ("Did anything improve?") back to before_after_comparison so the
    # comparison renderer runs instead of the evaluation verdict.
    guarded_frame_e, fired_e = _apply_evaluation_guard(prompt, frame)
    if fired_e:
        meta.evaluation_guard_fired = True
        meta.llm_intent = guarded_frame_e.intent
        frame = guarded_frame_e

    # B1-guard (A-006): force counterfactual prompts to intent="unknown"
    # so D4's needs_recompute affordance fires instead of confabulating a
    # descriptive answer. Runs after validation; never rejects.
    guarded_frame, fired = _apply_counterfactual_guard(prompt, frame)
    if fired:
        meta.counterfactual_guard_fired = True
        meta.llm_intent = guarded_frame.intent
        frame = guarded_frame

    # B1 ranking guard (A-006): force ranking-shaped prompts to
    # intent="unknown" so the evidence layer's ranking aspect dispatcher
    # fires instead of the LLM picking what_to_watch / lateness_summary
    # for "top 3 customers by lateness" etc.
    guarded_frame_r, fired_r = _apply_ranking_guard(prompt, frame)
    if fired_r:
        meta.ranking_guard_fired = True
        meta.llm_intent = guarded_frame_r.intent
        return guarded_frame_r, meta

    return frame, meta


# ---------------------------------------------------------------------------
# B1-guard (A-006) — counterfactual subjunctive guard
# ---------------------------------------------------------------------------
#
# Phase A §5 observed that LLM-on regresses counterfactual handling by
# re-classifying "what if vehicle 3 broke down" as perturbation_summary
# describing the *current* perturbation — bypassing D4's correct
# needs_recompute affordance. This guard fires on subjunctive prompt
# patterns and forces the LLM-returned frame's intent back to "unknown"
# so the downstream contract surfaces the recompute affordance instead
# of confabulating a descriptive answer.
#
# The guard runs only when the LLM frame would otherwise be accepted;
# it never affects D1-source frames.

_SUBJUNCTIVE_PATTERNS = re.compile(
    r"\b(what\s+if|"
    r"would\s+happen\s+if|"
    r"if\s+\w+\s+(?:was|were|broke|breaks|wasn'?t|weren'?t|hadn'?t|didn'?t)|"
    r"suppose|imagine|pretend|assuming|hypothetically)\b",
    re.IGNORECASE,
)


def _is_counterfactual(prompt: str) -> bool:
    return bool(prompt) and _SUBJUNCTIVE_PATTERNS.search(prompt) is not None


# Ranking-prompt detection mirrors the deterministic D1 detector in
# `product.copilot.intent`. Kept here so the LLM-side guard does not
# require an upstream import (intent.py imports the LLM adapter via the
# d_final path, so the inverse would create a cycle).
_RANKING_SUP_RE = re.compile(
    r"\b(worst|best|most|least|biggest|smallest|longest|shortest|"
    r"tightest|widest|heaviest|lightest|top|bottom|rank(?:ing)?|"
    r"closest|furthest|farthest|fastest|slowest|highest|lowest)\b",
    re.IGNORECASE,
)
_RANKING_TGT_RE = re.compile(
    r"\b(routes?|customers?|vehicles?|deliver(?:y|ies)|stops?|drivers?|"
    r"problems?|issues?|things?|items?|points?|risks?)\b",
    re.IGNORECASE,
)


def _is_ranking_prompt(prompt: str) -> bool:
    if not prompt:
        return False
    return (
        _RANKING_SUP_RE.search(prompt) is not None
        and _RANKING_TGT_RE.search(prompt) is not None
    )


def _apply_ranking_guard(
    prompt: str,
    llm_frame: Optional[LLMSemanticFrame],
) -> tuple[Optional[LLMSemanticFrame], bool]:
    """Force ranking-shaped prompts back to ``intent='unknown'``.

    Mirrors `_apply_counterfactual_guard`. Activates when the prompt has
    a superlative + target combination and the LLM-returned intent is
    anything other than ``unknown`` — typically the LLM picks
    ``what_to_watch`` or ``lateness_summary`` for prompts like "top 3
    customers by lateness", which preempts the deterministic ranking
    aspect dispatcher. The guard routes the prompt back to ``unknown``
    so the evidence layer's ``derive_ranking_spec`` + aspectual ranking
    branch can surface a ranked list.
    """
    if llm_frame is None:
        return llm_frame, False
    if not _is_ranking_prompt(prompt):
        return llm_frame, False
    if (getattr(llm_frame, "intent", None) or "unknown") == "unknown":
        return llm_frame, False
    try:
        guarded = llm_frame.model_copy(
            update={"intent": "unknown", "alternative_intents": []}
        )
    except Exception:  # pragma: no cover — defensive
        return llm_frame, False
    return guarded, True


# A-008: evaluation-guard. The LLM occasionally classifies
# comparison-shaped prompts ("Did anything improve?", "Did things get
# worse?") as evaluate_plan_acceptability because the verb implies a
# judgment. The deterministic guard re-routes such prompts to
# before_after_comparison so the comparison renderer runs.
_COMPARISON_REDIRECT_TOKENS = re.compile(
    r"\b(improve(?:d|ment)?|improving|got\s+(?:better|worse)|"
    r"any(?:thing)?\s+(?:better|worse|different|change)|"
    r"differs?|changed|change\s+from|delta|"
    r"versus|vs\.?|compared\s+to|against\s+baseline)\b",
    re.IGNORECASE,
)


def _apply_evaluation_guard(
    prompt: str,
    llm_frame: Optional[LLMSemanticFrame],
) -> tuple[Optional[LLMSemanticFrame], bool]:
    """Redirect LLM-emitted evaluation intent to comparison when the
    prompt has explicit comparison framing ("did anything improve",
    "got better/worse", etc.).
    """
    if llm_frame is None:
        return llm_frame, False
    intent = getattr(llm_frame, "intent", None) or ""
    if not intent.startswith("evaluate_"):
        return llm_frame, False
    if not _COMPARISON_REDIRECT_TOKENS.search(prompt or ""):
        return llm_frame, False
    try:
        guarded = llm_frame.model_copy(
            update={
                "intent": "before_after_comparison",
                "requires_baseline": True,
                "alternative_intents": [],
            }
        )
    except Exception:  # pragma: no cover — defensive
        return llm_frame, False
    return guarded, True


def _apply_counterfactual_guard(
    prompt: str,
    llm_frame: Optional[LLMSemanticFrame],
) -> tuple[Optional[LLMSemanticFrame], bool]:
    """Force counterfactual prompts back to ``intent='unknown'``.

    Returns ``(frame, guard_fired)``. When the prompt has a subjunctive
    pattern and the LLM frame's intent is anything other than ``unknown``,
    the frame is shallow-copied with ``intent='unknown'`` and the
    ``alternative_intents`` list emptied so downstream consumers can't
    re-promote the rejected intent. ``guard_fired`` is True in that case.
    """
    if llm_frame is None:
        return llm_frame, False
    if not _is_counterfactual(prompt):
        return llm_frame, False
    if (getattr(llm_frame, "intent", None) or "unknown") == "unknown":
        return llm_frame, False
    try:
        guarded = llm_frame.model_copy(
            update={"intent": "unknown", "alternative_intents": []}
        )
    except Exception:  # pragma: no cover — defensive
        return llm_frame, False
    return guarded, True


# ---------------------------------------------------------------------------
# Adapter modes
# ---------------------------------------------------------------------------


def infer_intent_llm_only(
    prompt: str,
    family: str,
    client: Any,
    available_fields: Optional[dict] = None,
    model: str = _LLM_MODEL,
) -> tuple[QueryFrame, LLMAdapterMetadata]:
    """LLM-only mode: no D1 involvement.

    For evaluation only; not the default product path.
    """
    from product.copilot.intent import infer_intent
    # Get C0 as the fallback baseline (not D1)
    c0_intent = infer_intent(prompt_text=prompt, family=family)

    frame, meta = _call_llm(client, prompt, available_fields, model)
    meta.d1_intent = c0_intent
    meta.mode = "llm_only"

    if frame is None:
        meta.validation_outcome = ValidationOutcome.fallback_to_unknown.value
        return (
            QueryFrame(intent="unknown", source="fallback", confidence=0.0,
                       adapter_notes=["llm_only_call_failed"], c0_intent=c0_intent),
            meta,
        )

    outcome, reason = validate_llm_frame(frame, d1_intent=c0_intent, mode="llm_only")
    meta.validation_outcome = outcome.value

    if outcome == ValidationOutcome.accepted:
        meta.accepted = True
        meta.llm_intent = frame.intent
        return _llm_frame_to_query_frame(frame, meta.model_name or model, c0_intent), meta

    meta.fallback_used = True
    meta.fallback_reason = reason
    fallback_frame = QueryFrame(
        intent=c0_intent or "unknown",
        source="fallback",
        confidence=0.5,
        adapter_notes=[f"llm_only_rejected: {reason}"],
        c0_intent=c0_intent,
    )
    if fallback_frame.intent == "unknown":
        retained = _frame_with_retained_llm_entities(
            fallback_frame, frame, "retained_llm_entities_for_aspect_fallback"
        )
        if retained is not fallback_frame:
            meta.rejected_llm_entities = True
            return retained, meta
    return fallback_frame, meta


def infer_intent_llm_fallback(
    prompt: str,
    family: str,
    client: Any,
    available_fields: Optional[dict] = None,
    model: str = _LLM_MODEL,
) -> tuple[QueryFrame, LLMAdapterMetadata]:
    """LLM-fallback mode: use D1 first; call LLM only on unknown/risk-zone."""
    from product.copilot.intent import infer_intent_d1_frame

    d1_frame = infer_intent_d1_frame(prompt_text=prompt, family=family)
    d1_intent = d1_frame.intent
    meta = LLMAdapterMetadata(mode="llm_fallback", source="d1", d1_intent=d1_intent)

    # If D1 is confident and not in risk zone, keep it
    if d1_intent not in _RISK_ZONE_INTENTS:
        meta.accepted = True
        meta.source = "d1"
        meta.validation_outcome = ValidationOutcome.accepted.value
        meta.confidence = d1_frame.confidence
        return d1_frame, meta

    # Call LLM to help
    llm_frame, llm_meta = _call_llm(client, prompt, available_fields, model)
    meta.model_name = llm_meta.model_name
    meta.latency_ms = llm_meta.latency_ms
    meta.tokens_prompt = llm_meta.tokens_prompt
    meta.tokens_completion = llm_meta.tokens_completion
    meta.schema_valid = llm_meta.schema_valid
    meta.llm_intent = llm_meta.llm_intent
    meta.validation_error_details = llm_meta.validation_error_details
    meta.counterfactual_guard_fired = llm_meta.counterfactual_guard_fired
    meta.ranking_guard_fired = llm_meta.ranking_guard_fired
    meta.evaluation_guard_fired = llm_meta.evaluation_guard_fired
    meta.retry_fired = llm_meta.retry_fired
    meta.retry_success = llm_meta.retry_success
    meta.retry_reason = llm_meta.retry_reason
    meta.retry_latency_ms = llm_meta.retry_latency_ms

    if llm_frame is None:
        meta.fallback_used = True
        meta.fallback_reason = llm_meta.fallback_reason
        meta.validation_outcome = ValidationOutcome.fallback_to_d1.value
        return d1_frame, meta

    outcome, reason = validate_llm_frame(llm_frame, d1_intent=d1_intent, mode="llm_fallback")
    meta.validation_outcome = outcome.value

    if outcome == ValidationOutcome.accepted:
        meta.accepted = True
        meta.source = "llm"
        meta.confidence = llm_frame.confidence
        return _llm_frame_to_query_frame(llm_frame, meta.model_name or model, d1_intent), meta

    # LLM rejected — keep D1, optionally retaining LLM-extracted entities
    # when D1 itself returned "unknown" (the aspectual-fallback layer can
    # use them downstream).
    meta.fallback_used = True
    meta.fallback_reason = reason
    meta.validation_outcome = ValidationOutcome.fallback_to_d1.value
    if d1_intent == "unknown":
        retained = _frame_with_retained_llm_entities(
            d1_frame, llm_frame, "retained_llm_entities_for_aspect_fallback"
        )
        if retained is not d1_frame:
            meta.rejected_llm_entities = True
            return retained, meta
    return d1_frame, meta


def infer_intent_hybrid_guarded(
    prompt: str,
    family: str,
    client: Any,
    available_fields: Optional[dict] = None,
    model: str = _LLM_MODEL,
) -> tuple[QueryFrame, LLMAdapterMetadata]:
    """Hybrid-guarded mode: run D1 and LLM, accept the safer frame.

    Policy:
    1. D1 confident + not in risk zone → keep D1 (no LLM call).
    2. D1 unknown → call LLM; accept if valid.
    3. D1 in risk zone with comparison/movement/causal language → prefer
       whichever frame preserves those semantic flags.
    4. LLM invalid/low-confidence → fall back to D1 or unknown.
    """
    from product.copilot.intent import infer_intent_d1_frame

    d1_frame = infer_intent_d1_frame(prompt_text=prompt, family=family)
    d1_intent = d1_frame.intent
    meta = LLMAdapterMetadata(mode="hybrid_guarded", source="d1", d1_intent=d1_intent)

    # 1. D1 confident and not in risk zone
    if d1_intent not in _RISK_ZONE_INTENTS:
        meta.accepted = True
        meta.source = "d1"
        meta.validation_outcome = ValidationOutcome.accepted.value
        meta.confidence = d1_frame.confidence
        return d1_frame, meta

    # 2. Consult LLM
    llm_frame, llm_meta = _call_llm(client, prompt, available_fields, model)
    meta.model_name = llm_meta.model_name
    meta.latency_ms = llm_meta.latency_ms
    meta.tokens_prompt = llm_meta.tokens_prompt
    meta.tokens_completion = llm_meta.tokens_completion
    meta.schema_valid = llm_meta.schema_valid
    meta.llm_intent = llm_meta.llm_intent
    meta.validation_error_details = llm_meta.validation_error_details
    meta.counterfactual_guard_fired = llm_meta.counterfactual_guard_fired
    meta.ranking_guard_fired = llm_meta.ranking_guard_fired
    meta.evaluation_guard_fired = llm_meta.evaluation_guard_fired
    meta.retry_fired = llm_meta.retry_fired
    meta.retry_success = llm_meta.retry_success
    meta.retry_reason = llm_meta.retry_reason
    meta.retry_latency_ms = llm_meta.retry_latency_ms

    if llm_frame is None:
        # LLM call failed — keep D1
        meta.fallback_used = True
        meta.fallback_reason = llm_meta.fallback_reason
        meta.validation_outcome = ValidationOutcome.fallback_to_d1.value
        return d1_frame, meta

    outcome, reason = validate_llm_frame(llm_frame, d1_intent=d1_intent, mode="hybrid_guarded")
    meta.validation_outcome = outcome.value

    if outcome != ValidationOutcome.accepted:
        meta.fallback_used = True
        meta.fallback_reason = reason
        if d1_intent == "unknown":
            retained = _frame_with_retained_llm_entities(
                d1_frame, llm_frame, "retained_llm_entities_for_aspect_fallback"
            )
            if retained is not d1_frame:
                meta.rejected_llm_entities = True
                return retained, meta
        return d1_frame, meta

    # 3. Both valid — prefer frame that preserves semantic flags
    llm_qf = _llm_frame_to_query_frame(llm_frame, meta.model_name or model, d1_intent)

    # If LLM flagged comparison/baseline need and D1 did not, prefer LLM
    if llm_frame.requires_baseline and not d1_frame.requires_baseline:
        meta.accepted = True
        meta.source = "llm"
        meta.confidence = llm_frame.confidence
        return llm_qf, meta

    # If D1 is unknown and LLM is not, prefer LLM
    if d1_intent == "unknown" and llm_frame.intent != "unknown":
        meta.accepted = True
        meta.source = "llm"
        meta.confidence = llm_frame.confidence
        return llm_qf, meta

    # Otherwise, if they agree, prefer D1 (deterministic preference)
    if d1_intent == llm_frame.intent:
        meta.accepted = True
        meta.source = "d1"
        meta.confidence = d1_frame.confidence
        return d1_frame, meta

    # Disagreement: prefer LLM when high-confidence
    if llm_frame.confidence >= _CONFIDENCE_ACCEPT:
        meta.accepted = True
        meta.source = "llm"
        meta.confidence = llm_frame.confidence
        return llm_qf, meta

    # Default: keep D1
    meta.fallback_used = True
    meta.fallback_reason = f"llm_disagrees_with_d1_but_low_confidence ({llm_frame.confidence:.2f})"
    meta.validation_outcome = ValidationOutcome.fallback_to_d1.value
    return d1_frame, meta


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------


def infer_intent_d_final_frame(
    prompt: str,
    family: str,
    client: Any,
    mode: str = "hybrid_guarded",
    available_fields: Optional[dict] = None,
    model: str = _LLM_MODEL,
) -> tuple[QueryFrame, LLMAdapterMetadata]:
    """Dispatch to the requested adapter mode and return (frame, metadata).

    Parameters
    ----------
    client:
        OpenAI client constructed by
        `product.evaluation.model_clients.openai_client.load_openai_client()`.
        Pass ``None`` to skip the LLM call and fall back to D1 deterministically.
    mode:
        "hybrid_guarded" | "llm_only" | "llm_fallback"
    """
    if client is None:
        # No LLM client available — fall back to D1 deterministically.
        from product.copilot.intent import infer_intent_d1_frame
        d1_frame = infer_intent_d1_frame(prompt_text=prompt, family=family)
        meta = LLMAdapterMetadata(
            mode=mode,
            source="d1",
            accepted=True,
            fallback_used=True,
            fallback_reason="no_llm_client",
            confidence=d1_frame.confidence,
            validation_outcome=ValidationOutcome.fallback_to_d1.value,
            d1_intent=d1_frame.intent,
        )
        return d1_frame, meta

    if mode == "llm_only":
        return infer_intent_llm_only(prompt, family, client, available_fields, model)
    if mode == "llm_fallback":
        return infer_intent_llm_fallback(prompt, family, client, available_fields, model)
    # default: hybrid_guarded
    return infer_intent_hybrid_guarded(prompt, family, client, available_fields, model)


__all__ = [
    "infer_intent_d_final_frame",
    "infer_intent_hybrid_guarded",
    "infer_intent_llm_fallback",
    "infer_intent_llm_only",
    "validate_llm_frame",
]
