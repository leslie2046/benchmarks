import type { Catalog, PlaygroundResult, Run, ServiceConfig, TestPlan } from "./types";

export type ProviderAccess = { provider: string; server_url: string; api_key?: string; config_id?: string; credential_id?: string; benchmark?: string; model?: string };
export type DiscoveredModel = { id: string; benchmark: string | null };

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.text();
    let detail = "";
    try {
      const parsed = JSON.parse(body) as { detail?: string };
      detail = parsed.detail ?? "";
    } catch { /* Non-JSON error response. */ }
    throw new Error(detail || body || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  catalog: () => request<Catalog>("/api/catalog"),
  playground: (payload: unknown) => request<PlaygroundResult>("/api/playground", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }),
  runs: () => request<Run[]>("/api/runs"),
  plans: () => request<TestPlan[]>("/api/plans"),
  createPlan: (payload: unknown) => request<TestPlan>("/api/plans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }),
  startPlan: (id: string) => request<TestPlan>(`/api/plans/${id}/start`, { method: "POST" }),
  pausePlan: (id: string) => request<TestPlan>(`/api/plans/${id}/pause`, { method: "POST" }),
  stopPlan: (id: string) => request<TestPlan>(`/api/plans/${id}/stop`, { method: "POST" }),
  deletePlan: (id: string) => request<void>(`/api/plans/${id}`, { method: "DELETE" }),
  createRun: (payload: unknown) => request<Run>("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }),
  cancelRun: (id: string) => request<Run>(`/api/runs/${id}/cancel`, { method: "POST" }),
  deleteRun: (id: string) => request<void>(`/api/runs/${id}`, { method: "DELETE" }),
  runPlan: (id: string) => request<Run>(`/api/plans/${id}/runs`, { method: "POST" }),
  serviceConfigs: () => request<ServiceConfig[]>("/api/service-configs"),
  verifyProvider: (payload: ProviderAccess) => request<{ valid: boolean }>("/api/provider-models/verify", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }),
  listProviderModels: (payload: ProviderAccess) => request<{ models: DiscoveredModel[] }>("/api/provider-models/list", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }),
  createServiceConfig: (payload: unknown) => request<ServiceConfig>("/api/service-configs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }),
  updateServiceConfig: (id: string, payload: unknown) => request<ServiceConfig>(`/api/service-configs/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }),
  deleteServiceConfig: (id: string) => request<void>(`/api/service-configs/${id}`, { method: "DELETE" }),
};

export function subscribeToRun(id: string, onRun: (run: Run) => void, onError: () => void) {
  const source = new EventSource(`/api/runs/${id}/events`);
  source.onmessage = (event) => onRun(JSON.parse(event.data) as Run);
  source.onerror = () => {
    source.close();
    onError();
  };
  return () => source.close();
}
