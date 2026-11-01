# Docker 部署

部署文件集中在本目录。以下命令在项目根目录执行；脚本按自身位置定位 Compose，从其他目录调用也可以。

## 环境要求

- Docker Engine / Docker Desktop 和 Docker Compose v2（`docker compose`）；Windows 使用 Linux 容器模式。
- 构建机器能访问基础镜像、PyPI 和 npm，首次构建需要联网。镜像内固定 uv 0.12.22、pnpm 10.28.2；Python 使用 `uv sync --locked --no-default-groups --group backend`，前端使用 `pnpm install --frozen-lockfile`。
- 宿主机端口 8080 可用；本机前端预览若占用该端口，需先停止或调整 Compose 的端口映射。

无需根目录 `.env`；可通过 `docker/.env` 自定义管理员认证及 PostgreSQL 密码和连接，见下文及 [数据库配置](../docs/postgresql.md)。模型与 API Key 在 Web 控制台配置。CLI 可选配置为 `cli/.env`，不复制进镜像，见 [CLI 文档](../docs/cli-reference.md)。

## 构建与启动

Linux / macOS（Bash）：

```bash
bash docker/build.sh
bash docker/start.sh
```

Windows PowerShell：

```powershell
.\docker\build.ps1
.\docker\start.ps1
```

`build` 构建 `prismlab-api:local`、`prismlab-web:local` 两个应用镜像；`start` 启动应用及 PostgreSQL，不自动构建，首次联网启动会拉取 `postgres:16`。修改源码后依次重新执行两个脚本。

打开 **http://localhost:8080**。容器启动成功不等于服务已就绪：API 会等待数据库健康，但 Web 的 `depends_on` 不等待 API 健康检查。短暂 502 可稍后刷新，持续失败请检查日志。

```bash
docker compose -f docker/compose.yaml ps
docker compose -f docker/compose.yaml logs -f
docker compose -f docker/compose.yaml down
```

也可直接执行 `docker compose -f docker/compose.yaml up --build -d`。后端仅启动一个 worker 和一个 API 实例，避免多个进程重复调度测试计划。数据库已使用 PostgreSQL。API 端口不直接暴露到宿主机，通过 Nginx 的 `/api/` 转发。

## 离线镜像包

导出镜像（父目录须已存在；已有同名归档会被 Docker 覆盖）：

```bash
bash docker/build.sh --archive /path/to/prismlab-images.tar
```

```powershell
.\docker\build.ps1 -Archive 'D:\packages\prismlab-images.tar'
```

目标机器保留 `docker/` 和相邻的 `audio/` 目录结构，然后：

```bash
docker image load --input /path/to/prismlab-images.tar
bash docker/start.sh
```

Windows 对应执行 `.\docker\start.ps1`。离线启动不需要源码，但必须保留 Compose 和启动脚本，不要执行 `up --build`。归档包含两个应用镜像与 `postgres:16`，**不含数据库、密钥、报告或运行时配置**；打包与目标机器必须使用兼容的 CPU 架构，脚本不自动转换架构。

## 持久化目录

| 部署方式 | 宿主机默认目录 | 容器内目录 |
| --- | --- | --- |
| 源码部署 | `backend/volumes/` | 不适用 |
| Docker 部署 | `docker/volumes/` | `/app/volumes` |

两套工作区独立，不自动共享。Compose 的 `./volumes` 相对 Compose 文件解析；源码部署可用进程环境变量 `BENCHMARK_DATA_DIR` 指定其他位置。Docker 自定义宿主机位置时修改挂载源，通常保持容器内路径不变。

```text
volumes/
  secret.key         # 未通过环境变量提供主密钥时生成
  reports/           # 场景 JSON 报告
```

两个文件目录均被 Git 忽略且排除在镜像构建上下文之外。应用结构化数据保存在 PostgreSQL 的 `postgres_data` 命名卷中。`down` 不删除宿主机绑定目录或命名卷；**不要使用 `down -v`，否则会删除数据库卷**。备份前停止后端，用 `pg_dump` 备份数据库，同时保存密钥和报告；迁移已有 SQLite 工作区见 [迁移指南](../docs/postgresql.md)。外部提供的 `BENCHMARK_SECRET_KEY` 需另行保存，丢失匹配密钥将无法解密凭据。

## 可选配置与安全

### 管理员密码

需要独立登录页面、GitHub 或 OIDC 时，设置 `AUTH_MODE=app`，参见 [登录与身份提供方配置](../docs/authentication.md)。下文 Nginx Basic Auth 是默认 `AUTH_MODE=basic` 的兼容模式；app 模式由 API 校验密码，不再弹出浏览器认证框。

Web 容器支持通过环境变量启用 Nginx HTTP Basic Auth，保护整个控制台和 `/api/`。这是单管理员的访问保护，不是应用内用户系统或 GitHub 登录。

首次配置可复制 `docker/.env.example` 为 `docker/.env`；已有文件只追加或修改以下两项，**不要覆盖现有数据库密码**：

```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD='替换为你自己的随机强密码'
```

`ADMIN_USERNAME` 默认 `admin`，仅允许英文字母、数字及 `_.@-`。`ADMIN_PASSWORD` 不允许换行，最长 72 字节（bcrypt 限制）。`.env` 中使用单引号可避免密码中的 `$` 被 Compose 插值；保留该文件的私密权限（Linux/macOS 可执行 `chmod 600 docker/.env`）。环境变量可被有 Docker 管理权限的用户查看，不要输出或分享完整的 `docker compose config` / `docker inspect`。

首次安装此功能须重新构建 Web 镜像；后续更换密码仅需重建 Web 容器，无需重新构建镜像或重启数据库：

```bash
docker compose -f docker/compose.yaml build web
docker compose -f docker/compose.yaml up -d --no-build --force-recreate web
```

容器每次启动将密码转换为 bcrypt 哈希，保存在容器内 `/etc/nginx/admin.htpasswd`，不修改宿主机密码文件，也不把密码写入镜像。修改 `.env` 后仅执行 `restart` 不会加载新环境变量，必须重建容器。使用自定义 Compose override 的部署应使用原有管理命令或全部原有 `-f` 参数，不要用基础命令覆盖生产部署。

未设置或清空 `ADMIN_PASSWORD` 时，优先沿用挂载的 `/etc/nginx/htpasswd`；没有该文件时保持开发环境无认证，并输出警告。**公网部署必须设置密码或保留有效认证文件**。自定义 Nginx 配置须在 `server` 中使用 `include /etc/nginx/admin-auth.conf;` 代替原有 `auth_basic` / `auth_basic_user_file`，且不要把 Basic Auth 的 `Authorization` 请求头转发给 API（参考本目录 `nginx.conf`）。API 端口不要直接暴露，否则可以绕过 Web 认证。

### 其他安全配置

后端不读取 `.env`。`DATABASE_URL` 在 Compose 中配置；`BENCHMARK_SECRET_KEY`、`BENCHMARK_CORS_ORIGINS` 等通过 API 服务的 `environment` 或 Compose override 注入。使用 override 时需手动传两个 `-f` 参数，当前脚本只加载基础 Compose。请妥善保管加密主密钥，不要随意更换。

app 模式提供共享工作区的用户身份与服务端会话，但不提供多租户或细粒度角色。公网仍需 HTTPS 和访问限制，任何登录方式都不能替代 HTTPS。

## 认证验证

Web 镜像对 JS、CSS 和 JSON 启用 gzip，带哈希的 `/assets/` 文件长期缓存；入口 HTML 需重新验证。认证接口不压缩，API 不启用代理缓存，不缓存跨空间数据。首页接口独立加载，模型目录或配置接口缓慢/失败不会阻塞已返回的运行和计划数据。

构建 Web 镜像后，可运行真实 Nginx 集成测试。测试使用独立临时容器和仅本机可访问的随机端口，不访问生产数据库或修改生产密码文件：

```bash
TEST_WEB_IMAGE=prismlab-web:local uv run --no-sync python -m unittest tests.test_docker_auth -v
```

未设置 `TEST_WEB_IMAGE` 时，常规 Python 测试会跳过此组 Docker 集成测试。
