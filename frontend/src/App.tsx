import { FormEvent, useEffect, useState } from "react";
import { api, subscribeToRun } from "./api";
import { PerfCharts } from "./components/PerfCharts";
import { Playground } from "./components/Playground";
import { ProviderManager } from "./components/ProviderManager";
import { providerDisplayName } from "./providerPresets";
import { tr, type Language } from "./i18n";
import type { Benchmark, Catalog, ProviderIcon, Run, ServiceConfig } from "./types";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
const TABS = ["overview", "new-run", "playground", "history", "settings", "dify", "api"] as const;
type Tab = typeof TABS[number];
const DEFAULT_LEVELS = [1, 5, 10, 20, 40, 80];
function Status({ value, language }: { value: string; language: Language }) {
  const label: Record<string, string> = { queued: "等待中", running: "运行中", completed: "已完成", failed: "失败", cancelled: "已取消" };
  return <span className={`status status-${value}`}><i />{tr(language, label[value] ?? value)}</span>;
}

function formatTime(value: string, language: Language) {
  return new Intl.DateTimeFormat(language, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

export default function App() {
  const [language, setLanguage] = useState<Language>(() => {
    const saved = localStorage.getItem("perflab-language");
    return saved === "en" || saved === "zh-CN" ? saved : navigator.language.startsWith("zh") ? "zh-CN" : "en";
  });
  const [themeMode, setThemeMode] = useState<"system" | "dark" | "light">(() => {
    const saved = localStorage.getItem("perflab-theme");
    return saved === "dark" || saved === "light" ? saved : "system";
  });
  const [resolvedDark, setResolvedDark] = useState(() => document.documentElement.dataset.theme !== "light");
  const t = (value: string) => tr(language, value);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [serviceConfigs, setServiceConfigs] = useState<ServiceConfig[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [benchmarkId, setBenchmarkId] = useState("reranker");
  const [providerIds, setProviderIds] = useState<string[]>([]);
  const [selectedModels, setSelectedModels] = useState<Record<string, string>>({});
  const [selectedCredentials, setSelectedCredentials] = useState<Record<string, string>>({});
  const [levels, setLevels] = useState<number[]>([1, 5, 10, 20]);
  const [customLevel, setCustomLevel] = useState("");
  const [levelMenuOpen, setLevelMenuOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>(() => {
    const hash = window.location.hash.slice(1);
    return TABS.includes(hash as Tab) ? hash as Tab : "overview";
  });
  const [requests, setRequests] = useState(100);
  const [timeout, setTimeout] = useState(60);
  const [difyQuery, setDifyQuery] = useState("");
  const [difyDatasetId, setDifyDatasetId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [configBenchmark, setConfigBenchmark] = useState("reranker");
  const [configName, setConfigName] = useState("");
  const [configUrl, setConfigUrl] = useState("");
  const [configIcon, setConfigIcon] = useState<ProviderIcon>("cube");
  const [configApiKey, setConfigApiKey] = useState("");
  const [savingConfig, setSavingConfig] = useState(false);
  const [editingConfigId, setEditingConfigId] = useState<string | null>(null);
  const [, setClock] = useState(0);

  const selected = runs.find((run) => run.id === selectedId) ?? runs[0] ?? null;
  const benchmark = catalog?.benchmarks.find((item) => item.id === benchmarkId) ?? null;
  const difyConfigs = serviceConfigs.filter((config) => config.provider === "dify");

  useEffect(() => {
    localStorage.setItem("perflab-language", language);
    document.documentElement.lang = language;
    document.title = `PerfLab · ${tr(language, "性能测试台")}`;
  }, [language]);

  useEffect(() => {
    localStorage.setItem("perflab-theme", themeMode);
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => { const dark = themeMode === "system" ? media.matches : themeMode === "dark"; document.documentElement.dataset.theme = dark ? "dark" : "light"; setResolvedDark(dark); };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [themeMode]);

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
    const onHashChange = () => {
      const hash = window.location.hash.slice(1);
      if (TABS.includes(hash as Tab)) setActiveTab(hash as Tab);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
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

  const failedScenarios = selected?.scenarios.filter((item) => item.status === "failed") ?? [];
  const activeScenario = selected?.scenarios.find((item) => item.status === "running") ?? null;
  const activeElapsed = activeScenario?.started_at
    ? Math.max(0, Math.floor((Date.now() - new Date(activeScenario.started_at).getTime()) / 1000))
    : 0;

  function changeBenchmark(next: Benchmark) {
    setBenchmarkId(next.id);
    setProviderIds(next.providers.filter((item) => item.endpoint_configured).slice(0, 2).map((item) => item.id));
    setSelectedModels({});
  }

  function navigate(tab: Tab) {
    window.location.hash = tab;
    setActiveTab(tab);
    window.scrollTo(0, 0);
  }

  function addConcurrencyLevel() {
    const value = Number(customLevel);
    if (!Number.isInteger(value) || value < 1 || value > 10000) {
      setMessage(t("自定义并发档位请输入 1–10000 的整数。"));
      return;
    }
    setLevels((current) => [...new Set([...current, value])].sort((a, b) => a - b));
    setCustomLevel("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!providerIds.length || !levels.length || !benchmark) {
      setMessage(t(benchmarkId.startsWith("dify-") ? "请至少选择一个 Dify 配置和一个并发档位。" : "请至少选择一个模型供应商和一个并发档位。"));
      return;
    }
    setSubmitting(true);
    setMessage("");
    try {
      const run = await api.createRun({
        name: `${benchmark.label} ${t("对比测试")}`,
        benchmark: benchmark.id,
        providers: providerIds.map((id) => ({ id, model: selectedModels[id] || benchmark.providers.find((item) => item.id === id)?.models[0]?.alias || benchmark.providers.find((item) => item.id === id)?.models[0]?.name || null, credential_id: selectedCredentials[id] || null })),
        concurrency_levels: levels,
        requests_per_scenario: requests,
        timeout_seconds: timeout,
        query: benchmark.id.startsWith("dify-") ? difyQuery : null,
        dataset_id: benchmark.id === "dify-retrieve" ? difyDatasetId : null,
      });
      setRuns((current) => [run, ...current]);
      setSelectedId(run.id);
      navigate("overview");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("创建测试失败"));
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
      setMessage(error instanceof Error ? error.message : t("取消失败"));
    }
  }

  async function rerun() {
    if (!selected) return;
    try {
      const run = await api.runPlan(selected.plan_id);
      setRuns((current) => [run, ...current]);
      setSelectedId(run.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("重新运行失败"));
    }
  }

  async function deleteRun(run: Run) {
    if (!window.confirm(`${t("删除运行记录")} “${run.name}”? ${t("此操作无法撤销。")}`)) return;
    try {
      await api.deleteRun(run.id);
      const remaining = runs.filter((item) => item.id !== run.id);
      setRuns(remaining);
      if (selectedId === run.id) setSelectedId(remaining[0]?.id ?? null);
      setMessage(t("运行记录已删除。"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("删除运行记录失败"));
    }
  }

  async function saveServiceConfig(event: FormEvent) {
    event.preventDefault();
    setSavingConfig(true);
    setMessage("");
    try {
      const payload = {
        name: configName,
        provider: "dify",
        models: [{ name: null, benchmark: configBenchmark.startsWith("dify-") ? configBenchmark : "dify-retrieve", base_url: configUrl.trim() }],
        icon: configIcon,
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
      setSelectedModels({});
      setConfigApiKey("");
      setEditingConfigId(null);
      setConfigName("");
      setConfigUrl("");
      setConfigIcon("cube");
      setMessage(`${t("Dify 配置")} “${config.name}” ${t("已保存")}${config.has_api_key ? ` · ${t("API Key 已加密")}` : ""}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("保存服务配置失败"));
    } finally {
      setSavingConfig(false);
    }
  }

  async function deleteServiceConfig(config: ServiceConfig) {
    if (!window.confirm(`${t(config.provider === "dify" ? "删除 Dify 配置" : "删除模型供应商")} “${config.name}”? ${t("此操作无法撤销。")}`)) return;
    try {
      await api.deleteServiceConfig(config.id);
      setServiceConfigs((current) => current.filter((item) => item.id !== config.id));
      setCatalog(await api.catalog());
      setProviderIds((current) => current.filter((id) => id !== config.id));
      if (editingConfigId === config.id) setEditingConfigId(null);
      setMessage(t(config.provider === "dify" ? "Dify 配置已删除。" : "模型供应商已删除。"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t(config.provider === "dify" ? "删除 Dify 配置失败" : "删除模型供应商失败"));
    }
  }

  function editServiceConfig(config: ServiceConfig) {
    setEditingConfigId(config.id);
    setConfigBenchmark(config.models[0]?.benchmark ?? config.benchmark);
    setConfigName(config.name);
    setConfigUrl(config.models[0]?.base_url ?? "");
    setConfigIcon(config.icon ?? "cube");
    setConfigApiKey("");
    navigate("dify");
  }

  function startDifyConfig() {
    setEditingConfigId(null);
    setConfigBenchmark("dify-retrieve");
    setConfigName("");
    setConfigUrl("");
    setConfigApiKey("");
    navigate("dify");
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><i /><i /><i /></span><span>PerfLab</span></div>
      <nav aria-label={t("主导航")}>
        <button className={activeTab === "overview" ? "active" : ""} onClick={() => navigate("overview")}><span>⌁</span>{t("概览")}</button>
        <button className={activeTab === "new-run" ? "active" : ""} onClick={() => navigate("new-run")}><span>＋</span>{t("新建测试")}</button>
        <button className={activeTab === "playground" ? "active" : ""} onClick={() => navigate("playground")}><span>▷</span>Playground</button>
        <button className={activeTab === "history" ? "active" : ""} onClick={() => navigate("history")}><span>≡</span>{t("运行记录")}</button>
        <button className={activeTab === "settings" ? "active" : ""} onClick={() => navigate("settings")}><span>⚙</span>{t("模型供应商")}</button>
        <button className={activeTab === "dify" ? "active" : ""} onClick={startDifyConfig}><span>◈</span>{t("Dify 配置")}</button>
        <button className={activeTab === "api" ? "active" : ""} onClick={() => navigate("api")}><span>◇</span>API</button>
      </nav>
    </aside>

    <main>
      <header className="topbar">
        <div><p className="eyebrow">AI MODEL BENCHMARKS</p><h1>{t(({ overview: "性能测试台", "new-run": "新建测试", playground: "Playground", history: "运行记录", settings: "模型供应商", dify: "Dify 配置", api: "API 文档" } as Record<Tab, string>)[activeTab])}</h1></div>
        <div className="preferences">
          <label className="preference-control" title={`${t("语言")}：${language === "zh-CN" ? "简体中文" : "English"}`}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.5 3.7 5.5 3.7 9S14.5 18.5 12 21M12 3c-2.5 2.5-3.7 5.5-3.7 9s1.2 6.5 3.7 9" /></svg>
            <span className="preference-badge" aria-hidden="true">{language === "zh-CN" ? "中" : "EN"}</span>
            <select aria-label={t("语言")} value={language} onChange={(event) => setLanguage(event.target.value as Language)}><option value="zh-CN">简体中文</option><option value="en">English</option></select>
          </label>
          <label className="preference-control" title={`${t("主题")}：${t(themeMode === "system" ? "跟随系统" : themeMode === "dark" ? "深色" : "浅色")}`}>
            {themeMode === "dark" ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20.5 14.4A8.7 8.7 0 0 1 9.6 3.5 8.7 8.7 0 1 0 20.5 14.4Z" /></svg> : themeMode === "light" ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" /></svg> : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="14" rx="2" /><path d="M8 22h8m-4-4v4" /></svg>}
            <select aria-label={t("主题")} value={themeMode} onChange={(event) => setThemeMode(event.target.value as "system" | "dark" | "light")}><option value="system">{t("跟随系统")}</option><option value="dark">{t("深色")}</option><option value="light">{t("浅色")}</option></select>
          </label>
        </div>
      </header>

      <div className="content">
        {message && <div className="alert" role="alert">{message}<button onClick={() => setMessage("")} aria-label={t("关闭")}>×</button></div>}
        {activeTab === "playground" && <Playground catalog={catalog} language={language} />}
        {activeTab === "overview" && <>
        <section className="metric-grid compact" aria-label={t("运行指标")}>
          <article><span>{t("当前状态")}</span><strong>{selected ? <Status value={selected.status} language={language} /> : t("暂无运行")}</strong><small>{selected?.name ?? t("创建第一个测试计划")}</small></article>
          <article><span>{t("场景进度")}</span><strong>{selected ? `${selected.completed_scenarios} / ${selected.total_scenarios}` : "—"}</strong><small>Provider × {t("并发档位")}</small></article>
        </section>

        </>}
        {(activeTab === "overview" || activeTab === "new-run") && <div className="workspace-grid single">
          {activeTab === "overview" &&
          <section className="panel run-panel">
            <div className="panel-head">
              <div><p className="eyebrow">ACTIVE PLAN</p><h2>{selected?.name ?? t("尚未创建测试")}</h2></div>
              {selected && <Status value={selected.status} language={language} />}
            </div>
            {selected ? <>
              <div className="run-meta">
                <div><span>{t("测试类型")}</span><strong>{selected.benchmark}</strong></div>
                <div><span>{t("并发档位")}</span><strong>{selected.concurrency_levels.join(" / ")}</strong></div>
                <div><span>{t("每场景请求")}</span><strong>{selected.requests_per_scenario}</strong></div>
                <div><span>{t("创建时间")}</span><strong>{formatTime(selected.created_at, language)}</strong></div>
              </div>
              <div className="progress"><span style={{ width: `${selected.total_scenarios ? selected.completed_scenarios / selected.total_scenarios * 100 : 0}%` }} /></div>
              {activeScenario && <div className="active-request">
                <div><span>{t("当前场景")}</span><strong>{activeScenario.provider_name || activeScenario.provider} · c={activeScenario.concurrency}</strong></div>
                <div><span>{t("请求进度")}</span><strong>{activeScenario.completed_requests ?? 0} / {activeScenario.total_requests ?? selected.requests_per_scenario}</strong></div>
                <div><span>{t("已运行")}</span><strong>{Math.floor(activeElapsed / 60).toString().padStart(2, "0")}:{(activeElapsed % 60).toString().padStart(2, "0")}</strong></div>
                <div className="request-progress"><i style={{ width: `${(activeScenario.completed_requests ?? 0) / Math.max(activeScenario.total_requests ?? selected.requests_per_scenario, 1) * 100}%` }} /></div>
              </div>}
              <div className="scenario-strip">
                {selected.scenarios.map((scenario) => <div className={`scenario ${scenario.status}`} key={scenario.id} title={scenario.error ?? scenario.id}>
                  <span>{scenario.provider_name || scenario.provider}</span><strong>c={scenario.concurrency}{scenario.status === "running" ? ` · ${scenario.completed_requests ?? 0}/${scenario.total_requests ?? selected.requests_per_scenario}` : ""}</strong>
                </div>)}
              </div>
              {selected.status === "running" && <button className="ghost danger" onClick={cancel}>{t("取消运行")}</button>}
              {TERMINAL.has(selected.status) && <button className="ghost" onClick={rerun}>{t("按此计划再次运行")}</button>}
              {selected.error && <p className="error-text">{selected.error}</p>}
              {failedScenarios.length > 0 && <div className="failure-summary" role="alert">
                <strong>{failedScenarios.length} {t("个场景失败")}</strong>
                <span>{failedScenarios[0].provider_name || failedScenarios[0].provider} · c={failedScenarios[0].concurrency}：{failedScenarios[0].error || t("没有成功请求，请检查服务配置")}</span>
              </div>}
            </> : <div className="empty-state">{t("前往“新建测试”选择模型和并发档位。")}</div>}
          </section>}

          {activeTab === "new-run" && <section className="panel config-panel">
            <div className="panel-head"><div><p className="eyebrow">NEW PLAN</p><h2>{t("测试配置")}</h2></div></div>
            {catalog && <form onSubmit={submit}>
              <fieldset><legend>{t("测试类型")}</legend><div className="segmented">{catalog.benchmarks.map((item) => <button type="button" className={item.id === benchmarkId ? "active" : ""} onClick={() => changeBenchmark(item)} key={item.id}>{item.label}</button>)}</div></fieldset>
              <fieldset><legend>{t(benchmarkId.startsWith("dify-") ? "Dify 配置" : "模型供应商与模型")}</legend><div className="provider-list">{benchmark?.providers.map((provider) => {
                const checked = providerIds.includes(provider.id);
                return <label className={`${checked ? "checked" : ""} ${!provider.endpoint_configured ? "disabled" : ""}`} key={provider.id}>
                  <input type="checkbox" disabled={!provider.endpoint_configured} checked={checked} onChange={() => setProviderIds((current) => checked ? current.filter((id) => id !== provider.id) : [...current, provider.id])} />
                  <span><strong>{benchmarkId.startsWith("dify-") ? "◈ " : ""}{providerDisplayName(provider.provider || provider.id, language, provider.label)}</strong><small>{benchmarkId.startsWith("dify-") ? t("Dify 服务") : provider.models.length ? language === "en" ? `${provider.models.length} ${provider.models.length === 1 ? "model" : "models"}` : `${provider.models.length} 个模型` : t("无模型")}</small></span>
                  <i className={provider.endpoint_configured ? "ready" : "warning"}>{provider.endpoint_configured ? t("已配置") : t("待配置")}</i>
                  {checked && provider.models.some((model) => model.name) && <select className="model-select" value={selectedModels[provider.id] || provider.models[0]?.alias || provider.models[0]?.name || ""} onClick={(event) => event.stopPropagation()} onChange={(event) => { setSelectedModels((current) => ({ ...current, [provider.id]: event.target.value })); setSelectedCredentials((current) => ({ ...current, [provider.id]: "" })); }} aria-label={`${provider.label} ${t("模型")}`}>{provider.models.filter((model) => model.name).map((model) => <option key={`${model.benchmark}-${model.alias || model.name}`} value={model.alias || model.name || ""}>{model.alias || model.name}</option>)}</select>}
                  {checked && (() => { const model = provider.models.find((item) => (item.alias || item.name) === (selectedModels[provider.id] || provider.models[0]?.alias || provider.models[0]?.name)); const credentials = model?.credentials || []; return credentials.length > 1 ? <select className="model-select" required value={selectedCredentials[provider.id] || ""} onClick={(event) => event.stopPropagation()} onChange={(event) => setSelectedCredentials((current) => ({ ...current, [provider.id]: event.target.value }))} aria-label={`${provider.label} ${t("凭据")}`}><option value="">{t("选择凭据")}</option>{credentials.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select> : null; })()}
                </label>;
              })}</div></fieldset>
              <fieldset><legend>{t("并发档位")}</legend><div className="multi-select"><button type="button" className="multi-select-trigger" aria-expanded={levelMenuOpen} onClick={() => setLevelMenuOpen((open) => !open)}>{levels.length ? levels.join("、") : t("选择并发档位")}<span>⌄</span></button>{levelMenuOpen && <div className="multi-select-menu">{[...new Set([...DEFAULT_LEVELS, ...levels])].sort((a, b) => a - b).map((level) => <label key={level}><input type="checkbox" checked={levels.includes(level)} onChange={() => setLevels((current) => current.includes(level) ? current.filter((item) => item !== level) : [...current, level].sort((a, b) => a - b))} />{level}</label>)}<div className="custom-level"><input type="number" min="1" max="10000" placeholder={t("自定义档位")} value={customLevel} onChange={(event) => setCustomLevel(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addConcurrencyLevel(); } }} /><button type="button" onClick={addConcurrencyLevel}>{t("添加")}</button></div></div>}</div><small className="field-help">{t("可多选，也可添加 1–10000 的自定义档位")}</small></fieldset>
              {benchmarkId.startsWith("dify-") && <label className="field"><span>Query</span><textarea required value={difyQuery} onChange={(event) => setDifyQuery(event.target.value)} placeholder={t("输入本次测试使用的问题")} /></label>}
              {benchmarkId === "dify-retrieve" && <label className="field"><span>Dataset ID</span><input required value={difyDatasetId} onChange={(event) => setDifyDatasetId(event.target.value)} placeholder={t("Dify 知识库 Dataset ID")} /></label>}
              <div className="field-row">
                <label className="field"><span>{t("每场景请求数")}</span><input type="number" min="1" value={requests} onChange={(event) => setRequests(Number(event.target.value))} /></label>
                <label className="field"><span>{t("超时（秒）")}</span><input type="number" min="1" value={timeout} onChange={(event) => setTimeout(Number(event.target.value))} /></label>
              </div>
              <div className="matrix-note"><span>{t("预计场景数")}</span><strong>{providerIds.length} × {levels.length} = {providerIds.length * levels.length}</strong></div>
              <button className="primary" disabled={submitting || !providerIds.length}>{submitting ? t("正在创建…") : t("开始测试")}<span>→</span></button>
            </form>}
          </section>}
        </div>}

        {activeTab === "overview" && <PerfCharts run={selected} language={language} dark={resolvedDark} />}

        {activeTab === "history" && <section className="panel history">
          <div className="panel-head"><div><p className="eyebrow">HISTORY</p><h2>{t("运行记录")}</h2></div><span className="unit">{t("最近")} {runs.length} {t("次")}</span></div>
          <div className="table-scroll"><table><thead><tr><th>{t("状态")}</th><th>{t("测试计划")}</th><th>{t("类型")}</th><th>{t("场景")}</th><th>{t("进度")}</th><th>{t("创建时间")}</th><th>{t("操作")}</th></tr></thead><tbody>{runs.map((run) => <tr className={selected?.id === run.id ? "selected" : ""} onClick={() => { setSelectedId(run.id); navigate("overview"); }} key={run.id}><td><Status value={run.status} language={language} /></td><td><strong>{run.name}</strong><small>{run.id}</small></td><td>{run.benchmark}</td><td>{run.total_scenarios}</td><td>{run.completed_scenarios} / {run.total_scenarios}</td><td>{formatTime(run.created_at, language)}</td><td><button type="button" className="ghost danger" disabled={!TERMINAL.has(run.status)} onClick={(event) => { event.stopPropagation(); void deleteRun(run); }}>{t("删除")}</button></td></tr>)}</tbody></table>{!runs.length && <div className="empty-state">{t("暂无运行记录")}</div>}</div>
        </section>}

        {activeTab === "settings" && <ProviderManager configs={serviceConfigs} benchmarks={catalog?.benchmarks || []} language={language} onChanged={async () => { const [nextConfigs, nextCatalog] = await Promise.all([api.serviceConfigs(), api.catalog()]); setServiceConfigs(nextConfigs); setCatalog(nextCatalog); }} />}
        {activeTab === "dify" && <section className="settings-grid">
          <article className="panel">
            <div className="panel-head"><div><p className="eyebrow">DIFY SERVICES</p><h2>{t("Dify 配置")}</h2></div><span className="unit">{difyConfigs.length} {t("个")}</span></div>
            <div className="service-list">{difyConfigs.map((config) => <div className="service-item" key={config.id}>
              <span className={config.has_api_key ? "service-icon secure" : "service-icon"}>◈</span>
              <span><strong>{config.name}</strong><small>{config.models[0]?.benchmark === "dify-chat" ? t("聊天应用") : t("知识库检索")}</small><small>{config.models[0]?.base_url || t("Endpoint 待配置")}</small></span>
              <div className="service-actions"><button type="button" className="ghost" onClick={() => editServiceConfig(config)}>{t("编辑")}</button><button type="button" className="ghost danger" onClick={() => void deleteServiceConfig(config)}>{t("删除")}</button></div>
            </div>)}{!difyConfigs.length && <div className="empty-state">{t("暂无 Dify 配置")}</div>}</div>
          </article>
          <article className="panel">
            <div className="panel-head"><div><p className="eyebrow">{editingConfigId ? "EDIT DIFY" : "ADD DIFY"}</p><h2>{t(editingConfigId ? "编辑 Dify 配置" : "新增 Dify 配置")}</h2></div>{editingConfigId && <button className="ghost" onClick={startDifyConfig}>{t("取消编辑")}</button>}</div>
            <form className="service-form" autoComplete="off" onSubmit={saveServiceConfig}>
              <label className="field"><span>{t("配置名称")}</span><input required value={configName} onChange={(event) => setConfigName(event.target.value)} placeholder={t("例如 Dify 生产环境")} /></label>
              <label className="field"><span>{t("Dify 类型")}</span><select value={configBenchmark.startsWith("dify-") ? configBenchmark : "dify-retrieve"} onChange={(event) => setConfigBenchmark(event.target.value)}><option value="dify-retrieve">{t("知识库检索")}</option><option value="dify-chat">{t("聊天应用")}</option></select></label>
              <label className="field"><span>{t("Dify 服务地址")}</span><input required type="url" value={configUrl} onChange={(event) => setConfigUrl(event.target.value)} placeholder="https://host" /></label>
              <label className="field"><span>{configBenchmark === "dify-chat" ? "Chat API Key" : "Dataset API Key"}</span><input type="password" autoComplete="new-password" value={configApiKey} onChange={(event) => setConfigApiKey(event.target.value)} placeholder={editingConfigId ? t("留空表示保留现有密钥") : configBenchmark === "dify-chat" ? t("填写 Chat API Key") : t("填写 Dataset API Key")} /></label>
              <button className="primary" disabled={savingConfig || !configUrl.trim()}>{savingConfig ? t("保存中…") : t("保存")}<span>→</span></button>
            </form>
          </article>
        </section>}
        {activeTab === "api" && <section className="panel api-docs"><div className="panel-head"><div><p className="eyebrow">OPENAPI</p><h2>{t("接口文档")}</h2></div><a className="ghost" href="/api/docs" target="_blank" rel="noreferrer">{t("在新窗口打开")}</a></div><iframe title="PerfLab API docs" src="/api/docs" /></section>}
      </div>
    </main>
  </div>;
}
