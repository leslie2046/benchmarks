export type ModelCredential = { id?: string; name: string; server_url: string; model_uid?: string | null; api_key?: string | null; copy_key_from?: string | null; has_api_key?: boolean; api_key_masked?: string | null };
export type ModelConfig = { name: string | null; alias?: string | null; benchmark: string; base_url: string | null; credentials?: ModelCredential[] };
export type ProviderIcon = "cube" | "spark" | "cloud" | "bolt" | "waves" | "database";

export type Provider = {
  dataset_id?: string | null;
  id: string;
  provider?: string;
  label: string;
  model: string | null;
  models: ModelConfig[];
  icon: ProviderIcon;
  endpoint_configured: boolean;
  credential_configured: boolean;
  credential_required: boolean;
};

export type Benchmark = {
  id: string;
  label: string;
  providers: Provider[];
  provider_kinds: Array<{ id: string; label: string }>;
};
export type Catalog = { benchmarks: Benchmark[] };
export type LlmSelection = { id: string; model: string; credential_id?: string | null };
export type SystemSettings = { default_llm: LlmSelection | null; updated_at?: string };
export type AiReport = { run_id: string; status: "none" | "generating" | "ready" | "failed"; content: string | null; error?: string | null; generated_at?: string; model?: { provider: string; model: string }; requested_model?: { provider: string; model: string } };
export type PlaygroundResult = { ok: boolean; status_code: number; duration_ms: number; data: unknown; truncated: boolean };
export type LlmParameter = { type: "integer" | "number" | "enum"; label: string; description: string; min?: number; max?: number; step?: number; default?: string | number; values: string[]; enabled_when: Record<string, string> };
export type LlmParameters = { model: string; provider: string; version: string; source?: string; model_specific: boolean; can_refresh: boolean; metadata: { context_window?: number; context_length?: number; max_output_tokens?: number; fetched_at?: string }; parameters: Record<string, LlmParameter> };

export type ServiceConfig = {
  dataset_id?: string | null;
  id: string;
  name: string;
  benchmark: string;
  provider: string;
  base_url: string | null;
  model: string | null;
  models: ModelConfig[];
  icon: ProviderIcon;
  has_api_key: boolean;
  api_key_masked?: string | null;
  endpoint_configured: boolean;
};

export type MetricSummary = {
  count: number;
  avg: number;
  p50: number;
  p95: number;
  p99: number;
  min: number;
  max: number;
};

export type Scenario = {
  id: string;
  provider: string;
  provider_name: string;
  model: string | null;
  concurrency: number;
  status: string;
  completed_requests: number;
  total_requests: number;
  started_at?: string;
  result: null | {
    success_rate: number;
    qps_success: number;
    success_count: number;
    failure_count: number;
    samples?: Array<{ completion_order?: number; ok: boolean; latency_ms: number }>;
    metrics: Record<string, MetricSummary>;
  };
  error: string | null;
};

export type Run = {
  id: string;
  plan_id: string;
  name: string;
  benchmark: string;
  status: string;
  created_at: string;
  updated_at: string;
  completed_scenarios: number;
  total_scenarios: number;
  concurrency_levels: number[];
  requests_per_scenario: number;
  query?: string | null;
  documents?: string[];
  scenarios: Scenario[];
  error: string | null;
};

export type TestPlan = {
  max_tokens?: number;
  dataset_id?: string | null;
  id: string;
  name: string;
  benchmark: string;
  providers: Array<{ id: string; model?: string | null; credential_id?: string | null }>;
  concurrency_levels: number[];
  requests_per_scenario: number;
  timeout_seconds: number;
  query?: string | null;
  documents?: string[];
  status: "active" | "paused" | "stopped" | "completed" | "error";
  start_at: string | null;
  next_run_at: string | null;
  repeat_mode: "once" | "count" | "forever";
  repeat_count: number | null;
  repeat_interval_seconds: number | null;
  run_count: number;
  schedule_run_count: number;
  last_run_id: string | null;
  last_run_at: string | null;
  schedule_error: string | null;
  created_at: string;
  updated_at: string;
};
