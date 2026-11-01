import { useEffect, useState, type FormEvent } from "react";
import { AlertCircle, Eye, EyeOff, Languages, LoaderCircle, LogIn, Moon, ShieldCheck, Sun } from "lucide-react";
import type { AuthStatus } from "../auth";
import { tr, type Language } from "../i18n";
import { BrandLogo } from "./BrandLogo";
import { Github } from "./Github";

const callbackErrors: Record<string, string> = {
  access_denied: "当前账号未获准访问，请联系管理员。",
  provider_error: "单点登录未完成或已过期，请重试。",
};

export function LoginPage({ status, loading, unavailable, onRetry, onLogin }: {
  status: AuthStatus | null;
  loading: boolean;
  unavailable: boolean;
  onRetry: () => void;
  onLogin: (status: AuthStatus) => void;
}) {
  const [language, setLanguage] = useState<Language>(() => localStorage.getItem("perflab-language") === "en" ? "en" : "zh-CN");
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem("perflab-theme");
    return saved === "dark" || (saved !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  });
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [redirecting, setRedirecting] = useState<string | null>(null);
  const [error, setError] = useState(() => callbackErrors[new URLSearchParams(window.location.search).get("auth_error") || ""] || "");
  const t = (text: string) => tr(language, text);
  const busy = submitting || Boolean(redirecting);

  useEffect(() => {
    document.documentElement.lang = language;
    document.title = `PrismLab · ${tr(language, "登录")}`;
    localStorage.setItem("perflab-language", language);
  }, [language]);
  useEffect(() => { document.documentElement.dataset.theme = dark ? "dark" : "light"; }, [dark]);
  useEffect(() => {
    if (window.location.search.includes("auth_error=")) {
      const url = new URL(window.location.href);
      url.searchParams.delete("auth_error");
      window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    }
  }, []);

  async function login(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
      if (!response.ok) {
        const failure = await response.json().catch(() => ({}));
        setError(response.status === 403 && failure.code === "origin_not_allowed"
          ? "当前访问地址未获准登录，请联系管理员检查 AUTH_PUBLIC_URL 和 AUTH_ALLOWED_ORIGINS。"
          : response.status === 401 ? "用户名或密码错误" : response.status === 429 ? "登录尝试过于频繁，请稍后重试。" : "登录失败，请稍后重试。");
        return;
      }
      setPassword("");
      onLogin(await response.json() as AuthStatus);
    } catch { setError("无法连接登录服务，请检查网络后重试。"); }
    finally { setSubmitting(false); }
  }

  return <main className="login-page">
    <header className="login-header">
      <a className="login-brand" href="/" aria-label="PrismLab"><BrandLogo /><strong>PrismLab</strong></a>
      <div className="preferences">
        <button type="button" className="icon-button" aria-label={t("切换语言")} title={t("切换语言")} onClick={() => setLanguage(language === "zh-CN" ? "en" : "zh-CN")}><Languages aria-hidden="true" /></button>
        <button type="button" className="icon-button" aria-label={t("切换主题")} title={t("切换主题")} onClick={() => { localStorage.setItem("perflab-theme", dark ? "light" : "dark"); setDark(!dark); }}>{dark ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}</button>
      </div>
    </header>
    <div className="login-body">
      <section className="login-panel" aria-labelledby="login-title" aria-busy={loading || busy}>
        <div className="login-heading"><h1 id="login-title" className="login-logo" aria-label={t("登录 PrismLab")}><BrandLogo /><span>PrismLab</span></h1></div>
        {loading ? <div className="login-status" role="status"><LoaderCircle className="login-spinner" aria-hidden="true" />{t("正在检查登录状态…")}</div> : unavailable ? <div className="login-retry"><p role="alert"><AlertCircle aria-hidden="true" />{t("无法连接登录服务，请检查网络后重试。")}</p><button className="secondary" type="button" onClick={onRetry}>{t("重试")}</button></div> : <>
          {error && <div className="login-error" role="alert"><AlertCircle aria-hidden="true" /><span>{t(error)}</span></div>}
          {status?.password_enabled && <form className="login-form" onSubmit={login}>
            <label htmlFor="login-username">{t("用户名")}<input id="login-username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={event => setUsername(event.target.value)} required maxLength={128} disabled={busy} /></label>
            <label htmlFor="login-password">{t("密码")}<span className="login-password"><input id="login-password" name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required disabled={busy} /><button type="button" aria-label={t(showPassword ? "隐藏密码" : "显示密码")} onClick={() => setShowPassword(!showPassword)} disabled={busy}>{showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}</button></span></label>
            <button type="submit" className="primary login-submit" disabled={busy || !username.trim() || !password}>{submitting ? <LoaderCircle className="login-spinner" aria-hidden="true" /> : <LogIn aria-hidden="true" />}{t(submitting ? "正在登录…" : "登录")}</button>
          </form>}
          {status?.password_enabled && <div className="login-divider"><span>{t("或")}</span></div>}
          <div className="login-providers">{status?.providers.map(provider => <button type="button" className="secondary login-provider" key={provider.id} disabled={!provider.enabled || busy} onClick={() => { setRedirecting(provider.id); window.location.assign(provider.login_url); }}>
            {redirecting === provider.id ? <LoaderCircle className="login-spinner" aria-hidden="true" /> : provider.id === "github" ? <Github aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
            <span>{provider.id === "github" ? t("使用 GitHub 登录") : language === "en" ? `Continue with ${provider.name}` : `使用 ${provider.name} 登录`}</span>{!provider.enabled && <small>{t("未配置")}</small>}
          </button>)}</div>
        </>}
      </section>
      <p className="login-note"><ShieldCheck aria-hidden="true" />{t("仅限授权账号访问 · 会话安全保存在服务端")}</p>
    </div>
    <footer className="login-footer"><span>{t("AI 模型测试与分析平台")}</span><a href="https://github.com/leslie2046/benchmarks" target="_blank" rel="noopener noreferrer"><Github aria-hidden="true" />GitHub</a></footer>
  </main>;
}
