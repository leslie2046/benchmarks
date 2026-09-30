import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { tr, type Language } from "../i18n";
import { providerDisplayName, providerPresets } from "../providerPresets";
import type { Benchmark, ModelConfig, ModelCredential, ServiceConfig } from "../types";

type ModelEditor = {
  kind: { id: string; label: string };
  config: ServiceConfig | null;
  index: number | null;
};

const blankCredential = (modelName = ""): ModelCredential => ({ name: "Default", server_url: "", model_uid: modelName, api_key: "" });

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

  const availableBenchmarks = benchmarks.filter((item) => !item.id.startsWith("dify-") && item.provider_kinds.some((kind) => kind.id === editor?.kind.id));
  const providerGroups = kinds.map((kind) => {
    const records = configs.filter((config) => config.provider === kind.id);
    const models = records.flatMap((config) => config.models.map((item, index) => ({ config, model: item, index })));
    return { kind, records, models };
  });
  const visibleGroups = providerGroups.filter((group) => !search.trim() || `${providerDisplayName(group.kind.id, language, group.kind.label)} ${group.kind.label} ${group.kind.id} ${group.models.map(({ model }) => `${model.name || ""} ${model.alias || ""}`).join(" ")}`.toLowerCase().includes(search.trim().toLowerCase()));

  useEffect(() => {
    if (!editor) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") closeEditor(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editor]);

  function closeEditor() {
    setEditor(null);
    setModel(null);
    setCredential(null);
    setNotice("");
  }

  function openEditor(kind: { id: string; label: string }, config: ServiceConfig | null, index: number | null) {
    const item = config && index !== null ? config.models[index] : null;
    const startingModel = item ? { ...item, credentials: item.credentials?.map((entry) => ({ ...entry })) || [] } : { name: "", alias: "", benchmark: benchmarks.find((entry) => !entry.id.startsWith("dify-") && entry.provider_kinds.some((provider) => provider.id === kind.id))?.id || "embedding", base_url: null, credentials: [] };
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
    const alias = (model.alias || "").trim();
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
    <div className="dify-provider-toolbar"><label><span className="search-icon" aria-hidden="true">⌕</span><input aria-label={t("搜索模型或供应商")} value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("搜索模型或供应商")} /></label><span>{kinds.length} {t("个供应商")}</span></div>
    <div className="dify-provider-stack">{visibleGroups.map(({ kind, records, models }) => {
      const isOpen = expanded[kind.id] ?? models.length > 0;
      const types = benchmarks.filter((item) => !item.id.startsWith("dify-") && item.provider_kinds.some((provider) => provider.id === kind.id));
      return <article className="dify-provider-card" key={kind.id}>
        <header className="dify-provider-card-head"><button className="dify-provider-title" onClick={() => setExpanded((current) => ({ ...current, [kind.id]: !isOpen }))} aria-expanded={isOpen}><strong>{providerDisplayName(kind.id, language, kind.label)}</strong><span className="dify-chevron">{isOpen ? "⌄" : "›"}</span></button><span className="dify-provider-count">{models.length} {t("个模型")}</span></header>
        <div className="dify-provider-tags">{types.map((type) => <span key={type.id}>{type.id.toUpperCase()}</span>)}</div>
        {isOpen && <div className="dify-provider-content"><div className="dify-model-toolbar"><span>{models.length} {t("个模型")}</span><button onClick={() => openEditor(kind, records[0] || null, null)}>＋ {t("添加模型")}</button></div><div className="dify-model-list">{models.map(({ config, model: item, index }) => <div className="dify-model-row" key={`${config.id}-${index}`}><div className="dify-model-main"><strong>{item.alias || item.name}</strong><span className="dify-type-tag">{item.benchmark.toUpperCase()}</span><small>{item.name}</small></div><div className="dify-model-actions"><span>{t("已配置凭据")}</span><button onClick={() => openEditor(kind, config, index)}>{t("配置")}</button></div></div>)}{!models.length && <div className="dify-empty compact">{t("暂无模型")}</div>}</div></div>}
        {!isOpen && <div className="dify-provider-collapsed"><button onClick={() => setExpanded((current) => ({ ...current, [kind.id]: true }))}>{t("显示模型")} ›</button><button onClick={() => openEditor(kind, records[0] || null, null)}>＋ {t("添加模型")}</button></div>}
      </article>;
    })}{!visibleGroups.length && <div className="dify-empty">{t("没有匹配的模型或供应商")}</div>}</div>
    {editor && model && credential && <div className="dify-modal-backdrop"><div className="dify-modal dify-credential-modal" role="dialog" aria-modal="true" aria-label={t(editor.index === null ? "添加模型" : "配置模型")}><div className="dify-modal-head"><div><h2>{t(editor.index === null ? "添加模型" : "配置模型")}</h2><p>{providerDisplayName(editor.kind.id, language, editor.kind.label)}</p></div><button type="button" className="dify-close" aria-label={t("关闭")} onClick={closeEditor}>×</button></div><form onSubmit={saveModel}><div className="dify-modal-body dify-credential-fields">
      <label className="dify-field"><span>{t("模型类型")}</span><select value={model.benchmark} onChange={(event) => setModel({ ...model, benchmark: event.target.value })}>{availableBenchmarks.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      <label className="dify-field"><span>{t("模型名（传参）")}</span><input required value={model.name || ""} onChange={(event) => { const value = event.target.value; setModel({ ...model, name: value }); if (!credential.model_uid || credential.model_uid === model.name) setCredential({ ...credential, model_uid: value }); }} placeholder="BAAI/bge-m3" /></label>
      <label className="dify-field"><span>{t("模型别名（区分）")}</span><input required value={model.alias || ""} onChange={(event) => setModel({ ...model, alias: event.target.value })} placeholder={t("例如 本地 bge-m3")} /></label>
      <div className="dify-form-divider"><strong>{t("模型凭据")}</strong><small>{t("每个模型配置一组凭据")}</small></div>
      <label className="dify-field"><span>{t("凭据名称")}</span><input required value={credential.name} onChange={(event) => setCredential({ ...credential, name: event.target.value })} placeholder={t("例如 主服务")} /></label>
      <label className="dify-field"><span>{t("服务器 URL")}</span><input required type="url" value={credential.server_url} onChange={(event) => setCredential({ ...credential, server_url: event.target.value })} placeholder="https://host:9997" /><small>{t("只需填写服务器根地址，接口路径会自动补齐。")}</small></label>
      <label className="dify-field"><span>API Key</span><input type="password" autoComplete="new-password" value={credential.api_key || ""} onChange={(event) => setCredential({ ...credential, api_key: event.target.value })} placeholder={editor.index === null ? t("留空表示服务不需要密钥") : t("留空表示保留现有密钥")} /></label>
      </div>{notice && <p className="dify-dialog-error" role="alert">{notice}</p>}<div className="dify-modal-footer">{editor.index !== null && <button type="button" className="dify-delete-button" disabled={busy} onClick={() => void deleteModel()}>{t("移除模型")}</button>}<span className="dify-footer-spacer" /><button type="button" className="dify-secondary-button" onClick={closeEditor}>{t("取消")}</button><button className="dify-blue-button" disabled={busy}>{busy ? t("正在验证并保存…") : t("验证并保存")}</button></div></form></div></div>}
  </section>;
}
