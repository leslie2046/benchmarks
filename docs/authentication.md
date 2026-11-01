# 登录、GitHub OAuth 与 OIDC

PrismLab 支持独立登录页面、管理员密码、GitHub OAuth 及一个通用 OIDC 提供方。GitHub 网站账号使用 **OAuth 2.0**，并非 OIDC；GitHub Actions 的 OIDC 令牌不用于网站用户登录。需要严格通过 OIDC 接入 GitHub 时，可在 Keycloak、Authentik 或 Dex 等身份代理配置 GitHub，再连接代理的 OIDC 接口。

## 启用登录页面

编辑 `docker/.env`，保留原有数据库设置：

```dotenv
AUTH_MODE=app
AUTH_PUBLIC_URL=https://prismlab.example.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD='替换为随机强密码'
```

`AUTH_PUBLIC_URL` 是浏览器使用的固定站点地址，不带路径、查询或片段，用于生成回调、配置 Cookie Secure 属性及检查变更请求的 Origin。公网必须使用 HTTPS；本机或可信局域网试用可显式使用 `http://localhost:8080` 或 `http://192.168.0.188:8441`。域名或端口改变时同步更新此变量及提供方的回调地址。Vite 开发时通过代理访问 API，配置为 Vite 的站点地址（通常 `http://localhost:5173`）。

同一部署有多个入口时，`AUTH_PUBLIC_URL` 应设为主要访问地址；其余可信入口可放在 `AUTH_ALLOWED_ORIGINS`，以逗号分隔，例如 `http://192.168.0.188:8441,http://localhost:8441`。每项必须是完整的协议、主机和端口（非默认端口不可省略），不能带路径或通配符。未列入名单的 Origin 仍被拒绝，不根据请求的 Host 或转发头自动放行。不要添加不受控制的域名。OAuth/OIDC 回调仍固定使用 `AUTH_PUBLIC_URL`，请从该主要地址开始单点登录。HTTPS 主站的 Secure Cookie 不支持 HTTP 别名，建议所有入口使用 HTTPS。

登录返回 403 且错误码为 `origin_not_allowed` 时，表示浏览器的实际地址与上述配置不一致，并非密码错误。核对协议、地址及端口，修改环境变量后重建 API 容器；不要关闭 Origin 或 CSRF 校验。

首次安装重新构建两个应用镜像，再重建 API 和 Web 容器，不必重建数据库：

```bash
docker compose -f docker/compose.yaml build api web
docker compose -f docker/compose.yaml up -d --no-build api web
```

后续仅修改环境变量时执行第二条命令，`restart` 不会加载新变量。使用生产 override 的部署须保留原有全部 `-f` 参数或使用原生产管理脚本，不要用基础 Compose 覆盖生产部署。源码启动时通过进程环境变量配置；后端不自动读取 `.env`。

app 模式下 Web 关闭 Basic Auth 弹框，由后端保护会话及整个业务 API。API 与 Web 必须使用相同模式，且不能将新 Web 与旧的未保护 API 混用。配置缺失或不完整时拒绝启动，不会静默开放访问。`ADMIN_PASSWORD` 留空可关闭密码登录，但至少需要一个配置完整的身份提供方。

**所有能通过已配置 GitHub 或 OIDC（包括 GitLab）提供方完成登录的用户均可使用独立个人空间，无需逐个配置用户 ID、用户名或邮箱。** 这不是免登录访问；未登录用户、伪造令牌和无效授权流程仍被拒绝。个人与团队数据相互隔离，团队通过指定用户邀请和 Owner/管理员/普通成员三级权限共享；参见[空间与权限](tenancy.md)。历史共享数据仅归本地管理员个人空间。

默认 `AUTH_MODE=basic` 保留旧部署行为：Web 使用环境密码或挂载的密码文件，应用不要求会话，前端不显示登录页。该模式无密码且无文件时仍是无认证开发模式，不可公开部署。API 不应直接暴露到公网。

## GitHub 配置

在 GitHub **Settings → Developer settings → OAuth Apps → New OAuth App** 创建应用：

- Homepage URL：`https://prismlab.example.com`
- Authorization callback URL：`https://prismlab.example.com/api/auth/github/callback`

在服务端环境配置：

```dotenv
GITHUB_CLIENT_ID=你的OAuthAppClientID
GITHUB_CLIENT_SECRET='你的OAuthAppClientSecret'
```

任意 GitHub 用户完成此应用的 OAuth 授权后即可登录，无需查询或填写用户数字 ID。应用仍通过 GitHub API 验证用户身份，不接受浏览器自报的 ID 或用户名。

重建 API 容器后，登录页 GitHub 按钮自动启用。授权范围仅 `read:user`，身份从 GitHub API 获取，不接受前端自报的用户信息。提供方令牌仅用于本次身份获取，不写入数据库或浏览器存储。

## 通用 OIDC 配置

在提供方创建机密 Web 客户端，启用 Authorization Code 和 PKCE S256，注册回调：

```text
https://prismlab.example.com/api/auth/oidc/callback
```

```dotenv
OIDC_PROVIDER_NAME='企业账号'
OIDC_ISSUER_URL=https://sso.example.com/realms/prismlab
OIDC_CLIENT_ID=prismlab
OIDC_CLIENT_SECRET='你的客户端密钥'
```

Issuer 必须使用 HTTPS，与 discovery 及 ID Token 中的 `iss` **完全一致**，包括末尾 `/`。系统通过 issuer 对应的 `/.well-known/openid-configuration` 发现端点，验证非对称签名、issuer、audience、有效期和 nonce；拒绝无签名或对称签名的 ID Token。

该提供方任何能完成授权、并返回有效 ID Token 的用户均可登录，不要求指定 sub 或验证邮箱。`sub` 仍须是有效非空字符串，由系统从已验证的令牌读取。身份由 issuer 与 sub 联合标识，不跨 issuer 关联用户，也不按邮箱自动合并本地、GitHub 或 OIDC 账号；邮箱仅用于显示，不作为受信任的账号关联依据。

## GitLab SSO 配置

GitLab 使用上面的通用 OIDC 入口，不是 `GITHUB_*` 入口；可与 GitHub 同时启用。GitLab.com 的 discovery 地址为 `https://gitlab.com/.well-known/openid-configuration`，issuer 为 `https://gitlab.com`，支持本应用使用的 RS256 和客户端密钥认证。

1. 在 GitLab 打开个人设置的 **Applications**，创建 OAuth 应用（GitLab.com 可访问 `https://gitlab.com/-/user_settings/applications`）。
2. 名称填 `PrismLab`，Redirect URI 填 `https://prismlab.example.com/api/auth/oidc/callback`，与实际 `AUTH_PUBLIC_URL` 一致。
3. 选择 **Confidential**，勾选 `openid`、`profile`、`email`，不需要 `api`、仓库读写或管理员权限。
4. 保存 Application ID 和 Secret，在私有环境文件设置：

```dotenv
OIDC_PROVIDER_NAME=GitLab
OIDC_ISSUER_URL=https://gitlab.com
OIDC_CLIENT_ID=你的GitLabApplicationID
OIDC_CLIENT_SECRET='你的GitLabSecret'
```

无需查询 GitLab 用户 ID 或填写 sub；所配置 GitLab 实例中任何能完成该应用授权的用户都可访问。没有公开邮箱或没有 `email_verified=true` 不影响登录，系统依然验证身份提供方签发的 ID Token。

自建 GitLab 将 issuer 改为自身的 HTTPS 地址，并确认与 discovery 的 `issuer` 完全一致，API 容器能访问其 discovery、token 和 JWKS 端点且信任证书。无需添加 GitLab 作为 `AUTH_ALLOWED_ORIGINS`；该变量只允许 PrismLab 自身的访问入口，不用于身份提供方域名。

保留原有 `AUTH_MODE=app`、管理员和数据库配置，只新增或修改身份提供方变量。配置完成，确认没有正在执行的压测后，使用原生产管理脚本重建 API 容器加载环境变量；基础 Compose 部署可执行 `docker compose -f docker/compose.yaml up -d --no-deps --no-build --force-recreate api`。如果已部署的镜像包含此功能，修改配置不需重新构建镜像或重启数据库。登录页按钮将显示“使用 GitLab 登录”。

官方参考：[GitHub OAuth App](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app)、[GitLab OIDC 提供方](https://docs.gitlab.com/integration/openid_connect_provider/)。

## 会话和授权边界

- `/login` 是独立登录页；未登录不能读取业务 API 或 API 文档。`/api/health` 仅提供最小存活信息供健康检查。
- `auth_users` 保存身份，`auth_sessions` 保存 24 小时会话，数据库只保存随机令牌的 SHA-256 摘要。浏览器使用 HttpOnly、SameSite=Lax Cookie；HTTPS 站点使用 Secure。
- 退出立即撤销服务端会话，重新登录轮换当前令牌，每个身份最多 10 个会话。修改密码、站点地址、提供方配置或签名密钥后旧会话失效。
- OAuth/OIDC 使用 PKCE、state 及 nonce（OIDC）。流程与浏览器绑定，`auth_flows` 保证 state 十分钟过期且单次消费。登录成功只回到本应用，不接受任意外部回跳。
- 修改请求要求会话绑定的 `X-CSRF-Token`，前端自动添加，同时拒绝其他 Origin 的变更请求。API 客户端须登录、保留 Cookie，并从登录响应或 `/api/auth/session` 获取 CSRF Token。
- 本地登录每客户端地址每分钟最多 10 次尝试。默认单 API 实例；反向代理后可能共用限流地址，不应无条件信任客户端转发头。
- 所有成功登录的账号默认仅访问本人个人空间；团队数据需要接受指定账号邀请，并遵守该团队角色权限。平台管理员不默认具有团队数据访问权。租户隔离与备份边界见[空间与权限](tenancy.md)。

旧版 `GITHUB_ALLOWED_IDS`、`GITHUB_ALLOWED_USERS`、`OIDC_ALLOWED_SUBJECTS`、`OIDC_ALLOWED_EMAILS` 已移除，不再读取或限制账号。升级后可以从私有 `.env` 删除这些项；保留旧项也不会生效。`AUTH_ALLOWED_ORIGINS` 则仍是必要的站点入口保护，与用户身份名单无关，不能为了开放用户登录而清空或绕过它。

## 密钥、备份和验证

`AUTH_SESSION_SECRET` 可设为至少 32 字符的随机值；否则在数据目录生成权限 600 的 `auth-session.key`。它与现有 API Key 的加密主密钥独立，应连同 PostgreSQL、`secret.key` 及报告备份，不要互相替换。

保持配置私密，不提交、不打包进镜像或发送给前端。`.env` 秘密建议用单引号保留 `$`；Docker 管理员仍能查看容器环境，不要公开完整的 `docker inspect` 或 `docker compose config`。HTTP 不加密密码和 Cookie，公网必须加 HTTPS，试用弱密码应及时更换。

设置独立 `TEST_DATABASE_URL` 后执行 `uv run --no-sync python -m unittest tests.test_auth -v`。测试使用模拟 GitHub/OIDC 提供方，覆盖任意有效身份登录、无效身份拒绝、会话、CSRF、撤销、限流、state/PKCE 及 ID Token 校验；模拟测试不等于真实提供方联调。

按钮显示“未配置”时检查 API 环境；回调失败检查站点地址、注册的回调及客户端密钥。错误页不回显上游令牌或密钥。旧 Basic Auth 不再用于 app 模式，可在隐私窗口检查新登录页。

## 昵称与头像

登录后的“账户”页可编辑昵称并上传/移除头像。资料保存在 PostgreSQL `auth_users` 的独立 `nickname`、`avatar`、`avatar_version` 字段；启动时幂等补充字段，旧账号默认沿用身份提供方名称与首字符头像。重新登录仅更新上游用户名和名称，不覆盖已设置的昵称或头像。邀请仍使用登录来源和准确用户名，不使用昵称。

`PATCH /api/auth/profile` 仅接受当前账号的 `nickname`（1–80 字符，去除首尾空白，不接受控制字符）。`PUT /api/auth/profile/avatar` 接受原始 PNG/JPEG/WebP 请求体，最大 1 MB；服务端校验实际图片、限制尺寸，重新编码为 256×256 PNG 并清除元数据。`DELETE /api/auth/profile/avatar` 恢复默认首字符头像。所有写入要求登录会话、可信 Origin 与 CSRF；不接受用户 ID、角色或任意头像 URL。

头像地址仅允许本人或同一有效团队的成员读取；不能通过知道头像 URL 跨账号空间浏览。账号资料不随空间切换变化，不影响团队 Owner、管理员或普通成员权限。详情及限制见 [多租户说明](tenancy.md)。测试增加 `tests.test_profile`，须使用独立 PostgreSQL 测试数据库。
