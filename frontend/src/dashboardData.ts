import type { Run, Scenario } from "./types";
import { llmMetricKey } from "./llmMetrics";

export type DashboardMetric = "p50" | "p95" | "p99" | "qps" | "error" | "ttft" | "tpot" | "tokens_per_second";
export function modelKey(scenario: Scenario) { return JSON.stringify([scenario.provider, scenario.provider_name, scenario.model]); }
export function modelLabel(scenario: Scenario) { return `${scenario.provider_name || scenario.provider}${scenario.model ? ` · ${scenario.model}` : ""}`; }
export function metricValue(scenario: Scenario, metric: DashboardMetric): number | null {
  const result = scenario.result;
  if (!result) return null;
  const total = result.success_count + result.failure_count;
  const value = metric === "error" ? (total ? result.failure_count / total * 100 : null)
    : !result.success_count ? null
    : metric === "qps" ? result.qps_success
    : metric === "ttft" || metric === "tpot" || metric === "tokens_per_second" ? result.metrics[llmMetricKey(metric)]?.avg
    : result.metrics.latency_ms?.[metric];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
export function validTrendRuns(runs: Run[], concurrency: number | undefined, metric: DashboardMetric) {
  return runs.filter((run) => run.scenarios.some((scenario) => (concurrency === undefined || scenario.concurrency === concurrency) && metricValue(scenario, metric) !== null));
}
export function trendSeries(runs: Run[], concurrency: number | undefined, metric: DashboardMetric) {
  const scenarios = runs.flatMap((run) => run.scenarios).filter((scenario) => concurrency === undefined || scenario.concurrency === concurrency);
  const models = [...new Map(scenarios.map((scenario) => [modelKey(scenario), scenario])).values()];
  return models.flatMap((model) => {
    const levels = [...new Set(scenarios.filter((scenario) => modelKey(scenario) === modelKey(model)).map((scenario) => scenario.concurrency))].sort((first, second) => first - second);
    return levels.map((level) => ({
      model, concurrency: level,
      data: runs.map((run) => {
        const scenario = run.scenarios.find((item) => modelKey(item) === modelKey(model) && item.concurrency === level && metricValue(item, metric) !== null);
        return scenario ? metricValue(scenario, metric) : null;
      }),
    }));
  });
}
export function hasTrend(runs: Run[], concurrency: number | undefined, metric: DashboardMetric) {
  return trendSeries(runs, concurrency, metric).some((series) => series.data.filter((value) => value !== null).length >= 2);
}
