"""Pydantic schema for LLM-structured semantic intent output.

The LLM adapter must output exactly this shape. Extra fields are
rejected; forbidden operational fields (evidence, warnings, answer
text, compute decisions) are explicitly excluded from the schema so
validation catches any model drift.

This file is types-only: no I/O, no model calls, no imports from
sibling intent/refusal/evidence modules.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Allowed values (mirror contracts.py — kept here to avoid circular import)
# ---------------------------------------------------------------------------


ALLOWED_INTENTS: frozenset[str] = frozenset({
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
    # Grounded overview intents — payload-derived explanations rather than
    # exact field lookups. The deterministic contract still owns
    # answerability, evidence, warnings, and compute decisions; these
    # intents simply widen the LLM adapter's vocabulary so high-level
    # operator questions ("what is this perturbation doing?") do not
    # collapse to "unknown".
    "perturbation_summary",
    "scenario_summary",
    "solution_summary",
    "perturbation_impact_summary",
    "route_impact_summary",
    "what_to_watch",
    # A-008: evaluation intents. The contract surfaces threshold-grounded
    # judgments ("acceptable" / "needs_review" / "unacceptable") backed by
    # documented per-family thresholds (see docs/threshold_rationale.md).
    # The PV exception escalates any PV-infeasibility check to
    # "unacceptable" — see evaluation.py for the aggregation rule.
    "evaluate_plan_acceptability",
    "evaluate_dimension_acceptability",
})

# Evaluation intents — A-008.
EVALUATION_INTENTS: frozenset[str] = frozenset({
    "evaluate_plan_acceptability",
    "evaluate_dimension_acceptability",
})

# Overview/explanation intents — convenience set for downstream layers.
OVERVIEW_INTENTS: frozenset[str] = frozenset({
    "perturbation_summary",
    "scenario_summary",
    "solution_summary",
    "perturbation_impact_summary",
    "route_impact_summary",
    "what_to_watch",
})

# Overview intents that require baseline/diff for a full answer. Without
# those fields the contract still answers — partially — by describing the
# current state and saying impact cannot be quantified.
OVERVIEW_INTENTS_REQUIRING_COMPARISON: frozenset[str] = frozenset({
    "perturbation_impact_summary",
    "route_impact_summary",
})

ALLOWED_COMPARISON_TYPES: frozenset[str] = frozenset({
    "none",
    "baseline",
    "previous_solution",
    "reference_solver",
    "implicit",
    "unsupported",
})


# ---------------------------------------------------------------------------
# LLM output schema
# ---------------------------------------------------------------------------


class LLMAmbiguity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_ambiguous: bool = False
    reason: Optional[str] = None


class LLMAlternativeIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: str
    reason: str


class LLMEntities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_ids: list[int] = Field(default_factory=list)
    route_labels: list[int] = Field(default_factory=list)


class LLMSemanticFrame(BaseModel):
    """The structured output the LLM must emit — nothing more, nothing less.

    Explicitly excludes: answer_text, evidence_paths, warnings,
    missing_fields, next_actions, compute_decision, ui_actions.
    Any of those in LLM output trigger a schema-validation rejection.
    """
    model_config = ConfigDict(extra="forbid")

    intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    entities: LLMEntities = Field(default_factory=LLMEntities)
    requires_baseline: bool = False
    comparison_type: str = "none"
    causal_request: bool = False
    recompute_request: bool = False
    ambiguity: LLMAmbiguity = Field(default_factory=LLMAmbiguity)
    alternative_intents: list[LLMAlternativeIntent] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation outcome
# ---------------------------------------------------------------------------


class ValidationOutcome(str, Enum):
    accepted = "accepted"
    rejected_invalid_schema = "rejected_invalid_schema"
    rejected_invalid_enum = "rejected_invalid_enum"
    rejected_low_confidence = "rejected_low_confidence"
    rejected_ambiguous = "rejected_ambiguous"
    rejected_unsafe_semantics = "rejected_unsafe_semantics"
    fallback_to_d1 = "fallback_to_d1"
    fallback_to_unknown = "fallback_to_unknown"


# ---------------------------------------------------------------------------
# Adapter call metadata (for logging + API response)
# ---------------------------------------------------------------------------


class LLMAdapterMetadata(BaseModel):
    """Call-level bookkeeping; never contains secrets."""
    model_config = ConfigDict(extra="forbid")

    mode: str = "hybrid_guarded"
    source: str = "llm"
    accepted: bool = False
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    confidence: Optional[float] = None
    model_name: Optional[str] = None
    latency_ms: Optional[float] = None
    tokens_prompt: Optional[int] = None
    tokens_completion: Optional[int] = None
    schema_valid: bool = False
    validation_outcome: str = ValidationOutcome.fallback_to_unknown.value
    d1_intent: Optional[str] = None
    llm_intent: Optional[str] = None
    # When True, the validated LLM frame was rejected but its extracted
    # entities (customer_ids, route_labels) were retained in the returned
    # QueryFrame for downstream consumers (e.g. the aspectual-fallback
    # layer). Only set when the final d1_intent is "unknown".
    rejected_llm_entities: bool = False
    # First 3 pydantic ValidationError entries (truncated for log volume)
    # when the LLM frame fails schema validation. Each entry is
    # ``{"loc": [...], "msg": "...", "type": "..."}``. Empty otherwise.
    # Surfaced in /copilot/ask telemetry for diagnosing LLM drift.
    validation_error_details: Optional[list[dict]] = None
    # B1-guard (A-006): True when the subjunctive-pattern guard forced
    # the LLM-emitted intent back to "unknown" so D4's needs_recompute
    # affordance fires on counterfactual prompts the LLM mis-classified
    # as descriptive (e.g. "what if vehicle 3 broke down" classified as
    # perturbation_summary).
    counterfactual_guard_fired: bool = False
    # B1 ranking guard (A-006): True when the LLM picked a non-ranking
    # intent (what_to_watch / lateness_summary / etc.) for a prompt that
    # has the superlative+target ranking shape; the guard forces the
    # intent back to "unknown" so the evidence layer's ranking aspect
    # dispatcher can surface a ranked list.
    ranking_guard_fired: bool = False
    # A-008 evaluation guard: True when the LLM picked evaluate_* but the
    # prompt has explicit comparison framing ("did anything improve?",
    # "any better/worse?"); the guard redirects to before_after_comparison.
    evaluation_guard_fired: bool = False
    # A-008.5 R2 retry telemetry: True when the LLM frame failed Pydantic
    # validation on the first call and a single retry with corrective
    # feedback was issued. ``retry_success`` is True if the retry produced
    # a schema-valid frame, False if it also failed (then we fall through
    # to D1). ``retry_reason`` is the categorical class of the *original*
    # failure that triggered the retry. ``retry_latency_ms`` is the
    # additional wall-clock cost of the retry attempt (does not include
    # the original call). Disabled by env var COPILOT_DISABLE_LLM_RETRY=1
    # for the Stage 4 ablation table.
    retry_fired: bool = False
    retry_success: Optional[bool] = None
    retry_reason: Optional[str] = None
    retry_latency_ms: Optional[int] = None


__all__ = [
    "ALLOWED_COMPARISON_TYPES",
    "ALLOWED_INTENTS",
    "OVERVIEW_INTENTS",
    "OVERVIEW_INTENTS_REQUIRING_COMPARISON",
    "LLMAdapterMetadata",
    "LLMAmbiguity",
    "LLMAlternativeIntent",
    "LLMEntities",
    "LLMSemanticFrame",
    "ValidationOutcome",
]
