import { FormEvent, useEffect, useRef, useState } from "react";
import { Send, Square } from "lucide-react"; import { LLM_METRICS, llmMetricKey, llmMetricLabel, llmMetricUnit, llmMetricTip } from "../llmMetrics";
import { api, streamPlayground } from "../api";
import { DEFAULT_RERANKER_DOCUMENTS, DEFAULT_TEST_QUERIES } from "../benchmarkDefaults";
import { tr, type Language } from "../i18n";
import { providerDisplayName } from "../providerPresets";
import type { Catalog, LlmParameters, PlaygroundResult } from "../types";
import { applicableParameters, LlmParameterFields } from "./LlmParameterFields";
import { InfoTip } from "./InfoTip";
import { createDocumentDraft, DocumentListEditor } from "./DocumentListEditor";

function readAudio(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(new Error("Could not read audio file"));
    reader.readAsDataURL(file);
  });
}

export function Playground({ catalog, language }: { catalog: Catalog | null; language: Language }) {
  const t = (value: string) => tr(language, value);
  const [benchmarkId, setBenchmarkId] = useState("embedding");
  const [providerId, setProviderId] = useState("");
  const [modelName, setModelName] = useState("");
  const [credentialId, setCredentialId] = useState("");
  const [text, setText] = useState(DEFAULT_TEST_QUERIES.embedding);
  const [queries, setQueries] = useState<Record<string, string>>(DEFAULT_TEST_QUERIES);
  const [documents, setDocuments] = useState(() => DEFAULT_RERANKER_DOCUMENTS.map(createDocumentDraft));
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [result, setResult] = useState<PlaygroundResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [parameters, setParameters] = useState<Record<string, string | number>>({});
  const [definition, setDefinition] = useState<LlmParameters | null>(null);
  const [parameterLoading, setParameterLoading] = useState(false);
  const [parameterError, setParameterError] = useState("");
  const parameterRequest = useRef(0);
  const [reasoningText, setReasoningText] = useState("");
  const [streamText, setStreamText] = useState("");
  const [streamTtft, setStreamTtft] = useState<number | null>(null);
  const [stopped, setStopped] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  const benchmark = catalog?.benchmarks.find((item) => item.id === benchmarkId);
  const providers = benchmark?.providers.filter((item) => item.endpoint_configured) ?? [];
  const provider = providers.find((item) => item.id === providerId) ?? providers[0];
  const models = provider?.models.filter((item) => item.name) ?? [];
  const selectedModel = models.find((item) => (item.alias || item.name) === modelName) ?? models[0];
  const model = selectedModel?.alias || selectedModel?.name || null;
  const credentials = selectedModel?.credentials || [];
  const isDify = benchmarkId.startsWith("dify-");
  const output = result ? typeof result.data === "string" ? result.data : JSON.stringify(result.data, (key, value) => benchmarkId === "llm" && ["ttft_ms", "tpot_ms", "tokens_per_second"].includes(key) && typeof value === "number" ? Math.round(value) : value, 2) : "";
  const timing = result?.data && typeof result.data === "object" ? result.data as Record<string, unknown> : {};

  async function loadParameters(refresh = false) {
    const revision = ++parameterRequest.current;
    setParameterLoading(true); setParameterError("");
    try {
      const value = await api.llmParameters({ id: provider!.id, model: model || "", credential_id: credentialId || null }, refresh);
      if (revision === parameterRequest.current) {
        setDefinition(value);
        if (refresh) setParameters(current => {
          const valid = Object.fromEntries(Object.entries(current).filter(([name, input]) => {
            const spec = value.parameters[name];
            return spec && (spec.type === "enum" ? spec.values.includes(String(input)) : typeof input === "number" && Number.isFinite(input) && input >= (spec.min ?? -Infinity) && input <= (spec.max ?? Infinity) && (spec.type !== "integer" || Number.isInteger(input)));
          }));
          const active = new Set(applicableParameters(value, valid).map(([name]) => name));
          return Object.fromEntries(Object.entries(valid).filter(([name]) => active.has(name)));
        });
      }
    } catch (reason) { if (revision === parameterRequest.current) setParameterError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (revision === parameterRequest.current) setParameterLoading(false); }
  }
  useEffect(() => {
    setParameters({}); setDefinition(null); setParameterError("");
    if (benchmarkId === "llm" && provider && (credentials.length <= 1 || credentialId)) void loadParameters();
    else setParameterLoading(false);
    return () => { parameterRequest.current += 1; };
  }, [benchmarkId, provider?.id, model, credentialId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!provider || busy) return;
    const documentTexts = documents.map((item) => item.text.trim());
    if (benchmarkId === "reranker" && !documentTexts.length) {
      setError(t("请至少填写一条 Document。"));
      return;
    }
    if (benchmarkId === "reranker" && documentTexts.some((item) => !item)) {
      setError(t("请填写每条文档，或删除空白条目。"));
      return;
    }
    setBusy(true);
    setError("");
    setResult(null);
    setStreamText("");
    setReasoningText("");
    setStreamTtft(null);
    setStopped(false);
    const abort = new AbortController();
    controller.current = abort;
    try {
      if (benchmarkId === "audio" && audioFile && audioFile.size > 5_000_000) {
        throw new Error(t("音频文件不能超过 5 MB。"));
      }
      const payload = {
        benchmark: benchmarkId,
        provider_id: provider.id,
        model,
        credential_id: credentialId || null,
        text: benchmarkId === "embedding" ? text : null,
        query: benchmarkId === "llm" || benchmarkId === "reranker" || isDify ? queries[benchmarkId] : null,
        max_tokens: typeof parameters.max_tokens === "number" ? parameters.max_tokens : Number(definition?.parameters.max_tokens?.default ?? 256),
        llm_parameters: benchmarkId === "llm" ? parameters : {},
        documents: benchmarkId === "reranker" ? documentTexts : [],
        audio_name: benchmarkId === "audio" ? audioFile?.name : null,
        audio_base64: benchmarkId === "audio" && audioFile ? await readAudio(audioFile) : null,
      };
      const response = benchmarkId === "llm"
        ? await streamPlayground(payload, (chunk, ttft, channel) => {
          if (channel === "reasoning") setReasoningText(current => (current + chunk).slice(0, 100_000));
          else setStreamText((current) => (current + chunk).slice(0, 100_000));
          setStreamTtft(ttft);
        }, abort.signal)
        : await api.playground(payload);
      setResult(response);
    } catch (cause) {
      if (abort.signal.aborted) setStopped(true);
      else setError(cause instanceof Error ? cause.message : t("请求失败"));
    } finally {
      setBusy(false);
      controller.current = null;
    }
  }

  return <section className="playground-grid">
    <article className="panel">
      <div className="panel-head"><div><h2>{t("单次请求")}</h2><p>{t("配置并发送一次真实服务请求")}</p></div></div>
      <form className="playground-form" onSubmit={submit}>
        <fieldset disabled={busy}>
        <label className="field"><span className="label-with-tip">{t("测试类型")}<InfoTip label={t("查看说明")} text={t("选择要调用的接口能力，并决定后续输入字段和返回格式。")}/></span><select value={benchmarkId} onChange={(event) => { setBenchmarkId(event.target.value); setProviderId(""); setModelName(""); setCredentialId(""); setResult(null); }}>{catalog?.benchmarks.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label>
        <label className="field"><span className="label-with-tip">{t(isDify ? "Dify 配置" : "模型供应商")}<InfoTip label={t("查看说明")} text={t("选择实际接收本次请求的已配置服务。")}/></span><select value={provider?.id ?? ""} onChange={(event) => { setProviderId(event.target.value); setModelName(""); setCredentialId(""); setResult(null); }}>{providers.map((item) => <option value={item.id} key={item.id}>{providerDisplayName(item.provider || item.id, language, item.label)}</option>)}</select>{!providers.length && <small>{t("此类型暂无已配置的服务。")}</small>}</label>
        {!!models.length && <label className="field"><span className="label-with-tip">{t("模型")}<InfoTip label={t("查看说明")} text={t("选择该供应商下用于本次请求的具体模型。")}/></span><select value={model ?? ""} onChange={(event) => { setModelName(event.target.value); setCredentialId(""); setResult(null); }}>{models.map((item) => <option value={item.alias || item.name || ""} key={`${item.benchmark}-${item.alias || item.name}`}>{item.alias || item.name}</option>)}</select></label>}
        {credentials.length > 1 && <label className="field"><span className="label-with-tip">{t("凭据")}<InfoTip label={t("查看说明")} text={t("同一模型存在多个服务端点时，选择本次请求使用的凭据。")}/></span><select required value={credentialId} onChange={(event) => { setCredentialId(event.target.value); setResult(null); }}><option value="">{t("选择凭据")}</option>{credentials.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        {benchmarkId === "embedding" && <label className="field"><span>{t("输入文本")}</span><textarea required value={text} onChange={(event) => setText(event.target.value)} placeholder={t("输入要生成向量的文本")} /></label>}
        {(benchmarkId === "llm" || benchmarkId === "reranker" || isDify) && <label className="field"><span>{t("问题")}</span><textarea required value={queries[benchmarkId] || ""} onChange={(event) => setQueries((current) => ({ ...current, [benchmarkId]: event.target.value }))} placeholder={t("输入要提交的问题")} /></label>}
        {benchmarkId === "llm" && <LlmParameterFields definition={definition} values={parameters} onChange={setParameters} language={language} loading={parameterLoading} error={parameterError} onRefresh={() => void loadParameters(true)} />}
        {benchmarkId === "reranker" && <DocumentListEditor documents={documents} onChange={setDocuments} language={language} />}
        {benchmarkId === "dify-retrieve" && <small className="field-help">{provider?.dataset_id ? `${t("知识库 ID")} · ${provider.dataset_id}` : t("请先在 Dify 配置中填写知识库 ID")}</small>}
        {benchmarkId === "audio" && <label className="field"><span>{t("音频文件")}</span><input required type="file" accept="audio/*,.wav,.mp3,.m4a,.flac" onChange={(event) => setAudioFile(event.target.files?.[0] ?? null)} /><small>{t("最大 5 MB；文件仅用于本次请求。")}</small></label>}
        <button className="primary" disabled={busy || !provider || (benchmarkId === "llm" && (!definition || parameterLoading))}><Send aria-hidden="true" />{busy ? t("请求中…") : t("发送请求")}</button>
        </fieldset>
      </form>
    </article>
    <article className="panel playground-result" aria-live="polite">
      <div className="panel-head"><div><h2>{t("返回结果")}</h2><p>{t("查看状态、耗时与响应正文")}</p></div>{result && <span className={result.ok ? "playground-ok" : "playground-error"}>HTTP {result.status_code} · {Math.round(result.duration_ms)} ms</span>}</div>
      {benchmarkId === "llm" && (busy || result || streamText || stopped || error) ? <>
        {busy && <div className="panel-head"><span>{t("正在生成…")}</span><button className="ghost" type="button" onClick={() => controller.current?.abort()}><Square aria-hidden="true" />{t("停止生成")}</button></div>}
        <div className="llm-timing-strip">{LLM_METRICS.map((metric) => {
          const value = timing[llmMetricKey(metric)] ?? (metric === "ttft" ? streamTtft : null);
          return <span key={metric}><span className="label-with-tip">{t(llmMetricLabel(metric))}<InfoTip label={t("查看说明")} text={t(llmMetricTip(metric))}/></span><strong>{typeof value === "number" ? Math.round(value) : "—"} {llmMetricUnit(metric)}</strong></span>;
        })}</div>
        {!!reasoningText && <details><summary>{t("思考过程")}</summary><pre>{reasoningText}</pre></details>}
        <pre>{streamText || (typeof timing.content === "string" ? timing.content : "") || (busy ? t("正在等待服务响应…") : "")}</pre>
        {error && <div className="playground-error-box">{error}</div>}
        {stopped && <small className="field-help">{t("已停止生成，已接收的内容已保留。")}</small>}
        {result && <details><summary>{t("原始结果")}</summary><pre>{output}</pre></details>}
        {(result?.truncated || streamText.length >= 100_000) && <small className="field-help">{t("响应过长，仅显示前 100 KB。")}</small>}
      </> : busy ? <div className="empty-state">{t("正在等待服务响应…")}</div> : error ? <div className="playground-error-box">{error}</div> : result ? <><pre>{output}</pre>{result.truncated && <small className="field-help">{t("响应过长，仅显示前 100 KB。")}</small>}</> : <div className="empty-state">{t("选择服务并发送一次请求，结果会显示在这里。")}</div>}
    </article>
  </section>;
}
