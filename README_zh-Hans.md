# PrismLab · 棱镜实验室

AI 模型测试与分析平台：验证服务、对比性能，让测试结果更容易理解。

[English](README.md) · [快速开始](#快速开始) · [命令行测试](#命令行测试) · [相关文档](#相关文档)

PrismLab 连接你已经部署或购买的模型服务，不负责部署模型。通过 Web 控制台进行交互测试、管理可重复运行的测试计划，也可以使用 CLI 进行轻量并发压测。

## 可以测试什么

| 测试类型 | 测试内容 | 主要指标 |
| --- | --- | --- |
| LLM | 流式文本生成 | TTFT、TPOT、tokens/s、请求耗时 |
| Embedding | 文本向量化 | 延迟、QPS、成功率 |
| Reranker | 问题与候选文档重排 | 延迟、QPS、成功率 |
| Audio | 语音转文字 | 延迟、QPS；已知音频时长时提供 RTF |
| Dify Retrieve | 知识库检索 | 延迟、QPS、成功率 |
| Dify Chat | 应用流式回复 | 首消息耗时、总耗时、成功率 |

控制台支持模型搜索与类型筛选、YAML 驱动的 LLM 参数、定时测试计划、运行记录、性能对比图表，以及手动生成的 AI 测试报告。界面支持中英文与浅色 / 深色主题。

内置供应商预设包括 DeepSeek、硅基流动、Xinference、vLLM、阿里云、讯飞星辰 MaaS 和华为云。可用测试类型及模型列表获取能力取决于供应商与实际部署，并非所有供应商都支持全部类型。

## 快速开始

部署使用选择 **Docker**；修改代码选择 **本地开发**。实际测试还需要一个可访问的模型服务或 Dify 实例。

### 方式一：Docker 部署

准备好 Git、Docker 和 Docker Compose v2（`docker compose`）。Windows Docker Desktop 使用 Linux 容器模式，并确保宿主机 8080 端口未被占用。

```bash
git clone https://github.com/leslie2046/benchmarks.git
cd benchmarks
```

启动控制台：

```bash
docker compose -f docker/compose.yaml up --build -d
```

打开 **http://localhost:8080**，在界面中配置模型服务与密钥。部署无需创建 `.env`；后端可选的系统配置通过进程或容器环境变量提供，不加载 `.env` 文件。

常用部署命令：

```bash
docker compose -f docker/compose.yaml logs -f
docker compose -f docker/compose.yaml up --build -d    # 拉取更新后重新构建
docker compose -f docker/compose.yaml down           # 停止服务
```

Docker 数据保存在宿主机 `docker/volumes/` 目录。升级前请备份，详见[数据与安全](#数据与安全)。

如需分开构建和启动，Linux/macOS 依次执行 `bash docker/build.sh`、`bash docker/start.sh`；Windows PowerShell 依次执行 `.\docker\build.ps1`、`.\docker\start.ps1`。启动脚本使用已有镜像，不自动构建。离线镜像打包和启动排错见 [Docker 部署指南](docker/README.md)。

Docker 中的 `127.0.0.1` 指向容器自身，不是宿主机。访问宿主机上的模型时，请使用 API 容器可访问的地址（例如 Docker Desktop 的 `host.docker.internal`），并检查服务监听地址与防火墙。

### 方式二：本地开发

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) **0.12.22**、[pnpm](https://pnpm.io/installation) **10.28.2**，以及 Node.js 22.12+（或 24+）。按上面的命令克隆项目。uv 自动创建 `.venv` 并选择 Python 3.12，无需手动激活虚拟环境。

**终端一：启动后端**，在项目根目录执行：

```bash
uv sync --locked
uv run --no-sync python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

**终端二：启动前端**：

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run dev --host 127.0.0.1
```

打开 **http://localhost:5173**。Vite 将 `/api` 请求转发到 8000 端口的后端；如果 Vite 使用了其他端口，请以终端显示的地址为准。

本地数据默认保存在 `backend/volumes/`。生产后端请保持 **单 worker**，因为计划调度与 SQLite 管理由该进程负责。

## 完成第一次测试

1. **模型供应商**：选择内置供应商，添加模型并配置服务地址和凭据，或在支持的供应商中获取并选择模型，然后保存。
2. **Playground**：选择测试类型和已配置的模型，发送一次请求检查配置。它会调用真实服务，但不会创建测试计划或运行记录。
3. **测试计划**：填写测试输入，选择模型、并发档位和请求数。建议从并发 1、请求数 5 开始。新建计划保存后不会立即运行，由你决定何时启动。
4. **运行记录**：查看进度、失败情况和测试结果。每次执行都会产生一条独立记录。
5. **分析看板**：比较不同并发档位，或同一计划的多次运行。使用相近的输入与生成参数，对比才有意义。

测试 Dify 时，先进入 **Dify 配置**。服务地址默认是 `https://api.dify.ai`，自部署实例请替换。知识库检索需要知识库 ID 和 Dataset API Key；聊天应用使用独立的应用 API Key。名称旁的刷新按钮可以获取对应名称，但不会自动保存。测试计划与 Playground 会复用配置中的知识库 ID，无需重复填写。

**测试会调用真实 API，可能产生费用。** 先验证单次请求，再提高并发或开启定时重复运行。

## LLM Playground 与 AI 报告

### 交互式生成

LLM Playground 支持系统提示词、流式回复、单独展示思考内容，以及模型专属参数。可以停止生成并保留已收到的文本。目前是 **单次请求，不携带对话历史**。

- 参数能力及请求字段映射来自 [config/llm-models.yaml](config/llm-models.yaml)，无需把每个模型的控件写死在前端。
- 思考模式、推理强度与思考预算仅对明确声明能力的模型开放；未知模型使用保守的基础兼容配置。
- 「刷新模型能力」仅通过已接入的供应商模型列表接口补充元数据；服务没有返回的上下文上限仍显示未知。
- **Playground 最大输出 token 数默认留空**：不发送 `max_tokens`，使用服务默认值。测试计划与 LLM CLI 仍默认 256；思考模型的输出预算可能包含推理内容，测试时应适当调整。
- Playground 的动态参数与系统提示词尚未作为完整参数编辑器同步到测试计划、CLI 和 AI 报告。

YAML 配置、参数校验及当前限制见 [LLM 模型定义与请求参数](docs/llm-model-configuration.md)。

### AI 性能分析报告

在 **系统配置** 中选择已配置的 LLM 作为默认分析模型。测试结束后，进入 **运行记录 → AI 报告 → 生成报告**，手动触发分析。生成可能产生模型费用；保存默认模型不会调用它，也不会更改测试目标。

报告持久化到 SQLite，后续查看或下载不再调用模型。重新分析仅在成功后替换旧报告，失败时保留旧版本；删除运行记录时，其 AI 报告也会删除。

分析模型只接收白名单性能统计、模型标识、输入长度与文档数量，不接收 API Key、服务地址、测试输入正文或原始错误。报告用于解释性能，不代表回答质量评估。

## 命令行测试

CLI 独立于 Web 控制台：读取进程环境变量和可选的 `cli/.env`，不读取界面中保存的凭据，也不读取根目录 `.env`。

在项目根目录仅安装 CLI 依赖：

```bash
uv sync --locked --only-group cli
```

可选的 `cli/.env` 配置步骤和供应商参数见 [CLI 配置文档](docs/cli-reference.md)。不要把真实密钥直接写到命令或提交的文件里。

配置好对应服务地址、模型与凭据后，选择下面 **一条** 命令开始：

```bash
uv run --no-sync python -m cli.perf_llm --provider deepseek --max-tokens 2048 -c 1 -n 5 --json-report output/llm.json
uv run --no-sync python -m cli.perf_embedding --provider vllm --model BAAI/bge-m3 -c 1 -n 5 --json-report output/embedding.json
uv run --no-sync python -m cli.perf_reranker --provider xinference -c 1 -n 5 --json-report output/reranker.json
uv run --no-sync python -m cli.perf_audio --provider xinference --file audio/asr_example.wav -c 1 -n 5 --json-report output/audio.json
uv run --no-sync python -m cli.perf_dify retrieve -c 1 -n 5 --json-report output/dify-retrieve.json
uv run --no-sync python -m cli.perf_dify chat -c 1 -n 5 --json-report output/dify-chat.json
```

`-c` 是并发数，`-n` 是总请求数。配置验证通过后再逐步增加。完整参数可通过 `--help` 查看，例如：

```bash
uv run --no-sync python -m cli.perf_llm --help
uv run --no-sync python -m cli.perf_dify retrieve --help
```

五个 CLI 模块均支持 JSON 导出，包含逐请求耗时、成功状态及汇总统计，不包含凭据、URL、查询文本、回复正文或原始错误。**Web 控制台目前不支持导入独立 CLI JSON。**

供应商端点、环境变量及多并发测试示例见 [CLI 配置参考](docs/cli-reference.md)。

## 如何理解指标

| 指标 | 含义 |
| --- | --- |
| P50 / P95 / P99 | 延迟分位数：50% / 95% / 99% 的有效成功请求在该时间内完成 |
| QPS | 吞吐量；JSON 中的 `qps_success` 是成功请求数除以总运行时间 |
| TTFT | 客户端发起请求到首段生成内容到达的时间，包含思考内容 |
| TPOT | `（整次请求耗时 − TTFT）÷（输出 token 数 − 1）` |
| tokens/s | `1000 ÷ TPOT`，不包含等待首 token 的时间 |
| 音频 RTF | 请求耗时除以音频时长，越低越快 |

LLM 的 TPOT 与生成速度依赖服务返回的输出 token 用量；缺失用量或 token 不足时显示不可用，不把流式分块数当作 token 数。界面数值显示整数，报告保留统计精度。

上述分位数与 QPS 定义对应 Web 控制台和导出 JSON。部分 CLI 终端摘要会将失败请求计入延迟统计，并按总请求数计算 QPS；对比成功请求性能时，请以 JSON 的 `metrics` 和 `qps_success` 为准。

这些是 **客户端端到端测量**，包含网络开销，不等于模型的纯推理耗时。少量请求适合验证连接，不适合判断稳定的 P95 / P99；不同运行的分位数不能直接取平均。

## 数据与安全

- API Key 使用 Fernet 加密。可配置稳定的 `BENCHMARK_SECRET_KEY`；未设置时在数据目录生成 `secret.key`。
- 备份前先停止后端，备份 **整个数据目录**，包括 `runs.sqlite3`、`secret.key`、报告及可能存在的 SQLite 附属文件。使用环境变量提供加密密钥时，另行妥善保存。丢失密钥将无法解密已保存的凭据。
- 测试计划会保存输入配置。CLI 导出与 AI 分析的数据脱敏，不代表应用全部本地数据都不含敏感输入。
- `cli/.env` 已被 Git 忽略，不要提交真实凭据或公开运行数据。
- 控制台没有内置登录认证。公网部署前，请在反向代理上配置认证与 HTTPS，并限制后端及已配置服务的访问范围。
- Docker 使用 `docker/volumes/`，源码部署使用 `backend/volumes/`。源码路径可通过 `BENCHMARK_DATA_DIR` 覆盖；Docker 路径通过修改宿主机挂载源调整，见 [部署指南](docker/README.md)。
- 两套目录是独立工作区，不自动共享数据。

## 开发与文档

```text
backend/    FastAPI、计划调度、持久化与模型能力
frontend/   React Web 控制台
docker/     Dockerfile、Compose、Nginx 与部署指南
cli/        命令行压测模块
shared/     供应商预设、流式客户端与报告工具
config/     版本化 LLM 模型定义
tests/      回归测试
docs/       使用、架构与品牌文档
audio/      音频测试素材
```

在项目根目录执行检查：

```bash
uv sync --locked
uv run --no-sync python -m unittest discover -s tests
cd frontend
pnpm install --frozen-lockfile
pnpm run build
pnpm run test:dashboard
pnpm run test:playground
pnpm run test:selection
```

### 相关文档

- [Docker 部署与打包启动脚本](docker/README.md)
- [依赖管理](docs/dependencies.md)
- [CLI 配置参考](docs/cli-reference.md)
- [模型列表获取与区域说明](docs/model-discovery.md)
- [LLM 模型定义与请求参数](docs/llm-model-configuration.md)
- [项目目录划分](docs/repository-layout.md)
- [PrismLab 品牌指南](docs/brand-guidelines.md)

## 许可证

[MIT](LICENSE)
