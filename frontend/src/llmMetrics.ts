export const LLM_METRICS = ["ttft", "tpot", "tokens_per_second"] as const;
export type LlmMetric = typeof LLM_METRICS[number];
export const llmMetricKey = (metric: LlmMetric) => metric === "tokens_per_second" ? metric : `${metric}_ms`;
export const llmMetricLabel = (metric: LlmMetric) => metric === "tokens_per_second" ? "生成速度" : metric.toUpperCase();
export const llmMetricUnit = (metric: LlmMetric) => metric === "tokens_per_second" ? "tokens/s" : metric === "tpot" ? "ms/token" : "ms";
export const llmMetricTip = (metric: LlmMetric) => metric === "tokens_per_second"
  ? "生成速度：1000 ÷ TPOT，即首 token 之后每秒生成的 token 数；不包含首 token 等待时间，缺少有效 TPOT 时不可用。"
  : metric === "ttft" ? "TTFT：请求发出到首段生成内容到达的时间，包含网络与排队时间。"
  : "TPOT：(整次请求耗时 − TTFT) ÷ (输出 token 数 − 1)。仅统计服务返回 token 用量且输出超过一个 token 的成功请求。";
