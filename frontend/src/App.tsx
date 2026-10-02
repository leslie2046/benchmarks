import { FormEvent, useEffect, useRef, useState } from "react";
import {
  Activity, BookOpen, Boxes, CalendarClock, ChevronDown, FlaskConical,
  History, Languages, LayoutDashboard, Menu, Monitor, Moon, Pencil, Play,
  Plus, Pause, RefreshCw, Settings, Sparkles, Square, Sun, Trash2, Workflow, X,
} from "lucide-react";
import { api, subscribeToRun } from "./api";
import { Github } from "./components/Github";
import { BrandLogo } from "./components/BrandLogo";
import { DifyTypeIcon } from "./components/DifyIdentity";
import { DEFAULT_RERANKER_DOCUMENTS, DEFAULT_TEST_QUERIES } from "./benchmarkDefaults";
import { AnalysisDashboard } from "./components/AnalysisDashboard";
import { createDocumentDraft, DocumentListEditor } from "./components/DocumentListEditor";
import { InfoTip } from "./components/InfoTip";
import { Overview } from "./components/Overview";
import { Playground } from "./components/Playground";
import { ProviderManager } from "./components/ProviderManager";
import { SystemSettings } from "./components/SystemSettings";
import { RunAiReport } from "./components/RunAiReport";
import { ProviderLogo } from "./components/ProviderLogo";
import { providerDisplayName } from "./providerPresets";
import { tr, type Language } from "./i18n";
import type { Benchmark, Catalog, ProviderIcon, Run, ServiceConfig, TestPlan } from "./types";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
const TABS = ["overview", "new-run", "history", "dashboard", "playground", "settings", "dify", "system", "api"] as const;
type Tab = typeof TABS[number];
const DEFAULT_LEVELS = [1, 5, 10, 20, 40, 80];
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
  const [analysisRun, setAnalysisRun] = useState<Run | null>(null);
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
  const [maxTokens, setMaxTokens] = useState(256);
  const [timeout, setTimeout] = useState(60);
  const [testQueries, setTestQueries] = useState<Record<string, string>>(DEFAULT_TEST_QUERIES);
  const [rerankerDocuments, setRerankerDocuments] = useState(() => DEFAULT_RERANKER_DOCUMENTS.map(createDocumentDraft));
  const [submitting, setSubmitting] = useState(false);
  const [planName, setPlanName] = useState("");
  const [editingPlanId, setEditingPlanId] = useState<string | null>(null);
  const planEditorRef = useRef<HTMLElement>(null);
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
  const [configUrl, setConfigUrl] = useState("https://api.dify.ai");
  const [configDatasetId, setConfigDatasetId] = useState("");
  const [configIcon, setConfigIcon] = useState<ProviderIcon>("cube");
  const [configApiKey, setConfigApiKey] = useState("");
  const [savingConfig, setSavingConfig] = useState(false);
  const [editingConfigId, setEditingConfigId] = useState<string | null>(null);
  const [difyEditorOpen, setDifyEditorOpen] = useState(false);
  const [difyEditorError, setDifyEditorError] = useState("");
  const [fetchingDifyName, setFetchingDifyName] = useState(false);
  const [difyNameNotice, setDifyNameNotice] = useState("");
  const difyDialogRef = useRef<HTMLDialogElement>(null);
  const difyTriggerRef = useRef<HTMLElement | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const selected = runs.find((run) => run.id === selectedId) ?? runs[0] ?? null;
  const benchmark = catalog?.benchmarks.find((item) => item.id === benchmarkId) ?? null;
  const difyConfigs = serviceConfigs.filter((config) => config.provider === "dify");
  const editingDifyConfig = difyConfigs.find((config) => config.id === editingConfigId) ?? null;
  const hasLiveActivity = plans.some((plan) => plan.status === "active") || runs.some((run) => !TERMINAL.has(run.status));

  useEffect(() => {
    if (!difyEditorOpen) return;
    if (activeTab !== "dify") { setDifyEditorOpen(false); return; }
    const dialog = difyDialogRef.current;
    dialog?.showModal();
    dialog?.querySelector<HTMLInputElement>("input")?.focus();
    return () => { if (dialog?.open) dialog.close(); };
  }, [difyEditorOpen, activeTab]);

  useEffect(() => {
    localStorage.setItem("perflab-language", language);
    document.documentElement.lang = language;
    document.title = `PrismLab · ${tr(language, "性能测试台")}`;
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
    if (!hasLiveActivity) return;
    const timer = window.setInterval(() => {
      Promise.all([api.plans(), api.runs()]).then(([planData, runData]) => {
        setPlans(planData);
        setRuns(runData);
      }).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [hasLiveActivity]);

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
    setSelectedCredentials({});
  }

  function canEditPlan(plan: TestPlan) {
    return plan.status !== "active" && !runs.some((run) => run.plan_id === plan.id && !TERMINAL.has(run.status));
  }

  function resetPlanEditor() {
    setEditingPlanId(null);
    setPlanName("");
    const initial = catalog?.benchmarks.find((item) => item.id === "reranker");
    if (initial) changeBenchmark(initial);
    setLevels([1, 5, 10, 20]); setCustomLevel(""); setLevelMenuOpen(false);
    setRequests(100); setTimeout(60); setMaxTokens(256);
    setTestQueries(DEFAULT_TEST_QUERIES);
    setRerankerDocuments(DEFAULT_RERANKER_DOCUMENTS.map(createDocumentDraft));
    setStartMode("now"); setScheduledAt("");
    setRepeatMode("once"); setRepeatCount(3); setRepeatEvery(1); setRepeatUnit("hours");
  }

  function editPlan(plan: TestPlan) {
    if (submitting || !canEditPlan(plan)) return;
    setEditingPlanId(plan.id); setPlanName(plan.name); setBenchmarkId(plan.benchmark);
    setProviderIds(plan.providers.map((item) => item.id));
    setSelectedModels(Object.fromEntries(plan.providers.map((item) => [item.id, item.model || ""])));
    setSelectedCredentials(Object.fromEntries(plan.providers.map((item) => [item.id, item.credential_id || ""])));
    setLevels([...plan.concurrency_levels]); setCustomLevel(""); setLevelMenuOpen(false);
    setRequests(plan.requests_per_scenario); setTimeout(plan.timeout_seconds); setMaxTokens(plan.max_tokens ?? 256);
    setTestQueries({ ...DEFAULT_TEST_QUERIES, [plan.benchmark]: plan.query ?? DEFAULT_TEST_QUERIES[plan.benchmark] ?? "" });
    setRerankerDocuments((plan.documents ?? DEFAULT_RERANKER_DOCUMENTS).map(createDocumentDraft));
    setStartMode(plan.start_at ? "scheduled" : "now");
    const date = plan.start_at ? new Date(plan.start_at) : null;
    setScheduledAt(date ? new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "");
    setRepeatMode(plan.repeat_mode); setRepeatCount(plan.repeat_count ?? 3);
    const interval = plan.repeat_interval_seconds ?? 3600;
    const unit = interval % 86400 === 0 ? "days" : interval % 3600 === 0 ? "hours" : "minutes";
    setRepeatUnit(unit); setRepeatEvery(interval / (unit === "days" ? 86400 : unit === "hours" ? 3600 : 60));
    setMessage("");
    requestAnimationFrame(() => {
      planEditorRef.current?.scrollIntoView({ block: "start" });
      planEditorRef.current?.querySelector<HTMLInputElement>("input")?.focus({ preventScroll: true });
    });
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
    const documents = rerankerDocuments.map((item) => item.text.trim());
    if ((benchmark.id === "llm" || benchmark.id === "embedding" || benchmark.id === "reranker" || benchmark.id.startsWith("dify-")) && !query) {
      setMessage(t("请填写测试 Query。"));
      return;
    }
    if (benchmark.id === "reranker" && !documents.length) {
      setMessage(t("请至少填写一条 Document。"));
      return;
    }
    if (benchmark.id === "reranker" && documents.some((item) => !item)) {
      setMessage(t("请填写每条文档，或删除空白条目。"));
      return;
    }
    setSubmitting(true);
    setMessage("");
    try {
      const multiplier = repeatUnit === "minutes" ? 60 : repeatUnit === "hours" ? 3600 : 86400;
      const payload = {
        name: planName.trim() || `${benchmark.label} ${t("对比测试")}`,
        benchmark: benchmark.id,
        providers: providerIds.map((id) => ({ id, model: selectedModels[id] || benchmark.providers.find((item) => item.id === id)?.models[0]?.alias || benchmark.providers.find((item) => item.id === id)?.models[0]?.name || null, credential_id: selectedCredentials[id] || null })),
        concurrency_levels: levels,
        requests_per_scenario: requests,
        timeout_seconds: timeout,
        max_tokens: benchmark.id === "llm" ? maxTokens : 256,
        query: benchmark.id === "audio" ? null : query,
        documents: benchmark.id === "reranker" ? documents : [],
        start_at: startMode === "scheduled" && scheduledAt ? new Date(scheduledAt).toISOString() : null,
        repeat_mode: repeatMode,
        repeat_count: repeatMode === "count" ? repeatCount : null,
        repeat_interval_seconds: repeatMode === "once" ? null : repeatEvery * multiplier,
      };
      const plan = editingPlanId ? await api.updatePlan(editingPlanId, payload) : await api.createPlan(payload);
      setPlans((current) => editingPlanId ? current.map((item) => item.id === plan.id ? plan : item) : [plan, ...current]);
      setMessage(t(editingPlanId ? "测试计划已更新，历史记录保留；请重新启动计划。" : "测试计划已保存，可在上方启动。"));
      if (editingPlanId) resetPlanEditor(); else setPlanName("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("保存测试计划失败"));
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
    if (fetchingDifyName) return;
    setSavingConfig(true);
    setDifyEditorError("");
    setMessage("");
    try {
      const payload = {
        name: configName,
        provider: "dify",
        models: [{ name: null, benchmark: configBenchmark.startsWith("dify-") ? configBenchmark : "dify-retrieve", base_url: configUrl.trim() }],
        icon: configIcon,
        dataset_id: configBenchmark === "dify-retrieve" ? configDatasetId.trim() : null,
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
      hideDifyDialog();
      setMessage(`${t("Dify 配置")} “${config.name}” ${t("已保存")}${config.has_api_key ? ` · ${t("API Key 已加密")}` : ""}`);
    } catch (error) {
      setDifyEditorError(error instanceof Error ? error.message : t("保存服务配置失败"));
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
    resetDifyNames();
    difyTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setEditingConfigId(config.id);
    setConfigBenchmark(config.models[0]?.benchmark ?? config.benchmark);
    setConfigName(config.name);
    setConfigUrl(config.models[0]?.base_url ?? "");
    setConfigDatasetId(config.dataset_id ?? "");
    setConfigIcon(config.icon ?? "cube");
    setConfigApiKey("");
    setDifyEditorError("");
    setDifyEditorOpen(true);
    navigate("dify");
  }

  function startDifyConfig() {
    resetDifyNames();
    difyTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setEditingConfigId(null);
    setConfigBenchmark("dify-retrieve");
    setConfigName("");
    setConfigUrl("https://api.dify.ai");
    setConfigDatasetId("");
    setConfigApiKey("");
    setConfigIcon("cube");
    setDifyEditorError("");
    setDifyEditorOpen(true);
    navigate("dify");
  }

  function closeDifyConfig() {
    if (savingConfig || fetchingDifyName) return;
    hideDifyDialog();
    setEditingConfigId(null);
    setConfigApiKey("");
    setDifyEditorError("");
  }

  function hideDifyDialog() {
    difyDialogRef.current?.close();
    difyTriggerRef.current?.focus();
    setDifyEditorOpen(false);
  }

  function resetDifyNames() {
    setDifyNameNotice("");
  }

  async function fetchDifyName() {
    if (savingConfig || fetchingDifyName) return;
    setFetchingDifyName(true);
    setDifyEditorError("");
    resetDifyNames();
    try {
      const response = await api.difyNames({ provider: "dify", benchmark: configBenchmark,
        server_url: configUrl.trim(), api_key: configApiKey || undefined,
        config_id: editingConfigId || undefined, dataset_id: configBenchmark === "dify-retrieve" ? configDatasetId.trim() : undefined });
      if (response.names.length === 1) {
        setConfigName(response.names[0].name.slice(0, 120));
        setDifyNameNotice("名称已填充，保存后才会更新配置。");
      } else throw new Error(t("Dify 未返回知识库名称，请检查知识库 ID 和权限。"));
    } catch (error) {
      setDifyEditorError(error instanceof Error ? t(error.message) : t("获取名称失败"));
    } finally { setFetchingDifyName(false); }
  }

  return <div className="app-shell">
    {sidebarOpen && <button className="sidebar-scrim" aria-label={t("关闭")} onClick={() => setSidebarOpen(false)} />}
    <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
      <div className="brand"><BrandLogo /><span><strong>PrismLab</strong><small>{t("AI 模型测试与分析平台")}</small></span></div>
      <nav aria-label={t("主导航")}>
        <span className="nav-label">Workspace</span>
        <button className={activeTab === "overview" ? "active" : ""} onClick={() => navigate("overview")}><Activity aria-hidden="true" />{t("概览")}</button>
        <button className={activeTab === "new-run" ? "active" : ""} onClick={() => navigate("new-run")}><CalendarClock aria-hidden="true" />{t("测试计划")}</button>
        <button className={activeTab === "history" ? "active" : ""} onClick={() => navigate("history")}><History aria-hidden="true" />{t("运行记录")}</button>
        <button className={activeTab === "dashboard" ? "active" : ""} onClick={() => navigate("dashboard")}><LayoutDashboard aria-hidden="true" />{t("分析看板")}</button>
        <button className={activeTab === "playground" ? "active" : ""} onClick={() => navigate("playground")}><FlaskConical aria-hidden="true" />Playground</button>
        <span className="nav-label">Configuration</span>
        <button className={activeTab === "settings" ? "active" : ""} onClick={() => navigate("settings")}><Boxes aria-hidden="true" />{t("模型供应商")}</button>
        <button className={activeTab === "dify" ? "active" : ""} onClick={() => navigate("dify")}><Workflow aria-hidden="true" />{t("Dify 配置")}</button>
        <button className={activeTab === "system" ? "active" : ""} onClick={() => navigate("system")}><Settings aria-hidden="true" />{t("系统配置")}</button>
        <button className={activeTab === "api" ? "active" : ""} onClick={() => navigate("api")}><BookOpen aria-hidden="true" />API</button>
      </nav>
      <div className="sidebar-foot"><span className="live-dot" />Local workspace<a className="sidebar-github" href="https://github.com/leslie2046/benchmarks" target="_blank" rel="noopener noreferrer" aria-label={t("打开项目 GitHub 仓库")} title={t("打开项目 GitHub 仓库")}><Github aria-hidden="true" /></a></div>
    </aside>

    <main>
      <header className="topbar">
        <div className="topbar-title"><button className="mobile-menu" onClick={() => setSidebarOpen(true)} aria-label={t("主导航")}><Menu aria-hidden="true" /></button><div><h1>{t(({ overview: "概览", "new-run": "测试计划", history: "运行记录", dashboard: "分析看板", playground: "Playground", settings: "模型供应商", dify: "Dify 配置", system: "系统配置", api: "API 文档" } as Record<Tab, string>)[activeTab])}</h1><p>{t(({ overview: "查看所有测试计划与运行记录的整体状态", "new-run": "管理计划、调度规则与测试配置", history: "检查并管理历史测试运行", dashboard: "聚合分析测试计划的多次运行结果", playground: "向已配置的服务发送单次请求", settings: "管理模型、端点与访问凭据", dify: "管理知识库与聊天应用连接", system: "管理系统默认模型与 AI 分析配置", api: "浏览 PrismLab HTTP API" } as Record<Tab, string>)[activeTab])}</p></div></div>
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
        {activeTab === "system" && <SystemSettings catalog={catalog} language={language} />}
        {analysisRun && <RunAiReport key={analysisRun.id} run={analysisRun} language={language} onClose={() => setAnalysisRun(null)} onSettings={() => { setAnalysisRun(null); navigate("system"); }} />}
        {message && <div className="alert" role="alert"><span>{message}</span><button onClick={() => setMessage("")} aria-label={t("关闭")}><X aria-hidden="true" /></button></div>}
        {activeTab === "playground" && <Playground catalog={catalog} language={language} />}
        {activeTab === "overview" && <Overview plans={plans} runs={runs} language={language} onOpenRun={openRunAnalysis} onOpenPlans={() => navigate("new-run")} onOpenDashboard={() => navigate("dashboard")} />}
        {activeTab === "new-run" && <div className="workspace-grid single">
          {activeTab === "new-run" && <>
          <section className="panel plan-list-panel">
            <div className="panel-head"><div><h2>{t("测试计划")}</h2><p>{t("计划定义何时运行；每次触发都会生成一条独立运行记录。")}</p></div><span className="unit">{plans.length} {t("个")}</span></div>
            <div className="table-scroll"><table className="plan-table"><thead><tr><th>{t("计划")}</th><th>{t("状态")}</th><th>{t("调度规则")}</th><th>{t("下次运行")}</th><th>{t("运行次数")}</th><th>{t("操作")}</th></tr></thead><tbody>{plans.map((plan) => <tr key={plan.id}>
              <td><button type="button" className="plan-name-button" disabled={submitting || !canEditPlan(plan)} onClick={() => editPlan(plan)}>{plan.name}</button><small>{plan.benchmark} · {plan.id}</small></td>
              <td><Status value={plan.status} language={language} />{plan.schedule_error && <small className="error-text">{plan.schedule_error}</small>}</td>
              <td>{repeatDescription(plan)}</td>
              <td>{plan.next_run_at && plan.status !== "stopped" ? formatTime(plan.next_run_at, language) : "—"}</td>
              <td>{plan.run_count}</td>
              <td><div className="row-actions">
                <button type="button" className="icon-button" title={t(canEditPlan(plan) ? "编辑测试计划" : "请先暂停计划，并等待当前运行结束后再编辑。")} aria-label={t("编辑测试计划")} disabled={submitting || planActionId === plan.id || !canEditPlan(plan)} onClick={() => editPlan(plan)}><Pencil aria-hidden="true" /></button>
                {plan.status !== "active" && <button type="button" className="icon-button" title={t("开始计划")} aria-label={t("开始计划")} disabled={planActionId === plan.id} onClick={() => void controlPlan(plan, "start")}><Play aria-hidden="true" /></button>}
                {plan.status === "active" && <button type="button" className="icon-button" title={t("暂停计划")} aria-label={t("暂停计划")} disabled={planActionId === plan.id} onClick={() => void controlPlan(plan, "pause")}><Pause aria-hidden="true" /></button>}
                {(plan.status === "active" || plan.status === "paused") && <button type="button" className="icon-button" title={t("停止计划")} aria-label={t("停止计划")} disabled={planActionId === plan.id} onClick={() => void controlPlan(plan, "stop")}><Square aria-hidden="true" /></button>}
                <button type="button" className="icon-button danger" title={t("删除测试计划")} aria-label={t("删除测试计划")} disabled={planActionId === plan.id} onClick={() => void deletePlan(plan)}><Trash2 aria-hidden="true" /></button>
              </div></td>
            </tr>)}</tbody></table>{!plans.length && <div className="empty-state compact-empty">{t("暂无测试计划，请在下方创建第一个计划。")}</div>}</div>
          </section>
          <section className="panel config-panel" ref={planEditorRef}>
            <div className="panel-head"><div><h2>{t(editingPlanId ? "编辑测试计划" : "新建测试计划")}</h2><p>{t(editingPlanId ? "修改只影响后续运行，历史记录保留。保存后请重新启动；重复次数从新配置重新计算。" : "保存后由你决定何时启动，计划不会自动立即运行。")}</p></div>{editingPlanId && <button type="button" className="ghost" disabled={submitting} onClick={resetPlanEditor}>{t("取消编辑")}</button>}</div>
            {catalog && <form onSubmit={submit}>
              <fieldset className="plan-save-lock" disabled={submitting}>
              <label className="field"><span>{t("计划名称")} <b className="required">*</b></span><input required value={planName} onChange={(event) => setPlanName(event.target.value)} placeholder={benchmark ? `${benchmark.label} ${t("对比测试")}` : t("输入计划名称")} /></label>
              <fieldset><legend className="label-with-tip">{t("首次运行")}<InfoTip label={t("查看说明")} text={t("立即表示启动计划后马上创建第一条运行记录；定时表示等待到指定时间。")}/></legend><div className="segmented"><button type="button" className={startMode === "now" ? "active" : ""} onClick={() => setStartMode("now")}>{t("启动后立即运行")}</button><button type="button" className={startMode === "scheduled" ? "active" : ""} onClick={() => setStartMode("scheduled")}>{t("指定时间")}</button></div>{startMode === "scheduled" && <label className="field inline-schedule"><span>{t("运行时间")} <b className="required">*</b></span><input required type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} /></label>}</fieldset>
              <fieldset><legend className="label-with-tip">{t("重复规则")}<InfoTip label={t("查看说明")} text={t("有限次数包含首次运行；一直重复会持续执行，直到计划被暂停、停止或删除。")}/></legend><div className="schedule-grid"><label className="field"><span>{t("重复方式")} <b className="required">*</b></span><select value={repeatMode} onChange={(event) => setRepeatMode(event.target.value as "once" | "count" | "forever")}><option value="once">{t("不重复")}</option><option value="count">{t("按次数重复")}</option><option value="forever">{t("一直重复")}</option></select></label>{repeatMode === "count" && <label className="field"><span>{t("总运行次数")} <b className="required">*</b></span><input type="number" min="2" max="10000" required value={repeatCount} onChange={(event) => setRepeatCount(Number(event.target.value))} /></label>}{repeatMode !== "once" && <label className="field interval-field"><span>{t("重复周期")} <b className="required">*</b></span><div><input type="number" min="1" required value={repeatEvery} onChange={(event) => setRepeatEvery(Number(event.target.value))} /><select value={repeatUnit} onChange={(event) => setRepeatUnit(event.target.value as "minutes" | "hours" | "days")}><option value="minutes">{t("分钟")}</option><option value="hours">{t("小时")}</option><option value="days">{t("天")}</option></select></div></label>}</div></fieldset>
              <fieldset><legend className="label-with-tip">{t("测试类型")}<InfoTip label={t("查看说明")} text={t("Embedding 测试向量生成，Reranker 测试候选文档重排，Dify 类型测试对应应用能力。")}/></legend><div className="segmented">{catalog.benchmarks.map((item) => <button type="button" className={item.id === benchmarkId ? "active" : ""} onClick={() => changeBenchmark(item)} key={item.id}>{item.label}</button>)}</div></fieldset>
              {benchmarkId !== "audio" && <fieldset className="test-inputs"><legend className="label-with-tip">{t("测试参数")}<InfoTip label={t("查看说明")} text={t("这些参数会在计划每次运行时发送给所选模型；已预填可直接使用的示例。")}/></legend>
                <label className="field"><span className="label-with-tip">Query <b className="required">*</b><InfoTip label={t("查看说明")} text={t(benchmarkId === "embedding" ? "发送给 Embedding 模型并转换为向量的文本。" : benchmarkId === "reranker" ? "用于判断候选文档相关性的检索问题。" : "测试期间重复发送给 Dify 应用或知识库的问题文本。")}/></span><textarea required value={testQueries[benchmarkId] || ""} onChange={(event) => setTestQueries((current) => ({ ...current, [benchmarkId]: event.target.value }))} /></label>
                {benchmarkId === "reranker" && <DocumentListEditor documents={rerankerDocuments} onChange={setRerankerDocuments} language={language} />}
              </fieldset>}
              <fieldset><legend className="label-with-tip">{t(benchmarkId.startsWith("dify-") ? "Dify 配置" : "模型供应商与模型")}<InfoTip label={t("查看说明")} text={t("可同时选择多个服务；每个服务都会与所选并发档位组成独立测试场景。")}/></legend><div className="provider-list">{benchmark?.providers.map((provider) => {
                const checked = providerIds.includes(provider.id);
                return <label className={`${checked ? "checked" : ""} ${!provider.endpoint_configured ? "disabled" : ""}`} key={provider.id}>
                  <input type="checkbox" disabled={!provider.endpoint_configured} checked={checked} onChange={() => setProviderIds((current) => checked ? current.filter((id) => id !== provider.id) : [...current, provider.id])} />
                  <span className="provider-identity">{!benchmarkId.startsWith("dify-") && <ProviderLogo providerId={provider.provider || provider.id} />}<span className="provider-identity-text"><strong>{providerDisplayName(provider.provider || provider.id, language, provider.label)}</strong><small>{benchmarkId.startsWith("dify-") ? benchmarkId === "dify-retrieve" ? provider.dataset_id ? `${t("知识库 ID")} · ${provider.dataset_id}` : t("请先在 Dify 配置中填写知识库 ID") : t("Dify 服务") : provider.models.length ? language === "en" ? `${provider.models.length} ${provider.models.length === 1 ? "model" : "models"}` : `${provider.models.length} 个模型` : t("无模型")}</small></span></span>
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
              {benchmarkId === "llm" && <label className="field"><span className="label-with-tip">{t("最大输出 token 数")}<b className="required">*</b><InfoTip label={t("查看说明")} text={t("限制每次生成长度，默认 256；TPOT 需要服务返回输出 token 用量，不能用流式分块数代替。")}/></span><input required type="number" min="2" max="8192" value={maxTokens} onChange={(event) => setMaxTokens(Number(event.target.value))} /><small className="field-help">{t("使用流式响应测量 TTFT 和 TPOT；不返回 token 用量时 TPOT 不可用。")}</small></label>}
              <div className="matrix-note"><span className="label-with-tip">{t("预计场景数")}<InfoTip label={t("查看说明")} text={t("场景数等于已选服务数乘以并发档位数，系统会按场景依次调度。")}/></span><strong>{providerIds.length} × {levels.length} = {providerIds.length * levels.length}</strong></div>
              <button className="primary" disabled={submitting || !providerIds.length}><CalendarClock aria-hidden="true" />{submitting ? t("保存中…") : t(editingPlanId ? "保存修改" : "保存测试计划")}</button>
              </fieldset>
            </form>}
          </section></>}
        </div>}

        {activeTab === "dashboard" && <AnalysisDashboard plans={plans} runs={runs} language={language} dark={resolvedDark} initialPlanId={dashboardPlanId} initialRunId={dashboardPlanId === selected?.plan_id ? selected?.id || null : null} onSelectRun={setSelectedId} />}

        {activeTab === "history" && <section className="panel history">
          <div className="panel-head"><div><h2>{t("运行记录")}</h2><p>{t("检查并管理所有性能测试运行")}</p></div><span className="unit">{t("最近")} {runs.length} {t("次")}</span></div>
          <div className="table-scroll"><table><thead><tr><th>{t("状态")}</th><th>{t("测试计划")}</th><th>{t("类型")}</th><th><span className="label-with-tip">{t("场景")}<InfoTip label={t("查看说明")} text={t("一个场景对应一个服务与一个并发档位的组合。")}/></span></th><th><span className="label-with-tip">{t("进度")}<InfoTip label={t("查看说明")} text={t("已完成场景数与全部场景数的比值。")}/></span></th><th>{t("创建时间")}</th><th>{t("操作")}</th></tr></thead><tbody>{runs.map((run) => <tr className={selected?.id === run.id ? "selected" : ""} onClick={() => openRunAnalysis(run)} key={run.id}><td><Status value={run.status} language={language} /></td><td><strong>{run.name}</strong><small>{run.id}</small></td><td>{run.benchmark}</td><td>{run.total_scenarios}</td><td>{run.completed_scenarios} / {run.total_scenarios}</td><td>{formatTime(run.created_at, language)}</td><td><div className="row-actions"><button type="button" className="ghost ai-report-trigger" disabled={!TERMINAL.has(run.status)} title={t("运行结束后可手动生成 AI 报告")} onClick={(event) => { event.stopPropagation(); setAnalysisRun(run); }}><Sparkles aria-hidden="true" />{t("AI 报告")}</button><button type="button" className="icon-button danger" aria-label={t("删除")} disabled={!TERMINAL.has(run.status)} onClick={(event) => { event.stopPropagation(); void deleteRun(run); }}><Trash2 aria-hidden="true" /></button></div></td></tr>)}</tbody></table>{!runs.length && <div className="empty-state">{t("暂无运行记录")}</div>}</div>
        </section>}

        {activeTab === "settings" && <ProviderManager configs={serviceConfigs} benchmarks={catalog?.benchmarks || []} language={language} onChanged={async () => { const [nextConfigs, nextCatalog] = await Promise.all([api.serviceConfigs(), api.catalog()]); setServiceConfigs(nextConfigs); setCatalog(nextCatalog); }} />}
        {activeTab === "dify" && <section className="dify-settings">
          <article className="panel">
            <div className="panel-head"><div><h2>{t("Dify 配置")}</h2><p>{t("管理知识库与聊天应用连接")}</p></div><button type="button" className="primary compact" onClick={startDifyConfig}><Plus aria-hidden="true" />{t("新增 Dify 配置")}</button></div>
            <div className="service-list">{difyConfigs.map((config) => <div className="service-item" key={config.id}>
              <DifyTypeIcon benchmark={config.models[0]?.benchmark || config.benchmark} language={language} />
              <span><strong>{config.name}</strong><small>{config.models[0]?.benchmark === "dify-chat" ? t("聊天应用") : t("知识库检索")}</small><small>{config.models[0]?.base_url || t("Endpoint 待配置")}</small></span>
              <div className="service-actions"><button type="button" className="icon-button" aria-label={t("编辑")} onClick={() => editServiceConfig(config)}><Pencil aria-hidden="true" /></button><button type="button" className="icon-button danger" aria-label={t("删除")} onClick={() => void deleteServiceConfig(config)}><Trash2 aria-hidden="true" /></button></div>
            </div>)}{!difyConfigs.length && <div className="empty-state">{t("暂无 Dify 配置")}</div>}</div>
          </article>
          {difyEditorOpen && <dialog ref={difyDialogRef} className="dify-modal dify-native-dialog" aria-labelledby="dify-editor-title" aria-describedby="dify-editor-description" onCancel={(event) => { event.preventDefault(); closeDifyConfig(); }}>
            <div className="dify-modal-head"><div><h2 id="dify-editor-title">{t(editingConfigId ? "编辑 Dify 配置" : "新增 Dify 配置")}</h2><p id="dify-editor-description">{t("保存前会探测 Endpoint；收到认证拒绝则不保存。密钥会加密存储。")}</p></div><button type="button" className="dify-close" disabled={savingConfig || fetchingDifyName} aria-label={t("关闭")} onClick={closeDifyConfig}><X aria-hidden="true" /></button></div>
            <form autoComplete="off" onSubmit={saveServiceConfig}>
              <div className="dify-modal-body">
                <div className="field"><label htmlFor="dify-config-name" className="label-with-tip">{t("配置名称")}<b className="required" aria-hidden="true">*</b></label><div className="dify-name-input"><input id="dify-config-name" required maxLength={120} disabled={savingConfig || fetchingDifyName} value={configName} onChange={(event) => setConfigName(event.target.value)} placeholder={t("例如 Dify 生产环境")} /><button type="button" className="icon-button" aria-label={t(configBenchmark === "dify-chat" ? "获取应用名称" : "获取知识库名称")} title={t(configBenchmark === "dify-chat" ? "获取应用名称" : "获取知识库名称")} disabled={savingConfig || fetchingDifyName || !configUrl.trim() || (configBenchmark === "dify-retrieve" && !configDatasetId.trim())} onClick={() => void fetchDifyName()}><RefreshCw aria-hidden="true" /></button></div><small className="field-help" role="status">{fetchingDifyName ? t("获取中…") : difyNameNotice ? t(difyNameNotice) : t("填写服务地址、API Key 和知识库 ID 后可获取名称；应用无需知识库 ID。")}</small></div>
                <label className="field"><span className="label-with-tip">{t("Dify 类型")}<b className="required" aria-hidden="true">*</b><InfoTip label={t("查看说明")} text={t("知识库检索直接调用 Dataset API；聊天应用调用已发布应用的 Chat API。")}/></span><select required disabled={savingConfig || fetchingDifyName} value={configBenchmark.startsWith("dify-") ? configBenchmark : "dify-retrieve"} onChange={(event) => { setConfigBenchmark(event.target.value); resetDifyNames(); }}><option value="dify-retrieve">{t("知识库检索")}</option><option value="dify-chat">{t("聊天应用")}</option></select></label>
                <label className="field"><span className="label-with-tip">{t("Dify 服务地址")}<b className="required" aria-hidden="true">*</b><InfoTip label={t("查看说明")} text={t("填写 Dify 实例根地址，不要包含 /v1 等接口路径。")}/></span><input required type="url" disabled={savingConfig || fetchingDifyName} value={configUrl} onChange={(event) => { setConfigUrl(event.target.value); resetDifyNames(); }} placeholder="https://host" /></label>
                {configBenchmark === "dify-retrieve" && <label className="field"><span className="label-with-tip">{t("知识库 ID")}<b className="required" aria-hidden="true">*</b><InfoTip label={t("查看说明")} text={t("知识库的唯一标识，可从 Dify 知识库页面 URL 复制；测试计划与 Playground 自动使用此 ID。")}/></span><input required maxLength={256} disabled={savingConfig || fetchingDifyName} value={configDatasetId} onChange={(event) => { setConfigDatasetId(event.target.value); resetDifyNames(); }} placeholder={t("填写 Dify 知识库 ID")} /></label>}
                <label className="field"><span className="label-with-tip">{configBenchmark === "dify-chat" ? "Chat API Key" : "Dataset API Key"}<i className="field-optional">{t("选填")}</i><InfoTip label={t("查看说明")} text={t(configBenchmark === "dify-chat" ? "在 Dify 应用的 API 访问页面创建，用于调用已发布应用。" : "在 Dify 知识库 API 页面创建，用于访问指定 Dataset。")}/></span><input disabled={savingConfig || fetchingDifyName} className={editingDifyConfig?.has_api_key && !configApiKey ? "masked-secret" : ""} type="password" autoComplete="new-password" value={configApiKey} onChange={(event) => { setConfigApiKey(event.target.value); resetDifyNames(); }} placeholder={editingDifyConfig?.has_api_key ? editingDifyConfig.api_key_masked || "••••••••" : editingConfigId ? t("留空表示保留现有密钥") : configBenchmark === "dify-chat" ? t("填写 Chat API Key") : t("填写 Dataset API Key")} /></label>
              </div>
              {difyEditorError && <p className="dify-dialog-error" role="alert">{difyEditorError}</p>}
              <div className="dify-modal-footer"><span className="dify-footer-spacer" /><button type="button" className="dify-secondary-button" disabled={savingConfig || fetchingDifyName} onClick={closeDifyConfig}>{t("取消")}</button><button className="dify-blue-button" disabled={savingConfig || fetchingDifyName || !configUrl.trim() || (configBenchmark === "dify-retrieve" && !configDatasetId.trim())}>{savingConfig ? t("保存中…") : t("保存")}</button></div>
            </form>
          </dialog>}
        </section>}
        {activeTab === "api" && <section className="panel api-docs"><div className="panel-head"><div><p className="eyebrow">OPENAPI</p><h2>{t("接口文档")}</h2></div><a className="ghost" href="/api/docs" target="_blank" rel="noreferrer">{t("在新窗口打开")}</a></div><iframe title="PrismLab API docs" src="/api/docs" /></section>}
      </div>
    </main>
  </div>;
}
