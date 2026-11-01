import { useState } from "react";
import { workspaceApi } from "../api";
import { tr, type Language } from "../i18n";
import { WorkspaceDialog } from "./WorkspaceDialog";

export function CreateTeamDialog({ language, onCreated, onClose }: {
  language: Language; onCreated: (id: string) => Promise<void>; onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [createdId, setCreatedId] = useState<string | null>(null);
  const t = (value: string) => tr(language, value);
  return <WorkspaceDialog title={t("创建团队")} busy={busy} language={language} onClose={onClose}>
    <form onSubmit={async event => {
      event.preventDefault(); if (busy) return;
      setBusy(true); setError("");
      try {
        const id = createdId ?? (await workspaceApi.create(name.trim())).id;
        setCreatedId(id);
        await onCreated(id); onClose();
      } catch (failure) { setError(failure instanceof Error ? failure.message : t("操作失败，请重试。")); }
      finally { setBusy(false); }
    }}><div className="workspace-dialog-body"><p className="workspace-muted">{t("个人空间与各团队的数据相互隔离。")}</p><label className="field"><span>{t("团队名称")}</span><input required maxLength={80} value={name} disabled={busy || Boolean(createdId)} onChange={event => setName(event.target.value)} /></label>{error && <p className="workspace-feedback error" role="alert">{error}</p>}</div><footer className="workspace-dialog-footer"><button type="button" className="ghost" disabled={busy} onClick={onClose}>{t("取消")}</button><button className="primary" disabled={busy || !name.trim()}>{t(busy ? "保存中…" : createdId ? "重试" : "创建团队")}</button></footer></form>
  </WorkspaceDialog>;
}
