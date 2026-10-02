# 依赖管理

Python 依赖由根目录 `pyproject.toml` 和 `uv.lock` 管理；前端依赖由 `frontend/package.json` 和 `frontend/pnpm-lock.yaml` 管理。锁文件应提交 Git，构建时不要重新解析版本。

## Python：uv

使用 uv **0.12.22**，安装方式见 [官方文档](https://docs.astral.sh/uv/getting-started/installation/)。默认 Python 为 `.python-version` 指定的 3.12；uv 可以自动下载缺少的 Python，也可用 `--python` 显式选择满足 `>=3.12` 的解释器。

在项目根目录执行：

```bash
uv sync --locked
uv run --no-sync python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

默认安装 `backend` 和 `dev` 分组。`backend` 包含 `cli`，因此后端任务子进程无需单独安装 CLI；`dev` 提供测试所需的 httpx。项目不作为 Python 包安装，继续使用模块入口。

```bash
# 只安装 CLI（不包含后端与测试依赖）
uv sync --locked --only-group cli
uv run --no-sync python -m cli.perf_llm --help

# 仅后端运行依赖
uv sync --locked --no-default-groups --group backend
```

`uv sync` 会精确同步当前环境，切换到 CLI-only 会移除后端和开发分组依赖；不要在正在运行后端的环境中切换分组。`uv run --no-sync` 使用已同步的环境，不重新安装默认分组；执行测试前先运行完整的 `uv sync --locked`。

需要分开的本地环境时，可设置进程环境变量 `UV_PROJECT_ENVIRONMENT`，例如将 CLI 环境放在 `.venv-cli`。环境文件与运行数据仍遵循各自目录规则，uv 不代替 `cli/.env` 的加载逻辑。

## 前端：pnpm

安装 [pnpm](https://pnpm.io/installation) **10.28.2**，与 `packageManager` 字段保持一致。使用 Node.js 22.12+ 或 24+。在 `frontend/` 中运行：

```bash
pnpm install --frozen-lockfile
pnpm run dev
pnpm run build
pnpm run test:dashboard
pnpm run test:playground
pnpm run test:selection
```

前端直接依赖固定为此次转换前的版本，避免安装时由 `latest` 意外引入升级。只允许 esbuild 与 Tailwind Oxide 的依赖构建脚本；其他依赖需要执行脚本时须明确审查并更新允许列表。

## 更新依赖

- 修改 Python 分组后执行 `uv lock`，随后 `uv sync --locked` 并跑测试。
- 修改前端依赖后执行 `pnpm install` 更新锁文件，再执行锁定安装、构建和测试。
- 更新工具版本时同步 `pyproject.toml`、`frontend/package.json`、Dockerfile 和文档。

Docker 仅安装后端运行分组；uv 与 pnpm 安装都校验锁文件。镜像构建细节见 [Docker 部署](../docker/README.md)。
