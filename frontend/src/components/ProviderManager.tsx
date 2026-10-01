import { FormEvent, useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import { api, type DiscoveredModel, type ProviderAccess } from "../api";
import { tr, type Language } from "../i18n";
import { providerDisplayName, providerPresets } from "../providerPresets";
import type { Benchmark, ModelConfig, ModelCredential, ServiceConfig } from "../types";
import { InfoTip } from "./InfoTip";
import { ProviderLogo } from "./ProviderLogo";

type ModelEditor = {
  kind: { id: string; label: string };
  config: ServiceConfig | null;
  index: number | null;
};

type DiscoveryEditor = {
  kind: { id: string; label: string };
  config: ServiceConfig | null;
  serverUrl: string;
  apiKey: string;
  sourceCredentialId?: string;
};

const discoverableProviders = new Set(["siliconflow", "xinference", "vllm"]);

const blankCredential = (modelName = ""): ModelCredential => ({ name: "Default", server_url: "", model_uid: modelName, api_key: "" });

const defaultModelName = (benchmark: string) => {
  if (benchmark.toLowerCase().includes("rerank")) return "BAAI/bge-reranker-v2-m3";
  if (benchmark.toLowerCase().includes("embed")) return "BAAI/bge-m3";
  return "";
};

export function ProviderManager({ configs, benchmarks, language, onChanged }: {
  configs: ServiceConfig[];
  benchmarks: Benchmark[];
  language: Language;
  onChanged: () => Promise<void>;
}) {
  const t = (value: string) => tr(language, value);
  const kinds = useMemo(() => [...new Map(benchmarks.filter((item) => !item.id.startsWith("dify-")).flatMap((item) => item.provider_kinds.map((kind) => [kind.id, kind] as const))).values()], [benchmarks]);
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [editor, setEditor] = useState<ModelEditor | null>(null);
  const [model, setModel] = useState<ModelConfig | null>(null);
  const [credential, setCredential] = useState<ModelCredential | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [verified, setVerified] = useState(false);
  const [discovery, setDiscovery] = useState<DiscoveryEditor | null>(null);
  const [discovered, setDiscovered] = useState<DiscoveredModel[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [discoveryTypes, setDiscoveryTypes] = useState<Record<string, string>>({});
  const [discoverySearch, setDiscoverySearch] = useState("");

  const availableBenchmarks = benchmarks.filter((item) => !item.id.startsWith("dify-") && item.provider_kinds.some((kind) => kind.id === editor?.kind.id));
  const providerGroups = kinds.map((kind) => {
    const records = configs.filter((config) => config.provider === kind.id);
    const models = records.flatMap((config) => config.models.map((item, index) => ({ config, model: item, index })));
    return { kind, records, models };
  });
  const visibleGroups = providerGroups.filter((group) => !search.trim() || `${providerDisplayName(group.kind.id, language, group.kind.label)} ${group.kind.label} ${group.kind.id} ${group.models.map(({ model }) => `${model.name || ""} ${model.alias || ""}`).join(" ")}`.toLowerCase().includes(search.trim().toLowerCase()));

  useEffect(() => {
    if (!editor && !discovery) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") { closeEditor(); closeDiscovery(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editor, discovery]);

  useEffect(() => { setVerified(false); }, [model?.name, model?.benchmark, credential?.server_url, credential?.api_key]);

  function closeEditor() {
    setEditor(null);
    setModel(null);
    setCredential(null);
    setNotice("");
    setVerified(false);
  }

  function closeDiscovery() {
    setDiscovery(null);
    setDiscovered([]);
    setSelected({});
    setDiscoveryTypes({});
    setDiscoverySearch("");
    setNotice("");
    setVerified(false);
  }

  function openDiscovery(kind: { id: string; label: string }, config: ServiceConfig | null) {
    const source = config?.models.flatMap((item) => item.credentials || []).find((item) => item.id);
    setDiscovery({ kind, config, serverUrl: source?.server_url || providerPresets[kind.id]?.serverUrl || "", apiKey: "", sourceCredentialId: source?.id });
    setDiscovered([]);
    setSelected({});
    setDiscoveryTypes({});
    setDiscoverySearch("");
    setVerified(false);
    setNotice("");
  }

  function discoveryAccess(): ProviderAccess | null {
    if (!discovery) return null;
    return { provider: discovery.kind.id, server_url: discovery.serverUrl.trim(), api_key: discovery.apiKey || undefined, config_id: discovery.config?.id, credential_id: discovery.sourceCredentialId };
  }

  async function verifyDiscovery() {
    const access = discoveryAccess();
    if (!access) return;
    setBusy(true); setNotice(""); setVerified(false);
    try { await api.verifyProvider(access); setVerified(true); }
    catch (error) { setNotice(error instanceof Error ? error.message : t("验证失败")); }
    finally { setBusy(false); }
  }

  async function fetchModels() {
    const access = discoveryAccess();
    if (!access || !discovery) return;
    setBusy(true); setNotice(""); setDiscovered([]); setSelected({});
    try {
      const result = await api.listProviderModels(access);
      const supported = new Set(benchmarks.filter((item) => item.provider_kinds.some((kind) => kind.id === discovery.kind.id)).map((item) => item.id));
      const existing = new Set(configs.filter((config) => config.provider === discovery.kind.id).flatMap((config) => config.models.map((item) => item.name)));
      setDiscovered(result.models);
      setSelected(Object.fromEntries(result.models.map((item) => [item.id, Boolean(item.benchmark && supported.has(item.benchmark) && !existing.has(item.id))])));
      setDiscoveryTypes(Object.fromEntries(result.models.filter((item) => item.benchmark).map((item) => [item.id, item.benchmark!])));
      setVerified(true);
    } catch (error) { setNotice(error instanceof Error ? error.message : t("获取模型失败")); }
    finally { setBusy(false); }
  }

  async function saveDiscovered() {
    if (!discovery) return;
    const supported = new Set(benchmarks.filter((item) => item.provider_kinds.some((kind) => kind.id === discovery.kind.id)).map((item) => item.id));
    const existing = new Set(configs.filter((config) => config.provider === discovery.kind.id).flatMap((config) => config.models.map((item) => item.name)));
    const imports = discovered.filter((item) => selected[item.id] && !existing.has(item.id) && supported.has(discoveryTypes[item.id]));
    if (!imports.length) return;
    const models: ModelConfig[] = imports.map((item) => ({ name: item.id, alias: item.id, benchmark: discoveryTypes[item.id], base_url: null, credentials: [{ name: "Default", server_url: discovery.serverUrl.trim(), model_uid: item.id, api_key: discovery.apiKey || undefined, copy_key_from: discovery.apiKey ? undefined : discovery.sourceCredentialId }] }));
    setBusy(true); setNotice("");
    try { await persist([...(discovery.config?.models || []), ...models], discovery.config, discovery.kind); closeDiscovery(); }
    catch (error) { setNotice(error instanceof Error ? error.message : t("保存模型失败")); }
    finally { setBusy(false); }
  }

  function openEditor(kind: { id: string; label: string }, config: ServiceConfig | null, index: number | null) {
    const item = config && index !== null ? config.models[index] : null;
    const startingBenchmark = benchmarks.find((entry) => !entry.id.startsWith("dify-") && entry.provider_kinds.some((provider) => provider.id === kind.id))?.id || "embedding";
    const defaultName = defaultModelName(startingBenchmark);
    const startingModel = item ? { ...item, alias: item.alias || item.name || "", credentials: item.credentials?.map((entry) => ({ ...entry })) || [] } : { name: defaultName, alias: defaultName, benchmark: startingBenchmark, base_url: null, credentials: [] };
    const firstCredential = startingModel.credentials?.[0] || (item?.base_url ? { name: "Default", server_url: item.base_url, model_uid: item.name } : { ...blankCredential(startingModel.name || ""), server_url: providerPresets[kind.id]?.serverUrl || "" });
    setEditor({ kind, config, index });
    setModel(startingModel);
    setCredential({ ...firstCredential, api_key: "" });
    setNotice("");
  }

  function modelAliasTaken(alias: string): boolean {
    const normalized = alias.trim().toLocaleLowerCase();
    return configs.some((config) => config.provider === editor?.kind.id && config.models.some((item, index) => {
      if (config.id === editor?.config?.id && index === editor.index) return false;
      return (item.alias || item.name || "").trim().toLocaleLowerCase() === normalized;
    }));
  }

  async function persist(nextModels: ModelConfig[], config: ServiceConfig | null, kind: { id: string; label: string }) {
    const payload = { name: config?.name || providerPresets[kind.id]?.en || kind.label, provider: kind.id, icon: config?.icon || "cube", models: nextModels };
    if (config) await api.updateServiceConfig(config.id, payload);
    else await api.createServiceConfig(payload);
    await onChanged();
  }

  async function saveModel(event: FormEvent) {
    event.preventDefault();
    if (!editor || !model || !credential) return;
    const alias = (model.alias || model.name || "").trim();
    if (modelAliasTaken(alias)) { setNotice(t("模型别名已存在，请换一个。")); return; }
    const normalizedCredential: ModelCredential = {
      ...credential,
      name: credential.name.trim() || "Default",
      server_url: credential.server_url.trim(),
      model_uid: model.name?.trim() || null,
      api_key: credential.api_key || undefined,
    };
    const nextModel: ModelConfig = {
      ...model,
      name: model.name?.trim() || null,
      alias,
      base_url: null,
      credentials: [normalizedCredential],
    };
    const nextModels = [...(editor.config?.models || [])];
    if (editor.index === null) nextModels.push(nextModel);
    else nextModels[editor.index] = nextModel;
    setBusy(true);
    setNotice("");
    try {
      await persist(nextModels, editor.config, editor.kind);
      closeEditor();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : t("保存服务配置失败"));
    } finally { setBusy(false); }
  }

  async function verifyModel() {
    if (!editor || !model || !credential) return;
    setBusy(true); setNotice(""); setVerified(false);
    try {
      await api.verifyProvider({ provider: editor.kind.id, server_url: credential.server_url.trim(), api_key: credential.api_key || undefined, config_id: editor.config?.id, credential_id: credential.id, benchmark: model.benchmark, model: model.name || undefined });
      setVerified(true);
    } catch (error) { setNotice(error instanceof Error ? error.message : t("验证失败")); }
    finally { setBusy(false); }
  }

  async function deleteModel() {
    if (!editor?.config || editor.index === null) return;
    if (!window.confirm(`${t("删除模型")} “${model?.alias || model?.name}”? ${t("此操作无法撤销。")}`)) return;
    setBusy(true);
    setNotice("");
    try {
      await persist(editor.config.models.filter((_, index) => index !== editor.index), editor.config, editor.kind);
      closeEditor();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : t("删除模型失败"));
    } finally { setBusy(false); }
  }

  return <section className="dify-providers">
    <div className="dify-providers-heading"><div><h2>{t("模型供应商")}</h2><p>{t("选择供应商，添加模型并配置对应的服务凭据。")}</p></div></div>
    <div className="dify-provider-toolbar"><label><Search className="search-icon" aria-hidden="true" /><input aria-label={t("搜索模型或供应商")} value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("搜索模型或供应商")} /></label><span>{kinds.length} {t("个供应商")}</span></div>
    <div className="dify-provider-stack">{visibleGroups.map(({ kind, records, models }) => {
      const isOpen = expanded[kind.id] ?? models.length > 0;
      const types = benchmarks.filter((item) => !item.id.startsWith("dify-") && item.provider_kinds.some((provider) => provider.id === kind.id));
      return <article className="dify-provider-card" key={kind.id}>
        <header className="dify-provider-card-head"><button className="dify-provider-title" onClick={() => setExpanded((current) => ({ ...current, [kind.id]: !isOpen }))} aria-expanded={isOpen}><span className="dify-chevron">{isOpen ? <ChevronDown aria-hidden="true" /> : <ChevronRight aria-hidden="true" />}</span><ProviderLogo providerId={kind.id} /><strong>{providerDisplayName(kind.id, language, kind.label)}</strong></button><span className="dify-provider-count">{models.length} {t("个模型")}</span></header>
        <div className="dify-provider-tags">{types.map((type) => <span key={type.id}>{type.id.toUpperCase()}</span>)}</div>
        {isOpen && <div className="dify-provider-content"><div className="dify-model-toolbar"><span>{models.length} {t("个模型")}</span><div className="dify-model-toolbar-actions">{discoverableProviders.has(kind.id) && <button onClick={() => openDiscovery(kind, records[0] || null)}><RefreshCw aria-hidden="true" />{t("获取模型列表")}</button>}<button onClick={() => openEditor(kind, records[0] || null, null)}><Plus aria-hidden="true" />{t("添加模型")}</button></div></div><div className="dify-model-list">{models.map(({ config, model: item, index }) => <div className="dify-model-row" key={`${config.id}-${index}`}><div className="dify-model-main"><strong>{item.alias || item.name}</strong><span className="dify-type-tag">{item.benchmark.toUpperCase()}</span><small>{item.name}</small></div><div className="dify-model-actions"><span>{t("已配置凭据")}</span><button onClick={() => openEditor(kind, config, index)}>{t("配置")}</button></div></div>)}{!models.length && <div className="dify-empty compact">{t("暂无模型")}</div>}</div></div>}
        {!isOpen && <div className="dify-provider-collapsed"><button onClick={() => setExpanded((current) => ({ ...current, [kind.id]: true }))}>{t("显示模型")}<ChevronRight aria-hidden="true" /></button><div className="dify-model-toolbar-actions">{discoverableProviders.has(kind.id) && <button onClick={() => openDiscovery(kind, records[0] || null)}><RefreshCw aria-hidden="true" />{t("获取模型列表")}</button>}<button onClick={() => openEditor(kind, records[0] || null, null)}><Plus aria-hidden="true" />{t("添加模型")}</button></div></div>}
      </article>;
    })}{!visibleGroups.length && <div className="dify-empty">{t("没有匹配的模型或供应商")}</div>}</div>
    {editor && model && credential && <div className="dify-modal-backdrop"><div className="dify-modal dify-credential-modal" role="dialog" aria-modal="true" aria-label={t(editor.index === null ? "添加模型" : "配置模型")}><div className="dify-modal-head"><h2>{t(editor.index === null ? "添加模型" : "配置模型")}</h2><button type="button" className="dify-close" aria-label={t("关闭")} onClick={closeEditor}><X aria-hidden="true" /></button></div><form onSubmit={saveModel}><div className="dify-modal-body dify-credential-fields">
      <label className="dify-field"><span className="label-with-tip">{t("模型类型")}<b className="field-required" aria-hidden="true">*</b><InfoTip label={t("查看说明")} text={t("决定模型使用的请求协议和参与的测试类型。")}/></span><select required value={model.benchmark} onChange={(event) => { const benchmark = event.target.value; const currentDefault = defaultModelName(model.benchmark); const name = !model.name || model.name === currentDefault ? defaultModelName(benchmark) : model.name; const alias = !model.alias || model.alias === model.name ? name : model.alias; setModel({ ...model, benchmark, name, alias }); if (!credential.model_uid || credential.model_uid === model.name) setCredential({ ...credential, model_uid: name }); }}>{availableBenchmarks.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      <label className="dify-field"><span className="label-with-tip">{t("模型名")}<b className="field-required" aria-hidden="true">*</b><InfoTip label={t("查看说明")} text={t("发送请求时传给服务端的真实模型标识，例如 BAAI/bge-m3。")}/></span><input required value={model.name || ""} onChange={(event) => { const value = event.target.value; const alias = !model.alias || model.alias === model.name ? value : model.alias; setModel({ ...model, name: value, alias }); if (!credential.model_uid || credential.model_uid === model.name) setCredential({ ...credential, model_uid: value }); }} placeholder={defaultModelName(model.benchmark)} /></label>
      <label className="dify-field"><span className="label-with-tip">{t("模型别名")}<b className="field-required" aria-hidden="true">*</b><InfoTip label={t("查看说明")} text={t("仅用于 PerfLab 界面识别模型；同一供应商下不可重复。")}/></span><input required value={model.alias || ""} onChange={(event) => setModel({ ...model, alias: event.target.value })} placeholder={t("例如 本地 bge-m3")} /></label>
      <div className="dify-form-divider"><strong>{t("模型凭据")}</strong></div>
      <label className="dify-field"><span className="label-with-tip">{t("服务器 URL")}<b className="field-required" aria-hidden="true">*</b><InfoTip label={t("查看说明")} text={t("填写服务根地址即可；PerfLab 会根据模型类型自动补齐接口路径。")}/></span><input required type="url" value={credential.server_url} onChange={(event) => setCredential({ ...credential, server_url: event.target.value })} placeholder="https://host:9997" /><small>{t("只需填写服务器根地址，接口路径会自动补齐。")}</small></label>
      <label className="dify-field"><span className="label-with-tip">API Key <i className="field-optional">{t("选填")}</i><InfoTip label={t("查看说明")} text={t("用于服务端鉴权；保存后会加密存储，编辑时留空可保留原密钥。")}/></span><input className={credential.has_api_key && !credential.api_key ? "masked-secret" : ""} type="password" autoComplete="new-password" value={credential.api_key || ""} onChange={(event) => setCredential({ ...credential, api_key: event.target.value })} placeholder={credential.has_api_key ? credential.api_key_masked || "••••••••" : editor.index === null ? t("留空表示服务不需要密钥") : t("留空表示保留现有密钥")} /></label>
      </div>{notice && <p className="dify-dialog-error" role="alert">{notice}</p>}{verified && <p className="dify-dialog-success" role="status">{t("验证成功，服务接口可访问。")}</p>}<div className="dify-modal-footer">{editor.index !== null && <button type="button" className="dify-delete-button" disabled={busy} onClick={() => void deleteModel()}><Trash2 aria-hidden="true" />{t("移除模型")}</button>}<span className="dify-footer-spacer" /><button type="button" className="dify-secondary-button" disabled={busy || !credential.server_url.trim() || !model.name?.trim()} onClick={() => void verifyModel()}>{busy ? t("验证中…") : t("验证 API Key")}</button><button type="button" className="dify-secondary-button" onClick={closeEditor}>{t("取消")}</button><button className="dify-blue-button" disabled={busy}>{busy ? t("保存中…") : t("保存")}</button></div></form></div></div>}
    {discovery && <div className="dify-modal-backdrop"><div className="dify-modal dify-discovery-modal" role="dialog" aria-modal="true" aria-label={t("获取模型列表")}><div className="dify-modal-head"><div><h2>{providerDisplayName(discovery.kind.id, language, discovery.kind.label)} · {t("获取模型列表")}</h2><p>{t("验证和获取不会保存配置；选择模型后再保存。")}</p></div><button type="button" className="dify-close" aria-label={t("关闭")} onClick={closeDiscovery}><X aria-hidden="true" /></button></div><div className="dify-modal-body"><label className="dify-field">{t("服务器 URL")}<input type="url" value={discovery.serverUrl} onChange={(event) => { setDiscovery({ ...discovery, serverUrl: event.target.value }); setVerified(false); setDiscovered([]); setSelected({}); }} placeholder="https://host:9997" /></label><label className="dify-field">API Key <i className="field-optional">{t("选填")}</i><input type="password" autoComplete="new-password" value={discovery.apiKey} onChange={(event) => { setDiscovery({ ...discovery, apiKey: event.target.value }); setVerified(false); setDiscovered([]); setSelected({}); }} placeholder={discovery.sourceCredentialId ? t("留空表示使用已保存密钥") : t("留空表示服务不需要密钥")} /></label><div className="dify-discovery-actions"><button type="button" className="dify-secondary-button" disabled={busy || !discovery.serverUrl.trim()} onClick={() => void verifyDiscovery()}>{busy ? t("验证中…") : t("验证 API Key")}</button><button type="button" className="dify-secondary-button" disabled={busy || !discovery.serverUrl.trim()} onClick={() => void fetchModels()}><RefreshCw aria-hidden="true" />{busy ? t("获取中…") : t("获取所有模型")}</button>{verified && <span className="dify-verified" role="status">{t("验证成功")}</span>}</div>{discovered.length > 0 && <div className="dify-discovery-list"><div className="dify-discovery-list-head"><strong>{discovered.length} {t("个模型")}</strong><input aria-label={t("搜索模型")} value={discoverySearch} onChange={(event) => setDiscoverySearch(event.target.value)} placeholder={t("搜索模型")} /></div><div className="dify-discovery-scroll">{discovered.filter((item) => item.id.toLowerCase().includes(discoverySearch.trim().toLowerCase())).map((item) => { const existing = configs.some((config) => config.provider === discovery.kind.id && config.models.some((model) => model.name === item.id)); const options = benchmarks.filter((entry) => entry.provider_kinds.some((kind) => kind.id === discovery.kind.id) && !entry.id.startsWith("dify-")); const supported = options.some((entry) => entry.id === discoveryTypes[item.id]); return <div className="dify-discovery-row" key={item.id}><label><input type="checkbox" checked={Boolean(selected[item.id])} disabled={Boolean(existing) || !supported} onChange={(event) => setSelected({ ...selected, [item.id]: event.target.checked })} /><span title={item.id}>{item.id}</span></label>{existing ? <small>{t("已添加")}</small> : <select aria-label={`${item.id} ${t("模型类型")}`} value={discoveryTypes[item.id] || ""} onChange={(event) => { setDiscoveryTypes({ ...discoveryTypes, [item.id]: event.target.value }); setSelected({ ...selected, [item.id]: Boolean(event.target.value) }); }}><option value="">{t("选择类型")}</option>{options.map((entry) => <option key={entry.id} value={entry.id}>{entry.label}</option>)}</select>}</div>; })}</div></div>}{discovered.length === 0 && verified && <p className="dify-discovery-hint">{t("尚无可导入模型，点击“获取所有模型”刷新列表。")}</p>}</div>{notice && <p className="dify-dialog-error" role="alert">{notice}</p>}<div className="dify-modal-footer"><span className="dify-footer-spacer" /><button type="button" className="dify-secondary-button" onClick={closeDiscovery}>{t("取消")}</button><button type="button" className="dify-blue-button" disabled={busy || !Object.values(selected).some(Boolean)} onClick={() => void saveDiscovered()}>{busy ? t("保存中…") : `${t("保存所选模型")} (${Object.values(selected).filter(Boolean).length})`}</button></div></div></div>}
  </section>;
}
