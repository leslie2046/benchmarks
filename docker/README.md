# Docker 部署

部署文件集中在本目录。以下命令在项目根目录执行；脚本按自身位置定位 Compose，从其他目录调用也可以。

## 环境要求

- Docker Engine / Docker Desktop 和 Docker Compose v2（`docker compose`）；Windows 使用 Linux 容器模式。
- 构建机器能访问基础镜像、PyPI 和 npm，首次构建需要联网。镜像内固定 uv 0.12.22、pnpm 10.28.2；Python 使用 `uv sync --locked --no-default-groups --group backend`，前端使用 `pnpm install --frozen-lockfile`。
- 宿主机端口 8080 可用；本机前端预览若占用该端口，需先停止或调整 Compose 的端口映射。

无需根目录 `.env`。模型与 API Key 在 Web 控制台配置。CLI 可选配置为 `cli/.env`，不复制进镜像，见 [CLI 文档](../docs/cli-reference.md)。

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

`build` 只构建 `prismlab-api:local`、`prismlab-web:local` 两个镜像；`start` 使用已有镜像后台启动，不自动构建。修改源码后依次重新执行两个脚本。

打开 **http://localhost:8080**。容器启动成功不等于服务已就绪：`depends_on` 仅控制创建顺序，不等待 API 健康检查。短暂 502 可稍后刷新，持续失败请检查日志。

```bash
docker compose -f docker/compose.yaml ps
docker compose -f docker/compose.yaml logs -f
docker compose -f docker/compose.yaml down
```

也可直接执行 `docker compose -f docker/compose.yaml up --build -d`。后端仅启动一个 worker，不要扩容多个 API 同时写同一 SQLite 工作区。API 端口不直接暴露到宿主机，通过 Nginx 的 `/api/` 转发。

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

Windows 对应执行 `.\docker\start.ps1`。离线启动不需要源码，但必须保留 Compose 和启动脚本，不要执行 `up --build`。归档仅包含镜像，**不含数据库、密钥、报告或运行时配置**；打包与目标机器必须使用兼容的 CPU 架构，脚本不自动转换架构。

## 持久化目录

| 部署方式 | 宿主机默认目录 | 容器内目录 |
| --- | --- | --- |
| 源码部署 | `backend/volumes/` | 不适用 |
| Docker 部署 | `docker/volumes/` | `/app/volumes` |

两套工作区独立，不自动共享。Compose 的 `./volumes` 相对 Compose 文件解析；源码部署可用进程环境变量 `BENCHMARK_DATA_DIR` 指定其他位置。Docker 自定义宿主机位置时修改挂载源，通常保持容器内路径不变。

```text
volumes/
  runs.sqlite3       # 模型、凭据、计划、运行记录、系统配置及 AI 报告
  secret.key         # 未通过环境变量提供主密钥时生成
  reports/           # 场景 JSON 报告
```

两个目录均被 Git 忽略且排除在镜像构建上下文之外。`down` 不删除宿主机绑定目录。备份前停止后端，整套备份数据库、密钥和报告；运行中的 SQLite 可能包含 WAL/SHM 文件，不能只复制正在写入的数据库。外部提供的 `BENCHMARK_SECRET_KEY` 需另行保存，丢失匹配密钥将无法解密凭据。

## 可选配置与安全

后端不读取 `.env`。`BENCHMARK_SECRET_KEY`、`BENCHMARK_CORS_ORIGINS` 等通过 API 服务的 `environment` 或 Compose override 注入。使用 override 时需手动传两个 `-f` 参数，当前脚本只加载基础 Compose。请妥善保管加密主密钥，不要随意更换。

控制台没有内置登录；公网部署前应配置认证、HTTPS 和访问限制。脚本不配置这些安全措施。
