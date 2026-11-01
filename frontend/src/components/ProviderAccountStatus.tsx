import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api, type ProviderBalance } from "../api";
import { tr, type Language } from "../i18n";
import type { ServiceConfig } from "../types";

const balanceProviders = new Set(["deepseek", "moonshot", "siliconflow"]);

export function ProviderAccountStatus({ providerId, records, language, configurationState }: { providerId: string; records: ServiceConfig[]; language: Language; configurationState: "loading" | "ready" | "error" }) {
  const t = (value: string) => tr(language, value);
  const source = records.flatMap(config => config.models.flatMap(model => (model.credentials || []).filter(credential => credential.has_api_key && credential.id && credential.server_url).map(credential => ({ config, credentialId: credential.id!, name: credential.name })))).at(0)
    || records.filter(config => config.has_api_key && config.base_url).map(config => ({ config, credentialId: "legacy", name: config.name })).at(0);
  const config = source?.config;
  const credentialId = source?.credentialId;
  const configured = Boolean(source || (["xinference", "vllm"].includes(providerId) && records.some(record => record.endpoint_configured)));
  const supported = balanceProviders.has(providerId);
  const [balanceState, setBalanceState] = useState<{ config: ServiceConfig; credentialId: string; value: ProviderBalance } | null>(null);
  const result = balanceState && balanceState.config === config && balanceState.credentialId === credentialId ? balanceState.value : null;
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    setBalanceState(null);
    if (!config || !credentialId || !supported || configurationState !== "ready") { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true);
    void api.providerBalance(config.id, credentialId, controller.signal).then(value => {
      if (!controller.signal.aborted) setBalanceState({ config, credentialId, value });
    }).catch(() => {
      if (!controller.signal.aborted) setBalanceState({ config, credentialId, value: { status: "error", balances: [] } });
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [config, credentialId, supported, revision, configurationState]);
  if (configurationState !== "ready") return <div className="provider-account-status" role="status"><span className="provider-config-state">{t(configurationState === "loading" ? "配置加载中…" : "配置加载失败")}</span></div>;
  let detail = "";
  if (configured) {
    if (!supported) detail = t("暂不支持余额查询");
    else if (loading || !result) detail = t("余额查询中…");
    else if (result.status === "available") detail = `${t("余额")} ${result.balances.map(balance => `${balance.currency || t("币种未知")} ${balance.amount}`).join(" / ")}`;
    else if (result.status === "invalid_key") detail = t("API Key 无效或无查询权限");
    else if (result.status === "unsupported") detail = t("暂不支持余额查询");
    else if (result.status === "unconfigured") detail = t("未配置");
    else detail = t("余额获取失败");
  }
  const checkedAt = result?.checked_at ? new Date(result.checked_at).toLocaleString(language) : "";
  const invalid = result?.status === "invalid_key";
  const tooltip = `${t("显示首个已配置密钥的余额，不合并不同账号；余额缓存 60 秒。")} ${source?.name || ""}${checkedAt ? ` · ${checkedAt}` : ""}`;
  return <div className="provider-account-status" aria-live="polite">
    <span className={`provider-config-state${invalid ? " is-invalid" : configured ? " is-configured" : ""}`}><span aria-hidden="true" />{t(invalid ? "配置异常" : configured ? "已配置" : "未配置")}</span>
    {detail && <span className="provider-balance" title={tooltip}>{detail}</span>}
    {source && supported && <button type="button" disabled={loading} onClick={() => setRevision(value => value + 1)} aria-label={t("刷新余额")} title={tooltip}><RefreshCw aria-hidden="true" /></button>}
  </div>;
}
