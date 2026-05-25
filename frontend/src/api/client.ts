// Thin fetch wrapper around the FastAPI dashboard backend.
// Dev: Vite proxy maps /api/* -> http://localhost:8000 (see vite.config.ts).

import {
  ApiError,
  type ApiErrorEnvelope,
  type CopilotAskRequest,
  type CopilotAskResponse,
  type DiffResponse,
  type HealthResponse,
  type InstancesResponse,
  type ScenarioResponse,
} from './types';

export { ApiError };

const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let body: ApiErrorEnvelope | null = null;
    try {
      body = (await res.json()) as ApiErrorEnvelope;
    } catch {
      // body not JSON
    }
    if (body && body.error) {
      throw new ApiError(res.status, body.error);
    }
    throw new ApiError(res.status, {
      code: 'http_' + res.status,
      message: res.statusText || 'Request failed',
    });
  }
  return (await res.json()) as T;
}

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export function fetchInstances(): Promise<InstancesResponse> {
  return request<InstancesResponse>('/instances');
}

export function fetchScenario(
  instanceId: string,
  perturbationId: string,
): Promise<ScenarioResponse> {
  const i = encodeURIComponent(instanceId);
  const p = encodeURIComponent(perturbationId);
  return request<ScenarioResponse>(`/scenarios/${i}/${p}`);
}

export function fetchDiff(
  instanceId: string,
  perturbationId: string,
): Promise<DiffResponse> {
  const i = encodeURIComponent(instanceId);
  const p = encodeURIComponent(perturbationId);
  return request<DiffResponse>(`/scenarios/${i}/${p}/diff`, { method: 'POST' });
}

export function fetchCopilotAsk(
  body: CopilotAskRequest,
): Promise<CopilotAskResponse> {
  return request<CopilotAskResponse>('/copilot/ask', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
