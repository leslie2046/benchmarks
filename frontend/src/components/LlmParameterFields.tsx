import { RefreshCw } from "lucide-react";
import { tr, type Language } from "../i18n";
import type { LlmParameters } from "../types";
import { InfoTip } from "./InfoTip";

export function applicableParameters(definition: LlmParameters, values: Record<string, string | number>) {
  const effective = Object.fromEntries(Object.entries(definition.parameters).map(([name, spec]) => [name, values[name] ?? spec.default]));
  return Object.entries(definition.parameters).filter(([, spec]) => Object.entries(spec.enabled_when).every(([key, value]) => effective[key] === value));
}

export function LlmParameterFields({ definition, values, onChange, language, loading, error, onRefresh }: {
  definition: LlmParameters | null; values: Record<string, string | number>; onChange: (values: Record<string, string | number>) => void;
  language: Language; loading: boolean; error: string; onRefresh: () => void;
}) {
  const t = (s: string) => tr(language, s);
  function change(name: string, value: string) {
    if (!definition) return;
    const next = { ...values };
    if (!value) delete next[name];
    else next[name] = definition.parameters[name].type === "enum" ? value : Number(value);
    const active = new Set(applicableParameters(definition, next).map(([key]) => key));
    onChange(Object.fromEntries(Object.entries(next).filter(([key]) => active.has(key))));
  }
  return <section className="llm-parameters" aria-label={t("模型参数")} aria-busy={loading}>
    <div className="llm-parameters-head"><strong>{t("模型参数")}</strong><div>
      <button type="button" className="ghost" disabled={loading || !definition} onClick={() => onChange({})}>{t("恢复默认值")}</button>
      {definition?.can_refresh && <button type="button" className="ghost" disabled={loading} onClick={onRefresh}><RefreshCw aria-hidden="true" />{t("刷新模型能力")}</button>}
    </div></div>
    {loading && <small role="status">{t("加载中…")}</small>}
    {error && <p className="playground-error-box" role="alert">{error}</p>}
    {definition && <>
      <small className="field-help">{definition.model_specific ? t("参数来自模型 YAML 定义；服务声明可通过刷新补充。") : t("此模型使用基础兼容参数；特殊能力尚未声明，可在 YAML 中补充。")}</small>
      <div className="llm-model-metadata">
        <span>{t("上下文窗口")} · {definition.metadata.context_window ?? definition.metadata.context_length ?? t("未知")}</span>
        <span>{t("服务输出上限")} · {definition.metadata.max_output_tokens ?? t("未知")}</span>
        <InfoTip label={t("查看说明")} text={t("容量信息不是请求参数；未知表示服务没有声明，并非没有限制。")}/>
      </div>
      <div className="llm-parameter-grid">{applicableParameters(definition, values).map(([name, spec]) => <label className="field" key={name}>
        <span className="label-with-tip">{t(spec.label)}<InfoTip label={t("查看说明")} text={t(spec.description)}/></span>
        {spec.type === "enum" ? <select value={values[name] ?? ""} onChange={e => change(name, e.target.value)}>
          <option value="">{t("使用服务默认")}{spec.default ? ` (${spec.default})` : ""}</option>
          {spec.values.map(value => <option value={value} key={value}>{value === "enabled" ? t("开启") : value === "disabled" ? t("关闭") : value}</option>)}
        </select> : <input type="number" min={spec.min} max={spec.max} step={spec.step ?? (spec.type === "integer" ? 1 : "any")} value={values[name] ?? ""} onChange={e => change(name, e.target.value)} placeholder={name === "max_tokens" ? t("使用服务默认") : spec.default != null ? String(spec.default) : t("使用服务默认")} />}
      </label>)}</div>
      <small className="field-help">{t("刷新保留有效参数，不再支持的设置会恢复默认值。")}</small>
      <small className="field-help">{t("TTFT 为首个输出（含思考）延迟；TPOT 和速度按服务报告的总输出 token 计算。")}</small>
    </>}
  </section>;
}
