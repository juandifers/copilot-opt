"""Product-copilot response contract.

Pydantic models for every shape the dashboard receives. Behavior lives in
sibling modules:

    product.copilot.intent            — text → intent string
    product.copilot.refusal_policy    — warnings + useful refusals
    product.copilot.response_builder  — orchestrator
    product.data.answerability        — intent + payload → AnswerabilityResult
    product.data.evidence             — intent + payload → evidence items
    product.data.product_schema       — payload augmentation (route labels)
    product.data.metrics              — run-level replay metrics

This file is types-only — no I/O, no logic, no imports from sibling
behavior modules. Pydantic is used as a general validation library, not
a FastAPI dependency.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums / discriminators
# ---------------------------------------------------------------------------

Intent = Literal[
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
    # exact field lookups. Answerability depends on what the payload supports
    # (descriptive vs. impact/change).
    "perturbation_summary",
    "scenario_summary",
    "solution_summary",
    "perturbation_impact_summary",
    "route_impact_summary",
    "what_to_watch",
]

AnswerabilityStatus = Literal["answerable", "partially_answerable", "not_answerable"]


# ---------------------------------------------------------------------------
# Sub-shapes
# ---------------------------------------------------------------------------


class PromptMetadata(BaseModel):
    prompt_id: str
    family: str
    source: str
    instance_id: str
    perturbation_id: str
    perturbation_family: Optional[str] = None
    instance_class: Optional[str] = None
    dataset: Optional[str] = None
    quadrant: Optional[str] = None
    sufficiency_label: Optional[str] = None
    policy_decision: Optional[str] = None
    action_taken: str
    template_id: Optional[str] = None
    prompt_text: str


class ClaimedRouteMembership(BaseModel):
    model_config = ConfigDict(extra="ignore")
    route_idx: int
    customer_ids: list[int]


class ClaimedCustomerTiming(BaseModel):
    model_config = ConfigDict(extra="ignore")
    customer_id: int
    stated_arrival_or_start: float


class GeneratorAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answer_text: str
    claimed_objective: Optional[float] = None
    claimed_feasible: Optional[bool] = None
    claimed_route_count: Optional[int] = None
    claimed_route_membership: Optional[list[ClaimedRouteMembership]] = None
    claimed_late_customers: Optional[list[int]] = None
    claimed_customer_timings: Optional[list[ClaimedCustomerTiming]] = None


class EvidenceItem(BaseModel):
    """One field-grounded fact pulled from the (augmented) payload.

    `field_path` is a display string; it may include predicate-style
    qualifiers (e.g. ``routes[route_idx=4].customer_ids``) that are NOT
    standard JSON paths — they communicate which item the value came from."""

    field_path: str
    value: Any = None
    supports: str
    display_label: Optional[str] = None


class VisualAction(BaseModel):
    """Hint to the frontend about what to highlight or render."""

    kind: str
    target: dict = Field(default_factory=dict)


class AnswerabilityResult(BaseModel):
    status: AnswerabilityStatus
    intent: Intent
    required_fields: list[str] = Field(default_factory=list)
    available_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    answerable_subclaims: list[str] = Field(default_factory=list)
    suggested_next_actions: list[str] = Field(default_factory=list)


class UsefulRefusal(BaseModel):
    refusal_reason: str
    missing_fields: list[str] = Field(default_factory=list)
    available_subclaims: list[str] = Field(default_factory=list)
    suggested_next_actions: list[str] = Field(default_factory=list)


class MetricsFlags(BaseModel):
    grounded_answer_available: bool = False
    evidence_shown: bool = False
    unsupported_comparison_detected: bool = False
    route_label_ambiguity_resolved: bool = False
    useful_refusal_available: bool = False


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------


class ProductCopilotResponse(BaseModel):
    """Shape returned by GET /prompts/{prompt_id}/copilot-context."""

    prompt_id: str
    run_id: str
    question: str
    answer_text: str
    family: str
    source: str
    quadrant: Optional[str] = None
    action_taken: str
    intent: Intent
    answerability: AnswerabilityResult
    evidence: list[EvidenceItem] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    useful_refusal: Optional[UsefulRefusal] = None
    suggested_next_actions: list[str] = Field(default_factory=list)
    visual_actions: list[VisualAction] = Field(default_factory=list)
    payload_augmented: Optional[dict] = None
    metrics_flags: MetricsFlags = Field(default_factory=MetricsFlags)
    warnings_loader: list[str] = Field(default_factory=list)
