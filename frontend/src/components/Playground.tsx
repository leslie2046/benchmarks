import { FormEvent, useState } from "react";
import { api } from "../api";
import { tr, type Language } from "../i18n";
import { providerDisplayName } from "../providerPresets";
import type { Catalog, PlaygroundResult } from "../types";

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
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [documents, setDocuments] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [result, setResult] = useState<PlaygroundResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const benchmark = catalog?.benchmarks.find((item) => item.id === benchmarkId);
  const providers = benchmark?.providers.filter((item) => item.endpoint_configured) ?? [];
  const provider = providers.find((item) => item.id === providerId) ?? providers[0];
  const models = provider?.models.filter((item) => item.name) ?? [];
  const selectedModel = models.find((item) => (item.alias || item.name) === modelName) ?? models[0];
  const model = selectedModel?.alias || selectedModel?.name || null;
  const credentials = selectedModel?.credentials || [];
  const isDify = benchmarkId.startsWith("dify-");
  const output = result ? typeof result.data === "string" ? result.data : JSON.stringify(result.data, null, 2) : "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!provider) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      if (benchmarkId === "audio" && audioFile && audioFile.size > 5_000_000) {
        throw new Error(t("音频文件不能超过 5 MB。"));
      }
      const response = await api.playground({
        benchmark: benchmarkId,
        provider_id: provider.id,
        model,
        credential_id: credentialId || null,
        text: benchmarkId === "embedding" ? text : null,
        query: benchmarkId === "reranker" || isDify ? query : null,
        documents: benchmarkId === "reranker" ? documents.split("\n").map((item) => item.trim()).filter(Boolean) : [],
        dataset_id: benchmarkId === "dify-retrieve" ? datasetId : null,
        audio_name: benchmarkId === "audio" ? audioFile?.name : null,
        audio_base64: benchmarkId === "audio" && audioFile ? await readAudio(audioFile) : null,
      });
      setResult(response);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("请求失败"));
    } finally {
      setBusy(false);
    }
  }

  return <section className="playground-grid">
    <article className="panel">
      <div className="panel-head"><div><p className="eyebrow">PLAYGROUND</p><h2>{t("单次请求")}</h2></div></div>
      <form className="playground-form" onSubmit={submit}>
        <label className="field"><span>{t("测试类型")}</span><select value={benchmarkId} onChange={(event) => { setBenchmarkId(event.target.value); setProviderId(""); setModelName(""); setCredentialId(""); setResult(null); }}>{catalog?.benchmarks.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label>
        <label className="field"><span>{t(isDify ? "Dify 配置" : "模型供应商")}</span><select value={provider?.id ?? ""} onChange={(event) => { setProviderId(event.target.value); setModelName(""); setCredentialId(""); setResult(null); }}>{providers.map((item) => <option value={item.id} key={item.id}>{providerDisplayName(item.provider || item.id, language, item.label)}</option>)}</select>{!providers.length && <small>{t("此类型暂无已配置的服务。")}</small>}</label>
        {!!models.length && <label className="field"><span>{t("模型")}</span><select value={model ?? ""} onChange={(event) => { setModelName(event.target.value); setCredentialId(""); setResult(null); }}>{models.map((item) => <option value={item.alias || item.name || ""} key={`${item.benchmark}-${item.alias || item.name}`}>{item.alias || item.name}</option>)}</select></label>}
        {credentials.length > 1 && <label className="field"><span>{t("凭据")}</span><select required value={credentialId} onChange={(event) => { setCredentialId(event.target.value); setResult(null); }}><option value="">{t("选择凭据")}</option>{credentials.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        {benchmarkId === "embedding" && <label className="field"><span>{t("输入文本")}</span><textarea required value={text} onChange={(event) => setText(event.target.value)} placeholder={t("输入要生成向量的文本")} /></label>}
        {(benchmarkId === "reranker" || isDify) && <label className="field"><span>{t("问题")}</span><textarea required value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("输入要提交的问题")} /></label>}
        {benchmarkId === "reranker" && <label className="field"><span>{t("候选文档")}</span><textarea required value={documents} onChange={(event) => setDocuments(event.target.value)} placeholder={t("每行一篇文档，最多 20 篇")} /><small>{t("每行一篇文档，最多 20 篇")}</small></label>}
        {benchmarkId === "dify-retrieve" && <label className="field"><span>Dataset ID</span><input required value={datasetId} onChange={(event) => setDatasetId(event.target.value)} placeholder={t("Dify 知识库 Dataset ID")} /></label>}
        {benchmarkId === "audio" && <label className="field"><span>{t("音频文件")}</span><input required type="file" accept="audio/*,.wav,.mp3,.m4a,.flac" onChange={(event) => setAudioFile(event.target.files?.[0] ?? null)} /><small>{t("最大 5 MB；文件仅用于本次请求。")}</small></label>}
        <button className="primary" disabled={busy || !provider}>{busy ? t("请求中…") : t("发送请求")}<span>→</span></button>
      </form>
    </article>
    <article className="panel playground-result" aria-live="polite">
      <div className="panel-head"><div><p className="eyebrow">RESPONSE</p><h2>{t("返回结果")}</h2></div>{result && <span className={result.ok ? "playground-ok" : "playground-error"}>HTTP {result.status_code} · {result.duration_ms} ms</span>}</div>
      {busy ? <div className="empty-state">{t("正在等待服务响应…")}</div> : error ? <div className="playground-error-box">{error}</div> : result ? <><pre>{output}</pre>{result.truncated && <small className="field-help">{t("响应过长，仅显示前 100 KB。")}</small>}</> : <div className="empty-state">{t("选择服务并发送一次请求，结果会显示在这里。")}</div>}
    </article>
  </section>;
}
