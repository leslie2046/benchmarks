import { FormEvent, useEffect, useState } from "react";
import {
  Activity, BookOpen, Boxes, CalendarClock, ChevronDown, Database, FlaskConical,
  History, KeyRound, Languages, LayoutDashboard, Menu, Monitor, Moon, Pencil, Play,
  Plus, Pause, Square, Sun, Trash2, X,
} from "lucide-react";
import { api, subscribeToRun } from "./api";
import { AnalysisDashboard } from "./components/AnalysisDashboard";
import { InfoTip } from "./components/InfoTip";
import { Overview } from "./components/Overview";
import { Playground } from "./components/Playground";
import { ProviderManager } from "./components/ProviderManager";
import { ProviderLogo } from "./components/ProviderLogo";
import { providerDisplayName } from "./providerPresets";
import { tr, type Language } from "./i18n";
import type { Benchmark, Catalog, ProviderIcon, Run, ServiceConfig, TestPlan } from "./types";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
const TABS = ["overview", "new-run", "history", "dashboard", "playground", "settings", "dify", "api"] as const;
type Tab = typeof TABS[number];
const DEFAULT_LEVELS = [1, 5, 10, 20, 40, 80];
const DEFAULT_TEST_QUERIES: Record<string, string> = {
  embedding: "Artificial intelligence is transforming healthcare through accurate diagnosis and personalized treatment.",
  reranker: "How can I improve smartphone battery life without affecting performance?",
  "dify-retrieve": "What information is most relevant to this question?",
  "dify-chat": "Explain the main idea clearly and concisely.",
};
const DEFAULT_RERANKER_DOCUMENTS = [
  "Reducing screen brightness can significantly extend smartphone battery life.",
  "Closing unused background applications may reduce unnecessary battery consumption.",
  "Using airplane mode in areas with poor signal helps save power.",
  "Playing graphics-intensive games consumes more battery than browsing the web.",
].join("\n");
function Status({ value, language }: { value: string; language: Language }) {
  const label: Record<string, string> = { queued: "等待中", running: "运行中", active: "已启动", paused: "已暂停", stopped: "已停止", completed: "已完成", error: "异常", failed: "失败", cancelled: "已取消" };
  const style = value === "active" ? "running" : value === "error" ? "failed" : value;
  return <span className={`status status-${style}`}><i />{tr(language, label[value] ?? value)}</span>;
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
  const [plans, setPlans] = useState<TestPlan[]>([]);
  const [serviceConfigs, setServiceConfigs] = useState<ServiceConfig[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dashboardPlanId, setDashboardPlanId] = useState<string | null>(null);
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
  const [testQueries, setTestQueries] = useState<Record<string, string>>(DEFAULT_TEST_QUERIES);
  const [rerankerDocuments, setRerankerDocuments] = useState(DEFAULT_RERANKER_DOCUMENTS);
  const [difyDatasetId, setDifyDatasetId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [planName, setPlanName] = useState("");
  const [startMode, setStartMode] = useState<"now" | "scheduled">("now");
  const [scheduledAt, setScheduledAt] = useState("");
  const [repeatMode, setRepeatMode] = useState<"once" | "count" | "forever">("once");
  const [repeatCount, setRepeatCount] = useState(3);
  const [repeatEvery, setRepeatEvery] = useState(1);
  const [repeatUnit, setRepeatUnit] = useState<"minutes" | "hours" | "days">("hours");
  const [planActionId, setPlanActionId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [configBenchmark, setConfigBenchmark] = useState("reranker");
  const [configName, setConfigName] = useState("");
  const [configUrl, setConfigUrl] = useState("");
  const [configIcon, setConfigIcon] = useState<ProviderIcon>("cube");
  const [configApiKey, setConfigApiKey] = useState("");
  const [savingConfig, setSavingConfig] = useState(false);
  const [editingConfigId, setEditingConfigId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const selected = runs.find((run) => run.id === selectedId) ?? runs[0] ?? null;
  const benchmark = catalog?.benchmarks.find((item) => item.id === benchmarkId) ?? null;
  const difyConfigs = serviceConfigs.filter((config) => config.provider === "dify");
  const editingDifyConfig = difyConfigs.find((config) => config.id === editingConfigId) ?? null;

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
    Promise.all([api.catalog(), api.runs(), api.plans(), api.serviceConfigs()]).then(([catalogData, runData, planData, configData]) => {
      setCatalog(catalogData);
      setRuns(runData);
      setPlans(planData);
      setServiceConfigs(configData);
      if (runData[0]) setSelectedId(runData[0].id);
      const initial = catalogData.benchmarks.find((item) => item.id === "reranker") ?? catalogData.benchmarks[0];
      setProviderIds(initial.providers.filter((item) => item.endpoint_configured).slice(0, 2).map((item) => item.id));
    }).catch((error: Error) => setMessage(error.message));
  }, []);

  useEffect(() => {
    if (!plans.some((plan) => plan.status === "active")) return;
    const timer = window.setInterval(() => {
      Promise.all([api.plans(), api.runs()]).then(([planData, runData]) => {
        setPlans(planData);
        setRuns(runData);
      }).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [plans.some((plan) => plan.status === "active")]);

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

  function changeBenchmark(next: Benchmark) {
    setBenchmarkId(next.id);
    setProviderIds(next.providers.filter((item) => item.endpoint_configured).slice(0, 2).map((item) => item.id));
    setSelectedModels({});
  }

  function navigate(tab: Tab) {
    window.location.hash = tab;
    setActiveTab(tab);
    setSidebarOpen(false);
    window.scrollTo(0, 0);
  }

  function openRunAnalysis(run: Run) {
    setSelectedId(run.id);
    setDashboardPlanId(run.plan_id);
    navigate("dashboard");
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
    const query = (testQueries[benchmark.id] || "").trim();
    const documents = rerankerDocuments.split("\n").map((item) => item.trim()).filter(Boolean);
    if ((benchmark.id === "embedding" || benchmark.id === "reranker" || benchmark.id.startsWith("dify-")) && !query) {
      setMessage(t("请填写测试 Query。"));
      return;
    }
    if (benchmark.id === "reranker" && !documents.length) {
      setMessage(t("请至少填写一条 Document。"));
      return;
    }
    setSubmitting(true);
    setMessage("");
    try {
      const multiplier = repeatUnit === "minutes" ? 60 : repeatUnit === "hours" ? 3600 : 86400;
      const plan = await api.createPlan({
        name: planName.trim() || `${benchmark.label} ${t("对比测试")}`,
        benchmark: benchmark.id,
        providers: providerIds.map((id) => ({ id, model: selectedModels[id] || benchmark.providers.find((item) => item.id === id)?.models[0]?.alias || benchmark.providers.find((item) => item.id === id)?.models[0]?.name || null, credential_id: selectedCredentials[id] || null })),
        concurrency_levels: levels,
        requests_per_scenario: requests,
        timeout_seconds: timeout,
        query: benchmark.id === "audio" ? null : query,
        documents: benchmark.id === "reranker" ? documents : [],
        dataset_id: benchmark.id === "dify-retrieve" ? difyDatasetId : null,
        start_at: startMode === "scheduled" && scheduledAt ? new Date(scheduledAt).toISOString() : null,
        repeat_mode: repeatMode,
        repeat_count: repeatMode === "count" ? repeatCount : null,
        repeat_interval_seconds: repeatMode === "once" ? null : repeatEvery * multiplier,
      });
      setPlans((current) => [plan, ...current]);
      setPlanName("");
      setMessage(t("测试计划已保存，可在上方启动。"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("创建测试失败"));
    } finally {
      setSubmitting(false);
    }
  }

  async function controlPlan(plan: TestPlan, action: "start" | "pause" | "stop") {
    setPlanActionId(plan.id);
    setMessage("");
    try {
      const updated = action === "start" ? await api.startPlan(plan.id) : action === "pause" ? await api.pausePlan(plan.id) : await api.stopPlan(plan.id);
      const [planData, runData] = await Promise.all([api.plans(), api.runs()]);
      setPlans(planData.map((item) => item.id === updated.id ? updated : item));
      setRuns(runData);
      if (updated.last_run_id) setSelectedId(updated.last_run_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("测试计划操作失败"));
    } finally {
      setPlanActionId(null);
    }
  }

  async function deletePlan(plan: TestPlan) {
    if (!window.confirm(`${t("删除测试计划")} “${plan.name}”? ${t("历史运行记录会保留。")}`)) return;
    setPlanActionId(plan.id);
    try {
      await api.deletePlan(plan.id);
      setPlans((current) => current.filter((item) => item.id !== plan.id));
      setMessage(t("测试计划已删除，历史运行记录已保留。"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("删除测试计划失败"));
    } finally {
      setPlanActionId(null);
    }
  }

  function repeatDescription(plan: TestPlan) {
    if (plan.repeat_mode === "once") return t("不重复");
    const seconds = plan.repeat_interval_seconds || 0;
    const interval = seconds % 86400 === 0 ? `${seconds / 86400} ${t("天")}` : seconds % 3600 === 0 ? `${seconds / 3600} ${t("小时")}` : `${seconds / 60} ${t("分钟")}`;
    return plan.repeat_mode === "forever" ? `${t("一直重复")} · ${t("每隔")} ${interval}` : `${t("共运行")} ${plan.repeat_count} ${t("次")} · ${t("每隔")} ${interval}`;
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
    {sidebarOpen && <button className="sidebar-scrim" aria-label={t("关闭")} onClick={() => setSidebarOpen(false)} />}
    <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
      <div className="brand"><span className="brand-mark"><Activity aria-hidden="true" /></span><span><strong>PerfLab</strong><small>Model benchmarks</small></span></div>
      <nav aria-label={t("主导航")}>
        <span className="nav-label">Workspace</span>
        <button className={activeTab === "overview" ? "active" : ""} onClick={() => navigate("overview")}><Activity aria-hidden="true" />{t("概览")}</button>
        <button className={activeTab === "new-run" ? "active" : ""} onClick={() => navigate("new-run")}><CalendarClock aria-hidden="true" />{t("测试计划")}</button>
        <button className={activeTab === "history" ? "active" : ""} onClick={() => navigate("history")}><History aria-hidden="true" />{t("运行记录")}</button>
        <button className={activeTab === "dashboard" ? "active" : ""} onClick={() => navigate("dashboard")}><LayoutDashboard aria-hidden="true" />{t("分析看板")}</button>
        <button className={activeTab === "playground" ? "active" : ""} onClick={() => navigate("playground")}><FlaskConical aria-hidden="true" />Playground</button>
        <span className="nav-label">Configuration</span>
        <button className={activeTab === "settings" ? "active" : ""} onClick={() => navigate("settings")}><Boxes aria-hidden="true" />{t("模型供应商")}</button>
        <button className={activeTab === "dify" ? "active" : ""} onClick={() => navigate("dify")}><Database aria-hidden="true" />{t("Dify 配置")}</button>
        <button className={activeTab === "api" ? "active" : ""} onClick={() => navigate("api")}><BookOpen aria-hidden="true" />API</button>
      </nav>
      <div className="sidebar-foot"><span className="live-dot" />Local workspace</div>
    </aside>

    <main>
      <header className="topbar">
        <div className="topbar-title"><button className="mobile-menu" onClick={() => setSidebarOpen(true)} aria-label={t("主导航")}><Menu aria-hidden="true" /></button><div><h1>{t(({ overview: "概览", "new-run": "测试计划", history: "运行记录", dashboard: "分析看板", playground: "Playground", settings: "模型供应商", dify: "Dify 配置", api: "API 文档" } as Record<Tab, string>)[activeTab])}</h1><p>{t(({ overview: "查看所有测试计划与运行记录的整体状态", "new-run": "管理计划、调度规则与测试配置", history: "检查并管理历史测试运行", dashboard: "聚合分析测试计划的多次运行结果", playground: "向已配置的服务发送单次请求", settings: "管理模型、端点与访问凭据", dify: "管理知识库与聊天应用连接", api: "浏览 PerfLab HTTP API" } as Record<Tab, string>)[activeTab])}</p></div></div>
        <div className="preferences">
          <label className="preference-control" title={`${t("语言")}：${language === "zh-CN" ? "简体中文" : "English"}`}>
            <Languages aria-hidden="true" />
            <select aria-label={t("语言")} value={language} onChange={(event) => setLanguage(event.target.value as Language)}><option value="zh-CN">简体中文</option><option value="en">English</option></select>
          </label>
          <label className="preference-control" title={`${t("主题")}：${t(themeMode === "system" ? "跟随系统" : themeMode === "dark" ? "深色" : "浅色")}`}>
            {themeMode === "dark" ? <Moon aria-hidden="true" /> : themeMode === "light" ? <Sun aria-hidden="true" /> : <Monitor aria-hidden="true" />}
            <select aria-label={t("主题")} value={themeMode} onChange={(event) => setThemeMode(event.target.value as "system" | "dark" | "light")}><option value="system">{t("跟随系统")}</option><option value="dark">{t("深色")}</option><option value="light">{t("浅色")}</option></select>
          </label>
        </div>
      </header>

      <div className="content">
        {message && <div className="alert" role="alert"><span>{message}</span><button onClick={() => setMessage("")} aria-label={t("关闭")}><X aria-hidden="true" /></button></div>}
        {activeTab === "playground" && <Playground catalog={catalog} language={language} />}
        {activeTab === "overview" && <Overview plans={plans} runs={runs} language={language} onOpenRun={openRunAnalysis} onOpenPlans={() => navigate("new-run")} onOpenDashboard={() => navigate("dashboard")} />}
        {activeTab === "new-run" && <div className="workspace-grid single">
          {activeTab === "new-run" && <>
          <section className="panel plan-list-panel">
            <div className="panel-head"><div><h2>{t("测试计划")}</h2><p>{t("计划定义何时运行；每次触发都会生成一条独立运行记录。")}</p></div><span className="unit">{plans.length} {t("个")}</span></div>
            <div className="table-scroll"><table className="plan-table"><thead><tr><th>{t("计划")}</th><th>{t("状态")}</th><th>{t("调度规则")}</th><th>{t("下次运行")}</th><th>{t("运行次数")}</th><th>{t("操作")}</th></tr></thead><tbody>{plans.map((plan) => <tr key={plan.id}>
              <td><strong>{plan.name}</strong><small>{plan.benchmark} · {plan.id}</small></td>
              <td><Status value={plan.status} language={language} />{plan.schedule_error && <small className="error-text">{plan.schedule_error}</small>}</td>
              <td>{repeatDescription(plan)}</td>
              <td>{plan.next_run_at && plan.status !== "stopped" ? formatTime(plan.next_run_at, language) : "—"}</td>
              <td>{plan.run_count}</td>
              <td><div className="row-actions">
                {plan.status !== "active" && <button type="button" className="icon-button" title={t("开始计划")} aria-label={t("开始计划")} disabled={planActionId === plan.id} onClick={() => void controlPlan(plan, "start")}><Play aria-hidden="true" /></button>}
                {plan.status === "active" && <button type="button" className="icon-button" title={t("暂停计划")} aria-label={t("暂停计划")} disabled={planActionId === plan.id} onClick={() => void controlPlan(plan, "pause")}><Pause aria-hidden="true" /></button>}
                {(plan.status === "active" || plan.status === "paused") && <button type="button" className="icon-button" title={t("停止计划")} aria-label={t("停止计划")} disabled={planActionId === plan.id} onClick={() => void controlPlan(plan, "stop")}><Square aria-hidden="true" /></button>}
                <button type="button" className="icon-button danger" title={t("删除测试计划")} aria-label={t("删除测试计划")} disabled={planActionId === plan.id} onClick={() => void deletePlan(plan)}><Trash2 aria-hidden="true" /></button>
              </div></td>
            </tr>)}</tbody></table>{!plans.length && <div className="empty-state compact-empty">{t("暂无测试计划，请在下方创建第一个计划。")}</div>}</div>
          </section>
          <section className="panel config-panel">
            <div className="panel-head"><div><h2>{t("新建测试计划")}</h2><p>{t("保存后由你决定何时启动，计划不会自动立即运行。")}</p></div></div>
            {catalog && <form onSubmit={submit}>
              <label className="field"><span>{t("计划名称")} <b className="required">*</b></span><input required value={planName} onChange={(event) => setPlanName(event.target.value)} placeholder={benchmark ? `${benchmark.label} ${t("对比测试")}` : t("输入计划名称")} /></label>
              <fieldset><legend className="label-with-tip">{t("首次运行")}<InfoTip label={t("查看说明")} text={t("立即表示启动计划后马上创建第一条运行记录；定时表示等待到指定时间。")}/></legend><div className="segmented"><button type="button" className={startMode === "now" ? "active" : ""} onClick={() => setStartMode("now")}>{t("启动后立即运行")}</button><button type="button" className={startMode === "scheduled" ? "active" : ""} onClick={() => setStartMode("scheduled")}>{t("指定时间")}</button></div>{startMode === "scheduled" && <label className="field inline-schedule"><span>{t("运行时间")} <b className="required">*</b></span><input required type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} /></label>}</fieldset>
              <fieldset><legend className="label-with-tip">{t("重复规则")}<InfoTip label={t("查看说明")} text={t("有限次数包含首次运行；一直重复会持续执行，直到计划被暂停、停止或删除。")}/></legend><div className="schedule-grid"><label className="field"><span>{t("重复方式")} <b className="required">*</b></span><select value={repeatMode} onChange={(event) => setRepeatMode(event.target.value as "once" | "count" | "forever")}><option value="once">{t("不重复")}</option><option value="count">{t("按次数重复")}</option><option value="forever">{t("一直重复")}</option></select></label>{repeatMode === "count" && <label className="field"><span>{t("总运行次数")} <b className="required">*</b></span><input type="number" min="2" max="10000" required value={repeatCount} onChange={(event) => setRepeatCount(Number(event.target.value))} /></label>}{repeatMode !== "once" && <label className="field interval-field"><span>{t("重复周期")} <b className="required">*</b></span><div><input type="number" min="1" required value={repeatEvery} onChange={(event) => setRepeatEvery(Number(event.target.value))} /><select value={repeatUnit} onChange={(event) => setRepeatUnit(event.target.value as "minutes" | "hours" | "days")}><option value="minutes">{t("分钟")}</option><option value="hours">{t("小时")}</option><option value="days">{t("天")}</option></select></div></label>}</div></fieldset>
              <fieldset><legend className="label-with-tip">{t("测试类型")}<InfoTip label={t("查看说明")} text={t("Embedding 测试向量生成，Reranker 测试候选文档重排，Dify 类型测试对应应用能力。")}/></legend><div className="segmented">{catalog.benchmarks.map((item) => <button type="button" className={item.id === benchmarkId ? "active" : ""} onClick={() => changeBenchmark(item)} key={item.id}>{item.label}</button>)}</div></fieldset>
              {benchmarkId !== "audio" && <fieldset className="test-inputs"><legend className="label-with-tip">{t("测试参数")}<InfoTip label={t("查看说明")} text={t("这些参数会在计划每次运行时发送给所选模型；已预填可直接使用的示例。")}/></legend>
                <label className="field"><span className="label-with-tip">Query <b className="required">*</b><InfoTip label={t("查看说明")} text={t(benchmarkId === "embedding" ? "发送给 Embedding 模型并转换为向量的文本。" : benchmarkId === "reranker" ? "用于判断候选文档相关性的检索问题。" : "测试期间重复发送给 Dify 应用或知识库的问题文本。")}/></span><textarea required value={testQueries[benchmarkId] || ""} onChange={(event) => setTestQueries((current) => ({ ...current, [benchmarkId]: event.target.value }))} /></label>
                {benchmarkId === "reranker" && <label className="field"><span className="label-with-tip">Document <b className="required">*</b><InfoTip label={t("查看说明")} text={t("每行一篇候选文档，Reranker 会根据 Query 计算相关性并重新排序。")}/></span><textarea className="documents-input" required value={rerankerDocuments} onChange={(event) => setRerankerDocuments(event.target.value)} /><small>{t("每行一篇文档，最多 20 篇")}</small></label>}
                {benchmarkId === "dify-retrieve" && <label className="field"><span className="label-with-tip">Dataset ID <b className="required">*</b><InfoTip label={t("查看说明")} text={t("Dify 知识库的唯一标识，可在知识库页面 URL 或 API 中找到。")}/></span><input required value={difyDatasetId} onChange={(event) => setDifyDatasetId(event.target.value)} placeholder={t("Dify 知识库 Dataset ID")} /></label>}
              </fieldset>}
              <fieldset><legend className="label-with-tip">{t(benchmarkId.startsWith("dify-") ? "Dify 配置" : "模型供应商与模型")}<InfoTip label={t("查看说明")} text={t("可同时选择多个服务；每个服务都会与所选并发档位组成独立测试场景。")}/></legend><div className="provider-list">{benchmark?.providers.map((provider) => {
                const checked = providerIds.includes(provider.id);
                return <label className={`${checked ? "checked" : ""} ${!provider.endpoint_configured ? "disabled" : ""}`} key={provider.id}>
                  <input type="checkbox" disabled={!provider.endpoint_configured} checked={checked} onChange={() => setProviderIds((current) => checked ? current.filter((id) => id !== provider.id) : [...current, provider.id])} />
                  <span className="provider-identity">{!benchmarkId.startsWith("dify-") && <ProviderLogo providerId={provider.provider || provider.id} />}<span className="provider-identity-text"><strong>{providerDisplayName(provider.provider || provider.id, language, provider.label)}</strong><small>{benchmarkId.startsWith("dify-") ? t("Dify 服务") : provider.models.length ? language === "en" ? `${provider.models.length} ${provider.models.length === 1 ? "model" : "models"}` : `${provider.models.length} 个模型` : t("无模型")}</small></span></span>
                  <i className={provider.endpoint_configured ? "ready" : "warning"}>{provider.endpoint_configured ? t("已配置") : t("待配置")}</i>
                  {checked && provider.models.some((model) => model.name) && <select className="model-select" value={selectedModels[provider.id] || provider.models[0]?.alias || provider.models[0]?.name || ""} onClick={(event) => event.stopPropagation()} onChange={(event) => { setSelectedModels((current) => ({ ...current, [provider.id]: event.target.value })); setSelectedCredentials((current) => ({ ...current, [provider.id]: "" })); }} aria-label={`${provider.label} ${t("模型")}`}>{provider.models.filter((model) => model.name).map((model) => <option key={`${model.benchmark}-${model.alias || model.name}`} value={model.alias || model.name || ""}>{model.alias || model.name}</option>)}</select>}
                  {checked && (() => { const model = provider.models.find((item) => (item.alias || item.name) === (selectedModels[provider.id] || provider.models[0]?.alias || provider.models[0]?.name)); const credentials = model?.credentials || []; return credentials.length > 1 ? <select className="model-select" required value={selectedCredentials[provider.id] || ""} onClick={(event) => event.stopPropagation()} onChange={(event) => setSelectedCredentials((current) => ({ ...current, [provider.id]: event.target.value }))} aria-label={`${provider.label} ${t("凭据")}`}><option value="">{t("选择凭据")}</option>{credentials.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select> : null; })()}
                </label>;
              })}{!benchmark?.providers.length && <div className="empty-state">{t("此类型暂无已配置的服务。")}</div>}</div></fieldset>
              <fieldset><legend className="label-with-tip">{t("并发档位")}<InfoTip label={t("查看说明")} text={t("表示同一时刻并行发送的请求数量；建议从低到高选择多个档位观察性能拐点。")}/></legend><div className="multi-select"><button type="button" className="multi-select-trigger" aria-expanded={levelMenuOpen} onClick={() => setLevelMenuOpen((open) => !open)}>{levels.length ? levels.join("、") : t("选择并发档位")}<ChevronDown aria-hidden="true" /></button>{levelMenuOpen && <div className="multi-select-menu">{[...new Set([...DEFAULT_LEVELS, ...levels])].sort((a, b) => a - b).map((level) => <label key={level}><input type="checkbox" checked={levels.includes(level)} onChange={() => setLevels((current) => current.includes(level) ? current.filter((item) => item !== level) : [...current, level].sort((a, b) => a - b))} />{level}</label>)}<div className="custom-level"><input type="number" min="1" max="10000" placeholder={t("自定义档位")} value={customLevel} onChange={(event) => setCustomLevel(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addConcurrencyLevel(); } }} /><button type="button" onClick={addConcurrencyLevel}>{t("添加")}</button></div></div>}</div><small className="field-help">{t("可多选，也可添加 1–10000 的自定义档位")}</small></fieldset>
              <div className="field-row">
                <label className="field"><span className="label-with-tip">{t("每场景请求数")}<InfoTip label={t("查看说明")} text={t("每个服务与并发档位组合发送的请求总数；数量越大，统计越稳定但耗时越长。")}/></span><input type="number" min="1" value={requests} onChange={(event) => setRequests(Number(event.target.value))} /></label>
                <label className="field"><span className="label-with-tip">{t("超时（秒）")}<InfoTip label={t("查看说明")} text={t("单个请求允许等待的最长时间；超过后记为失败请求。")}/></span><input type="number" min="1" value={timeout} onChange={(event) => setTimeout(Number(event.target.value))} /></label>
              </div>
              <div className="matrix-note"><span className="label-with-tip">{t("预计场景数")}<InfoTip label={t("查看说明")} text={t("场景数等于已选服务数乘以并发档位数，系统会按场景依次调度。")}/></span><strong>{providerIds.length} × {levels.length} = {providerIds.length * levels.length}</strong></div>
              <button className="primary" disabled={submitting || !providerIds.length}><CalendarClock aria-hidden="true" />{submitting ? t("正在创建…") : t("保存测试计划")}</button>
            </form>}
          </section></>}
        </div>}

        {activeTab === "dashboard" && <AnalysisDashboard plans={plans} runs={runs} language={language} dark={resolvedDark} initialPlanId={dashboardPlanId} initialRunId={dashboardPlanId === selected?.plan_id ? selected?.id || null : null} onSelectRun={setSelectedId} />}

        {activeTab === "history" && <section className="panel history">
          <div className="panel-head"><div><h2>{t("运行记录")}</h2><p>{t("检查并管理所有性能测试运行")}</p></div><span className="unit">{t("最近")} {runs.length} {t("次")}</span></div>
          <div className="table-scroll"><table><thead><tr><th>{t("状态")}</th><th>{t("测试计划")}</th><th>{t("类型")}</th><th><span className="label-with-tip">{t("场景")}<InfoTip label={t("查看说明")} text={t("一个场景对应一个服务与一个并发档位的组合。")}/></span></th><th><span className="label-with-tip">{t("进度")}<InfoTip label={t("查看说明")} text={t("已完成场景数与全部场景数的比值。")}/></span></th><th>{t("创建时间")}</th><th>{t("操作")}</th></tr></thead><tbody>{runs.map((run) => <tr className={selected?.id === run.id ? "selected" : ""} onClick={() => openRunAnalysis(run)} key={run.id}><td><Status value={run.status} language={language} /></td><td><strong>{run.name}</strong><small>{run.id}</small></td><td>{run.benchmark}</td><td>{run.total_scenarios}</td><td>{run.completed_scenarios} / {run.total_scenarios}</td><td>{formatTime(run.created_at, language)}</td><td><button type="button" className="icon-button danger" aria-label={t("删除")} disabled={!TERMINAL.has(run.status)} onClick={(event) => { event.stopPropagation(); void deleteRun(run); }}><Trash2 aria-hidden="true" /></button></td></tr>)}</tbody></table>{!runs.length && <div className="empty-state">{t("暂无运行记录")}</div>}</div>
        </section>}

        {activeTab === "settings" && <ProviderManager configs={serviceConfigs} benchmarks={catalog?.benchmarks || []} language={language} onChanged={async () => { const [nextConfigs, nextCatalog] = await Promise.all([api.serviceConfigs(), api.catalog()]); setServiceConfigs(nextConfigs); setCatalog(nextCatalog); }} />}
        {activeTab === "dify" && <section className="settings-grid dify-settings">
          <article className="panel">
            <div className="panel-head"><div><h2>{t("Dify 配置")}</h2><p>{t("管理知识库与聊天应用连接")}</p></div><button type="button" className="primary compact" onClick={startDifyConfig}><Plus aria-hidden="true" />{t("新增 Dify 配置")}</button></div>
            <div className="service-list">{difyConfigs.map((config) => <div className="service-item" key={config.id}>
              <span className={config.has_api_key ? "service-icon secure" : "service-icon"}><KeyRound aria-hidden="true" /></span>
              <span><strong>{config.name}</strong><small>{config.models[0]?.benchmark === "dify-chat" ? t("聊天应用") : t("知识库检索")}</small><small>{config.models[0]?.base_url || t("Endpoint 待配置")}</small></span>
              <div className="service-actions"><button type="button" className="icon-button" aria-label={t("编辑")} onClick={() => editServiceConfig(config)}><Pencil aria-hidden="true" /></button><button type="button" className="icon-button danger" aria-label={t("删除")} onClick={() => void deleteServiceConfig(config)}><Trash2 aria-hidden="true" /></button></div>
            </div>)}{!difyConfigs.length && <div className="empty-state">{t("暂无 Dify 配置")}</div>}</div>
          </article>
          <article className="panel">
            <div className="panel-head"><div><h2>{t(editingConfigId ? "编辑 Dify 配置" : "新增 Dify 配置")}</h2><p>{t("保存前会探测 Endpoint；收到认证拒绝则不保存。密钥会加密存储。")}</p></div>{editingConfigId && <button className="ghost" onClick={startDifyConfig}><X aria-hidden="true" />{t("取消编辑")}</button>}</div>
            <form className="service-form" autoComplete="off" onSubmit={saveServiceConfig}>
              <label className="field"><span>{t("配置名称")}</span><input required value={configName} onChange={(event) => setConfigName(event.target.value)} placeholder={t("例如 Dify 生产环境")} /></label>
              <label className="field"><span className="label-with-tip">{t("Dify 类型")}<InfoTip label={t("查看说明")} text={t("知识库检索直接调用 Dataset API；聊天应用调用已发布应用的 Chat API。")}/></span><select value={configBenchmark.startsWith("dify-") ? configBenchmark : "dify-retrieve"} onChange={(event) => setConfigBenchmark(event.target.value)}><option value="dify-retrieve">{t("知识库检索")}</option><option value="dify-chat">{t("聊天应用")}</option></select></label>
              <label className="field"><span className="label-with-tip">{t("Dify 服务地址")}<InfoTip label={t("查看说明")} text={t("填写 Dify 实例根地址，不要包含 /v1 等接口路径。")}/></span><input required type="url" value={configUrl} onChange={(event) => setConfigUrl(event.target.value)} placeholder="https://host" /></label>
              <label className="field"><span className="label-with-tip">{configBenchmark === "dify-chat" ? "Chat API Key" : "Dataset API Key"}<InfoTip label={t("查看说明")} text={t(configBenchmark === "dify-chat" ? "在 Dify 应用的 API 访问页面创建，用于调用已发布应用。" : "在 Dify 知识库 API 页面创建，用于访问指定 Dataset。")}/></span><input className={editingDifyConfig?.has_api_key && !configApiKey ? "masked-secret" : ""} type="password" autoComplete="new-password" value={configApiKey} onChange={(event) => setConfigApiKey(event.target.value)} placeholder={editingDifyConfig?.has_api_key ? editingDifyConfig.api_key_masked || "••••••••" : editingConfigId ? t("留空表示保留现有密钥") : configBenchmark === "dify-chat" ? t("填写 Chat API Key") : t("填写 Dataset API Key")} /></label>
              <button className="primary" disabled={savingConfig || !configUrl.trim()}><Database aria-hidden="true" />{savingConfig ? t("保存中…") : t("保存")}</button>
            </form>
          </article>
        </section>}
        {activeTab === "api" && <section className="panel api-docs"><div className="panel-head"><div><p className="eyebrow">OPENAPI</p><h2>{t("接口文档")}</h2></div><a className="ghost" href="/api/docs" target="_blank" rel="noreferrer">{t("在新窗口打开")}</a></div><iframe title="PerfLab API docs" src="/api/docs" /></section>}
      </div>
    </main>
  </div>;
}
