import type { Catalog, PlaygroundResult, Run, ServiceConfig } from "./types";

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
  createRun: (payload: unknown) => request<Run>("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }),
  cancelRun: (id: string) => request<Run>(`/api/runs/${id}/cancel`, { method: "POST" }),
  deleteRun: (id: string) => request<void>(`/api/runs/${id}`, { method: "DELETE" }),
  runPlan: (id: string) => request<Run>(`/api/plans/${id}/runs`, { method: "POST" }),
  serviceConfigs: () => request<ServiceConfig[]>("/api/service-configs"),
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
