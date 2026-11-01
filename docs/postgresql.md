# PostgreSQL 配置与 SQLite 迁移

后端仅使用 PostgreSQL，不再读写 SQLite。数据库保存模型部署配置、加密凭据、测试计划、运行记录、系统设置和 AI 报告；`BENCHMARK_DATA_DIR` 仍用于 `secret.key` 与场景报告文件。支持 PostgreSQL 15+，Compose 默认使用 PostgreSQL 16。

启用 `AUTH_MODE=app` 时还会自动创建 `auth_users`、`auth_sessions`、`auth_flows`，保存身份、可撤销会话和一次性授权流程；原五类业务表不变。认证密钥 `auth-session.key` 也需备份，详见 [登录配置](authentication.md)。

## 源码运行

可使用已有 PostgreSQL，或启动仅监听本机的实例：

```bash
docker run -d --name prismlab-postgres \
  -p 127.0.0.1:5432:5432 \
  -e POSTGRES_DB=prismlab -e POSTGRES_USER=prismlab -e POSTGRES_PASSWORD=prismlab \
  -v prismlab-postgres:/var/lib/postgresql/data postgres:16
export DATABASE_URL='postgresql://prismlab:prismlab@127.0.0.1:5432/prismlab'
uv sync --locked
uv run --no-sync python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

等待数据库就绪后启动 API。默认连接 URL 与上例一致；数据库和账户须预先创建，后端启动时自动建表。数据库不可连接时 API 启动失败，不回退 SQLite。后端不自动读取 `.env`，请使用进程环境变量；systemd 部署需在服务环境中设置 `DATABASE_URL`。URL 中的密码包含特殊字符时须进行 URL 编码，也可使用 psycopg 支持的 libpq conninfo 字符串。

上例密码仅用于本机开发。部署时更换强密码、限制网络访问，远程连接按环境要求配置 TLS。保留单 API 实例、单 worker：PostgreSQL 行锁保护同一运行记录的 AI 报告并发，但不会将内存中的计划调度和任务管理变成分布式服务。

## Docker Compose

`docker/compose.yaml` 内含 `db` 服务、健康检查和 `postgres_data` 命名卷；API 等待数据库健康后启动。数据库不映射到宿主机端口。

默认无需 `.env`。自定义密码可将 `docker/.env.example` 复制为 `docker/.env`，同时修改 `POSTGRES_PASSWORD` 和 `DATABASE_URL` 中的密码，后者须 URL 编码。Compose 读取此文件仅用于变量替换，后端本身仍不读取环境文件。更换数据库镜像的初始化环境变量不会修改已有卷中的账户密码，应使用 PostgreSQL 管理命令修改。

```bash
bash docker/build.sh
bash docker/start.sh
```

使用外部数据库时设置 `DATABASE_URL`。基础 Compose 仍会启动内置数据库，可通过独立部署配置移除 `db` 服务及 API 对其的依赖。

## 迁移已有 SQLite 数据

迁移不会自动执行。先停止旧后端，确保没有正在执行的任务，再备份原 SQLite 数据库、匹配的 `secret.key`（或 `BENCHMARK_SECRET_KEY`）以及报告目录。不要更换密钥。

准备空 PostgreSQL 数据库，然后执行：

```bash
export DATABASE_URL='postgresql://prismlab:prismlab@127.0.0.1:5432/prismlab'
uv run --no-sync python -m backend.migrate_sqlite backend/volumes/runs.sqlite3
```

Docker 工作区迁移（先构建新镜像）：

```bash
docker compose -f docker/compose.yaml stop api
docker compose -f docker/compose.yaml up -d --wait db
docker compose -f docker/compose.yaml run --rm --no-deps api \
  python -m backend.migrate_sqlite /app/volumes/runs.sqlite3
docker compose -f docker/compose.yaml up -d --no-build
```

工具以只读方式读取 SQLite，并在一个 PostgreSQL 事务中导入五类表；目标表已有任何数据就拒绝导入，错误会整体回滚，不覆盖原有数据。较旧工作区缺少系统设置或 AI 报告表时可迁移；三张核心表必须存在。成功后输出各表导入行数。原 SQLite 文件保留不变；切换后新数据只写入 PostgreSQL，旧文件不再同步。

迁移期间保持 API 停止，迁移成功后设置同一 `DATABASE_URL` 并启动 API。继续使用原密钥和报告目录；从源码部署切换到 Docker 时须复制这些文件，报告中的原路径也应保持可访问。启动恢复逻辑会将旧工作区未完成的运行记录和 AI 报告标记为失败。确认数据和凭据可读取后，再按备份策略归档旧文件。

## 备份与测试

停止 API 后，用 `pg_dump --dbname="$DATABASE_URL" --format=custom --file=prismlab.dump` 备份数据库，同时备份密钥和报告。恢复使用 `pg_restore` 导入空数据库。Docker 可通过 `docker compose -f docker/compose.yaml exec -T db pg_dump -U prismlab -d prismlab -Fc > prismlab.dump` 导出。`docker compose down` 保留数据库卷，**`down -v` 会删除数据库卷**。

数据库测试必须使用独立测试数据库，账户需要创建和删除 schema 的权限：

```bash
createdb --maintenance-db="$DATABASE_URL" prismlab_test
export TEST_DATABASE_URL='postgresql://prismlab:prismlab@127.0.0.1:5432/prismlab_test'
uv run --no-sync python -m unittest discover -s tests
```

测试为每个临时工作区创建独立 schema，并在结束后删除，不使用应用的 `DATABASE_URL`。未配置 `TEST_DATABASE_URL` 时，数据库相关测试会明确跳过，其余测试正常运行。
