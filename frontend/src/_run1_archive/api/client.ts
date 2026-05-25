/**
 * Typed API client for the Stage 2 backend.
 *
 * All paths are relative (`/api/...`) so the Vite proxy forwards them to
 * the FastAPI server. No hardcoded localhost URLs.
 */
import type {
  AnswerabilityResponse,
  EvidenceResponse,
  HealthResponse,
  InstanceGeometry,
  PerturbationContext,
  ProductCopilotResponse,
  ProductMetrics,
  PromptResponse,
  RunResultsResponse,
  VisualContext,
} from '../types';

const DEFAULT_RUN_ID = 'full-run-v1';

class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body && typeof body === 'object' && 'detail' in body) {
        detail = `HTTP ${response.status}: ${String(body.detail)}`;
      }
    } catch {
      /* ignore body parse errors — the status is the signal */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/api/healthz');
}

export async function getRunResults(
  runId: string = DEFAULT_RUN_ID,
): Promise<RunResultsResponse> {
  return request<RunResultsResponse>(`/api/runs/${encodeURIComponent(runId)}/results`);
}

export async function getProductMetrics(
  runId: string = DEFAULT_RUN_ID,
): Promise<ProductMetrics> {
  return request<ProductMetrics>(
    `/api/runs/${encodeURIComponent(runId)}/product-metrics`,
  );
}

export async function getPrompt(
  promptId: string,
  runId: string = DEFAULT_RUN_ID,
): Promise<PromptResponse> {
  return request<PromptResponse>(
    `/api/prompts/${encodeURIComponent(promptId)}?run_id=${encodeURIComponent(runId)}`,
  );
}

export async function getCopilotContext(
  promptId: string,
  runId: string = DEFAULT_RUN_ID,
): Promise<ProductCopilotResponse> {
  return request<ProductCopilotResponse>(
    `/api/prompts/${encodeURIComponent(promptId)}/copilot-context?run_id=${encodeURIComponent(runId)}`,
  );
}

export async function getEvidence(
  promptId: string,
  runId: string = DEFAULT_RUN_ID,
): Promise<EvidenceResponse> {
  return request<EvidenceResponse>(
    `/api/prompts/${encodeURIComponent(promptId)}/evidence?run_id=${encodeURIComponent(runId)}`,
  );
}

export async function getAnswerability(
  promptId: string,
  runId: string = DEFAULT_RUN_ID,
): Promise<AnswerabilityResponse> {
  return request<AnswerabilityResponse>(
    `/api/prompts/${encodeURIComponent(promptId)}/answerability?run_id=${encodeURIComponent(runId)}`,
  );
}

export async function getInstanceGeometry(
  instanceId: string,
): Promise<InstanceGeometry> {
  return request<InstanceGeometry>(
    `/api/instances/${encodeURIComponent(instanceId)}/geometry`,
  );
}

export async function getVisualContext(
  promptId: string,
  runId: string = DEFAULT_RUN_ID,
): Promise<VisualContext> {
  return request<VisualContext>(
    `/api/prompts/${encodeURIComponent(promptId)}/visual-context?run_id=${encodeURIComponent(runId)}`,
  );
}

export async function getPerturbationContext(
  promptId: string,
  runId: string = DEFAULT_RUN_ID,
): Promise<PerturbationContext> {
  return request<PerturbationContext>(
    `/api/prompts/${encodeURIComponent(promptId)}/perturbation-context?run_id=${encodeURIComponent(runId)}`,
  );
}

export { ApiError, DEFAULT_RUN_ID };
