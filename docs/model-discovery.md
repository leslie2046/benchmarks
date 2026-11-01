# 模型列表获取

在「模型供应商」点击「获取模型列表」，填写对应区域的服务地址与 API Key，再获取并选择模型。验证、获取、能力刷新均使用只读 GET，不调用生成接口，也不自动保存；点击「保存所选模型」后才导入配置。

云供应商的模型获取及模型配置弹窗提供“获取 API Key”链接，在新标签页打开对应官方平台。部分平台需登录后再进入密钥管理，并选择与服务地址匹配的区域。链接不会携带已填写的密钥、服务器地址或其他配置，也不会保存表单；Xinference、vLLM 等自部署服务不显示此入口，由部署管理员提供凭据。

## 新增云供应商

| 供应商 / ID | 默认服务器 URL | 支持类型 | 模型列表 |
| --- | --- | --- | --- |
| Moonshot（月之暗面 / Kimi）`moonshot` | `https://api.moonshot.cn/v1` | LLM | `GET /v1/models` |
| 千问 `qwen` | `https://maas.qianwenaiapi.com/compatible-mode/v1` | LLM、Embedding、Reranker、Audio（同步 ASR） | 千问域名的 `/api/v1/models` 分页接口 |
| MiniMax `minimax` | `https://api.minimax.cn/v1` | LLM | `GET /v1/models`，也可手动填写模型 ID |
| 火山方舟 `volcengine` | `https://ark.cn-beijing.volces.com/api/v3` | LLM | 手动填写模型 ID / 推理接入点 ID |

千问 `qwen` 对应 [千问 AI 平台](https://platform.qianwenai.com/)，在 [API Key 页面](https://platform.qianwenai.com/home/api-keys) 创建密钥，默认接口主机为 `maas.qianwenaiapi.com`，不是百炼的 `dashscope.aliyuncs.com`。凭据和模型不会与已有 `aliyun` 百炼配置自动合并或复制；仅复用兼容协议及向量/重排路径适配。首次配置可获取模型列表，或手动添加账号可用的模型；具体可用性以官方控制台为准。已保存的服务器 URL 和密钥不会自动改写；此前在 `qwen` 下保存了百炼地址的配置，请手动改用千问地址及对应密钥，或继续通过“阿里云百炼”使用百炼账号。

### 千问 Audio（语音识别）

在千问的“添加模型”中选择 Audio，默认模型为 `qwen3-asr-flash`；也支持 `qwen-audio-3.0-asr-flash`、`qwen-audio-3.1-asr-flash` 及其日期快照。Playground 上传本地音频、连通性验证和测试计划均使用原生同步 `POST /api/v1/services/aigc/multimodal-generation/generation`：音频编码为 Base64 Data URL，按模型系列发送对应 JSON；不使用 `/audio/transcriptions` 或只支持公网 URL 的 OpenAI 兼容方式。保留用户配置的主机及网关前缀。已知同步 ASR 模型在发现列表自动归为 Audio，其他未知模型仍需手动指定类型。

本次不包含 TTS、实时 WebSocket、异步 filetrans 或 Omni 对话。Playground 保持 5 MB 上传限制；CLI 单文件上限 10 MB；`qwen3-asr-flash` 官方时长上限为 5 分钟，具体格式与各模型限制见[千问录音文件转写](https://platform.qianwenai.com/docs/developer-guides/speech/asr)。连通性验证会转写短静音 WAV，属于真实模型调用，可能收费。

CLI 示例：

```bash
python -m cli.perf_audio --provider qwen --model qwen3-asr-flash --file audio/asr_example.wav -c 1 -n 1
```

使用 `QWEN_API_KEY`、`QWEN_AUDIO_URL`、`QWEN_AUDIO_MODEL`；Web app 模式仍使用当前空间保存的密钥，不读取其他空间或服务端环境密钥。

Moonshot、MiniMax、火山方舟不预填其他供应商的模型名。Moonshot 可以获取并选择账号可用模型；MiniMax 请填写控制台提供的实际模型 ID；方舟填写账号支持的模型 ID 或 `ep-...` 推理接入点 ID。这里接入 OpenAI 兼容的流式文本生成，不代表已接入这些平台的图像、视频、语音或原生专属 API。三者先使用基础生成参数，不根据模型名称猜测思考模式或预算能力。

服务地址可修改，例如 Moonshot 国际站或 MiniMax 国际站 `https://api.minimax.io/v1`。使用与地址/区域匹配的密钥；Coding Plan 专用密钥与地址不保证适用于按量 API。MiniMax 支持使用 Bearer API Key 获取 OpenAI 兼容模型列表及验证密钥，列表中的模型归类为 LLM；不调用生成接口。方舟会使用 `/api/v3/chat/completions`，不要替换为 `/v1/chat/completions`。方舟暂不展示“获取模型列表”；手动模型验证会发起少量真实生成请求，可能收费。

新增供应商可用于 Playground、测试计划、AI 分析默认模型和 LLM CLI。CLI 使用对应的 `MOONSHOT_API_KEY`、`QWEN_API_KEY`、`MINIMAX_API_KEY`、`VOLCENGINE_API_KEY`，通过 `--provider` 和 `--model` 指定供应商和实际模型，参见 `cli/.env.example`。Web app 模式仅使用当前空间保存的凭据，不读取这些环境变量作为跨空间后备。

官方参考：[Moonshot / Kimi](https://platform.kimi.com/docs)、[百炼兼容接口](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)、[MiniMax OpenAI SDK](https://platform.minimax.cn/docs/api-reference/text-openai-api)、[MiniMax 模型列表](https://platform.minimax.cn/docs/api-reference/models/openai/list-models)、[火山方舟](https://www.volcengine.com/docs/82379/1330310)。

| 供应商 | 模型列表路径 | 处理方式 |
| --- | --- | --- |
| 百炼 | `/api/v1/models` | 自动分页，读取 `output.models`，使用 `model` 作为模型 ID |
| 华为云 MaaS | `/v2/models` | 读取 `data`，使用 `id` 作为模型 ID |

百炼会移除服务地址末尾的 `/compatible-mode`、`/compatible-api` 或版本路径，再拼接模型列表路径；保留所填写的域名、区域及网关前缀。华为云同样保留域名，不自动跨区域重试或转发密钥。

百炼默认 LLM 服务地址为 `https://dashscope.aliyuncs.com/compatible-mode`，请求时拼接 `/v1/chat/completions`。`qwen3-rerank` 则使用 `/compatible-api/v1/reranks`，不能全局替换这两个前缀。北京地域模型列表接口推荐填写工作空间专属域名 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode`，列表请求会转换为同域名的 `/api/v1/models`。鉴权使用对应地域和工作空间的百炼 API Key（Bearer），不是阿里云 AccessKey ID/Secret。

## 区域与地址

- 百炼请使用当前区域支持模型列表接口的域名。官方文档列出的北京地址需要 Workspace ID，例如 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com`；新加坡为 `https://dashscope-intl.aliyuncs.com`。已有 DashScope 地址会按原域名请求，不自动改用其他域名。
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
