// Types mirroring product/api/models.py. Permissive on optional fields.

export interface ApiErrorBody {
  code: string;
  message: string;
  detail?: Record<string, unknown>;
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody;
}

export class ApiError extends Error {
  status: number;
  body: ApiErrorBody;
  constructor(status: number, body: ApiErrorBody) {
    super(`${body.code}: ${body.message}`);
    this.status = status;
    this.body = body;
  }
}

export interface HealthResponse {
  status: 'ok';
  run2_contract_base_commit: string;
  run2_contract_base_tag: string;
  current_git_commit: string | null;
  available_systems: string[];
  default_system: string;
}

export interface InstanceSummary {
  instance_id: string;
  family: string;
  n_customers: number | null;
  available_perturbations: string[];
}

export interface InstancesResponse {
  instances: InstanceSummary[];
}

export interface CustomerGeometry {
  customer_id: number;
  x: number;
  y: number;
  demand: number;
  time_window_start: number;
  time_window_end: number;
  service_time: number;
}

export interface Depot {
  x: number;
  y: number;
}

export interface InstanceBlock {
  depot: Depot;
  customers: CustomerGeometry[];
  vehicle_capacity: number | null;
}

export interface Route {
  route_idx: number;
  route_label: string;
  customer_ids: number[];
  load: number | null;
  capacity: number | null;
  distance: number | null;
  end_time: number | null;
}

export interface CustomerScheduleRow {
  customer_id: number;
  route_idx: number;
  route_label: string;
  position_in_route: number;
  arrival: number | null;
  service_start: number | null;
  service_end: number | null;
  time_window_start: number | null;
  time_window_end: number | null;
  is_late: boolean;
  lateness_minutes: number;
  waiting_minutes: number | null;
}

export interface SolutionBlock {
  feasible: boolean | null;
  objective: number | null;
  n_routes: number | null;
  routes: Route[] | null;
  customer_schedule: CustomerScheduleRow[] | null;
}

export interface AvailableFields {
  solution: boolean;
  routes: boolean;
  customer_schedule: boolean;
  route_end_times: boolean;
  baseline_solution: boolean;
  diff: boolean;
  objective_delta: boolean;
  causal_diagnostics: boolean;
}

export interface ScenarioResponse {
  scenario_id: string;
  instance_id: string;
  perturbation_id: string;
  perturbation_summary: string;
  instance: InstanceBlock | null;
  solution: SolutionBlock | null;
  baseline_solution: Record<string, unknown> | null;
  diff: Record<string, unknown> | null;
  available_fields: AvailableFields;
}

export interface DisplayAnchor {
  type: string;
  [key: string]: unknown;
}

export interface EvidenceItem {
  field_path: string;
  value: unknown;
  display_anchor: DisplayAnchor;
}

export interface AnswerabilityBlock {
  status: string;
  missing_fields: string[];
}

export interface ComputeDecisionBlock {
  mode: string;
  requires_recompute: boolean;
  recommended_action: string;
  query_family: string;
  reason: string;
  confidence: number;
  required_fields: string[];
  available_fields: string[];
  missing_for_full_answer: string[];
  expected_runtime_seconds: number | null;
  policy_source: string;
}

export interface CopilotAskRequest {
  scenario_id: string;
  prompt: string;
  system?: string;
  family?: string;
}

export interface AspectualDispatchBlock {
  triggered: boolean;
  intent_at_dispatch: string;
  family: string;
  aspect: string;
  entities_resolved: {
    customer_ids: number[];
    route_labels: string[];
  };
  field_paths_surfaced: string[];
}

export interface VisualAction {
  kind: string;
  target: Record<string, unknown>;
}

export interface CopilotAskResponse {
  system: string;
  scenario_id: string;
  intent: string;
  answerability: AnswerabilityBlock;
  behavior_class: string;
  answer_text: string | null;
  evidence: EvidenceItem[];
  warnings: string[];
  useful_refusal: Record<string, unknown> | null;
  suggested_next_actions: string[];
  compute_decision: ComputeDecisionBlock | null;
  aspectual_dispatch?: AspectualDispatchBlock | null;
  // Highlight contract: (intent, evidence) -> deterministic UI hints.
  // Optional for back-compat with pre-fix backends; empty list on refusal.
  visual_actions?: VisualAction[];
}

export interface DiffResponse {
  scenario_id: string;
  objective_delta_absolute: number | null;
  objective_delta_percent: number | null;
  feasibility_changed: boolean | null;
  customer_changes: Record<string, unknown>[];
  route_changes: Record<string, unknown>[];
}
