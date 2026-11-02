import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Check, MoreHorizontal, Pencil, Search, UserPlus, Users } from "lucide-react";
import { useAuth } from "../auth";
import { workspaceApi, type SentInvitation, type WorkspaceInvitation, type WorkspaceMember } from "../api";
import { tr, type Language } from "../i18n";
import { pageItems } from "../pagination";
import { memberPermissions } from "../workspacePermissions";
import { Dropdown, IdentityAvatar } from "./Dropdown";
import { Pagination, usePagination } from "./Pagination";
import { WorkspaceDialog } from "./WorkspaceDialog";
import { AccountSettings } from "./AccountSettings";

export type WorkspaceSettingsSection = "members" | "invitations" | "account";

export function WorkspaceSettings({ section, language }: {
  section: WorkspaceSettingsSection; language: Language;
}) {
  const auth = useAuth();
  const workspace = auth.workspace;
  const t = (value: string) => tr(language, value);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [invitations, setInvitations] = useState<WorkspaceInvitation[]>([]);
  const [sent, setSent] = useState<SentInvitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [list, setList] = useState<"members" | "pending">("members");
  const [dialog, setDialog] = useState<"invite" | "rename" | null>(null);
  const [dialogError, setDialogError] = useState("");
  const [teamName, setTeamName] = useState(workspace?.name || "");
  const [provider, setProvider] = useState("github");
  const [username, setUsername] = useState("");
  const team = workspace?.kind === "team";
  const roleName = (role: string) => t(role === "owner" ? "所有者" : role === "admin" ? "管理员" : "普通成员");
  const providerName = (value: string) => value === "github" ? "GitHub" : value === "oidc" ? "GitLab" : t("本地账号");
  const displayName = team ? workspace.name : t("个人空间");
  const filtered = members.filter(member => `${member.name} ${member.username} ${member.provider}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const memberPagination = usePagination(filtered.length, search);
  const sentPagination = usePagination(sent.length);
  const invitationPagination = usePagination(invitations.length);
  const date = (value: string) => new Intl.DateTimeFormat(language, { dateStyle: "medium" }).format(new Date(value));
  const getData = useCallback(async () => {
    const [nextMembers, nextInvitations, nextSent] = await Promise.all([
      workspace ? workspaceApi.members(workspace.id) : Promise.resolve([]), workspaceApi.invitations(),
      workspace?.kind === "team" && auth.canManage ? workspaceApi.sent(workspace.id) : Promise.resolve([]),
    ]);
    return { members: nextMembers, invitations: nextInvitations, sent: nextSent };
  }, [workspace?.id, workspace?.kind, auth.canManage]);
  const applyData = (data: Awaited<ReturnType<typeof getData>>) => { setMembers(data.members); setInvitations(data.invitations); setSent(data.sent); };
  useEffect(() => {
    if (!["members", "invitations"].includes(section)) { setLoading(false); return; }
    let active = true;
    setLoading(true); setError("");
    getData().then(data => { if (active) applyData(data); }).catch(failure => { if (active) setError(failure instanceof Error ? failure.message : t("加载失败，请重试。")); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [getData, section]);

  async function reload() {
    setLoading(true); setError("");
    try { applyData(await getData()); }
    catch (failure) { setError(failure instanceof Error ? failure.message : t("加载失败，请重试。")); }
    finally { setLoading(false); }
  }

  async function act(action: () => Promise<unknown>, message = "操作成功") {
    if (busy) return;
    setBusy(true); setError(""); setDialogError(""); setNotice("");
    try { await action(); setDialog(null); setNotice(t(message)); window.dispatchEvent(new Event("prismlab:invitations-changed")); await reload(); }
    catch (failure) {
      const text = failure instanceof Error ? failure.message : t("操作失败，请重试。");
      if (dialog) setDialogError(text); else setError(text);
    } finally { setBusy(false); }
  }

  function openDialog(value: "invite" | "rename") {
    setDialogError(""); setUsername(""); setTeamName(workspace?.name || ""); setDialog(value);
  }

  if (!auth.user || !workspace) return <section className="panel"><p>{t("请先登录后管理空间。")}</p></section>;
  return <div className="workspace-settings-page">
    {error && <div className="workspace-feedback error" role="alert"><AlertCircle aria-hidden="true" /><span>{error}</span><button type="button" className="ghost" disabled={loading || busy} onClick={() => void reload()}>{t("重试")}</button></div>}
    {notice && <p className="workspace-feedback success" role="status"><Check aria-hidden="true" />{notice}</p>}
    {loading && <p className="workspace-muted" role="status">{t("正在加载…")}</p>}
    {section === "members" && <>
      <section className="workspace-summary"><IdentityAvatar name={displayName} workspace /><div className="workspace-summary-name"><div><h2>{displayName}</h2>{team && auth.canManage && <button type="button" className="icon-button" aria-label={t("修改团队名称")} disabled={busy} onClick={() => openDialog("rename")}><Pencil aria-hidden="true" /></button>}</div><p>{members.length} {t("位成员")} · {roleName(workspace.role)}</p></div>{team && auth.canManage && <button type="button" className="primary" disabled={busy || loading} onClick={() => openDialog("invite")}><UserPlus aria-hidden="true" />{t("添加成员")}</button>}</section>
      {!team && <p className="workspace-personal-note"><Users aria-hidden="true" />{t("只有你能访问个人空间。邀请成员请先创建或切换到团队。")}</p>}
      <section className="workspace-member-panel">
        <div className="workspace-member-toolbar"><div className="workspace-list-tabs"><button type="button" aria-pressed={list === "members"} onClick={() => setList("members")}>{t("成员")} <span>{members.length}</span></button>{team && auth.canManage && <button type="button" aria-pressed={list === "pending"} onClick={() => setList("pending")}>{t("待处理邀请")} <span>{sent.length}</span></button>}</div>{list === "members" && <label className="workspace-search"><Search aria-hidden="true" /><input aria-label={t("搜索成员")} placeholder={t("搜索成员")} value={search} onChange={event => setSearch(event.target.value)} /></label>}</div>
        {list === "members" ? <><div className="workspace-table-wrap"><table><thead><tr><th>{t("姓名")}</th><th>{t("登录来源")}</th><th>{t("角色")}</th><th className="workspace-action-heading">{t("操作")}</th></tr></thead><tbody>{pageItems(filtered, memberPagination.page, memberPagination.pageSize).map(member => {
          const self = member.id === auth.user?.id;
          const permissions = memberPermissions(workspace, auth.user!.id, member);
          const canAct = permissions.remove || permissions.changeRole;
          return <tr key={member.id}><td><div className="workspace-member-identity"><IdentityAvatar name={member.name} src={member.avatar_url} /><span><strong>{member.name}{self && <small className="workspace-you">{t("（你）")}</small>}</strong><small className="workspace-member-id">{member.username}</small></span></div></td><td><span className="workspace-provider-badge">{providerName(member.provider)}</span></td><td><span className={`workspace-role-badge role-${member.role}`}>{roleName(member.role)}</span></td><td className="workspace-action-cell">{canAct && <Dropdown label={`${member.username} ${t("成员操作")}`} trigger={<MoreHorizontal aria-hidden="true" />} className="icon-button" width={220}>{close => <>
            {permissions.changeRole && <button type="button" className="identity-menu-item" disabled={busy} onClick={() => { close(); void act(() => workspaceApi.role(workspace.id, member.id, member.role === "admin" ? "member" : "admin")); }}>{t(member.role === "admin" ? "设为普通成员" : "设为管理员")}</button>}
            <div className="identity-menu-divider" /><button type="button" className="identity-menu-item danger" disabled={busy} onClick={() => { close(); if (window.confirm(t("确认移除此成员？其个人空间不受影响。"))) void act(() => workspaceApi.remove(workspace.id, member.id)); }}>{t("移除成员")}</button>
          </>}</Dropdown>}</td></tr>;
        })}</tbody></table>{!loading && !error && !filtered.length && <div className="empty-state compact-empty">{t("没有匹配的成员")}</div>}</div><Pagination {...memberPagination} total={filtered.length} language={language} label={t("成员")} disabled={busy || loading} /></> : <><div className="workspace-invitation-list">{pageItems(sent, sentPagination.page, sentPagination.pageSize).map(invitation => <div className="workspace-invitation" key={invitation.id}><div><strong>{invitation.username}</strong><p>{providerName(invitation.provider)} · {t("有效期至")} {date(invitation.expires_at)}</p></div><button type="button" className="ghost" disabled={busy} onClick={() => void act(() => workspaceApi.revoke(workspace.id, invitation.id))}>{t("撤销邀请")}</button></div>)}{!sent.length && <div className="empty-state compact-empty">{t("暂无待处理邀请")}</div>}</div><Pagination {...sentPagination} total={sent.length} language={language} label={t("待处理邀请")} disabled={busy || loading} /></>}
      </section>
    </>}
    {section === "invitations" && <section className="workspace-member-panel"><div className="workspace-section-head"><div><h2>{t("收到的邀请")}</h2><p className="workspace-muted">{t("接受邀请后加入团队，个人空间的数据不会合并。")}</p></div><button type="button" className="ghost" disabled={busy || loading} onClick={() => void reload()}>{t("刷新")}</button></div><div className="workspace-invitation-list">{pageItems(invitations, invitationPagination.page, invitationPagination.pageSize).map(invitation => <div className="workspace-invitation" key={invitation.id}><div><strong>{invitation.workspace_name}</strong><p>{t("邀请人")}：{invitation.invited_by} · {t("有效期至")} {date(invitation.expires_at)}</p></div><div className="workspace-actions"><button type="button" className="primary" disabled={busy} onClick={() => void act(async () => { const result = await workspaceApi.accept(invitation.id); await auth.refreshWorkspaces(result.workspace_id); })}>{t("接受邀请")}</button><button type="button" className="ghost" disabled={busy} onClick={() => void act(() => workspaceApi.decline(invitation.id))}>{t("拒绝")}</button></div></div>)}{!loading && !error && !invitations.length && <div className="empty-state compact-empty">{t("暂无待处理邀请")}</div>}</div><Pagination {...invitationPagination} total={invitations.length} language={language} label={t("收到的邀请")} disabled={busy || loading} /></section>}
    {section === "account" && <AccountSettings language={language} />}
    {dialog && <WorkspaceDialog title={t(dialog === "invite" ? "添加成员" : "修改团队名称")} busy={busy} language={language} onClose={() => setDialog(null)}><form onSubmit={event => {
      event.preventDefault();
      if (dialog === "invite") void act(() => workspaceApi.invite(workspace.id, provider, username.trim()), "邀请已发送");
      else void act(async () => { await workspaceApi.rename(workspace.id, teamName.trim()); await auth.refreshWorkspaces(); });
    }}><div className="workspace-dialog-body">{dialog === "invite" ? <><p className="workspace-muted">{t("对方需先登录过本系统。填写登录来源及准确用户名，对方接受后以普通成员加入；邀请七天有效。")}</p><label className="field"><span>{t("登录来源")}</span><select aria-label={t("登录来源")} value={provider} disabled={busy} onChange={event => setProvider(event.target.value)}><option value="github">GitHub</option><option value="oidc">GitLab</option><option value="local">{t("本地账号")}</option></select></label><label className="field"><span>{t("对方用户名")}</span><input required maxLength={128} value={username} disabled={busy} onChange={event => setUsername(event.target.value)} placeholder={t("不是昵称、邮箱或主页链接")} /></label></> : <label className="field"><span>{t("团队名称")}</span><input required maxLength={80} value={teamName} disabled={busy} onChange={event => setTeamName(event.target.value)} /></label>}{dialogError && <p className="workspace-feedback error" role="alert">{dialogError}</p>}</div><footer className="workspace-dialog-footer"><button type="button" className="ghost" disabled={busy} onClick={() => setDialog(null)}>{t("取消")}</button><button className="primary" disabled={busy || (dialog === "invite" ? !username.trim() : !teamName.trim() || teamName.trim() === workspace.name)}>{t(busy ? "保存中…" : dialog === "invite" ? "发送邀请" : "保存")}</button></footer></form></WorkspaceDialog>}
  </div>;
}
