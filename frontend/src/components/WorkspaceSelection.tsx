import { useEffect, useState } from "react";
import { ArrowRight, Home, LogOut, Plus, RefreshCw, Users } from "lucide-react";
import type { AuthUser, Workspace } from "../auth";
import { tr, type Language } from "../i18n";
import { BrandLogo } from "./BrandLogo";
import { CreateTeamDialog } from "./CreateTeamDialog";

export function WorkspaceSelection({ user, workspaces, onSelect, onLogout, onRefresh, onCreated }: {
  user: AuthUser; workspaces: Workspace[]; onSelect: (id: string) => void;
  onLogout: () => Promise<void>; onRefresh: () => Promise<void>; onCreated: (id: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const language: Language = localStorage.getItem("perflab-language") === "en" ? "en" : "zh-CN";
  const t = (value: string) => tr(language, value);
  useEffect(() => {
    document.title = `PrismLab · ${tr(language, "选择空间")}`;
    document.documentElement.lang = language;
    const theme = localStorage.getItem("perflab-theme");
    document.documentElement.dataset.theme = theme === "dark" || (theme !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
  }, [language]);
  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError("");
    try { await action(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : t("操作失败，请重试。")); }
    finally { setBusy(false); }
  }
  return <div className="login-page workspace-selection">
    <header className="login-header"><div className="login-brand"><BrandLogo /><strong>PrismLab</strong></div><button type="button" className="ghost" disabled={busy} onClick={() => void perform(onLogout)}><LogOut aria-hidden="true" />{t("退出登录")}</button></header>
    <main className="login-body"><section className="workspace-selection-panel" aria-labelledby="workspace-selection-title">
      <header className="workspace-selection-heading"><h1 id="workspace-selection-title">{t("选择空间")}</h1><p>{user.name} · {t("请选择进入个人空间或团队空间。")}</p></header>
      {error && <p className="workspace-feedback error" role="alert">{error}</p>}
      {(["personal", "team"] as const).map(kind => <section className="workspace-selection-group" key={kind} aria-label={t(kind === "personal" ? "个人空间" : "团队空间")}>
        <h2>{t(kind === "personal" ? "个人空间" : "团队空间")}</h2>
        {workspaces.filter(workspace => workspace.kind === kind).map(workspace => <button type="button" className="workspace-selection-option" disabled={busy} key={workspace.id} onClick={() => onSelect(workspace.id)}>
          {kind === "personal" ? <Home aria-hidden="true" /> : <Users aria-hidden="true" />}<span><strong>{kind === "personal" ? t("个人空间") : workspace.name}</strong><small>{kind === "personal" ? t("仅你自己可访问的数据空间") : t(workspace.role === "owner" ? "所有者" : workspace.role === "admin" ? "管理员" : "普通成员")}</small></span><ArrowRight aria-hidden="true" />
        </button>)}
        {kind === "team" && <>{!workspaces.some(workspace => workspace.kind === "team") && <p className="workspace-muted">{t("暂未加入团队。可创建团队，或进入个人空间查看收到的邀请。")}</p>}<button type="button" className="ghost" disabled={busy} onClick={() => setCreating(true)}><Plus aria-hidden="true" />{t("创建团队")}</button></>}
      </section>)}
      <footer className="workspace-selection-footer"><p>{t("个人空间与各团队的数据相互隔离。")}</p><button type="button" className="ghost" disabled={busy} onClick={() => void perform(onRefresh)}><RefreshCw aria-hidden="true" />{t("刷新空间")}</button></footer>
    </section></main>
    {creating && <CreateTeamDialog language={language} onClose={() => setCreating(false)} onCreated={onCreated} />}
  </div>;
}
