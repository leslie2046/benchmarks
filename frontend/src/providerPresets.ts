import type { Language } from "./i18n";

export const providerPresets: Record<string, { zh: string; en: string; serverUrl?: string }> = {
  siliconflow: { zh: "SiliconFlow 平台（硅基流动）", en: "SiliconFlow", serverUrl: "https://api.siliconflow.cn" },
  aliyun: { zh: "阿里云百炼 / 大模型服务平台百炼", en: "Alibaba Cloud Model Studio", serverUrl: "https://dashscope.aliyuncs.com/compatible-api" },
  huaweiyun: { zh: "ModelArts Studio（MaaS）/ MaaS 模型即服务平台", en: "ModelArts Studio (MaaS)", serverUrl: "https://api.modelarts-maas.com" },
  xunfei: { zh: "讯飞星火认知大模型", en: "SparkDesk", serverUrl: "https://maas-api.cn-huabei-1.xf-yun.com" },
  vllm: { zh: "vLLM", en: "vLLM" },
};

export function providerDisplayName(id: string, language: Language, fallback: string): string {
  const preset = providerPresets[id];
  return preset ? preset[language === "zh-CN" ? "zh" : "en"] : fallback;
}
