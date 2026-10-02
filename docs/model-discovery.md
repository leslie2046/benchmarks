# 模型列表获取

在「模型供应商」点击「获取模型列表」，填写对应区域的服务地址与 API Key，再获取并选择模型。验证、获取、能力刷新均使用只读 GET，不调用生成接口，也不自动保存；点击「保存所选模型」后才导入配置。

| 供应商 | 模型列表路径 | 处理方式 |
| --- | --- | --- |
| 百炼 | `/api/v1/models` | 自动分页，读取 `output.models`，使用 `model` 作为模型 ID |
| 华为云 MaaS | `/v2/models` | 读取 `data`，使用 `id` 作为模型 ID |

百炼会移除服务地址末尾的 `/compatible-mode`、`/compatible-api` 或版本路径，再拼接模型列表路径；保留所填写的域名、区域及网关前缀。华为云同样保留域名，不自动跨区域重试或转发密钥。

百炼默认 LLM 服务地址为 `https://dashscope.aliyuncs.com/compatible-mode`，请求时拼接 `/v1/chat/completions`。`qwen3-rerank` 则使用 `/compatible-api/v1/reranks`，不能全局替换这两个前缀。北京地域模型列表接口推荐填写工作空间专属域名 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode`，列表请求会转换为同域名的 `/api/v1/models`。鉴权使用对应地域和工作空间的百炼 API Key（Bearer），不是阿里云 AccessKey ID/Secret。

## 区域与地址

- 百炼请使用当前区域支持模型列表接口的域名。官方文档列出的北京地址需要 Workspace ID，例如 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com`；新加坡为 `https://dashscope-intl.aliyuncs.com`。已有 DashScope 地址会按原域名请求，不自动迁移到新域名。
- 华为云中国站文档注明该接口支持「西南-贵阳一」，地址为 `https://api.modelarts-maas.com/v2/models`。国际站文档注明「中国-香港」，地址为 `https://api-ap-southeast-1.modelarts-maas.com/v2/models`。请使用对应区域的 API Key。
- 401 / 403 会提示密钥被拒绝；其他 HTTP 错误或异常响应不会被替换成静态模型列表。区域不支持时，可继续手动添加模型。

## 模型类型与能力

分类优先采用明确的 `model_type` / `type` / `sub_type`；百炼随后使用官方确认的模型 ID 目录补充分类（见 `backend/model_discovery.py` 的 `ALIYUN_MODEL_TYPES`），最后才使用能力标签。`qwen3-rerank`、`qwen3-vl-rerank`、`qwen3.7-text-rerank`、`gte-rerank-v2` 归为 Reranker，不会因粗粒度 `TR` 标签被误归为 Embedding。`TG` / `Reasoning` 归为 LLM，其他 `TR` 默认归为 Embedding。未知模型不会仅凭名称猜测，需要手动选择类型。华为云示例响应没有明确的测试类型字段，因此允许手动指定。

百炼已支持文本 Embedding 的模型配置、Playground、测试计划和 CLI，使用 `/compatible-mode/v1/embeddings`，默认模型为 `text-embedding-v4`；CLI 凭据变量为 `ALIYUN_API_KEY`，可通过 `ALIYUN_EMBEDDING_URL` / `ALIYUN_EMBEDDING_MODEL` 覆盖默认值。分类只表示模型用途，不表示所有模型共用同一个调用协议：本次支持的是文本 Embedding 的 OpenAI 兼容接口，不包含多模态输入、原生 DashScope Embedding 或原生 Rerank 协议的适配。

Playground 的「刷新模型能力」复用相同解析器；百炼 `model_info` 中的上下文窗口与输出上限可以补充 YAML 元数据。模型列表不等于完整参数说明，思考模式、effort 等请求字段仍以 YAML 中明确配置的规则为准。

获取列表与保存配置的限制相互独立：模型列表不会在 500 个处截断，百炼会持续分页拉取；异常保护上限为 10000 个模型、100 页，超过安全上限或分页不前进会明确报错，不返回伪装成完整列表的部分结果。每个供应商配置仍最多保存 500 个模型（含已有模型）；候选模型超过剩余额度时不自动全选，可通过搜索和类型过滤手动选择。

## 其他供应商的分类与测试

所有供应商共用明确类型字段的解析规则，支持 `task: text_embedding`、`sub_type: reranking` 等别名及明确的能力标签；无法识别的字段不会覆盖其他有效字段。华为云的官方 `bge-m3` / `bge-reranker-v2-m3` ID 分别补充归类为 Embedding / Reranker。硅基流动优先使用分类列表，并用模型自身元数据补充；未知类型仍可手动选择。

华为云和讯飞星辰新增文本 Embedding，可用于 Playground、测试计划和 CLI。讯飞模型 ID 必须填写控制台中的部署 ID；新服务默认 `/v2/embeddings`，显式 `/v1` 地址保持不变。讯飞仍采用手动添加模型，不虚构模型发现接口。DeepSeek 保持 LLM 能力边界。

全选、全不选以及当前搜索/类型筛选结果的批量选择，对所有支持模型发现的供应商统一生效；未分类模型需先选择类型才能导入。

### 官方接口依据

- [华为云：文本 Embedding](https://support.huaweicloud.com/model-call-maas/model-call-027.html)
- [讯飞星辰：Embedding 与 Rerank](https://www.xfyun.cn/doc/spark/Embedding%26Rerank%E6%9C%8D%E5%8A%A1_HTTP%E5%8D%8F%E8%AE%AE.html)

- [百炼：查询模型列表](https://help.aliyun.com/en/model-studio/list-models)
- [华为云：中国站 Models/GET](https://support.huaweicloud.com/model-call-maas/model-call-029.html)
- [华为云：国际站 Models/GET](https://support.huaweicloud.com/intl/zh-cn/model-call-maas/model-call-029.html)

接口与区域说明核对日期：2026-10-02。模型可用性以对应区域、账号的实际响应为准。
