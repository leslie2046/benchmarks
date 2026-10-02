# 项目目录划分

## 职责与依赖

`frontend/` 通过 HTTP 访问 `backend/`。后端通过受控的 `python -m cli.perf_<类型>` 子进程执行压测，复用后端当前 Python 解释器，工作目录为项目根目录。`backend/` 与 `cli/` 都依赖 `shared/`，但 `shared/` 不反向导入它们；CLI 不依赖 FastAPI、SQLite 或前端。

- `backend/`：FastAPI 入口、计划调度、SQLite 存储、凭据加密、连接验证、模型能力、Playground 和 AI 报告。依赖定义在根目录 `pyproject.toml` 的 `backend` 分组，使用 `uv.lock` 锁定版本。
- `frontend/`：React Web 控制台，依赖与脚本定义在 `frontend/package.json`。
- `cli/`：5 个压测模块、命令行入口、可选环境文件加载。依赖定义在根目录 `pyproject.toml` 的 `cli` 分组；Dify 提供 retrieve/chat 两种模式。可选配置为 `cli/.env`，模板为 `cli/.env.example`。
- `shared/`：供应商预设、LLM 流式协议与指标计算、脱敏 JSON 报告输出。
- `docker/`：前后端 Dockerfile、Compose、Nginx、打包启动脚本与部署说明。
- `config/`：版本化的模型能力 YAML。
- `tests/`：后端、CLI 与前端逻辑的回归测试。
- `docs/`：使用、架构和品牌文档。
- `audio/`：音频测试素材。

依赖管理见 [uv 与 pnpm 使用说明](dependencies.md)。运行下面命令前，在根目录执行 `uv sync --locked`；仅使用 CLI 时执行 `uv sync --locked --only-group cli`。

## 运行入口

以下命令在项目根目录运行：

| 用途 | 命令 |
| --- | --- |
| 后端 | `uv run --no-sync python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000` |
| LLM 测试 | `uv run --no-sync python -m cli.perf_llm --help` |
| Embedding 测试 | `uv run --no-sync python -m cli.perf_embedding --help` |
| Reranker 测试 | `uv run --no-sync python -m cli.perf_reranker --help` |
| Audio 测试 | `uv run --no-sync python -m cli.perf_audio --help` |
| Dify 测试 | `uv run --no-sync python -m cli.perf_dify chat --help` |
| Docker 部署 | `docker compose -f docker/compose.yaml up --build -d` |
| 回归测试 | `uv run --no-sync python -m unittest discover -s tests` |

前端开发在 `frontend/` 中运行 `pnpm install --frozen-lockfile`、`pnpm run dev`。CLI 模块入口不依赖临时修改 sys.path 或调用方的 PYTHONPATH，配置详见 [CLI 文档](cli-reference.md)。

## 持久化数据

源码部署默认使用 `backend/volumes/`；Docker 将宿主机 `docker/volumes/` 挂载至容器 `/app/volumes`。两套工作区独立，不自动共享数据。目录内包含 SQLite 数据库、匹配的加密密钥和场景报告，不提交 Git，也不加入镜像构建上下文。

源码部署可通过进程环境变量 `BENCHMARK_DATA_DIR` 指定其他位置。Docker 自定义宿主机位置时调整 Compose 挂载源。备份前停止对应后端，完整备份数据库、密钥和报告，不能混用不同工作区的数据库与密钥。

CLI JSON 输出独立于 Web 运行记录，目前不能直接导入分析看板。用户数据、环境配置、加密密钥、历史报告和音频素材不是冗余代码，不应作为源码清理对象。

## Docker 配置

部署入口为 `docker/compose.yaml`，前后端均使用根目录构建上下文。打包与启动说明见 [Docker 部署指南](../docker/README.md)。保持单个 API worker，并避免多个后端进程同时写同一个 SQLite 工作区。
