import { useId } from "react";
import { Plus, Trash2 } from "lucide-react";
import { tr, type Language } from "../i18n";
import { InfoTip } from "./InfoTip";

export type DocumentDraft = { id: string; text: string };

export function createDocumentDraft(text = ""): DocumentDraft {
  return { id: crypto.randomUUID(), text };
}

const MAX_DOCUMENTS = 20;

export function DocumentListEditor({ documents, onChange, language }: {
  documents: DocumentDraft[];
  onChange: (documents: DocumentDraft[]) => void;
  language: Language;
}) {
  const labelId = useId();
  const t = (value: string) => tr(language, value);

  return <div className="field document-editor" role="group" aria-labelledby={labelId}>
    <div className="document-editor-heading">
      <span className="label-with-tip" id={labelId}>Document <b className="required">*</b><InfoTip label={t("查看说明")} text={t("每条是一篇候选文档，Reranker 会根据 Query 计算相关性并重新排序。")} /></span>
      <span className="document-editor-count" aria-live="polite">{documents.length} / {MAX_DOCUMENTS} {t("篇")}</span>
    </div>
    <ol className="document-editor-list">
      {documents.map((document, index) => <li className="document-editor-row" key={document.id}>
        <span className="document-editor-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
        <input required pattern=".*\S.*" maxLength={20000} autoFocus={!document.text} aria-label={`Document ${index + 1}`} value={document.text} placeholder={t("输入候选文档内容")} onChange={(event) => onChange(documents.map((item) => item.id === document.id ? { ...item, text: event.target.value } : item))} />
        <button type="button" className="document-editor-remove" aria-label={`${t("删除文档")} ${index + 1}`} title={`${t("删除文档")} ${index + 1}`} onClick={() => onChange(documents.filter((item) => item.id !== document.id))}><Trash2 aria-hidden="true" /></button>
      </li>)}
    </ol>
    {!documents.length && <p className="document-editor-empty">{t("暂无文档，请添加至少一篇候选文档。")}</p>}
    <div className="document-editor-footer">
      <button type="button" className="document-editor-add" disabled={documents.length >= MAX_DOCUMENTS} onClick={() => onChange([...documents, createDocumentDraft()])}><Plus aria-hidden="true" />{t("添加文档")}</button>
      <small>{t("每条一篇文档，最多 20 篇")}</small>
    </div>
  </div>;
}
