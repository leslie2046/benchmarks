import { useEffect, useRef, useState } from "react";
import { Download, RefreshCw, Sparkles, X } from "lucide-react";
import { api } from "../api";
import { tr, type Language } from "../i18n";
import type { AiReport, Run } from "../types";

export function RunAiReport({ run, language, onClose, onSettings }: { run: Run; language: Language; onClose: () => void; onSettings: () => void }) {
  const t = (text: string) => tr(language, text);
  const dialog = useRef<HTMLDialogElement>(null);
  const [report, setReport] = useState<AiReport | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const busy = submitting || report?.status === "generating";
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => { dialog.current?.close(); previous?.focus(); };
  }, []);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await api.aiReport(run.id);
        if (!alive) return;
        setReport(value); setError("");
        if (value.status === "generating") timer = setTimeout(load, 2500);
      } catch (reason) {
        if (alive) { setError(reason instanceof Error ? reason.message : String(reason)); timer = setTimeout(load, 5000); }
      } finally { if (alive) setLoading(false); }
    }
    void load();
    return () => { alive = false; clearTimeout(timer); };
  }, [run.id, submitting]);
  async function generate() {
    setSubmitting(true); setError("");
    try { setReport(await api.generateAiReport(run.id, Boolean(report?.content), language)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setSubmitting(false); }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([`${run.name}\n${report?.content || ""}`], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `prismlab-${run.id}-ai-report.txt`; link.click(); URL.revokeObjectURL(url);
  }
  return <dialog ref={dialog} className="dify-modal dify-native-dialog ai-report-dialog" aria-labelledby="ai-report-title" onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <div className="dify-modal-head"><div><h2 id="ai-report-title">{t("AI 测试报告")}</h2><p>{run.name} · {run.id}</p></div><button className="dify-close" aria-label={t("关闭")} onClick={onClose}><X aria-hidden="true" /></button></div>
    <div className="ai-report-body">
      <p className="field-help">{t("仅发送测试统计、模型标识和输入长度，不发送 API Key、服务地址或测试输入正文。AI 结论仅供参考。")}</p>
      <p className="field-help">{t("生成或重新分析可能产生模型调用费用；查看已保存报告不会调用模型。")}</p>
      {loading && <p role="status">{t("加载中…")}</p>}
      {(error || report?.error) && <div className="alert" role="alert">{t(error || report?.error || "")}</div>}
      {busy && <p className="ai-report-progress" role="status"><RefreshCw aria-hidden="true" />{t("正在生成报告，可关闭弹窗，稍后返回查看。")}</p>}
      {report?.content ? <>
        <div className="ai-report-meta"><span>{report.model?.provider} · {report.model?.model}</span><time>{report.generated_at ? new Date(report.generated_at).toLocaleString(language) : ""}</time></div>
        {busy && <small className="field-help">{t("以下为上一次保存的报告，新报告成功后才会替换。")}</small>}
        <article className="ai-report-content">{report.content}</article>
      </> : !loading && !busy && <div className="empty-state"><Sparkles aria-hidden="true" /><p>{t("尚未生成报告。点击分析，使用系统默认 LLM 解读本次测试。")}</p></div>}
    </div>
    <div className="dify-modal-footer ai-report-footer"><button className="ghost" onClick={onSettings}>{t("系统配置")}</button><span className="dify-footer-spacer" />{report?.content && <button className="dify-secondary-button" onClick={download}><Download aria-hidden="true" />{t("下载报告")}</button>}<button className="dify-blue-button" disabled={loading || busy} onClick={() => void generate()}>{report?.content ? <RefreshCw aria-hidden="true" /> : <Sparkles aria-hidden="true" />}{t(busy ? "分析中…" : report?.content ? "重新分析" : "生成报告")}</button></div>
  </dialog>;
}
