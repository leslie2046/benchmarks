import type { AiReport, AuthUser, Catalog, LlmParameters, LlmSelection, PlaygroundResult, Run, ServiceConfig, SystemSettings, TestPlan } from "./types";
import type { PageResult } from "./pagination";

export type ProviderAccess = { provider: string; server_url: string; api_key?: string; config_id?: string; credential_id?: string; benchmark?: string; model?: string };
export type DiscoveredModel = { id: string; benchmark: string | null };
export type ProviderBalance = { status: "available" | "unsupported" | "unconfigured" | "invalid_key" | "error"; balances: Array<{ currency: string | null; amount: string }>; checked_at?: string };

let csrfToken: string | null = null;
let workspaceId: string | null = null;

export function setWorkspaceId(value: string | null) {
  workspaceId = value;
}

export function setCsrfToken(value: string | null) {
  csrfToken = value;
}

export async function authenticatedFetch(url: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (workspaceId) headers.set("X-Workspace-Id", workspaceId);
  if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes((init?.method || "GET").toUpperCase())) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(url, { ...init, headers, credentials: "same-origin" });
  if (response.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event("prismlab:unauthorized"));
  if (response.status === 403 && typeof window !== "undefined") {
    const body = await response.clone().json().catch(() => null);
    if (body?.detail?.code === "workspace_unavailable") window.dispatchEvent(new Event("prismlab:workspaces-changed"));
  }
  return response;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(url, init);
  if (!response.ok) {
    const body = await response.text();
    let detail = "";
    try {
      const parsed = JSON.parse(body) as { detail?: string | { message?: string } };
      detail = typeof parsed.detail === "string" ? parsed.detail : parsed.detail?.message ?? "";
    } catch { /* Non-JSON error response. */ }
    throw new Error(detail || body || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function streamPlayground(payload: unknown, onDelta: (text: string, ttft: number, channel?: string) => void, signal: AbortSignal): Promise<PlaygroundResult> {
  const response = await authenticatedFetch("/api/playground/stream", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  if (!response.body) throw new Error("Streaming response is unavailable");
  const reader = response.body.getReader();
  const cancelReader = () => { void reader.cancel().catch(() => {}); };
  signal.addEventListener("abort", cancelReader, { once: true });
  if (signal.aborted) cancelReader();
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
      if (signal.aborted) throw new DOMException("Request cancelled", "AbortError");
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
    signal.removeEventListener("abort", cancelReader);
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export const api = {
  providerBalance: (configId: string, credentialId: string, signal?: AbortSignal) => request<ProviderBalance>(`/api/service-configs/${encodeURIComponent(configId)}/balance?credential_id=${encodeURIComponent(credentialId)}`, { signal }),
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
  runsPage: (page: number, size: number, signal: AbortSignal) => request<PageResult<Run>>(`/api/runs?page=${page}&page_size=${size}`, { signal }),
  plansPage: (page: number, size: number, signal: AbortSignal) => request<PageResult<TestPlan>>(`/api/plans?page=${page}&page_size=${size}`, { signal }),
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
  deleteRun: (id: string) => request<void>(`/api/runs/${id}`, { method: "DELETE" }),
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
  const scope = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
  const source = new EventSource(`/api/runs/${id}/events${scope}`);
  source.onmessage = (event) => onRun(JSON.parse(event.data) as Run);
  source.onerror = () => {
    source.close();
    onError();
  };
  return () => source.close();
}

export type WorkspaceMember = { id: string; name: string; username: string; provider: string; avatar_url?: string | null; role: "owner" | "admin" | "member" };
export const profileApi = {
  nickname: (nickname: string) => request<AuthUser>("/api/auth/profile", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nickname }) }),
  avatar: (file: File) => request<AuthUser>("/api/auth/profile/avatar", { method: "PUT", headers: { "Content-Type": file.type }, body: file }),
  removeAvatar: () => request<AuthUser>("/api/auth/profile/avatar", { method: "DELETE" }),
};
export type WorkspaceInvitation = { id: string; workspace_id: string; workspace_name: string; invited_by: string; expires_at: string };
export type SentInvitation = { id: string; username: string; provider: string; expires_at: string };
const jsonRequest = (method: string, payload: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
export const workspaceApi = {
  create: (name: string) => request<{ id: string }>("/api/workspaces", jsonRequest("POST", { name })),
  rename: (id: string, name: string) => request(`/api/workspaces/${id}`, jsonRequest("PATCH", { name })),
  members: (id: string) => request<WorkspaceMember[]>(`/api/workspaces/${id}/members`),
  invitations: () => request<WorkspaceInvitation[]>("/api/workspaces/invitations"),
  sent: (id: string) => request<SentInvitation[]>(`/api/workspaces/${id}/invitations`),
  invite: (id: string, provider: string, username: string) => request(`/api/workspaces/${id}/invitations`, jsonRequest("POST", { provider, username })),
  accept: (id: string) => request<{ workspace_id: string }>(`/api/workspaces/invitations/${id}/accept`, { method: "POST" }),
  decline: (id: string) => request(`/api/workspaces/invitations/${id}/decline`, { method: "POST" }),
  revoke: (id: string, invitation: string) => request(`/api/workspaces/${id}/invitations/${invitation}`, { method: "DELETE" }),
  role: (id: string, userId: string, role: string) => request(`/api/workspaces/${id}/members/${userId}`, jsonRequest("PATCH", { role })),
  remove: (id: string, userId: string) => request(`/api/workspaces/${id}/members/${userId}`, { method: "DELETE" }),
  leave: (id: string) => request(`/api/workspaces/${id}/leave`, { method: "POST" }),
  delete: (id: string) => request(`/api/workspaces/${id}`, { method: "DELETE" }),
};
