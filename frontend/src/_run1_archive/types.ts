/**
 * Frontend types mirroring the Stage 2 backend contract
 * (`product.copilot.contracts`, `product.api.schemas`).
 *
 * These are pragmatic — they cover the major Stage 2 response fields
 * the UI consumes, but the backend remains the source of truth.
 */

export type Intent =
  | 'objective_value'
  | 'objective_delta'
  | 'feasibility_status'
  | 'route_count'
  | 'single_customer_route_membership'
  | 'same_route_boolean'
  | 'route_end_time'
  | 'customer_arrival'
  | 'lateness_summary'
  | 'before_after_comparison'
  | 'new_customer_assignment'
  | 'refusal_or_insufficient_payload'
  | 'unknown';

export type AnswerabilityStatus =
  | 'answerable'
  | 'partially_answerable'
  | 'not_answerable';

export interface EvidenceItem {
  field_path: string;
  value: unknown;
  supports: string;
  display_label?: string | null;
}

export interface VisualAction {
  kind: string;
  target: Record<string, unknown>;
}

export interface AnswerabilityResult {
  status: AnswerabilityStatus;
  intent: Intent;
  required_fields: string[];
  available_fields: string[];
  missing_fields: string[];
  answerable_subclaims: string[];
  suggested_next_actions: string[];
}

export interface UsefulRefusal {
  refusal_reason: string;
  missing_fields: string[];
  available_subclaims: string[];
  suggested_next_actions: string[];
}

export interface MetricsFlags {
  grounded_answer_available: boolean;
  evidence_shown: boolean;
  unsupported_comparison_detected: boolean;
  route_label_ambiguity_resolved: boolean;
  useful_refusal_available: boolean;
}

export interface PromptMetadata {
  prompt_id: string;
  family: string;
  source: string;
  instance_id: string;
  perturbation_id: string;
  perturbation_family?: string | null;
  instance_class?: string | null;
  dataset?: string | null;
  quadrant?: string | null;
  sufficiency_label?: string | null;
  policy_decision?: string | null;
  action_taken: string;
  template_id?: string | null;
  prompt_text: string;
}

export interface GeneratorAnswer {
  answer_text: string;
  claimed_objective?: number | null;
  claimed_feasible?: boolean | null;
  claimed_route_count?: number | null;
  claimed_route_membership?: unknown;
  claimed_late_customers?: number[] | null;
  claimed_customer_timings?: unknown;
}

export interface ProductCopilotResponse {
  prompt_id: string;
  run_id: string;
  question: string;
  answer_text: string;
  family: string;
  source: string;
  quadrant?: string | null;
  action_taken: string;
  intent: Intent;
  answerability: AnswerabilityResult;
  evidence: EvidenceItem[];
  missing_fields: string[];
  warnings: string[];
  useful_refusal?: UsefulRefusal | null;
  suggested_next_actions: string[];
  visual_actions: VisualAction[];
  payload_augmented?: Record<string, unknown> | null;
  metrics_flags: MetricsFlags;
  warnings_loader: string[];
}

/**
 * A row from /api/runs/{run_id}/results. We type only the columns the UI
 * uses; the backend returns every column from the joined CSV.
 */
export interface RunResultRow {
  prompt_id: string;
  family: string;
  source: string;
  instance_id?: string;
  perturbation_id?: string;
  perturbation_family?: string;
  instance_class?: string;
  dataset?: string;
  quadrant?: string;
  sufficiency_label?: string;
  policy_decision?: string;
  action_taken?: string;
  faithfulness_score?: number | null;
  runner_op_validity_pass?: boolean | null;
  runner_refusal_detected?: boolean | null;
  judge_refusal_detected?: boolean | null;
  prompt_text?: string;
  answer_text?: string;
  [k: string]: unknown;
}

export interface RunResultsResponse {
  run_id: string;
  n_rows: number;
  rows: RunResultRow[];
}

/* ---------- product metrics ---------- */

export interface RateMetric {
  rate: number;
  numerator: number;
  denominator: number;
  definition?: string;
}

export interface CountMetric {
  count: number;
  prompt_ids: string[];
  definition?: string;
}

export interface ConventionConsistency {
  consistent: string[];
  inconsistent: string[];
  not_applicable: string[];
  definition?: string;
}

export interface UsefulRefusalRateBlock {
  rate: number | null;
  numerator: number;
  denominator: number;
  definition?: string;
}

export interface ProductMetrics {
  run_id: string;
  n_prompts: number;
  grounded_answer_accuracy: RateMetric;
  evidence_coverage: RateMetric;
  user_requested_unsupported_comparison_detection: CountMetric;
  volunteered_or_risky_comparison_guardrail_hits: CountMetric;
  convention_consistency: ConventionConsistency;
  route_label_ambiguity_incidents: CountMetric;
  useful_refusal_rate: UsefulRefusalRateBlock;
  route_indexing_warning_count: CountMetric;
  struct_membership_warning_count: CountMetric;
  time_to_answer_reduction: number | null;
  time_to_answer_reduction_note: string;
}

/* ---------- envelopes for prompt-scoped endpoints ---------- */

export interface PromptResponse {
  run_id: string;
  prompt_id: string;
  prompt: PromptMetadata;
  generator_answer: GeneratorAnswer;
  judge?: Record<string, unknown> | null;
  joined_row: Record<string, unknown>;
  warnings: string[];
}

export interface EvidenceResponse {
  run_id: string;
  prompt_id: string;
  intent: Intent;
  evidence: EvidenceItem[];
  visual_actions: VisualAction[];
}

export interface AnswerabilityResponse {
  run_id: string;
  prompt_id: string;
  answerability: AnswerabilityResult;
}

export interface HealthResponse {
  status: string;
}

/* ---------- visual grounding (Stage 4) ---------- */

export interface CustomerGeometry {
  customer_id: number;
  x: number;
  y: number;
  demand: number;
  service_time: number;
  tw_early: number;
  tw_late: number;
}

export interface InstanceGeometry {
  instance_id: string;
  n_customers: number;
  capacity?: number;
  n_vehicles?: number;
  depot: CustomerGeometry;
  customers: CustomerGeometry[];
  coordinate_system: string;
  notes?: string;
}

export interface RoutePolylinePoint {
  customer_id: number;
  x: number;
  y: number;
  kind: 'depot' | 'customer';
}

export interface RoutePolyline {
  route_idx: number;
  route_label?: string | null;
  display_route_number?: number | null;
  customer_ids: number[];
  points: RoutePolylinePoint[];
  n_customers: number;
}

export interface HighlightedRoute {
  route_idx: number;
  route_label?: string | null;
  display_route_number?: number | null;
}

export interface ScheduleRow {
  customer_id: number;
  route_idx?: number;
  route_label?: string | null;
  display_route_number?: number | null;
  arrival?: number | null;
  start_service?: number | null;
  end_service?: number | null;
  tw_early?: number | null;
  tw_late?: number | null;
  is_late?: boolean | null;
  lateness_minutes?: number | null;
}

export interface RouteEndTimeRow {
  route_idx: number;
  route_label?: string | null;
  display_route_number?: number | null;
  end_time?: number | null;
  has_time_warp?: boolean | null;
}

export interface PerturbationContext {
  perturbation_id: string | null;
  perturbation_family: string | null;
  summary: string;
  known_fields: Record<string, unknown>;
  missing_fields: string[];
}

export interface VisualContext {
  prompt_id: string;
  run_id: string;
  instance_id: string | null;
  perturbation_id: string | null;
  perturbation_family: string | null;
  intent: Intent;
  answerability_status: AnswerabilityStatus;
  coordinate_system: string;
  coordinate_note?: string | null;
  depot: CustomerGeometry | null;
  customers: CustomerGeometry[];
  n_customers: number;
  routes: RoutePolyline[];
  highlighted_customers: number[];
  highlighted_routes: HighlightedRoute[];
  schedule: ScheduleRow[];
  route_end_times: RouteEndTimeRow[];
  visual_actions: VisualAction[];
  perturbation_context: PerturbationContext;
  warnings: string[];
  limitations: string[];
  geometry_error: string | null;
}
