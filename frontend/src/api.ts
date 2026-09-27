import type { Decision, Incident, IncidentSummary, Memory, Runbook, Strategy } from "./types";

interface Envelope<T> {
  data: T;
  meta: Record<string, unknown>;
  error: { message: string } | null;
}

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  const body = (await response.json().catch(() => null)) as Envelope<T> | null;
  if (!response.ok || !body) {
    throw new ApiError(body?.error?.message ?? `HTTP ${response.status}`);
  }
  return body.data;
}

export interface DecisionPayload {
  decision: Decision;
  operator: string;
  comment?: string;
  runbook_id?: string;
  params?: Record<string, unknown>;
}

export const api = {
  incidents: () => request<IncidentSummary[]>("/v1/incidents?limit=50"),
  incident: (id: string) => request<Incident>(`/v1/incidents/${encodeURIComponent(id)}`),
  decide: (id: string, payload: DecisionPayload) =>
    request<unknown>(`/v1/incidents/${encodeURIComponent(id)}/decisions`, { method: "POST", body: JSON.stringify(payload) }),
  trigger: () => request<{ id: string }>("/v1/incidents", { method: "POST", body: JSON.stringify({ title: "Manual investigation" }) }),
  runbooks: () => request<Runbook[]>("/v1/runbooks"),
  strategies: () => request<Strategy[]>("/v1/strategies"),
  memories: (query: string) => request<Memory[]>(`/v1/memories?query=${encodeURIComponent(query)}`),
};
