import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { BarChart, BoxplotChart, LineChart } from "echarts/charts";
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";
import { tr, type Language } from "../i18n";
import type { Run, Scenario } from "../types";
import { InfoTip } from "./InfoTip";

echarts.use([BarChart, BoxplotChart, LineChart, AriaComponent, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

type Metric = "qps" | "p50" | "p95" | "p99" | "error";

function themeValue(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function chartColors() {
  return Array.from({ length: 6 }, (_, index) => themeValue(`--chart-${index + 1}`));
}

function percentile(sorted: number[], fraction: number) {
  const position = (sorted.length - 1) * fraction;
  const lower = Math.floor(position);
  return sorted[lower] + (sorted[Math.min(lower + 1, sorted.length - 1)] - sorted[lower]) * (position - lower);
}

function samples(scenario: Scenario) {
  return (scenario.result?.samples ?? []).filter((row) => row.ok && Number.isFinite(row.latency_ms) && row.latency_ms >= 0).map((row) => row.latency_ms).sort((a, b) => a - b);
}

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

function Chart({ option, label, empty, dark }: { option: EChartsCoreOption; label: string; empty: string | null; dark: boolean }) {
  const element = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.EChartsType | null>(null);

  useEffect(() => {
    if (!element.current || empty) return;
    const instance = echarts.init(element.current, undefined, { renderer: "canvas" });
    chart.current = instance;
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(element.current);
    return () => { observer.disconnect(); instance.dispose(); chart.current = null; };
  }, [empty]);

  useEffect(() => {
    if (!chart.current || empty) return;
    chart.current.setOption({
      backgroundColor: "transparent",
      color: chartColors(),
      textStyle: { color: themeValue("--muted-foreground"), fontFamily: "Inter, Segoe UI, PingFang SC, sans-serif" },
      animationDuration: 180,
      aria: { show: true },
      ...option,
    }, true);
    chart.current.resize();
  }, [option, empty, dark]);

  return empty ? <div className="perf-chart-empty">{empty}</div> : <div ref={element} className="perf-chart-canvas" role="img" aria-label={label} />;
}

function baseOption(dark: boolean, yLabel: string, xLabel: string): EChartsCoreOption {
  const text = themeValue("--muted-foreground");
  const grid = themeValue("--border");
  return {
    tooltip: { trigger: "axis", confine: true, backgroundColor: themeValue("--surface-raised"), borderColor: grid, textStyle: { color: themeValue("--foreground"), fontSize: 11 } },
    legend: { bottom: 0, type: "scroll", textStyle: { color: text, fontSize: 11 } },
    grid: { top: 24, right: 24, bottom: 57, left: 60, containLabel: false },
    xAxis: { type: "category", name: xLabel, nameLocation: "middle", nameGap: 26, axisLabel: { color: text }, axisLine: { lineStyle: { color: grid } }, axisTick: { show: false } },
    yAxis: { type: "value", name: yLabel, nameTextStyle: { color: text }, axisLabel: { color: text }, splitLine: { lineStyle: { color: grid } } },
  };
}

function lineOption(scenarios: Scenario[], levels: number[], providers: string[], metric: Metric, dark: boolean, language: Language): EChartsCoreOption {
  const colors = chartColors();
  const isError = metric === "error";
  const option = baseOption(dark, metric === "qps" ? "QPS" : isError ? "%" : "ms", tr(language, "并发数"));
  return {
    ...option,
    xAxis: { ...(option.xAxis as object), data: levels.map(String) },
    yAxis: { ...(option.yAxis as object), min: 0, max: isError ? 100 : undefined },
    series: providers.map((provider, index) => ({
      name: provider,
      type: "line",
      showSymbol: true,
      symbolSize: 8,
      lineStyle: { width: 2.5 },
      itemStyle: { color: colors[index % colors.length] },
      connectNulls: false,
      data: levels.map((level) => {
        const scenario = scenarios.find((item) => (item.provider_name || item.provider) === provider && item.concurrency === level);
        const value = scenario ? metricValue(scenario, metric) : null;
        return value === null ? null : Number(value.toFixed(2));
      }),
    })),
  };
}

function boxOption(scenarios: Scenario[], levels: number[], providers: string[], dark: boolean, language: Language): EChartsCoreOption {
  const colors = chartColors();
  const option = baseOption(dark, "ms", tr(language, "并发数"));
  return {
    ...option,
    tooltip: { ...(option.tooltip as object), trigger: "item" },
    xAxis: { ...(option.xAxis as object), data: levels.map(String) },
    series: providers.map((provider, index) => ({
      name: provider,
      type: "boxplot",
      itemStyle: { color: colors[index % colors.length] + "44", borderColor: colors[index % colors.length], borderWidth: 1.5 },
      data: levels.map((level) => {
        const scenario = scenarios.find((item) => (item.provider_name || item.provider) === provider && item.concurrency === level);
        const values = scenario ? samples(scenario) : [];
        return values.length ? [values[0], percentile(values, .25), percentile(values, .5), percentile(values, .75), values[values.length - 1]] : null;
      }),
    })),
  };
}

function histogramOption(scenarios: Scenario[], concurrency: number, providers: string[], dark: boolean, language: Language): EChartsCoreOption {
  const colors = chartColors();
  const groups = providers.map((provider) => {
    const scenario = scenarios.find((item) => (item.provider_name || item.provider) === provider && item.concurrency === concurrency);
    return samples(scenario ?? ({ result: null } as Scenario));
  });
  const all = groups.flat().sort((a, b) => a - b);
  const min = all[0];
  const cap = percentile(all, .99);
  const bins = Math.min(20, Math.max(12, Math.ceil(Math.sqrt(all.length / Math.max(groups.length, 1)))));
  const width = Math.max((cap - min) / bins, .001);
  const hasOverflow = all[all.length - 1] > cap;
  const format = (value: number) => value < 10 ? value.toFixed(1) : Math.round(value).toString();
  const labels = Array.from({ length: bins }, (_, index) => `${format(min + index * width)}–${format(min + (index + 1) * width)}`);
  if (hasOverflow) labels.push(`>${format(cap)}`);
  const option = baseOption(dark, "%", tr(language, "延迟区间（ms）"));
  return {
    ...option,
    xAxis: { ...(option.xAxis as object), data: labels, axisLabel: { rotate: 35, interval: Math.max(0, Math.floor(bins / 8) - 1), color: themeValue("--muted-foreground") } },
    grid: { top: 24, right: 24, bottom: 85, left: 60 },
    series: providers.map((provider, index) => {
      const values = groups[index];
      const counts = Array(labels.length).fill(0) as number[];
      values.forEach((value) => { counts[value > cap ? bins : Math.min(Math.floor((value - min) / width), bins - 1)] += 1; });
      return { name: `${provider} (n=${values.length})`, type: "bar", barMaxWidth: 32, itemStyle: { color: colors[index % colors.length], opacity: .82 }, data: counts.map((count) => values.length ? Number((count / values.length * 100).toFixed(1)) : 0) };
    }),
  };
}

function cdfOption(scenarios: Scenario[], concurrency: number, providers: string[], dark: boolean, language: Language): EChartsCoreOption {
  const colors = chartColors();
  const option = baseOption(dark, "%", tr(language, "延迟（ms）"));
  return {
    ...option,
    xAxis: { type: "value", name: tr(language, "延迟（ms）"), nameLocation: "middle", nameGap: 27, min: 0, axisLabel: { color: themeValue("--muted-foreground") }, splitLine: { show: false } },
    yAxis: { ...(option.yAxis as object), min: 0, max: 100 },
    series: providers.map((provider, index) => {
      const scenario = scenarios.find((item) => (item.provider_name || item.provider) === provider && item.concurrency === concurrency);
      const values = scenario ? samples(scenario) : [];
      return { name: provider, type: "line", showSymbol: false, step: "end", lineStyle: { width: 2 }, itemStyle: { color: colors[index % colors.length] }, data: values.map((value, point) => [value, Number(((point + 1) / values.length * 100).toFixed(2))]) };
    }),
  };
}

export function PerfCharts({ run, language, dark }: { run: Run | null; language: Language; dark: boolean }) {
  const t = (text: string) => tr(language, text);
  const scenarios = useMemo(() => run?.scenarios ?? [], [run]);
  const levels = useMemo(() => [...new Set(scenarios.map((item) => item.concurrency))].sort((a, b) => a - b), [scenarios]);
  const providers = useMemo(() => [...new Set(scenarios.map((item) => item.provider_name || item.provider))], [scenarios]);
  const [latencyMetric, setLatencyMetric] = useState<"p50" | "p95" | "p99">("p95");
  const [selectedLevel, setSelectedLevel] = useState<number | null>(null);
  const level = selectedLevel !== null && levels.includes(selectedLevel) ? selectedLevel : levels[0];
  const hasSummary = scenarios.some((item) => metricValue(item, "qps") !== null);
  const hasResults = scenarios.some((item) => item.result);
  const hasSamples = scenarios.some((item) => samples(item).length > 0);
  const levelHasSamples = scenarios.some((item) => item.concurrency === level && samples(item).length > 0);
  const summaryEmpty = hasSummary ? null : t("暂无成功请求，无法绘制吞吐和延迟曲线");
  const sampleEmpty = hasSamples ? null : t("当前运行没有可用的逐请求延迟样本");

  return <section className="perf-results" aria-label={t("性能分析图表")}>
    <div className="perf-section-heading"><div><p className="eyebrow">PERFORMANCE ANALYSIS</p><h2>{t("性能分析图表")}</h2></div><span>{t("基于每场景的真实请求结果")}</span></div>
    <div className="perf-chart-grid">
      <article className="panel perf-chart-panel"><div className="panel-head"><div><p className="eyebrow">THROUGHPUT</p><h2 className="title-with-tip">{t("吞吐量与并发")}<InfoTip label={t("查看图表说明")} text={t("QPS 表示每秒成功完成的请求数；曲线越高，代表相同时间内处理的请求越多。")}/></h2></div><span className="unit">QPS</span></div><Chart option={lineOption(scenarios, levels, providers, "qps", dark, language)} label={t("吞吐量与并发")} empty={summaryEmpty} dark={dark} /><p className="perf-chart-caption">{t("成功请求数 ÷ 场景耗时；按供应商比较扩展能力。")}</p></article>
      <article className="panel perf-chart-panel"><div className="panel-head"><div><p className="eyebrow">TAIL LATENCY</p><h2 className="title-with-tip">{t("延迟分位数与并发")}<InfoTip label={t("查看图表说明")} text={t("P50 是中位延迟；P95/P99 表示 95%/99% 的成功请求在该时间内完成，用于观察尾延迟。")}/></h2></div><div className="metric-toggle">{(["p50", "p95", "p99"] as const).map((item) => <button className={latencyMetric === item ? "active" : ""} onClick={() => setLatencyMetric(item)} key={item}>{item.toUpperCase()}</button>)}</div></div><Chart option={lineOption(scenarios, levels, providers, latencyMetric, dark, language)} label={`${latencyMetric.toUpperCase()} ${t("延迟分位数与并发")}`} empty={summaryEmpty} dark={dark} /><p className="perf-chart-caption">{t("仅统计成功请求；切换分位数观察尾延迟变化。")}</p></article>
      <article className="panel perf-chart-panel"><div className="panel-head"><div><p className="eyebrow">RELIABILITY</p><h2 className="title-with-tip">{t("失败率与并发")}<InfoTip label={t("查看图表说明")} text={t("失败率等于失败请求数除以总请求数；随并发升高可观察服务稳定性变化。")}/></h2></div><span className="unit">%</span></div><Chart option={lineOption(scenarios, levels, providers, "error", dark, language)} label={t("失败率与并发")} empty={hasResults ? null : t("暂无已完成场景")} dark={dark} /><p className="perf-chart-caption">{t("失败请求数 ÷ 总请求数；零值代表该场景全部成功。")}</p></article>
      <article className="panel perf-chart-panel"><div className="panel-head"><div><p className="eyebrow">SPREAD</p><h2 className="title-with-tip">{t("各并发档位延迟箱线图")}<InfoTip label={t("查看图表说明")} text={t("箱体展示 P25–P75，中线是中位数，须线是最小值和最大值；箱体越短代表波动越小。")}/></h2></div><span className="unit">ms</span></div><Chart option={boxOption(scenarios, levels, providers, dark, language)} label={t("各并发档位延迟箱线图")} empty={sampleEmpty} dark={dark} /><p className="perf-chart-caption">{t("箱体为 P25–P75，中线为中位数，须线为最小值与最大值。")}</p></article>
    </div>
    <div className="perf-distribution-heading"><div><p className="eyebrow">REQUEST DISTRIBUTION</p><h2>{t("指定并发下的延迟分布")}</h2><p>{t("选择并发档位，比较各供应商成功请求的真实延迟样本。")}</p></div><label><span className="label-with-tip">{t("并发档位")}<InfoTip label={t("查看说明")} text={t("选择一个场景并发值，下面两张图会使用该档位的逐请求样本。")}/></span><select value={level ?? ""} onChange={(event) => setSelectedLevel(Number(event.target.value))} disabled={!levels.length}>{levels.map((item) => <option key={item} value={item}>{item}</option>)}</select></label></div>
    <div className="perf-chart-grid">
      <article className="panel perf-chart-panel"><div className="panel-head"><div><p className="eyebrow">HISTOGRAM</p><h2 className="title-with-tip">{t("延迟直方图")}<InfoTip label={t("查看图表说明")} text={t("横轴是延迟区间，纵轴是请求占比；柱子集中在左侧通常表示响应更快。")}/></h2></div><span className="unit">%</span></div><Chart option={levelHasSamples ? histogramOption(scenarios, level, providers, dark, language) : {}} label={t("延迟直方图")} empty={levelHasSamples ? null : t("此并发档位暂无成功请求的延迟样本")} dark={dark} /><p className="perf-chart-caption">{t("统一分桶，超过 P99 的样本进入末档；纵轴为各供应商自身请求的占比。")}</p></article>
      <article className="panel perf-chart-panel"><div className="panel-head"><div><p className="eyebrow">CUMULATIVE</p><h2 className="title-with-tip">{t("延迟累计分布 CDF")}<InfoTip label={t("查看图表说明")} text={t("CDF 展示低于某个延迟阈值的累计请求占比；曲线越靠左上，整体响应越快。")}/></h2></div><span className="unit">%</span></div><Chart option={cdfOption(scenarios, level, providers, dark, language)} label={t("延迟累计分布 CDF")} empty={levelHasSamples ? null : t("此并发档位暂无成功请求的延迟样本")} dark={dark} /><p className="perf-chart-caption">{t("在任意延迟阈值下，查看已有多少请求完成。")}</p></article>
    </div>
  </section>;
}
