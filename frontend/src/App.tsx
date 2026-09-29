import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, subscribeToRun } from "./api";
import { LineChart } from "./components/LineChart";
import type { Benchmark, Catalog, Run, ServiceConfig } from "./types";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

function Status({ value }: { value: string }) {
  const label: Record<string, string> = { queued: "等待中", running: "运行中", completed: "已完成", failed: "失败", cancelled: "已取消" };
  return <span className={`status status-${value}`}><i />{label[value] ?? value}</span>;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function average(values: number[]) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

export default function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [serviceConfigs, setServiceConfigs] = useState<ServiceConfig[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [benchmarkId, setBenchmarkId] = useState("reranker");
  const [providerIds, setProviderIds] = useState<string[]>([]);
  const [levels, setLevels] = useState("1, 5, 10, 20, 30");
  const [requests, setRequests] = useState(100);
  const [timeout, setTimeout] = useState(60);
  const [difyQuery, setDifyQuery] = useState("");
  const [difyDatasetId, setDifyDatasetId] = useState("");
  const [latencyMetric, setLatencyMetric] = useState<"p50" | "p95" | "p99">("p95");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [configBenchmark, setConfigBenchmark] = useState("reranker");
  const [configProvider, setConfigProvider] = useState("vllm");
  const [configName, setConfigName] = useState("vLLM Production");
  const [configUrl, setConfigUrl] = useState("http://127.0.0.1:8000/v1/rerank");
  const [configModel, setConfigModel] = useState("BAAI/bge-reranker-v2-m3");
  const [configApiKey, setConfigApiKey] = useState("");
  const [savingConfig, setSavingConfig] = useState(false);
  const [editingConfigId, setEditingConfigId] = useState<string | null>(null);
  const [, setClock] = useState(0);

  const selected = runs.find((run) => run.id === selectedId) ?? runs[0] ?? null;
  const benchmark = catalog?.benchmarks.find((item) => item.id === benchmarkId) ?? null;

  useEffect(() => {
    Promise.all([api.catalog(), api.runs(), api.serviceConfigs()]).then(([catalogData, runData, configData]) => {
      setCatalog(catalogData);
      setRuns(runData);
      setServiceConfigs(configData);
      if (runData[0]) setSelectedId(runData[0].id);
      const initial = catalogData.benchmarks.find((item) => item.id === "reranker") ?? catalogData.benchmarks[0];
      setProviderIds(initial.providers.filter((item) => item.endpoint_configured).slice(0, 2).map((item) => item.id));
    }).catch((error: Error) => setMessage(error.message));
  }, []);

  useEffect(() => {
    if (!selected || TERMINAL.has(selected.status)) return;
    return subscribeToRun(selected.id, (updated) => {
      setRuns((current) => [updated, ...current.filter((item) => item.id !== updated.id)]);
    }, () => undefined);
  }, [selected?.id, selected?.status]);

  useEffect(() => {
    if (selected?.status !== "running") return;
    const timer = window.setInterval(() => setClock((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [selected?.status]);

  const stats = useMemo(() => {
    const successful = selected?.scenarios.filter((item) => item.result && item.result.success_count > 0) ?? [];
    return {
      qps: average(successful.map((item) => item.result!.qps_success)),
      p95: average(successful.map((item) => item.result!.metrics.latency_ms?.p95 ?? 0)),
      success: average(successful.map((item) => item.result!.success_rate)),
    };
  }, [selected]);
  const failedScenarios = selected?.scenarios.filter((item) => item.status === "failed") ?? [];
  const activeScenario = selected?.scenarios.find((item) => item.status === "running") ?? null;
  const activeElapsed = activeScenario?.started_at
    ? Math.max(0, Math.floor((Date.now() - new Date(activeScenario.started_at).getTime()) / 1000))
    : 0;

  function changeBenchmark(next: Benchmark) {
    setBenchmarkId(next.id);
    setProviderIds(next.providers.filter((item) => item.endpoint_configured).slice(0, 2).map((item) => item.id));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const concurrency = levels.split(/[，,\s]+/).filter(Boolean).map(Number).filter((value) => Number.isInteger(value) && value > 0);
    if (!providerIds.length || !concurrency.length || !benchmark) {
      setMessage("请至少选择一个 Provider，并填写有效的并发档位。");
      return;
    }
    setSubmitting(true);
    setMessage("");
    try {
      const run = await api.createRun({
        name: `${benchmark.label} 对比测试`,
        benchmark: benchmark.id,
        providers: providerIds.map((id) => ({ id, model: benchmark.providers.find((item) => item.id === id)?.model })),
        concurrency_levels: concurrency,
        requests_per_scenario: requests,
        timeout_seconds: timeout,
        query: benchmark.id.startsWith("dify-") ? difyQuery : null,
        dataset_id: benchmark.id === "dify-retrieve" ? difyDatasetId : null,
      });
      setRuns((current) => [run, ...current]);
      setSelectedId(run.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建测试失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function cancel() {
    if (!selected) return;
    try {
      const updated = await api.cancelRun(selected.id);
      setRuns((current) => [updated, ...current.filter((item) => item.id !== updated.id)]);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "取消失败");
    }
  }

  async function rerun() {
    if (!selected) return;
    try {
      const run = await api.runPlan(selected.plan_id);
      setRuns((current) => [run, ...current]);
      setSelectedId(run.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "重新运行失败");
    }
  }

  async function saveServiceConfig(event: FormEvent) {
    event.preventDefault();
    setSavingConfig(true);
    setMessage("");
    try {
      const payload = {
        name: configName,
        benchmark: configBenchmark,
        provider: configProvider,
        base_url: configUrl || null,
        model: configModel || null,
        api_key: configApiKey || null,
      };
      const config = editingConfigId
        ? await api.updateServiceConfig(editingConfigId, payload)
        : await api.createServiceConfig(payload);
      setServiceConfigs((current) => editingConfigId
        ? current.map((item) => item.id === config.id ? config : item)
        : [...current, config]);
      const nextCatalog = await api.catalog();
      setCatalog(nextCatalog);
      setConfigApiKey("");
      setEditingConfigId(null);
      setMessage(`服务配置“${config.name}”已保存${config.has_api_key ? "，API Key 已加密" : ""}。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存服务配置失败");
    } finally {
      setSavingConfig(false);
    }
  }

  const configBenchmarkInfo = catalog?.benchmarks.find((item) => item.id === configBenchmark);

  function editServiceConfig(config: ServiceConfig) {
    setEditingConfigId(config.id);
    setConfigBenchmark(config.benchmark);
    setConfigProvider(config.provider);
    setConfigName(config.name);
    setConfigUrl(config.base_url ?? "");
    setConfigModel(config.model ?? "");
    setConfigApiKey("");
    document.querySelector("#settings")?.scrollIntoView({ behavior: "smooth" });
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><i /><i /><i /></span><span>PerfLab</span></div>
      <nav aria-label="主导航">
        <a className="active" href="#overview"><span>⌁</span>概览</a>
        <a href="#new-run"><span>＋</span>新建测试</a>
        <a href="#history"><span>≡</span>运行记录</a>
        <a href="#settings"><span>⚙</span>服务配置</a>
      </nav>
      <div className="executor"><span /><div><strong>执行器在线</strong><small>顺序调度模式</small></div></div>
    </aside>

    <main>
      <header className="topbar">
        <div><p className="eyebrow">AI MODEL BENCHMARKS</p><h1>性能测试台</h1></div>
        <div className="environment"><span className="pulse" />生产测试环境</div>
      </header>

      <div className="content" id="overview">
        {message && <div className="alert" role="alert">{message}<button onClick={() => setMessage("")} aria-label="关闭">×</button></div>}
        <section className="metric-grid" aria-label="运行指标">
          <article><span>当前状态</span><strong>{selected ? <Status value={selected.status} /> : "暂无运行"}</strong><small>{selected?.name ?? "创建第一个测试计划"}</small></article>
          <article><span>场景进度</span><strong>{selected ? `${selected.completed_scenarios} / ${selected.total_scenarios}` : "—"}</strong><small>Provider × 并发档位</small></article>
          <article><span>平均 QPS</span><strong>{stats.qps ? stats.qps.toFixed(1) : "—"}</strong><small>已完成场景</small></article>
          <article><span>平均 P95</span><strong>{stats.p95 ? `${stats.p95.toFixed(0)} ms` : "—"}</strong><small>{stats.success ? `${stats.success.toFixed(1)}% 成功率` : "等待结果"}</small></article>
        </section>

        <div className="workspace-grid">
          <section className="panel run-panel">
            <div className="panel-head">
              <div><p className="eyebrow">ACTIVE PLAN</p><h2>{selected?.name ?? "尚未创建测试"}</h2></div>
              {selected && <Status value={selected.status} />}
            </div>
            {selected ? <>
              <div className="run-meta">
                <div><span>测试类型</span><strong>{selected.benchmark}</strong></div>
                <div><span>并发档位</span><strong>{selected.concurrency_levels.join(" / ")}</strong></div>
                <div><span>每场景请求</span><strong>{selected.requests_per_scenario}</strong></div>
                <div><span>创建时间</span><strong>{formatTime(selected.created_at)}</strong></div>
              </div>
              <div className="progress"><span style={{ width: `${selected.total_scenarios ? selected.completed_scenarios / selected.total_scenarios * 100 : 0}%` }} /></div>
              {activeScenario && <div className="active-request">
                <div><span>当前场景</span><strong>{activeScenario.provider_name || activeScenario.provider} · c={activeScenario.concurrency}</strong></div>
                <div><span>请求进度</span><strong>{activeScenario.completed_requests ?? 0} / {activeScenario.total_requests ?? selected.requests_per_scenario}</strong></div>
                <div><span>已运行</span><strong>{Math.floor(activeElapsed / 60).toString().padStart(2, "0")}:{(activeElapsed % 60).toString().padStart(2, "0")}</strong></div>
                <div className="request-progress"><i style={{ width: `${(activeScenario.completed_requests ?? 0) / Math.max(activeScenario.total_requests ?? selected.requests_per_scenario, 1) * 100}%` }} /></div>
              </div>}
              <div className="scenario-strip">
                {selected.scenarios.map((scenario) => <div className={`scenario ${scenario.status}`} key={scenario.id} title={scenario.error ?? scenario.id}>
                  <span>{scenario.provider_name || scenario.provider}</span><strong>c={scenario.concurrency}{scenario.status === "running" ? ` · ${scenario.completed_requests ?? 0}/${scenario.total_requests ?? selected.requests_per_scenario}` : ""}</strong>
                </div>)}
              </div>
              {selected.status === "running" && <button className="ghost danger" onClick={cancel}>取消运行</button>}
              {TERMINAL.has(selected.status) && <button className="ghost" onClick={rerun}>按此计划再次运行</button>}
              {selected.error && <p className="error-text">{selected.error}</p>}
              {failedScenarios.length > 0 && <div className="failure-summary" role="alert">
                <strong>{failedScenarios.length} 个场景失败</strong>
                <span>{failedScenarios[0].provider_name || failedScenarios[0].provider} · c={failedScenarios[0].concurrency}：{failedScenarios[0].error || "没有成功请求，请检查服务配置"}</span>
              </div>}
            </> : <div className="empty-state">在右侧配置 Provider 和并发档位，然后启动测试。</div>}
          </section>

          <section className="panel config-panel" id="new-run">
            <div className="panel-head"><div><p className="eyebrow">NEW PLAN</p><h2>测试配置</h2></div></div>
            {catalog && <form onSubmit={submit}>
              <fieldset><legend>测试类型</legend><div className="segmented">{catalog.benchmarks.map((item) => <button type="button" className={item.id === benchmarkId ? "active" : ""} onClick={() => changeBenchmark(item)} key={item.id}>{item.label}</button>)}</div></fieldset>
              <fieldset><legend>Providers</legend><div className="provider-list">{benchmark?.providers.map((provider) => {
                const checked = providerIds.includes(provider.id);
                return <label className={`${checked ? "checked" : ""} ${!provider.endpoint_configured ? "disabled" : ""}`} key={provider.id}>
                  <input type="checkbox" disabled={!provider.endpoint_configured} checked={checked} onChange={() => setProviderIds((current) => checked ? current.filter((id) => id !== provider.id) : [...current, provider.id])} />
                  <span><strong>{provider.label}</strong><small>{provider.model ?? "服务器配置"}</small></span>
                  <i className={provider.endpoint_configured ? "ready" : "warning"}>{provider.endpoint_configured ? "已配置" : "待配置"}</i>
                </label>;
              })}</div></fieldset>
              <label className="field"><span>并发档位</span><input value={levels} onChange={(event) => setLevels(event.target.value)} placeholder="1, 5, 10, 20, 30" /><small>逗号分隔；至少填写两个档位才能形成对比曲线</small></label>
              {benchmarkId.startsWith("dify-") && <label className="field"><span>Query</span><textarea required value={difyQuery} onChange={(event) => setDifyQuery(event.target.value)} placeholder="输入本次测试使用的问题" /></label>}
              {benchmarkId === "dify-retrieve" && <label className="field"><span>Dataset ID</span><input required value={difyDatasetId} onChange={(event) => setDifyDatasetId(event.target.value)} placeholder="Dify 知识库 Dataset ID" /></label>}
              <div className="field-row">
                <label className="field"><span>每场景请求数</span><input type="number" min="1" value={requests} onChange={(event) => setRequests(Number(event.target.value))} /></label>
                <label className="field"><span>超时（秒）</span><input type="number" min="1" value={timeout} onChange={(event) => setTimeout(Number(event.target.value))} /></label>
              </div>
              <div className="matrix-note"><span>预计场景数</span><strong>{providerIds.length} × {levels.split(/[，,\s]+/).filter(Boolean).length} = {providerIds.length * levels.split(/[，,\s]+/).filter(Boolean).length}</strong></div>
              <button className="primary" disabled={submitting || !providerIds.length}>{submitting ? "正在创建…" : "开始测试"}<span>→</span></button>
            </form>}
          </section>
        </div>

        <section className="charts-grid">
          <article className="panel chart-panel"><div className="panel-head"><div><p className="eyebrow">THROUGHPUT</p><h2>吞吐量对比</h2></div><span className="unit">QPS</span></div><LineChart scenarios={selected?.scenarios ?? []} metric="qps" /></article>
          <article className="panel chart-panel"><div className="panel-head"><div><p className="eyebrow">LATENCY</p><h2>延迟对比</h2></div><div className="metric-toggle">{(["p50", "p95", "p99"] as const).map((item) => <button className={latencyMetric === item ? "active" : ""} onClick={() => setLatencyMetric(item)} key={item}>{item.toUpperCase()}</button>)}</div></div><LineChart scenarios={selected?.scenarios ?? []} metric={latencyMetric} /></article>
        </section>

        <section className="panel history" id="history">
          <div className="panel-head"><div><p className="eyebrow">HISTORY</p><h2>运行记录</h2></div><span className="unit">最近 {runs.length} 次</span></div>
          <div className="table-scroll"><table><thead><tr><th>状态</th><th>测试计划</th><th>类型</th><th>场景</th><th>进度</th><th>创建时间</th></tr></thead><tbody>{runs.map((run) => <tr className={selected?.id === run.id ? "selected" : ""} onClick={() => setSelectedId(run.id)} key={run.id}><td><Status value={run.status} /></td><td><strong>{run.name}</strong><small>{run.id}</small></td><td>{run.benchmark}</td><td>{run.total_scenarios}</td><td>{run.completed_scenarios} / {run.total_scenarios}</td><td>{formatTime(run.created_at)}</td></tr>)}</tbody></table>{!runs.length && <div className="empty-state">暂无运行记录</div>}</div>
        </section>

        <section className="settings-grid" id="settings">
          <article className="panel">
            <div className="panel-head"><div><p className="eyebrow">SERVICES</p><h2>服务配置</h2></div><span className="unit">SQLite 持久化</span></div>
            <div className="service-list">{serviceConfigs.map((config) => <button type="button" onClick={() => editServiceConfig(config)} key={config.id}>
              <span className={config.has_api_key ? "service-icon secure" : "service-icon"}>{config.has_api_key ? "◆" : "◇"}</span>
              <span><strong>{config.name}</strong><small>{config.benchmark} · {config.provider} · {config.model ?? "未指定模型"}</small></span>
              <i className={!config.endpoint_configured ? "invalid" : ""}>{!config.endpoint_configured ? "Endpoint 待配置" : config.has_api_key ? "密钥已加密" : "无密钥"}</i>
            </button>)}</div>
          </article>
          <article className="panel">
            <div className="panel-head"><div><p className="eyebrow">{editingConfigId ? "EDIT SERVICE" : "ADD SERVICE"}</p><h2>{editingConfigId ? "编辑服务" : "新增服务"}</h2></div>{editingConfigId && <button className="ghost" onClick={() => setEditingConfigId(null)}>取消编辑</button>}</div>
            <form className="service-form" autoComplete="off" onSubmit={saveServiceConfig}>
              <div className="field-row">
                <label className="field"><span>测试类型</span><select value={configBenchmark} onChange={(event) => {
                  const next = event.target.value;
                  setConfigBenchmark(next);
                  const info = catalog?.benchmarks.find((item) => item.id === next);
                  if (info?.provider_kinds[0]) setConfigProvider(info.provider_kinds[0].id);
                }}>{catalog?.benchmarks.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label>
                <label className="field"><span>Provider 类型</span><select value={configProvider} onChange={(event) => setConfigProvider(event.target.value)}>{configBenchmarkInfo?.provider_kinds.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label>
              </div>
              <label className="field"><span>配置名称</span><input required value={configName} onChange={(event) => setConfigName(event.target.value)} /></label>
              <label className="field"><span>Endpoint</span><input value={configUrl} onChange={(event) => setConfigUrl(event.target.value)} placeholder="https://host/v1/rerank" /></label>
              <label className="field"><span>模型</span><input value={configModel} onChange={(event) => setConfigModel(event.target.value)} /></label>
              <label className="field"><span>{configBenchmark === "dify-retrieve" ? "Dataset API Key" : "API Key"}</span><input type="password" autoComplete="new-password" value={configApiKey} onChange={(event) => setConfigApiKey(event.target.value)} placeholder={editingConfigId ? "留空表示保留现有密钥" : "留空表示服务不需要密钥"} /><small>使用服务器主密钥加密后写入 SQLite，保存后不再显示。</small></label>
              <button className="primary" disabled={savingConfig}>{savingConfig ? "正在保存…" : editingConfigId ? "更新服务配置" : "保存服务配置"}<span>→</span></button>
            </form>
          </article>
        </section>
      </div>
    </main>
  </div>;
}
