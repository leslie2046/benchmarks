import type { Scenario } from "../types";

const COLORS = ["#37c9ee", "#a88bff", "#49d49d", "#ffb44c", "#f57089", "#6fa8ff"];

type Metric = "qps" | "p50" | "p95" | "p99";

function metricValue(scenario: Scenario, metric: Metric) {
  if (!scenario.result || scenario.result.success_count <= 0) return null;
  if (metric === "qps") return scenario.result.qps_success;
  return scenario.result.metrics.latency_ms?.[metric] ?? null;
}

export function LineChart({ scenarios, metric }: { scenarios: Scenario[]; metric: Metric }) {
  const completed = scenarios.filter((item) => metricValue(item, metric) !== null);
  const providers = [...new Set(scenarios.map((item) => item.provider_name || item.provider))];
  const levels = [...new Set(scenarios.map((item) => item.concurrency))].sort((a, b) => a - b);
  const values = completed.map((item) => metricValue(item, metric) as number);
  const max = Math.max(...values, 1) * 1.12;
  const width = 760;
  const height = 270;
  const pad = { left: 52, right: 20, top: 18, bottom: 42 };
  const x = (level: number) => pad.left + (levels.indexOf(level) / Math.max(levels.length - 1, 1)) * (width - pad.left - pad.right);
  const y = (value: number) => pad.top + (1 - value / max) * (height - pad.top - pad.bottom);

  return (
    <div className="chart-shell">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${metric} 按并发数对比图`}>
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const value = max * (1 - ratio);
          const top = pad.top + ratio * (height - pad.top - pad.bottom);
          return <g key={ratio}>
            <line x1={pad.left} x2={width - pad.right} y1={top} y2={top} className="chart-grid" />
            <text x={pad.left - 10} y={top + 4} textAnchor="end" className="chart-label">{value >= 100 ? value.toFixed(0) : value.toFixed(1)}</text>
          </g>;
        })}
        {levels.map((level) => <text key={level} x={x(level)} y={height - 14} textAnchor="middle" className="chart-label">{level}</text>)}
        {providers.map((provider, providerIndex) => {
          const items = completed.filter((item) => (item.provider_name || item.provider) === provider).sort((a, b) => a.concurrency - b.concurrency);
          const points = items.map((item) => `${x(item.concurrency)},${y(metricValue(item, metric) as number)}`).join(" ");
          const color = COLORS[providerIndex % COLORS.length];
          return <g key={provider}>
            {items.length > 1 && <polyline points={points} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" />}
            {items.map((item) => <circle key={item.id} cx={x(item.concurrency)} cy={y(metricValue(item, metric) as number)} r="4.5" fill="#0c1825" stroke={color} strokeWidth="2.5"><title>{provider} · c={item.concurrency} · {(metricValue(item, metric) as number).toFixed(2)}</title></circle>)}
          </g>;
        })}
      </svg>
      {completed.length === 0 && <div className="chart-empty">没有可绘制的成功样本，请检查失败场景与服务配置</div>}
      {completed.length === 1 && <div className="chart-notice">当前只有 1 个有效数据点；至少需要 2 个并发档位才能形成曲线</div>}
      <div className="chart-legend">
        {providers.map((provider, index) => <span key={provider}><i style={{ background: COLORS[index % COLORS.length] }} />{provider}</span>)}
      </div>
    </div>
  );
}
