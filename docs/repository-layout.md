# 目录划分与迁移

## 职责与依赖

`frontend/` 通过 HTTP 访问 `backend/`。后端通过受控的 `python -m cli.perf_<类型>` 子进程执行压测，工作目录固定为项目根目录。`backend/` 与 `cli/` 都依赖 `shared/`，但 `shared/` 不反向导入它们；CLI 不依赖 FastAPI、SQLite 或前端。

- `backend/`：应用入口 `main.py`、调度 runner、SQLite store、凭据加密、连接验证、模型能力解析、Playground 和 AI 报告。依赖为 `backend/requirements.txt`。
- `cli/`：5 个压测模块，各自的 argparse 入口与测试流程，依赖为 `cli/requirements.txt`。Dify 同一模块提供 retrieve/chat 两种模式。
- `shared/`：供应商预设、根目录 `.env` 加载、LLM 流式协议与指标计算、隐私安全的 JSON 报告输出。共用协议修复只做一次。
- `config/`：模型能力 YAML。后端 Docker 镜像明确复制此目录。
- `tests/`：在项目根目录执行 `python -m unittest discover -s tests`。

## 命令迁移

| 旧命令 | 新命令 |
| --- | --- |
| python -m uvicorn webapp.main:app | python -m uvicorn backend.main:app |
| python perf_llm.py | python -m cli.perf_llm |
| python perf_embedding.py | python -m cli.perf_embedding |
| python perf_reranker.py | python -m cli.perf_reranker |
| python perf_audio.py | python -m cli.perf_audio |
| python perf_dify.py chat | python -m cli.perf_dify chat |

以上命令在项目根目录运行，原有 CLI 参数保留。模块入口避免临时修改 sys.path 或依赖调用方的 PYTHONPATH；不保留根目录旧脚本副本。

## 删除与保留

旧版 `report_viewer.html` 已退出代码树，README 不再提供该入口。本次清理前的完整副本保存在本地忽略目录 `output/cleanup-backup/report_viewer-20261002.html`，包括未提交的修改，可复制回来恢复。CLI JSON 输出仍保留，但 Web 分析看板只分析控制台运行记录，目前不直接导入独立 CLI JSON。

`report_writer.py` 仍被所有 CLI 使用，因此移入 `shared/`，不删除。`CONTEXT.md` 仍是领域术语说明，也保留。用户数据、环境文件、加密密钥、历史报告、音频素材不属于冗余代码，不做删除或搬迁。`data/`、`output/web/`、`BENCHMARK_DATA_DIR` 的含义保持不变。

Docker Compose 改用 `backend/Dockerfile`，构建上下文保持根目录，数据库挂载保持 `./data:/data`。重新构建 API 镜像后再启动即可，不能删除旧数据卷或 secret.key。
