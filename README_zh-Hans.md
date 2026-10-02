# BenchLens · 衡镜

AI 服务性能测试与分析控制台。新品牌以「测量窗口＋对比刻度」表达用数据看清模型表现，详见[品牌指南](docs/brand-guidelines.md)。

## 系统配置与 AI 测试报告

在左侧「系统配置」中选择已经配置的 LLM 作为默认分析模型（有多套凭据时可分别选择），保存不会调用模型，也不会更改测试计划。运行结束后，在「运行记录」点击「AI 报告」→「生成报告」手动分析。

报告独立持久化到本地 SQLite，包含生成时间和分析模型，可再次查看、下载或重新分析；重新分析成功后替换旧报告，失败时保留旧内容。关闭弹窗不影响后台分析，服务重启会标记未完成分析并允许重试。删除运行记录也会删除其 AI 报告。

模型只接收白名单性能统计、模型标识、输入长度和文档数量，不接收 API Key、端点、输入正文或原始错误。报告仅供性能分析参考，不代表回答质量评估；手动生成及重新分析可能产生模型调用费用。HTTP API：`GET/PUT /api/system-settings`、`GET/POST /api/runs/{run_id}/ai-report`（POST 可传 `regenerate: true`、`language: zh-CN|en`）。

Dify 知识库配置需填写知识库 ID，名称旁的刷新按钮通过 [`/v1/datasets/{dataset_id}`](https://docs.dify.ai/en/api-reference/knowledge-bases/get-knowledge-base) 获取对应名称；应用通过 [`/v1/info`](https://docs.dify.ai/en/api-reference/applications/get-app-info) 获取名称。获取不会自动保存。测试计划和 Playground 自动使用配置中的知识库 ID，无需重复填写；每次运行将对应 ID 保存到场景中，多知识库计划分别使用各自配置。旧计划的 Dataset ID 作为未补齐配置时的兼容回退，历史记录不修改。编辑时可复用已保存的密钥，更改服务地址或类型后需提供新密钥。

## LLM 流式测试

DeepSeek 官方 provider 已支持 LLM：默认根地址 `https://api.deepseek.com`，预填模型 `deepseek-flash`。可单独验证 API Key、获取服务当前模型列表、选择后保存；验证使用只读模型列表，不发送付费生成请求。配置后可用于 Playground、测试计划和系统默认分析模型。CLI 使用 `--provider deepseek` 与 `DEEPSEEK_API_KEY`，可通过 `--model` 或 `LLM_MODEL` 覆盖模型。

Playground 已支持 YAML 驱动的动态 LLM 参数：所有 LLM provider 提供基础采样参数，已声明的模型还支持思考模式、reasoning_effort 或思考预算。参数范围、提示语及模型匹配规则在 `config/llm-models.yaml` 中定义；可用「刷新模型能力」补充已接入供应商的只读元数据。模型列表支持搜索与类型过滤，系统默认 LLM 支持搜索选择。使用方式与后续计划见 [LLM 模型定义与请求参数方案](docs/llm-model-configuration.md)。预填模型标识应通过[官方模型列表](https://api-docs.deepseek.com/api/list-models/)确认当前可用性。

在模型供应商中添加 LLM 模型后，可以在测试计划与 Playground 中选择 LLM。
接口使用 OpenAI 兼容的 `/v1/chat/completions`，支持预填 Prompt 和最大输出 token 数（默认 256）。
TTFT 为客户端发出请求到首段生成内容（含推理内容）到达的时间，包含网络与排队时间。
TPOT =（整次请求耗时 − TTFT）÷（服务端返回的输出 token 数 − 1）。没有用量数据或只输出一个 token 时显示不可用，不把分块数当成 token 数。
生成速度 = 1000 ÷ TPOT（tokens/s），不含首 token 等待时间；没有有效的正值 TPOT 时不可用。界面数值显示整数，报告保留统计精度。
报告包含有效样本数、平均值、P50/P95/P99；看板支持单次并发对比和同计划多次运行趋势。
测试报告不保存 Prompt 或回答正文，Playground 会显示本次回答。真实测试请求可能产生费用。

```bash
python3 -m cli.perf_llm --provider vllm --base-url http://127.0.0.1:8000/v1/chat/completions \
  --model Qwen/Qwen3-8B --max-tokens 256 -c 1 -n 5 --json-report output/llm.json
```

CLI 可通过 `LLM_MODEL` 和 `<供应商大写>_LLM_URL` 配置模型与端点，API Key 沿用对应供应商的环境变量。

Embedding、Reranker、Xinference 语音转文字及 Dify 知识库和 Chat API 的并发压测脚本，输出成功率、QPS 和延迟分位数。

[English](README.md)

## 运行（Linux）

需要 Python 3 和 `requests` 包。通过环境变量或本地 `.env` 文件配置服务，变量名见 `.env.example`。脚本会自动加载 `.env`，已有的系统环境变量优先；`.env` 已被 Git 忽略。不要把真实密钥写入命令或提交的文件。

选择已配置的服务运行：

```bash
python3 -m cli.perf_embedding --provider vllm --model BAAI/bge-m3 -c 5 -n 50
python3 -m cli.perf_reranker --provider local -c 5 -n 50
python3 -m cli.perf_audio --file audio/asr_example.wav -c 5 -n 50
python3 -m cli.perf_dify retrieve -c 5 -n 50
python3 -m cli.perf_dify chat -c 5 -n 50
```

`-c` 指定并发数，`-n` 指定请求数。建议先用 `-c 1 -n 5` 检查配置。压测会产生实际 API 调用，可能产生费用。

### 批量测试不同并发数

对同一工作负载依次测试多个并发数，每次运行单独保存 JSON：

```bash
for c in 1 5 10 20 30; do
  echo "====== concurrency=$c ======"
  python3 -m cli.perf_reranker --provider xinference -c "$c" -n 100 \
    --json-report "output/reranker-c${c}.json"
done
```

这些命令导出 JSON，供外部工具分析。需要内置可视化时，请在 Web 控制台创建测试计划，并在「分析看板」比较多次运行。旧版独立 HTML 查看器已移除；控制台目前不支持直接导入独立 CLI JSON。

## 配置说明

<details>
<summary>Embedding 服务</summary>

用 `--provider` 选择预设；`--base-url` 和 `--model` 可以覆盖预设值。

| Provider | 默认接口 | 默认模型 | 密钥变量 | 接口 / 模型变量 |
| --- | --- | --- | --- | --- |
| `siliconflow` | `https://api.siliconflow.cn/v1/embeddings` | `BAAI/bge-m3` | `EMBEDDING_API_KEY`（可选；未设置时使用 `XINFERENCE_API_KEY`） | `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL` |
| `xinference` | `http://127.0.0.1:9997/v1/embeddings` | 需指定 | `XINFERENCE_API_KEY`（可选） | `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL` |
| `vllm` | `http://127.0.0.1:8000/v1/embeddings` | 需指定 | `VLLM_API_KEY`（可选） | `VLLM_EMBEDDING_URL`、`VLLM_EMBEDDING_MODEL` |

</details>

<details>
<summary>Reranker 服务</summary>

用 `--provider` 选择预设；`--base-url` 和 `--model` 可以覆盖预设值。`--proxy` 指定 HTTP 代理；`--batch-size 0` 不发送服务专用的 `kwargs.batch_size` 参数。vLLM 预设始终不发送该参数。

| Provider | 默认接口 | 默认模型 | 密钥变量 | 接口 / 模型变量 |
| --- | --- | --- | --- | --- |
| `local` | `http://127.0.0.1:9997/v1/rerank` | `bge-reranker-large` | 无 | 无 |
| `siliconflow` | `https://api.siliconflow.cn/v1/rerank` | `BAAI/bge-reranker-v2-m3` | `SILICONFLOW_API_KEY` | 无 |
| `aliyun` | 需指定 | `qwen3-rerank` | `ALIYUN_API_KEY` | `ALIYUN_RERANK_URL` |
| `xunfei` | `https://maas-api.cn-huabei-1.xf-yun.com/v2/rerank` | `xop3qwen8breranker` | `XUNFEI_API_KEY` | 无 |
| `huaweiyun` | `https://api.modelarts-maas.com/v1/rerank` | `bge-reranker-v2-m3` | `HUAWEIYUN_API_KEY` | 无 |
| `xinference` | 需指定 | 需指定 | `XINFERENCE_API_KEY` | `XINFERENCE_RERANK_URL`、`XINFERENCE_RERANK_MODEL` |
| `vllm` | `http://127.0.0.1:8000/v1/rerank` | 需指定 | `VLLM_API_KEY`（可选） | `VLLM_RERANK_URL`、`VLLM_RERANK_MODEL` |

</details>

<details>
<summary>Xinference 语音转文字</summary>

`perf_audio.py` 每次请求都向 `/v1/audio/transcriptions` 以 `multipart/form-data` 上传同一音频文件；文件只会在压测开始前读入内存一次。

| 配置 | 默认值 / 用途 |
| --- | --- |
| `XINFERENCE_AUDIO_URL` / `--base-url` | `http://127.0.0.1:9997/v1/audio/transcriptions` |
| `XINFERENCE_AUDIO_MODEL` / `--model` | `Qwen3-ASR-0.6B`；填写已启动的模型 UID |
| `XINFERENCE_AUDIO_FILE` / `--file` | 必填，音频文件路径 |
| `XINFERENCE_API_KEY` | 可选 Bearer Token |
| `--audio-duration` | 音频时长（秒）；WAV 可自动识别，其他格式可能需要手动指定 |

已知时长时，结果还会显示平均 RTF（平均延迟 / 音频时长）和音频速度（处理的音频秒数 / 总运行时间）。例如，对 30.5 秒的 MP3 添加 `--audio-duration 30.5`。

</details>

<details>
<summary>Dify 知识库和 Chat</summary>

在 `.env` 中设置 `DIFY_BASE_URL`（服务地址，可带或不带 `/v1`）和 `DIFY_QUERY`。知识库检索还需 `DIFY_DATASET_ID`、`DIFY_DATASET_API_KEY`；Chat 使用单独的 `DIFY_CHAT_API_KEY`。非密钥参数可用 `--base-url`、`--query` 或 `--dataset-id` 覆盖。

知识库检索调用 `POST /v1/datasets/{dataset_id}/retrieve`，统计完整请求延迟。Chat 以流式模式调用 `POST /v1/chat-messages`，每次请求创建新会话，统计首个 `message` 事件耗时（`ttft_ms`）、`message_end_ms`、可选的 workflow 事件耗时及总耗时。只有收到 `message_end` 才算 Chat 请求成功。

两个模式均支持 `--timeout` 和 `--no-verify-ssl`；Chat 还支持 `--user`。每次请求使用同一查询。

</details>

## 结果与参数

脚本输出成功率、QPS、平均延迟和 P50/P95/P99。Dify 的延迟汇总只计算成功请求，QPS 为成功请求数除以总运行时间。已知音频时长时，语音测试还会输出 RTF 和音频速度。

五个 CLI 模块都支持 `--json-report PATH`。JSON 包含逐请求耗时、成功状态和汇总统计，不包含 API Key、URL、查询文本、响应正文或错误内容。父目录会自动创建。CLI JSON 导出独立于 Web 控制台的运行记录保留；延迟指标只用成功请求计算。

在项目根目录运行 `python3 -m cli.perf_<类型> --help` 查看完整参数；Dify 使用 `python3 -m cli.perf_dify retrieve --help` 或 `python3 -m cli.perf_dify chat --help`。仅运行 CLI 时，依赖安装命令为 `python -m pip install -r cli/requirements.txt`。

## 项目目录

```text
backend/    FastAPI、计划调度、持久化、模型能力及后端镜像
cli/        LLM、Embedding、Reranker、Audio、Dify 命令行压测
shared/     共用的供应商预设、环境加载、流式客户端和 JSON 报告
frontend/   Web 控制台
config/     模型 YAML 定义
tests/      回归测试
docs/       品牌、架构和使用文档
audio/      音频测试素材
data/       Docker 部署数据（数据库及密钥）
output/     本地运行数据、报告及临时产物
```

CLI 使用 `python -m cli.perf_<类型>`，后端使用 `python -m uvicorn backend.main:app`，均从项目根目录启动。根目录 `.env` 的加载位置保持不变，已有数据库、密钥和历史报告路径也不变。后端镜像入口改为 `backend/Dockerfile`，构建上下文仍为项目根目录。详细说明见[目录划分与迁移](docs/repository-layout.md)。

## Web 可视化控制台

仓库同时提供前后端分离的 BenchLens 控制台。每个侧边栏入口都有独立页面；「模型供应商」管理模型，「Dify 配置」单独管理知识库检索和聊天应用的服务地址与密钥，「API」页面提供接口文档入口。界面支持简体中文、英文，以及浅色、深色、跟随系统主题。一次测试计划可以选择多个模型或 Dify 配置和多个并发档位（预设档位可多选，也可添加自定义值），后端会展开场景矩阵并依次执行。结果页用两张图分别比较 QPS 和 P50/P95/P99 延迟，运行记录支持删除。

「Playground」可以直接选择已配置的模型或 Dify 服务，发送一次 Embedding、Reranker、Audio 或 Dify 请求，查看服务响应、HTTP 状态和耗时。音频文件上限为 5 MB。Playground 不创建压测计划或运行记录。

数据统一保存在 SQLite：

- 模型供应商，包括共享的加密 API Key，以及多个可分别指定测试类型和 Endpoint 的模型；
- Dify 配置，包括知识库检索或聊天应用的服务根地址与加密 API Key；
- 可重复执行的测试计划；
- 每次运行的场景进度、日志摘要、中间结果和最终报告。

API Key 使用 Fernet 加密。主密钥优先从 `BENCHMARK_SECRET_KEY` 读取；未设置时会在数据目录生成 `secret.key`。迁移或备份时必须同时保存 SQLite 数据库和该密钥。

新增或更新供应商时，后端会使用所填凭据逐个探测模型 Endpoint。连接失败或收到认证拒绝（HTTP 401/403）时返回错误且不会保存。该探测只验证 Endpoint 可访问及显式认证拒绝，不发起实际模型推理；其他业务权限仍需通过测试运行确认。旧版服务配置会按原有数据读取，编辑时可将多个模型加入同一供应商。

### 本地开发

```bash
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload

cd frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`。Vite 会把 `/api` 转发到 `http://127.0.0.1:8000`。

### Docker 部署

复制 `.env.example` 为 `.env` 并配置服务地址、模型及 `BENCHMARK_SECRET_KEY`，然后运行：

```bash
docker compose up --build -d
```

访问 `http://服务器地址:8080`。SQLite、测试计划、报告和自动生成的密钥位于宿主机 `data/`。后端固定使用一个 Uvicorn worker，以确保本地任务调度和 SQLite 写入顺序一致。

控制台可以向已保存的 Endpoint 发起请求，部署到公网时应在 Nginx、Traefik 或其他网关上增加登录认证和 HTTPS，不要直接暴露 FastAPI 端口。

## License

[MIT](LICENSE)
## Audio 与 LLM 流式交互

Audio 语音转文字支持 Xinference、vLLM 和硅基流动，模型供应商可选择 Audio 类型，测试计划和 Playground 使用对应供应商凭据。硅基流动获取模型列表会自动识别 `speech-to-text` 模型；Audio 暂不包含语音合成。

Playground 的 LLM 回答边生成边显示，可停止并保留已接收内容。首段返回后显示 TTFT，完成后显示 TPOT 和生成速度（需要服务返回输出 token 用量）；原始 JSON 可展开查看。
