import { useState } from "react";
import { createPortal } from "react-dom";
import { ChevronUp, ChevronsUpDown, LogOut, Plus, Trash2, UserRound } from "lucide-react";
import { useAuth } from "../auth";
import { tr, type Language } from "../i18n";
import { Dropdown, IdentityAvatar } from "./Dropdown";
import { WorkspaceControls } from "./WorkspaceControls";
import { CreateTeamDialog } from "./CreateTeamDialog";
import { TeamActionDialog } from "./TeamActionDialog";

export function AccountMenu({ language, onSettings, onSwitch, loggingOut, onLogout }: {
  language: Language; onSwitch: () => void;
  onSettings: (section: "account" | "members" | "invitations") => void; loggingOut: boolean; onLogout: () => Promise<void>;
}) {
  const auth = useAuth();
  const [creating, setCreating] = useState(false);
  const [teamAction, setTeamAction] = useState(false);
  const { user } = auth;
  if (!user) return null;
  const t = (value: string) => tr(language, value);
  const displayName = auth.workspace?.kind === "team" ? auth.workspace.name : user.name;
  return <><Dropdown label={t("账户菜单")} className="account-trigger" side="top" disabled={loggingOut} trigger={<><IdentityAvatar name={user.name} src={user.avatar_url} /><span className="identity-name"><strong title={displayName}>{displayName}</strong></span><ChevronUp aria-hidden="true" /></>}>
    {close => <>
      <div className="account-menu-profile"><IdentityAvatar name={user.name} src={user.avatar_url} /><span className="identity-name"><strong>{user.name}</strong><small>{user.provider === "github" ? "GitHub" : user.provider === "oidc" ? "GitLab / OIDC" : t("本地账号")} · {user.username}</small></span></div>
      <button type="button" className="identity-menu-item" onClick={() => { close(); onSettings("account"); }}><UserRound aria-hidden="true" />{t("账户")}</button>
      <button type="button" className="identity-menu-item" onClick={() => { close(); onSwitch(); auth.chooseWorkspace(); }}><ChevronsUpDown aria-hidden="true" />{t("切换空间")}</button>
      <button type="button" className="identity-menu-item" onClick={() => { close(); setCreating(true); }}><Plus aria-hidden="true" />{t("创建团队")}</button>
      {auth.workspace?.kind === "team" && <button type="button" className="identity-menu-item danger" onClick={() => { close(); setTeamAction(true); }}>{auth.workspace.role === "owner" ? <Trash2 aria-hidden="true" /> : <LogOut aria-hidden="true" />}{t(auth.workspace.role === "owner" ? "删除团队" : "退出团队")}</button>}
      {auth.canManageTeams && <WorkspaceControls language={language} onSettings={onSettings} onClose={close} />}
      <div className="identity-menu-divider" />
      <button type="button" className="identity-menu-item" disabled={loggingOut} onClick={() => { close(); void onLogout(); }}><LogOut aria-hidden="true" />{t("退出登录")}</button>
    </>}
  </Dropdown>
    {creating && createPortal(<CreateTeamDialog language={language} onClose={() => setCreating(false)} onCreated={async id => { onSettings("members"); await auth.refreshWorkspaces(id); }} />, document.body)}
    {teamAction && auth.workspace?.kind === "team" && createPortal(<TeamActionDialog workspace={auth.workspace} language={language} onClose={() => setTeamAction(false)} onCompleted={async () => { await auth.refreshWorkspaces(); onSwitch(); }} />, document.body)}
  </>;
}
