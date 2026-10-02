import type { AiReport, Catalog, LlmParameters, LlmSelection, PlaygroundResult, Run, ServiceConfig, SystemSettings, TestPlan } from "./types";

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

export async function streamPlayground(payload: unknown, onDelta: (text: string, ttft: number, channel?: string) => void, signal: AbortSignal): Promise<PlaygroundResult> {
  const response = await fetch("/api/playground/stream", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  if (!response.body) throw new Error("Streaming response is unavailable");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: PlaygroundResult | null = null;
  function consume(line: string) {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === "error") throw new Error(event.message);
    if (event.type === "delta") onDelta(event.content, event.ttft_ms, event.channel);
    if (event.type === "result") result = event.result;
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let newline: number;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        consume(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);
      }
      if (done) break;
    }
    consume(buffer);
    if (!result) throw new Error("LLM stream ended before completion");
    return result;
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export const api = {
  llmParameters: (selection: LlmSelection, refresh = false) => request<LlmParameters>(`/api/llm/parameters?refresh=${refresh}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(selection) }),
  systemSettings: () => request<SystemSettings>("/api/system-settings"),
  saveSystemSettings: (payload: SystemSettings) => request<SystemSettings>("/api/system-settings", {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }),
  aiReport: (id: string) => request<AiReport>(`/api/runs/${id}/ai-report`),
  generateAiReport: (id: string, regenerate: boolean, language: string) => request<AiReport>(`/api/runs/${id}/ai-report`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ regenerate, language }),
  }),
  catalog: () => request<Catalog>("/api/catalog"),
  playground: (payload: unknown) => request<PlaygroundResult>("/api/playground", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }),
  runs: () => request<Run[]>("/api/runs"),
  plans: () => request<TestPlan[]>("/api/plans"),
  updatePlan: (id: string, payload: unknown) => request<TestPlan>(`/api/plans/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }),
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
  difyNames: (payload: ProviderAccess & { page?: number; dataset_id?: string }) => request<{ names: { id: string; name: string }[]; has_more: boolean; page: number }>("/api/dify/names", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }),
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
