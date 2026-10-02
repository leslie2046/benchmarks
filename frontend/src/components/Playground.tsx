import { FormEvent, useEffect, useRef, useState } from "react";
import { ChevronDown, Copy, MessageSquare, Send, SlidersHorizontal, Square, Trash2 } from "lucide-react"; import { LLM_METRICS, llmMetricKey, llmMetricLabel, llmMetricUnit, llmMetricTip } from "../llmMetrics";
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
  const [benchmarkId, setBenchmarkId] = useState("llm");
  const [providerId, setProviderId] = useState("");
  const [modelName, setModelName] = useState("");
  const [credentialId, setCredentialId] = useState("");
  const [text, setText] = useState(DEFAULT_TEST_QUERIES.embedding);
  const [queries, setQueries] = useState<Record<string, string>>(DEFAULT_TEST_QUERIES);
  const [systemPrompt, setSystemPrompt] = useState("You are a helpful assistant.");
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
  const [sentPrompt, setSentPrompt] = useState("");
  const [copyNotice, setCopyNotice] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(true);
  const responseRef = useRef<HTMLDivElement>(null);
  const followOutput = useRef(true);
  const controller = useRef<AbortController | null>(null);
  const activeRequest = useRef(0);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 768px)");
    const update = () => setSettingsOpen(!media.matches);
    update(); media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

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
  const answer = streamText || (typeof timing.content === "string" ? timing.content : "");
  const hasResponse = !!(result || streamText || reasoningText || error || stopped || busy);
  function clearResponse() {
    setResult(null); setStreamText(""); setReasoningText(""); setStreamTtft(null);
    setStopped(false); setError(""); setSentPrompt(""); setCopyNotice(""); followOutput.current = true;
  }
  useEffect(() => { clearResponse(); }, [benchmarkId, provider?.id, model, credentialId]);
  useEffect(() => {
    if (followOutput.current && responseRef.current) responseRef.current.scrollTop = responseRef.current.scrollHeight;
  }, [streamText, reasoningText, result]);
  async function copyResponse() {
    try { await navigator.clipboard.writeText(benchmarkId === "llm" ? answer : output); setCopyNotice(t("已复制")); }
    catch { setCopyNotice(t("复制失败，请手动选择文本复制。")); }
  }
  function stopGeneration() {
    activeRequest.current += 1;
    controller.current?.abort(); controller.current = null;
    setBusy(false); setStopped(true);
  }

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
    if (!provider || busy || (credentials.length > 1 && !credentialId) || (benchmarkId === "llm" && (!definition || parameterLoading))) return;
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
    setSentPrompt(benchmarkId === "embedding" ? text : queries[benchmarkId] || "");
    setCopyNotice(""); followOutput.current = true;
    const abort = new AbortController();
    const revision = ++activeRequest.current;
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
        max_tokens: typeof parameters.max_tokens === "number" ? parameters.max_tokens : null,
        llm_parameters: benchmarkId === "llm" ? parameters : {},
        system_prompt: benchmarkId === "llm" ? systemPrompt : null,
        documents: benchmarkId === "reranker" ? documentTexts : [],
        audio_name: benchmarkId === "audio" ? audioFile?.name : null,
        audio_base64: benchmarkId === "audio" && audioFile ? await readAudio(audioFile) : null,
      };
      const response = benchmarkId === "llm"
        ? await streamPlayground(payload, (chunk, ttft, channel) => {
          if (revision !== activeRequest.current) return;
          if (channel === "reasoning") setReasoningText(current => (current + chunk).slice(0, 100_000));
          else setStreamText((current) => (current + chunk).slice(0, 100_000));
          setStreamTtft(ttft);
        }, abort.signal)
        : await api.playground(payload);
      if (revision === activeRequest.current) setResult(response);
    } catch (cause) {
      if (revision !== activeRequest.current) return;
      if (abort.signal.aborted) setStopped(true);
      else setError(cause instanceof Error ? cause.message : t("请求失败"));
    } finally {
      if (revision === activeRequest.current) {
        setBusy(false); controller.current = null;
      }
    }
  }

  return <form className="playground-workspace" onSubmit={submit}>
    <aside className="playground-settings" aria-label={t("请求配置")}>
      <details className="playground-settings-disclosure" open={settingsOpen} onToggle={(event) => setSettingsOpen(event.currentTarget.open)}>
      <summary className="playground-settings-heading"><SlidersHorizontal aria-hidden="true" /><h2>{t("请求配置")}</h2><ChevronDown className="playground-settings-chevron" aria-hidden="true" /></summary>
      <div className="playground-form">
        <fieldset disabled={busy}>
        <label className="field"><span className="label-with-tip">{t("测试类型")}<InfoTip label={t("查看说明")} text={t("选择要调用的接口能力，并决定后续输入字段和返回格式。")}/></span><select value={benchmarkId} onChange={(event) => { setBenchmarkId(event.target.value); setProviderId(""); setModelName(""); setCredentialId(""); setResult(null); }}>{catalog?.benchmarks.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label>
        <label className="field"><span className="label-with-tip">{t(isDify ? "Dify 配置" : "模型供应商")}<InfoTip label={t("查看说明")} text={t("选择实际接收本次请求的已配置服务。")}/></span><select value={provider?.id ?? ""} onChange={(event) => { setProviderId(event.target.value); setModelName(""); setCredentialId(""); setResult(null); }}>{providers.map((item) => <option value={item.id} key={item.id}>{providerDisplayName(item.provider || item.id, language, item.label)}</option>)}</select>{!providers.length && <small>{t("此类型暂无已配置的服务。")}</small>}</label>
        {!!models.length && <label className="field"><span className="label-with-tip">{t("模型")}<InfoTip label={t("查看说明")} text={t("选择该供应商下用于本次请求的具体模型。")}/></span><select value={model ?? ""} onChange={(event) => { setModelName(event.target.value); setCredentialId(""); setResult(null); }}>{models.map((item) => <option value={item.alias || item.name || ""} key={`${item.benchmark}-${item.alias || item.name}`}>{item.alias || item.name}</option>)}</select></label>}
        {credentials.length > 1 && <label className="field"><span className="label-with-tip">{t("凭据")}<InfoTip label={t("查看说明")} text={t("同一模型存在多个服务端点时，选择本次请求使用的凭据。")}/></span><select required value={credentialId} onChange={(event) => { setCredentialId(event.target.value); setResult(null); }}><option value="">{t("选择凭据")}</option>{credentials.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        {benchmarkId === "llm" && <>
          <label className="field"><span className="label-with-tip">{t("系统提示词")}<InfoTip label={t("查看说明")} text={t("作为 system 消息发送，定义模型角色与回答规则；留空则不发送。")}/></span><textarea rows={4} maxLength={20_000} value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} placeholder={t("可选：定义模型的角色与回答规则")} /><small>{t("仅用于本次 Playground 请求，不改变测试计划或系统默认模型配置。")}</small></label>
          <LlmParameterFields definition={definition} values={parameters} onChange={setParameters} language={language} loading={parameterLoading} error={parameterError} onRefresh={() => void loadParameters(true)} />
        </>}
        {benchmarkId === "reranker" && <DocumentListEditor documents={documents} onChange={setDocuments} language={language} />}
        {benchmarkId === "dify-retrieve" && <small className="field-help">{provider?.dataset_id ? `${t("知识库 ID")} · ${provider.dataset_id}` : t("请先在 Dify 配置中填写知识库 ID")}</small>}
        {benchmarkId === "audio" && <label className="field"><span>{t("音频文件")}</span><input required type="file" accept="audio/*,.wav,.mp3,.m4a,.flac" onChange={(event) => setAudioFile(event.target.files?.[0] ?? null)} /><small>{t("最大 5 MB；文件仅用于本次请求。")}</small></label>}
        </fieldset>
      </div>
      </details>
    </aside>
    <section className={`playground-session playground-result ${benchmarkId === "llm" ? "playground-chat" : ""}`} aria-label={t("响应工作区")}>
      <header className="playground-session-toolbar"><div><strong>{model || provider?.label || benchmark?.label || "Playground"}</strong><small>{t(benchmarkId === "llm" ? "流式输出 · 单次请求，不携带对话历史" : "单次请求 · 查看真实服务响应")}</small></div><div className="playground-session-actions">
        {result && <span className={result.ok ? "playground-ok" : "playground-error"}>HTTP {result.status_code} · {Math.round(result.duration_ms)} ms</span>}
        {benchmarkId !== "llm" && <button type="button" className="icon-button" aria-label={t("复制回答")} title={t("复制回答")} disabled={busy || !output} onClick={() => void copyResponse()}><Copy aria-hidden="true" /></button>}
        <button type="button" className="icon-button" aria-label={t("清空结果")} title={t("清空结果")} disabled={busy || !hasResponse} onClick={clearResponse}><Trash2 aria-hidden="true" /></button>
      </div></header>
      <div className="playground-response-scroll" ref={responseRef} onScroll={(event) => { const node = event.currentTarget; followOutput.current = node.scrollHeight - node.scrollTop - node.clientHeight < 60; }}>
      {!!sentPrompt && <div className="playground-user-message"><span>{t("本次输入")}</span><p>{sentPrompt}</p></div>}
      {benchmarkId === "llm" && (busy || result || streamText || stopped || error) ? <>
        {busy && <p className="playground-generation-status" role="status">{t("正在生成…")}</p>}
        {!!reasoningText && <details><summary>{t("思考过程")}</summary><pre>{reasoningText}</pre></details>}
        <div className="playground-answer">{answer || (busy ? t("正在等待服务响应…") : "")}</div>
        {(answer || reasoningText || result) && <footer className="playground-answer-meta" aria-label={t("回答统计")}>
          <span>{t("输出 tokens")}：{typeof timing.output_tokens === "number" ? Math.round(timing.output_tokens) : "—"}</span>
          {LLM_METRICS.map((metric) => {
            const value = timing[llmMetricKey(metric)] ?? (metric === "ttft" ? streamTtft : null);
            return <span key={metric} className="playground-answer-metric"><span className="label-with-tip">{t(llmMetricLabel(metric))}<InfoTip label={t("查看说明")} text={t(llmMetricTip(metric))}/></span>：{typeof value === "number" ? Math.round(value) : "—"} {llmMetricUnit(metric)}</span>;
          })}
          <button type="button" className="icon-button" aria-label={t("复制回答")} title={t("复制回答")} disabled={busy || !answer} onClick={() => void copyResponse()}><Copy aria-hidden="true" /></button>
        </footer>}
        {error && <div className="playground-error-box" role="alert">{error}</div>}
        {stopped && <small className="field-help">{t("已停止生成，已接收的内容已保留。")}</small>}
        {result && <details><summary>{t("原始结果")}</summary><pre>{output}</pre></details>}
        {(result?.truncated || streamText.length >= 100_000) && <small className="field-help">{t("响应过长，仅显示前 100 KB。")}</small>}
      </> : busy ? <div className="empty-state" role="status">{t("正在等待服务响应…")}</div> : error ? <div className="playground-error-box" role="alert">{error}</div> : result ? <><pre>{output}</pre>{result.truncated && <small className="field-help">{t("响应过长，仅显示前 100 KB。")}</small>}</> : <div className="playground-welcome"><MessageSquare aria-hidden="true" /><h2>{t("开始一次测试")}</h2><p>{t("在左侧选择模型与参数，在下方输入内容并发送。")}</p></div>}
      </div>
      <div className="playground-composer">
        {benchmarkId !== "audio" && <fieldset disabled={busy}>
          <label className="field"><span>{t(benchmarkId === "embedding" ? "输入文本" : "问题")}</span><textarea required rows={3} value={benchmarkId === "embedding" ? text : queries[benchmarkId] || ""} onChange={(event) => benchmarkId === "embedding" ? setText(event.target.value) : setQueries(current => ({...current, [benchmarkId]:event.target.value}))} placeholder={t("输入内容，Ctrl / ⌘ + Enter 发送")} onKeyDown={(event) => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} /></label>
        </fieldset>}
        <div className="playground-composer-actions"><span role="status">{copyNotice || t("发送请求会调用实际服务，可能产生费用。")}</span>{busy && benchmarkId === "llm" ? <button key="stop" type="button" className="ghost" onClick={stopGeneration}><Square aria-hidden="true" />{t("停止生成")}</button> : <button key="send" type="submit" className="primary" disabled={busy || !provider || (credentials.length > 1 && !credentialId) || (benchmarkId === "llm" && (!definition || parameterLoading))}><Send aria-hidden="true" />{t(busy ? "请求中…" : "发送请求")}</button>}</div>
      </div>
    </section>
  </form>;
}
