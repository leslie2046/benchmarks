import type { Language } from "./i18n";

export const providerPresets: Record<string, { zh: string; en: string; serverUrl?: string; logoUrl: string; logoMonochrome?: boolean; apiKeyRequired?: boolean; apiKeyUrl?: string }> = {
  moonshot: { zh: "Moonshot（月之暗面）", en: "Moonshot (Kimi)", serverUrl: "https://api.moonshot.cn/v1", logoUrl: "/provider-logos/moonshot.svg", logoMonochrome: true, apiKeyRequired: true, apiKeyUrl: "https://platform.kimi.com/console/api-keys" },
  qwen: { zh: "千问", en: "Qwen", serverUrl: "https://maas.qianwenaiapi.com/compatible-mode/v1", logoUrl: "/provider-logos/qianwen.svg", apiKeyRequired: true, apiKeyUrl: "https://platform.qianwenai.com/home/api-keys" },
  minimax: { zh: "MiniMax", en: "MiniMax", serverUrl: "https://api.minimax.cn/v1", logoUrl: "/provider-logos/minimax.svg", apiKeyRequired: true, apiKeyUrl: "https://platform.minimax.cn/" },
  volcengine: { zh: "火山方舟", en: "Volcengine Ark", serverUrl: "https://ark.cn-beijing.volces.com/api/v3", logoUrl: "/provider-logos/volcengine.svg", apiKeyRequired: true, apiKeyUrl: "https://console.volcengine.com/ark/" },
  deepseek: { zh: "DeepSeek", en: "DeepSeek", serverUrl: "https://api.deepseek.com", logoUrl: "/provider-logos/deepseek.ico", apiKeyRequired: true, apiKeyUrl: "https://platform.deepseek.com/api_keys" },
  siliconflow: { zh: "硅基流动", en: "SiliconFlow", serverUrl: "https://api.siliconflow.cn", logoUrl: "/provider-logos/siliconflow.ico", apiKeyUrl: "https://cloud.siliconflow.cn/account/ak" },
  xinference: { zh: "Xinference", en: "Xinference", logoUrl: "/provider-logos/xinference.png" },
  vllm: { zh: "vLLM", en: "vLLM", logoUrl: "/provider-logos/vllm.ico" },
  aliyun: { zh: "阿里云百炼", en: "Alibaba Cloud Model Studio", serverUrl: "https://dashscope.aliyuncs.com/compatible-mode", logoUrl: "/provider-logos/aliyun.ico", apiKeyRequired: true, apiKeyUrl: "https://bailian.console.aliyun.com/" },
  xunfei: { zh: "讯飞星辰MaaS", en: "iFLYTEK Xingchen MaaS", serverUrl: "https://maas-api.cn-huabei-1.xf-yun.com", logoUrl: "/provider-logos/xunfei.ico", apiKeyRequired: true, apiKeyUrl: "https://maas.xfyun.cn/" },
  huaweiyun: { zh: "华为云MaaS", en: "Huawei Cloud MaaS", serverUrl: "https://api.modelarts-maas.com", logoUrl: "/provider-logos/huaweiyun.ico", apiKeyRequired: true, apiKeyUrl: "https://console.huaweicloud.com/modelarts/" },
};

export function providerDisplayName(id: string, language: Language, fallback: string): string {
  const preset = providerPresets[id];
  return preset ? preset[language === "zh-CN" ? "zh" : "en"] : fallback;
}
