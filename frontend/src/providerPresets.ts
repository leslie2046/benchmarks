import type { Language } from "./i18n";

export const providerPresets: Record<string, { zh: string; en: string; serverUrl?: string; logoUrl?: string }> = {
  siliconflow: { zh: "硅基流动", en: "SiliconFlow", serverUrl: "https://api.siliconflow.cn", logoUrl: "/provider-logos/siliconflow.ico" },
  xinference: { zh: "Xinference", en: "Xinference", logoUrl: "/provider-logos/xinference.png" },
  vllm: { zh: "vLLM", en: "vLLM", logoUrl: "/provider-logos/vllm.ico" },
  aliyun: { zh: "阿里云百炼", en: "Alibaba Cloud Model Studio", serverUrl: "https://dashscope.aliyuncs.com/compatible-api", logoUrl: "/provider-logos/aliyun.ico" },
  xunfei: { zh: "讯飞星辰MaaS", en: "iFLYTEK Xingchen MaaS", serverUrl: "https://maas-api.cn-huabei-1.xf-yun.com", logoUrl: "/provider-logos/xunfei.ico" },
  huaweiyun: { zh: "华为云MaaS", en: "Huawei Cloud MaaS", serverUrl: "https://api.modelarts-maas.com", logoUrl: "/provider-logos/huaweiyun.ico" },
};

export function providerDisplayName(id: string, language: Language, fallback: string): string {
  const preset = providerPresets[id];
  return preset ? preset[language === "zh-CN" ? "zh" : "en"] : fallback;
}
