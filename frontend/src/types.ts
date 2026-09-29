export type Provider = {
  id: string;
  provider?: string;
  label: string;
  model: string | null;
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

export type ServiceConfig = {
  id: string;
  name: string;
  benchmark: string;
  provider: string;
  base_url: string | null;
  model: string | null;
  has_api_key: boolean;
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
  scenarios: Scenario[];
  error: string | null;
};
