import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";
import { BarChart3, GitCompareArrows, LineChart as LineChartIcon, ShieldCheck } from "lucide-react";
import { tr, type Language } from "../i18n";
import type { Run, Scenario, TestPlan } from "../types";
import { InfoTip } from "./InfoTip";
import { PerfCharts } from "./PerfCharts";

echarts.use([LineChart, AriaComponent, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

type Metric = "p50" | "p95" | "p99" | "qps" | "error";
type View = "trend" | "comparison" | "stability";

function themeValue(name: string) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

function metricValue(scenario: Scenario, metric: Metric): number | null {
  const result = scenario.result;
  if (!result) return null;
  if (metric === "error") {
    const total = result.success_count + result.failure_count;
    return total ? result.failure_count / total * 100 : null;
  }
  if (!result.success_count) return null;
  if (metric === "qps") return result.qps_success;
  return result.metrics.latency_ms?.[metric] ?? null;
}

function seriesKey(scenario: Scenario) {
  return `${scenario.provider_name || scenario.provider}${scenario.model ? ` · ${scenario.model}` : ""} · c=${scenario.concurrency}`;
}

function formatTime(value: string, language: Language) {
  return new Intl.DateTimeFormat(language, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function TrendChart({ runs, metric, concurrency, language, dark }: { runs: Run[]; metric: Metric; concurrency: number | "all"; language: Language; dark: boolean }) {
  const element = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.EChartsType | null>(null);
  const scenarios = runs.flatMap((run) => run.scenarios).filter((scenario) => concurrency === "all" || scenario.concurrency === concurrency);
  const keys = [...new Set(scenarios.map(seriesKey))].filter((key) => runs.some((run) => {
    const scenario = run.scenarios.find((item) => seriesKey(item) === key);
    return scenario ? metricValue(scenario, metric) !== null : false;
  }));
  const option = useMemo<EChartsCoreOption>(() => {
    const border = themeValue("--border");
    const muted = themeValue("--muted-foreground");
    const colors = Array.from({ length: 6 }, (_, index) => themeValue(`--chart-${index + 1}`));
    return {
      backgroundColor: "transparent",
      color: colors,
      aria: { show: true },
      animationDuration: 180,
      tooltip: { trigger: "axis", confine: true, backgroundColor: themeValue("--surface-raised"), borderColor: border, textStyle: { color: themeValue("--foreground"), fontSize: 11 } },
      legend: { bottom: 0, type: "scroll", textStyle: { color: muted, fontSize: 10 } },
      grid: { top: 24, right: 22, bottom: 62, left: 58 },
      xAxis: { type: "category", data: runs.map((run) => formatTime(run.created_at, language)), axisLabel: { color: muted, hideOverlap: true }, axisLine: { lineStyle: { color: border } }, axisTick: { show: false } },
      yAxis: { type: "value", min: 0, max: metric === "error" ? 100 : undefined, name: metric === "qps" ? "QPS" : metric === "error" ? "%" : "ms", nameTextStyle: { color: muted }, axisLabel: { color: muted }, splitLine: { lineStyle: { color: border } } },
      series: keys.map((key) => ({ name: key, type: "line", connectNulls: false, showSymbol: true, symbolSize: 7, lineStyle: { width: 2 }, data: runs.map((run) => {
        const scenario = run.scenarios.find((item) => seriesKey(item) === key);
        const value = scenario ? metricValue(scenario, metric) : null;
        return value === null ? null : Number(value.toFixed(2));
      }) })),
    };
  }, [runs, metric, concurrency, language, dark, keys.join("|")]);

  useEffect(() => {
    if (!element.current || !keys.length) return;
    const instance = echarts.init(element.current, undefined, { renderer: "canvas" });
    chart.current = instance;
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(element.current);
    return () => { observer.disconnect(); instance.dispose(); chart.current = null; };
  }, [keys.length]);

  useEffect(() => { chart.current?.setOption(option, true); chart.current?.resize(); }, [option]);
  return keys.length ? <div ref={element} className="dashboard-trend-chart" role="img" aria-label={tr(language, "测试计划多次运行趋势图")} /> : <div className="perf-chart-empty">{tr(language, "当前筛选条件下暂无可绘制结果")}</div>;
}

export function AnalysisDashboard({ plans, runs, language, dark, initialPlanId, initialRunId, onSelectRun }: {
  plans: TestPlan[];
  runs: Run[];
  language: Language;
  dark: boolean;
  initialPlanId: string | null;
  initialRunId: string | null;
  onSelectRun: (id: string) => void;
}) {
  const t = (value: string) => tr(language, value);
  const planChoices = [...new Set(runs.map((run) => run.plan_id))].map((id) => {
    const plan = plans.find((item) => item.id === id);
    const planRuns = runs.filter((run) => run.plan_id === id);
    return { id, name: plan?.name || planRuns[0]?.name || id, benchmark: plan?.benchmark || planRuns[0]?.benchmark || "—", count: planRuns.length };
  });
  const richestPlanId = [...new Set(runs.map((run) => run.plan_id))].sort((a, b) => runs.filter((run) => run.plan_id === b).length - runs.filter((run) => run.plan_id === a).length)[0] || "";
  const fallbackPlanId = initialPlanId && runs.some((run) => run.plan_id === initialPlanId) ? initialPlanId : richestPlanId;
  const [planId, setPlanId] = useState(fallbackPlanId);
  const [view, setView] = useState<View>("trend");
  const [metric, setMetric] = useState<Metric>("p95");
  const [concurrency, setConcurrency] = useState<number | "all">("all");
  useEffect(() => {
    if (initialPlanId && runs.some((run) => run.plan_id === initialPlanId)) setPlanId(initialPlanId);
    else if (!runs.some((run) => run.plan_id === planId)) setPlanId(richestPlanId);
  }, [initialPlanId, runs, planId, richestPlanId]);
  const planRuns = useMemo(() => runs.filter((run) => run.plan_id === planId).sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()), [runs, planId]);
  const levels = [...new Set(planRuns.flatMap((run) => run.scenarios.map((scenario) => scenario.concurrency)))].sort((a, b) => a - b);
  const preferredRun = initialRunId && planRuns.some((run) => run.id === initialRunId) ? initialRunId : planRuns.at(-1)?.id || "";
  const [comparisonRunId, setComparisonRunId] = useState(preferredRun);
  useEffect(() => { setComparisonRunId(preferredRun); }, [preferredRun]);
  const comparisonRun = planRuns.find((run) => run.id === comparisonRunId) || planRuns.at(-1) || null;
  const completed = planRuns.filter((run) => run.status === "completed").length;
  const failed = planRuns.filter((run) => run.status === "failed").length;
  const latest = planRuns.at(-1);
  const successRate = planRuns.length ? completed / planRuns.length * 100 : 0;

  return <div className="dashboard-page">
    <section className="panel dashboard-toolbar">
      <label className="field"><span>{t("测试计划")}</span><select value={planId} onChange={(event) => setPlanId(event.target.value)}>{planChoices.map((plan) => <option key={plan.id} value={plan.id}>{plan.name} · {plan.benchmark} · {plan.count} {t("次")} · {plan.id.slice(-6)}</option>)}</select></label>
      <div className="dashboard-view-switch" aria-label={t("看板视图")}>
        <button className={view === "trend" ? "active" : ""} onClick={() => setView("trend")}><LineChartIcon aria-hidden="true" />{t("趋势")}</button>
        <button className={view === "comparison" ? "active" : ""} onClick={() => setView("comparison")}><GitCompareArrows aria-hidden="true" />{t("单次对比")}</button>
        <button className={view === "stability" ? "active" : ""} onClick={() => setView("stability")}><ShieldCheck aria-hidden="true" />{t("稳定性")}</button>
      </div>
    </section>

    <section className="metric-grid dashboard-metrics" aria-label={t("计划运行汇总")}>
      <article><span>{t("运行记录")}</span><strong>{planRuns.length}</strong><small>{t("该计划产生的全部运行")}</small></article>
      <article><span>{t("已完成")}</span><strong>{completed}</strong><small>{successRate.toFixed(0)}% {t("运行完成率")}</small></article>
      <article><span>{t("失败")}</span><strong className={failed ? "metric-danger" : ""}>{failed}</strong><small>{t("失败运行记录")}</small></article>
      <article><span>{t("最近运行")}</span><strong className="metric-time">{latest ? formatTime(latest.created_at, language) : "—"}</strong><small>{latest?.benchmark || t("暂无运行记录")}</small></article>
    </section>

    {view === "trend" && <section className="panel dashboard-chart-panel">
      <div className="panel-head"><div><p className="eyebrow">PLAN TREND</p><h2 className="title-with-tip">{t("多次运行趋势")}<InfoTip label={t("查看图表说明")} text={t("每个点代表一次运行的场景指标；同一供应商、模型与并发档位形成一条曲线。")}/></h2><p>{t("同一测试计划下的运行记录聚合在一张图中。")}</p></div><BarChart3 aria-hidden="true" /></div>
      <div className="dashboard-chart-controls">
        <div className="metric-toggle">{(["p50", "p95", "p99", "qps"] as Metric[]).map((item) => <button className={metric === item ? "active" : ""} onClick={() => setMetric(item)} key={item}>{item.toUpperCase()}</button>)}</div>
        <label><span>{t("并发档位")}</span><select value={concurrency} onChange={(event) => setConcurrency(event.target.value === "all" ? "all" : Number(event.target.value))}><option value="all">{t("全部")}</option>{levels.map((level) => <option value={level} key={level}>{level}</option>)}</select></label>
      </div>
      <TrendChart runs={planRuns} metric={metric} concurrency={concurrency} language={language} dark={dark} />
      <p className="perf-chart-caption">{t("P50/P95/P99 展示每次运行自身的分位数，不对分位数做跨运行平均。")}</p>
    </section>}

    {view === "stability" && <section className="panel dashboard-chart-panel">
      <div className="panel-head"><div><p className="eyebrow">RELIABILITY</p><h2 className="title-with-tip">{t("失败率趋势")}<InfoTip label={t("查看图表说明")} text={t("按运行时间观察各模型和并发档位的失败请求占比。")}/></h2><p>{t("用于发现随时间出现的稳定性退化。")}</p></div><ShieldCheck aria-hidden="true" /></div>
      <div className="dashboard-chart-controls"><span className="unit">%</span><label><span>{t("并发档位")}</span><select value={concurrency} onChange={(event) => setConcurrency(event.target.value === "all" ? "all" : Number(event.target.value))}><option value="all">{t("全部")}</option>{levels.map((level) => <option value={level} key={level}>{level}</option>)}</select></label></div>
      <TrendChart runs={planRuns} metric="error" concurrency={concurrency} language={language} dark={dark} />
    </section>}

    {view === "comparison" && <>
      <section className="panel comparison-run-toolbar"><div><p className="eyebrow">RUN SNAPSHOT</p><h2>{t("单次运行对比")}</h2><p>{t("选择一次运行，查看模型与并发档位的详细结果。")}</p></div><label className="field"><span>{t("运行记录")}</span><select value={comparisonRun?.id || ""} onChange={(event) => { setComparisonRunId(event.target.value); onSelectRun(event.target.value); }}>{[...planRuns].reverse().map((run) => <option key={run.id} value={run.id}>{formatTime(run.created_at, language)} · {t(({ completed: "已完成", failed: "失败", cancelled: "已取消", running: "运行中", queued: "等待中" } as Record<string, string>)[run.status] || run.status)}</option>)}</select></label></section>
      <PerfCharts run={comparisonRun} language={language} dark={dark} />
    </>}
    {!planRuns.length && <div className="panel empty-state">{t("该测试计划还没有运行记录")}</div>}
  </div>;
}
