import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";
import { GitCompareArrows, LineChart as LineChartIcon, ShieldCheck } from "lucide-react";
import { tr, type Language } from "../i18n";
import type { Run, Scenario, TestPlan } from "../types";
import { hasTrend, metricValue, modelKey, modelLabel, type DashboardMetric as Metric } from "../dashboardData";
import { llmMetricLabel, llmMetricTip } from "../llmMetrics";

echarts.use([LineChart, AriaComponent, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);
type View = "comparison" | "trend" | "stability";
function themeValue(name: string) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
function formatTime(value: string, language: Language) {
  return new Intl.DateTimeFormat(language, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value));
}
function metricLabel(metric: Metric) {
  return metric === "error" ? "失败率" : metric === "qps" ? "吞吐量" : ["p50", "p95", "p99"].includes(metric) ? `${metric.toUpperCase()} 延迟` : llmMetricLabel(metric as "ttft" | "tpot" | "tokens_per_second");
}
function metricUnit(metric: Metric) { return metric === "qps" ? "QPS" : metric === "error" ? "%" : metric === "tokens_per_second" ? "tokens/s" : metric === "tpot" ? "ms/token" : "ms"; }
function formatValue(value: number | null, metric: Metric) { return value === null ? "—" : metric === "qps" || metric === "error" ? value.toFixed(2) : String(Math.round(value)); }

function ResultChart({ runs, metric, concurrency, trend, language, dark }: { runs: Run[]; metric: Metric; concurrency: number | undefined; trend: boolean; language: Language; dark: boolean }) {
  const element = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.EChartsType | null>(null);
  const option = useMemo<EChartsCoreOption>(() => {
    const scenarios = runs.flatMap((run) => run.scenarios).filter((scenario) => !trend || scenario.concurrency === concurrency);
    const models = [...new Map(scenarios.map((scenario) => [modelKey(scenario), scenario])).values()];
    const levels = [...new Set(scenarios.map((scenario) => scenario.concurrency))].sort((a, b) => a - b);
    const border = themeValue("--border");
    const muted = themeValue("--muted-foreground");
    return {
      backgroundColor: "transparent", color: Array.from({ length: 6 }, (_, index) => themeValue(`--chart-${index + 1}`)),
      aria: { show: true, label: { description: `${tr(language, trend ? "历史运行趋势" : "并发性能对比")} · ${tr(language, metricLabel(metric))} (${metricUnit(metric)})` } }, animationDuration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 180,
      tooltip: { trigger: "axis", confine: true, backgroundColor: themeValue("--surface-raised"), borderColor: border, textStyle: { color: themeValue("--foreground"), fontSize: 11 }, valueFormatter: (value: unknown) => typeof value === "number" ? `${formatValue(value, metric)} ${metricUnit(metric)}` : "—" },
      legend: { top: 0, type: "scroll", textStyle: { color: muted, fontSize: 11 } },
      grid: { top: 64, right: 20, bottom: 58, left: 16, containLabel: true },
      xAxis: { type: "category", name: tr(language, trend ? "运行时间／序号" : "并发数"), nameTextStyle: { color: muted }, nameLocation: "middle", nameGap: 36, data: trend ? runs.map((run, index) => `#${index + 1} · ${formatTime(run.created_at, language)}`) : levels.map(String), axisLabel: { color: muted, hideOverlap: true }, axisLine: { lineStyle: { color: border } }, axisTick: { show: false } },
      yAxis: { type: "value", min: 0, max: metric === "error" ? 100 : undefined, name: metricUnit(metric), nameTextStyle: { color: muted }, axisLabel: { color: muted }, splitLine: { lineStyle: { color: border } } },
      series: models.map((model, index) => ({ name: modelLabel(model), type: "line", connectNulls: false, showSymbol: true, symbol: ["circle", "rect", "triangle", "diamond", "roundRect", "pin"][index % 6], symbolSize: 8, lineStyle: { width: 2 }, data: (trend ? runs : levels).map((entry) => {
        const candidates = typeof entry === "number" ? scenarios : entry.scenarios;
        const level = typeof entry === "number" ? entry : concurrency;
        const scenario = candidates.find((item) => modelKey(item) === modelKey(model) && item.concurrency === level);
        return scenario ? metricValue(scenario, metric) : null;
      }) })),
    };
  }, [runs, metric, concurrency, trend, language, dark]);
  useEffect(() => {
    if (!element.current) return;
    const instance = echarts.init(element.current, undefined, { renderer: "canvas" });
    chart.current = instance;
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(element.current);
    return () => { observer.disconnect(); instance.dispose(); chart.current = null; };
  }, []);
  useEffect(() => { chart.current?.setOption(option, true); }, [option]);
  return <div ref={element} className="dashboard-trend-chart" role="img" aria-label={tr(language, trend ? "历史运行趋势" : "并发性能对比")} />;
}

export function AnalysisDashboard({ plans, runs, language, dark, initialPlanId, initialRunId, onSelectRun }: {
  plans: TestPlan[]; runs: Run[]; language: Language; dark: boolean; initialPlanId: string | null; initialRunId: string | null; onSelectRun: (id: string) => void;
}) {
  const t = (value: string) => tr(language, value);
  const planChoices = [...new Set(runs.map((run) => run.plan_id))].map((id) => ({ id, name: plans.find((plan) => plan.id === id)?.name || runs.find((run) => run.plan_id === id)?.name || id, count: runs.filter((run) => run.plan_id === id).length }));
  const richestPlanId = [...planChoices].sort((a, b) => b.count - a.count)[0]?.id || "";
  const [planId, setPlanId] = useState(initialPlanId || richestPlanId);
  const [view, setView] = useState<View>("comparison");
  const [metric, setMetric] = useState<Metric>("p95");
  const [selectedLevel, setSelectedLevel] = useState<number | null>(null);
  const [comparisonRunId, setComparisonRunId] = useState(initialRunId || "");
  useEffect(() => { if (initialPlanId) setPlanId(initialPlanId); }, [initialPlanId]);
  useEffect(() => {
    if (!runs.some((run) => run.plan_id === planId)) setPlanId(richestPlanId);
  }, [runs, planId, richestPlanId]);
  const planRuns = useMemo(() => runs.filter((run) => run.plan_id === planId).sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime() || a.id.localeCompare(b.id)), [runs, planId]);
  const levels = [...new Set(planRuns.flatMap((run) => run.scenarios.map((scenario) => scenario.concurrency)))].sort((a, b) => a - b);
  const concurrency = selectedLevel !== null && levels.includes(selectedLevel) ? selectedLevel : levels[0];
  const comparisonRun = planRuns.find((run) => run.id === comparisonRunId) || planRuns.at(-1) || null;
  useEffect(() => { if (initialRunId) setComparisonRunId(initialRunId); }, [initialRunId]);
  const latest = planRuns.at(-1);
  const isLlm = latest?.benchmark === "llm";
  const selectedMetric = !isLlm && ["ttft", "tpot", "tokens_per_second"].includes(metric) ? "p95" : metric;
  const activeMetric = view === "stability" ? "error" : selectedMetric;
  const trend = view !== "comparison";
  const chartRuns = trend ? planRuns : comparisonRun ? [comparisonRun] : [];
  const drawable = trend ? hasTrend(planRuns, concurrency, activeMetric) : !!comparisonRun?.scenarios.some((scenario) => metricValue(scenario, activeMetric) !== null);
  const rows: Array<{ run: Run; scenario: Scenario }> = chartRuns.flatMap((run) => run.scenarios.filter((scenario) => !trend || scenario.concurrency === concurrency).map((scenario) => ({ run, scenario })));
  const completed = planRuns.filter((run) => run.status === "completed").length;
  const failed = planRuns.filter((run) => run.status === "failed").length;
  return <div className="dashboard-page">
    <section className="panel dashboard-toolbar">
      <label className="field"><span>{t("测试计划")}</span><select value={planId} disabled={!planChoices.length} onChange={(event) => { setPlanId(event.target.value); setComparisonRunId(""); setSelectedLevel(null); }}>{planChoices.map((plan) => <option key={plan.id} value={plan.id}>{plan.name} · {plan.count} {t("次")} · {plan.id.slice(-6)}</option>)}</select></label>
      <div className="dashboard-view-switch" aria-label={t("看板视图")}>
        {(["comparison", "trend", "stability"] as View[]).map((item) => <button key={item} aria-pressed={view === item} className={view === item ? "active" : ""} onClick={() => setView(item)}>{item === "comparison" ? <GitCompareArrows aria-hidden="true" /> : item === "trend" ? <LineChartIcon aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}{t(item === "comparison" ? "并发性能对比" : item === "trend" ? "历史运行趋势" : "稳定性")}</button>)}
      </div>
    </section>
    <section className="metric-grid dashboard-metrics" aria-label={t("计划运行汇总")}>
      <article><span>{t("运行记录")}</span><strong>{planRuns.length}</strong><small>{t("该计划产生的全部运行")}</small></article>
      <article><span>{t("已完成")}</span><strong>{completed}</strong><small>{planRuns.length ? Math.round(completed / planRuns.length * 100) : 0}% {t("运行完成率")}</small></article>
      <article><span>{t("失败")}</span><strong className={failed ? "metric-danger" : ""}>{failed}</strong><small>{t("失败运行记录")}</small></article>
      <article><span>{t("最近运行")}</span><strong className="metric-time">{latest ? formatTime(latest.created_at, language) : "—"}</strong><small>{latest?.benchmark || t("暂无运行记录")}</small></article>
    </section>
    <section className="panel dashboard-chart-panel">
      <div className="panel-head"><div><h2>{t(view === "comparison" ? "并发性能对比" : view === "trend" ? "历史运行趋势" : "失败率趋势")}</h2><p>{t(trend ? "固定一个并发档位，观察同一模型在多次运行中的变化。" : "横轴为并发数，每条曲线代表一个模型；比较不同负载下的性能。")}</p></div></div>
      <div className="dashboard-chart-controls">
        {view !== "stability" && <div className="metric-toggle">{(["p50", "p95", "p99", "qps", ...(isLlm ? ["ttft", "tpot", "tokens_per_second"] : [])] as Metric[]).map((item) => <button key={item} aria-pressed={selectedMetric === item} className={selectedMetric === item ? "active" : ""} onClick={() => setMetric(item)}>{item === "tokens_per_second" ? "tokens/s" : item.toUpperCase()}</button>)}</div>}
        {trend ? <label><span>{t("并发档位")}</span><select value={concurrency ?? ""} disabled={!levels.length} onChange={(event) => setSelectedLevel(Number(event.target.value))}>{levels.map((level) => <option key={level} value={level}>{level}</option>)}</select></label>
          : <label className="dashboard-run-select"><span>{t("运行记录")}</span><select value={comparisonRun?.id || ""} disabled={!planRuns.length} onChange={(event) => { setComparisonRunId(event.target.value); onSelectRun(event.target.value); }}>{[...planRuns].reverse().map((run) => <option key={run.id} value={run.id}>{formatTime(run.created_at, language)} · {t(({ completed: "已完成", failed: "失败", running: "运行中", queued: "等待中", cancelled: "已取消" } as Record<string, string>)[run.status] || run.status)} · {run.id.slice(-6)}</option>)}</select></label>}
      </div>
      <p className="dashboard-metric-description">{t(metricLabel(activeMetric))} · {metricUnit(activeMetric)} · {t(activeMetric === "qps" || activeMetric === "tokens_per_second" ? "越高越好" : "越低越好")}</p>
      {drawable ? <ResultChart runs={chartRuns} metric={activeMetric} concurrency={concurrency} trend={trend} language={language} dark={dark} /> : <div className="perf-chart-empty">{t(!planRuns.length ? "该测试计划还没有运行记录" : trend ? "同一模型在所选并发档位下至少需要两次有效运行，才能展示趋势。" : "当前指标暂无有效结果，缺失值不会显示为零。")}</div>}
      <p className="perf-chart-caption">{t(trend ? "每个点对应一条独立运行记录，不合并时间相近的运行。" : "仅比较本次运行，不跨运行平均分位数。")}</p>
      <p className="perf-chart-caption">{t(["ttft", "tpot", "tokens_per_second"].includes(activeMetric) ? llmMetricTip(activeMetric as "ttft" | "tpot" | "tokens_per_second") : activeMetric === "qps" ? "QPS 表示每秒成功完成的请求数。" : activeMetric === "error" ? "失败率等于失败请求数除以总请求数。" : "P50 是中位延迟；P95/P99 表示 95%/99% 的成功请求在该时间内完成。")}</p>
      <h3 className="dashboard-data-heading">{t("指标数值明细")}</h3>
      <div className="table-scroll"><table className="dashboard-data-table"><thead><tr>{trend && <th>{t("运行记录")}</th>}<th>{t("模型")}</th><th>{t("并发数")}</th><th>{t(metricLabel(activeMetric))} ({metricUnit(activeMetric)})</th><th>{t("成功请求")}</th><th>{t("失败请求")}</th></tr></thead><tbody>{rows.map(({ run, scenario }) => <tr key={`${run.id}-${scenario.id}`}>{trend && <td>{formatTime(run.created_at, language)}<small className="mono">{run.id.slice(-6)}</small></td>}<td>{modelLabel(scenario)}</td><td>{scenario.concurrency}</td><td>{formatValue(metricValue(scenario, activeMetric), activeMetric)}</td><td>{scenario.result?.success_count ?? "—"}</td><td>{scenario.result?.failure_count ?? "—"}</td></tr>)}{!rows.length && <tr><td colSpan={trend ? 6 : 5}>{t("当前筛选条件下暂无可绘制结果")}</td></tr>}</tbody></table></div>
    </section>
  </div>;
}
