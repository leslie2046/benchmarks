import { useState } from "react";
import { workspaceApi } from "../api";
import type { Workspace } from "../auth";
import { tr, type Language } from "../i18n";
import { WorkspaceDialog } from "./WorkspaceDialog";

export function TeamActionDialog({ workspace, language, onCompleted, onClose }: {
  workspace: Workspace; language: Language; onCompleted: () => Promise<void>; onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [completed, setCompleted] = useState(false);
  const owner = workspace.role === "owner";
  const t = (value: string) => tr(language, value);
  const action = t(owner ? "删除团队" : "退出团队");
  return <WorkspaceDialog title={action} busy={busy} language={language} onClose={onClose}>
    <form onSubmit={async event => {
      event.preventDefault(); if (busy || workspace.kind !== "team") return;
      setBusy(true); setError("");
      try {
        if (!completed) {
          if (owner) await workspaceApi.delete(workspace.id);
          else await workspaceApi.leave(workspace.id);
          setCompleted(true);
        }
        await onCompleted(); onClose();
      } catch (failure) { setError(failure instanceof Error ? failure.message : t("操作失败，请重试。")); }
      finally { setBusy(false); }
    }}><div className="workspace-dialog-body"><p><strong>{workspace.name}</strong></p><p className="workspace-muted">{t(owner ? "确认删除团队？所有成员将失去访问权限，此操作不可在界面撤销。" : "确认退出团队？你的个人空间不受影响。")}</p>{error && <p className="workspace-feedback error" role="alert">{error}</p>}</div><footer className="workspace-dialog-footer"><button type="button" className="ghost" disabled={busy} onClick={onClose}>{t("取消")}</button><button type="submit" className="ghost danger" disabled={busy}>{busy ? t("处理中…") : completed ? t("重试") : action}</button></footer></form>
  </WorkspaceDialog>;
}
