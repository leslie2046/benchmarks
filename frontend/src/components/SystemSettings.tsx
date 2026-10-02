import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { api } from "../api";
import { tr, type Language } from "../i18n";
import type { Catalog } from "../types";
import { InfoTip } from "./InfoTip";
import { SearchableSelect } from "./SearchableSelect";
import { providerDisplayName } from "../providerPresets";

export function SystemSettings({ catalog, language }: { catalog: Catalog | null; language: Language }) {
  const t = (text: string) => tr(language, text);
  const choices = (catalog?.benchmarks.find((item) => item.id === "llm")?.providers || []).flatMap((provider) =>
    provider.models.filter((model) => model.name).flatMap((model) => {
      const credentials = model.credentials?.length ? model.credentials : [null];
      return credentials.map((credential) => ({
        selection: { id: provider.id, model: model.alias || model.name || "", credential_id: credential?.id || null },
        label: `${providerDisplayName(provider.provider || provider.id, language, provider.label)} · ${model.alias || model.name}${credentials.length > 1 ? ` · ${credential?.name}` : ""}`,
      }));
    }));
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const stale = Boolean(selected && !choices.some((item) => JSON.stringify(item.selection) === selected));
  useEffect(() => {
    let alive = true;
    api.systemSettings().then((value) => { if (alive) { setSelected(value.default_llm ? JSON.stringify({ ...value.default_llm, credential_id: value.default_llm.credential_id || null }) : ""); setLoaded(true); } })
      .catch((reason) => { if (alive) setError(String(reason.message)); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  return <section className="panel system-settings-panel">
    <div className="panel-head"><div><h2>{t("系统默认 LLM")}</h2><p>{t("用于手动生成运行记录的 AI 测试报告，不改变测试计划中选择的模型。")}</p></div></div>
    <form className="system-settings-form" onSubmit={async (event) => {
      event.preventDefault(); setSaving(true); setError(""); setSaved(false);
      try { await api.saveSystemSettings({ default_llm: selected ? JSON.parse(selected) : null }); setSaved(true); }
      catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
      finally { setSaving(false); }
    }}>
      <div className="field"><span className="label-with-tip">{t("默认分析模型")}<InfoTip label={t("查看说明")} text={t("仅可选择模型供应商中已配置的 LLM；使用其现有端点和凭据。保存配置不会调用模型。")}/></span>
        <SearchableSelect label={t("默认分析模型")} language={language} value={selected} disabled={loading || saving} onChange={value => { setSelected(value); setSaved(false); }} options={[{ value: "", label: t("未设置（禁用 AI 分析）") }, ...choices.map(item => ({ value: JSON.stringify(item.selection), label: item.label }))]} />
        {stale && <small role="alert">{t("原默认模型已失效，请重新选择")}</small>}
        <small className="field-help">{loading ? t("加载中…") : !choices.length ? t("暂无已配置的 LLM，请先在模型供应商中添加。") : t("生成报告可能产生模型调用费用，仅在手动分析时调用。")}</small>
      </div>
      {error && <div className="alert" role="alert">{error}</div>}
      {saved && <p className="success-text" role="status">{t("系统配置已保存")}</p>}
      <button className="primary compact" disabled={!loaded || loading || saving || stale}><Save aria-hidden="true" />{t(saving ? "保存中…" : "保存配置")}</button>
    </form>
  </section>;
}
