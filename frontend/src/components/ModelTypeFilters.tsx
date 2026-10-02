import { tr, type Language } from "../i18n";

export function ModelTypeFilters({ value, onChange, counts, language }: {
  value: string; onChange: (value: string) => void; counts: Record<string, number>; language: Language;
}) {
  const t = (s: string) => tr(language, s);
  return <div className="model-type-filters" role="group" aria-label={t("按模型类型过滤")}>
    {["all", ...Object.keys(counts)].map(type => <button type="button" key={type} aria-pressed={value === type} onClick={() => onChange(type)}>{type === "all" ? t("所有模型") : type === "unknown" ? t("未分类") : type === "llm" ? "LLM" : type === "audio" ? "Audio" : type === "embedding" ? "Embedding" : "Reranker"} <span>{type === "all" ? Object.values(counts).reduce((a, b) => a + b, 0) : counts[type]}</span></button>)}
  </div>;
}
