import { useEffect, useRef, useState } from "react";
import { Check, Upload } from "lucide-react";
import { profileApi } from "../api";
import { useAuth, type AuthUser } from "../auth";
import { tr, type Language } from "../i18n";
import { IdentityAvatar } from "./Dropdown";

export function AccountSettings({ language }: { language: Language }) {
  const { user, updateUser } = useAuth();
  const [nickname, setNickname] = useState(user?.name ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const upload = useRef<HTMLInputElement>(null);
  const t = (value: string) => tr(language, value);
  useEffect(() => setNickname(user?.name ?? ""), [user?.id, user?.name]);
  if (!user) return null;
  async function save(action: () => Promise<AuthUser>) {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { updateUser(await action()); setNotice(t("已保存")); }
    catch (failure) { setError(failure instanceof Error ? failure.message : t("操作失败，请重试。")); }
    finally { setBusy(false); }
  }
  const provider = user.provider === "github" ? "GitHub" : user.provider === "oidc" ? "GitLab" : t("本地账号");
  return <section className="panel workspace-account-panel">
    <div className="account-detail-heading"><IdentityAvatar name={user.name} src={user.avatar_url} /><div><h2>{user.name}</h2><p className="workspace-muted">{t("昵称和头像可自行修改，登录身份保持不变。")}</p></div></div>
    {error && <p className="workspace-feedback error" role="alert">{t(error)}</p>}
    {notice && <p className="workspace-feedback success" role="status"><Check aria-hidden="true" />{notice}</p>}
    <dl><div><dt>{t("头像")}</dt><dd><div className="account-avatar-actions"><button type="button" className="ghost" disabled={busy} onClick={() => upload.current?.click()}><Upload aria-hidden="true" />{t("上传头像")}</button>{user.avatar_url && <button type="button" className="ghost" disabled={busy} onClick={() => void save(profileApi.removeAvatar)}>{t("移除头像")}</button>}</div><input ref={upload} type="file" hidden accept="image/png,image/jpeg,image/webp" aria-label={t("选择头像")} disabled={busy} onChange={event => {
      const file = event.target.files?.[0]; event.target.value = "";
      if (!file) return;
      setError(""); setNotice("");
      if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) { setError("请选择 PNG、JPEG 或 WebP 图片。"); return; }
      if (file.size > 1024 * 1024) { setError("头像不能超过 1 MB。"); return; }
      void save(() => profileApi.avatar(file));
    }} /><p className="workspace-muted account-avatar-note">{t("支持 PNG、JPEG、WebP，最大 1 MB；未设置头像时显示昵称首字符。")}</p></dd></div>
    <div><dt>{t("登录来源")}</dt><dd>{provider}</dd></div><div><dt>{t("用户名")}</dt><dd>{user.username}</dd></div>
    <div><dt><label htmlFor="account-nickname">{t("昵称")}</label></dt><dd><form className="account-nickname-form" onSubmit={event => { event.preventDefault(); void save(() => profileApi.nickname(nickname.trim())); }}><input id="account-nickname" value={nickname} maxLength={80} required disabled={busy} onChange={event => setNickname(event.target.value)} /><button className="primary" disabled={busy || !nickname.trim() || nickname.trim() === user.name}>{t(busy ? "保存中…" : "保存")}</button></form></dd></div>
    <div><dt>{t("账号 ID")}</dt><dd className="workspace-account-id">{user.id}</dd></div></dl>
    <p className="workspace-muted">{t("邀请你加入团队时，请使用以上登录来源和用户名。")}</p>
  </section>;
}
