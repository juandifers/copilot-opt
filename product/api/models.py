"""Pydantic request/response models for the dashboard API.

The shapes here are deliberately permissive: payload availability
varies across scenarios, and the API surfaces ``null`` for anything
the underlying artifacts do not carry.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


class ApiErrorBody(BaseModel):
    code: str
    message: str
    detail: dict = Field(default_factory=dict)


class ApiError(BaseModel):
    error: ApiErrorBody


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok"]
    run2_contract_base_commit: str
    run2_contract_base_tag: str
    current_git_commit: Optional[str] = None
    available_systems: list[str]
    default_system: str


# ---------------------------------------------------------------------------
# /instances
# ---------------------------------------------------------------------------


class InstanceSummary(BaseModel):
    instance_id: str
    family: str
    n_customers: Optional[int] = None
    available_perturbations: list[str] = Field(default_factory=list)


class InstancesResponse(BaseModel):
    instances: list[InstanceSummary]


# ---------------------------------------------------------------------------
# /scenarios/{instance_id}/{perturbation_id}
# ---------------------------------------------------------------------------


class CustomerGeometry(BaseModel):
    customer_id: int
    x: float
    y: float
    demand: int
    time_window_start: float
    time_window_end: float
    service_time: float


class Depot(BaseModel):
    x: float
    y: float


class InstanceBlock(BaseModel):
    depot: Depot
    customers: list[CustomerGeometry] = Field(default_factory=list)
    vehicle_capacity: Optional[int] = None


class Route(BaseModel):
    route_idx: int
    route_label: str
    customer_ids: list[int] = Field(default_factory=list)
    load: Optional[int] = None
    capacity: Optional[int] = None
    distance: Optional[float] = None
    end_time: Optional[float] = None


class CustomerScheduleRow(BaseModel):
    customer_id: int
    route_idx: int
    route_label: str
    position_in_route: int
    arrival: Optional[float] = None
    service_start: Optional[float] = None
    service_end: Optional[float] = None
    time_window_start: Optional[float] = None
    time_window_end: Optional[float] = None
    is_late: bool = False
    lateness_minutes: float = 0.0
    waiting_minutes: Optional[float] = None


class SolutionBlock(BaseModel):
    feasible: Optional[bool] = None
    objective: Optional[float] = None
    n_routes: Optional[int] = None
    routes: Optional[list[Route]] = None
    customer_schedule: Optional[list[CustomerScheduleRow]] = None


class AvailableFields(BaseModel):
    solution: bool = False
    routes: bool = False
    customer_schedule: bool = False
    route_end_times: bool = False
    baseline_solution: bool = False
    diff: bool = False
    objective_delta: bool = False
    causal_diagnostics: bool = False


class ScenarioResponse(BaseModel):
    scenario_id: str
    instance_id: str
    perturbation_id: str
    perturbation_summary: str
    instance: Optional[InstanceBlock] = None
    solution: Optional[SolutionBlock] = None
    baseline_solution: Optional[dict] = None
    diff: Optional[dict] = None
    available_fields: AvailableFields


# ---------------------------------------------------------------------------
# /copilot/ask
# ---------------------------------------------------------------------------


class CopilotAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    prompt: str
    system: Optional[str] = None
    family: Optional[str] = None


class DisplayAnchor(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str


class EvidenceItem(BaseModel):
    field_path: str
    value: Any = None
    display_anchor: DisplayAnchor


class AnswerabilityBlock(BaseModel):
    status: str
    missing_fields: list[str] = Field(default_factory=list)


class ComputeDecisionBlock(BaseModel):
    """D4 compute-decision enrichment.

    Mirrors ``product.evaluation.system_d4.ComputeDecision``. Kept as a
    standalone API model so the dashboard pydantic surface does not
    depend on the evaluation harness package.
    """

    mode: str
    requires_recompute: bool
    recommended_action: str
    query_family: str
    reason: str
    confidence: float
    required_fields: list[str] = Field(default_factory=list)
    available_fields: list[str] = Field(default_factory=list)
    missing_for_full_answer: list[str] = Field(default_factory=list)
    expected_runtime_seconds: Optional[float] = None
    policy_source: str


class UiAction(BaseModel):
    """D5 frontend-facing action affordance.

    Emitted by ``/copilot/ask`` when D4's ``compute_decision`` says the
    payload is insufficient and a recomputation is required. The
    ``endpoint`` + ``method`` pair is what the frontend should POST to
    after the operator clicks the affordance — ``/copilot/ask`` never
    runs a solver itself.
    """

    model_config = ConfigDict(extra="allow")

    type: str
    label: str
    action: str
    enabled: bool = True
    requires_confirmation: bool = True
    endpoint: str
    method: Literal["POST"] = "POST"
    reason: str = ""
    expected_runtime_seconds: Optional[float] = None


class AdapterEntities(BaseModel):
    """LLM-extracted entities surfaced on the API response.

    Populated whenever the LLM frame's entity extraction is consumed —
    either because the frame was accepted (validated path) or because the
    frame was rejected but its entities were retained for the aspectual
    fallback layer (``rejected_llm_entities=True``).
    """

    model_config = ConfigDict(extra="allow")

    customer_ids: list[int] = []
    route_labels: list[str] = []


class SemanticAdapterMetadata(BaseModel):
    """D-Final semantic adapter call metadata.

    Emitted only when system == "d_final". Null for all other systems.
    Never contains API keys or raw model chain-of-thought.
    """

    model_config = ConfigDict(extra="allow")

    mode: str
    source: str
    accepted: bool
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    confidence: Optional[float] = None
    model_name: Optional[str] = None
    latency_ms: Optional[float] = None
    schema_valid: Optional[bool] = None
    validation_outcome: Optional[str] = None
    d1_intent: Optional[str] = None
    llm_intent: Optional[str] = None
    rejected_llm_entities: bool = False
    entities: Optional[AdapterEntities] = None


class CopilotAskResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    system: str
    scenario_id: str
    intent: str
    answerability: AnswerabilityBlock
    behavior_class: str
    answer_text: Optional[str] = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    useful_refusal: Optional[dict] = None
    suggested_next_actions: list[str] = Field(default_factory=list)
    # D4-only enrichment. Null for c0/d1/d2/d3 responses; pre-D4
    # clients can ignore the unknown key.
    compute_decision: Optional[ComputeDecisionBlock] = None
    # D5: list of structured frontend affordances. Always present;
    # empty list when no action is recommended. The only currently
    # emitted action is ``type == "recompute"``.
    ui_actions: list[UiAction] = Field(default_factory=list)
    # D-Final: semantic adapter metadata. Null for all other systems.
    semantic_adapter: Optional[SemanticAdapterMetadata] = None


# ---------------------------------------------------------------------------
# /diff
# ---------------------------------------------------------------------------


class CustomerChange(BaseModel):
    model_config = ConfigDict(extra="allow")
    customer_id: int


class RouteChange(BaseModel):
    model_config = ConfigDict(extra="allow")
    route_idx: int


class DiffResponse(BaseModel):
    scenario_id: str
    objective_delta_absolute: Optional[float] = None
    objective_delta_percent: Optional[float] = None
    feasibility_changed: Optional[bool] = None
    customer_changes: list[dict] = Field(default_factory=list)
    route_changes: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# D5 — /scenarios/{scenario_id}/recompute
# ---------------------------------------------------------------------------


class RecomputePerturbation(BaseModel):
    """Optional perturbation descriptor on a recompute request.

    Permissive by design: validation happens in
    ``recompute_service._validate_perturbation`` so we can surface a
    structured ``invalid_perturbation`` error.
    """

    model_config = ConfigDict(extra="allow")

    type: str


class RecomputeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    requested_action: str
    perturbation: Optional[dict] = None
    confirm: bool = False


class RecomputeSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    feasible: Optional[bool] = None
    objective: Optional[float] = None
    n_routes: Optional[int] = None
    n_late_customers: Optional[int] = None


class RecomputeNextAction(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    scenario_id: str
    label: str


class RecomputeArtifacts(BaseModel):
    scenario_path: str
    payload_path: str


class RecomputeResponseModel(BaseModel):
    """Success response from ``/scenarios/{scenario_id}/recompute``."""

    status: Literal["completed"]
    source_scenario_id: str
    new_scenario_id: str
    action_used: str
    runtime_seconds: float
    summary: RecomputeSummary
    artifacts: RecomputeArtifacts
    next_actions: list[RecomputeNextAction] = Field(default_factory=list)


__all__ = [
    "AnswerabilityBlock",
    "ApiError",
    "ApiErrorBody",
    "AvailableFields",
    "ComputeDecisionBlock",
    "CopilotAskRequest",
    "CopilotAskResponse",
    "CustomerChange",
    "CustomerGeometry",
    "CustomerScheduleRow",
    "Depot",
    "DiffResponse",
    "DisplayAnchor",
    "EvidenceItem",
    "HealthResponse",
    "InstanceBlock",
    "InstanceSummary",
    "InstancesResponse",
    "RecomputeArtifacts",
    "RecomputeNextAction",
    "RecomputePerturbation",
    "RecomputeRequest",
    "RecomputeResponseModel",
    "RecomputeSummary",
    "Route",
    "RouteChange",
    "ScenarioResponse",
    "SemanticAdapterMetadata",
    "SolutionBlock",
    "UiAction",
]
