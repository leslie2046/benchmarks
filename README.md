# PrismLab

AI model testing & analysis — benchmark your services, compare performance, and understand the results.

[简体中文](README_zh-Hans.md) · [Quick start](#quick-start) · [Workspaces](#accounts-and-workspaces) · [CLI](#command-line-testing) · [Documentation](#documentation)

PrismLab connects to services you already run or subscribe to. It does not host models. Use the web console for interactive testing and repeatable test plans, or the CLI for lightweight concurrency benchmarks.

## What you can test

| Test type | Workload | Key metrics |
| --- | --- | --- |
| LLM | Streaming text generation | TTFT, TPOT, tokens/s, request latency |
| Embedding | Text-to-vector requests | Latency, QPS, success rate |
| Reranker | Query and candidate documents | Latency, QPS, success rate |
| Audio | Speech-to-text transcription | Latency, QPS; RTF when audio duration is known |
| Dify Retrieve | Knowledge base retrieval | Latency, QPS, success rate |
| Dify Chat | Streaming application responses | First-message latency, total latency, success rate |

The console includes model search and type filters, YAML-driven LLM parameters, scheduled test plans, run history, comparison charts, and manually generated AI performance reports. It supports English, Simplified Chinese, and light/dark themes.

- **Sign-in:** local password, GitHub OAuth, and GitLab or another OIDC provider.
- **Isolated workspaces:** private personal spaces and shared teams with Owner, administrator, and member roles.
- **Collaboration:** invite specific existing users, switch spaces, and customize your nickname and avatar.
- **Responsive data loading:** paginated lists, independently loaded home-page data, and compressed responses in the Docker deployment.

The web application uses **PostgreSQL**; SQLite is supported only as a source for the one-time migration tool. Docker Compose includes PostgreSQL 16. Redis is not required.

Provider presets include Moonshot (Kimi), Qwen, MiniMax, Volcengine Ark, DeepSeek, SiliconFlow, Xinference, vLLM, Alibaba Cloud, Xunfei MaaS, and Huawei Cloud. Qwen is a separate provider from Alibaba Cloud Model Studio; existing configurations are unchanged. Available test types and model discovery depend on the provider and deployed model; not every provider supports every type. See [provider setup](docs/model-discovery.md#新增云供应商).

## Quick start

Choose **Docker** for deployment or **local development** to modify the code. You need a reachable model service or Dify instance for actual testing.

### Option A: Docker

Prerequisites: Git, Docker, and Docker Compose v2 (`docker compose`). Windows Docker Desktop must use Linux containers. Keep host port 8080 available.

```bash
git clone https://github.com/leslie2046/PrismLab.git
cd PrismLab
```

Copy the example configuration:

```bash
cp docker/.env.example docker/.env
```

For a local deployment with a sign-in page and isolated workspaces, edit these entries in `docker/.env`:

```dotenv
AUTH_MODE=app
AUTH_PUBLIC_URL=http://localhost:8080
ADMIN_USERNAME=admin
ADMIN_PASSWORD='replace-with-a-strong-password'
```

Then build and start the services:

```bash
docker compose --env-file docker/.env -f docker/compose.yaml up --build -d
```

Open **http://localhost:8080**, sign in with the configured local account, and select a workspace. Configure model services and credentials inside that space. For a public deployment, set `AUTH_PUBLIC_URL` to the actual HTTPS site address and replace the example database password in both `POSTGRES_PASSWORD` and `DATABASE_URL`; URL-encode the password in the latter. See [authentication setup](docs/authentication.md) to enable GitHub and GitLab SSO or disable local password login.

Compose reads the explicitly supplied environment file for variable substitution; the backend does not load `.env` files itself. Without configuration, the default `basic` mode has no sign-in page or tenant isolation and, without a password or password file, is unauthenticated. Do not expose that development setup publicly.

Useful deployment commands:

```bash
docker compose --env-file docker/.env -f docker/compose.yaml logs -f
docker compose --env-file docker/.env -f docker/compose.yaml up --build -d    # Rebuild after pulling updates
docker compose --env-file docker/.env -f docker/compose.yaml down           # Stop the services; retain data
```

PostgreSQL data is stored in the Compose `postgres_data` named volume; encryption/session keys and report files are stored in the host's `docker/volumes/` directory. Back up both before upgrading. **Do not use `down -v` unless you intend to delete the database volume.** See [Data and security](#data-and-security).

For separate build/start steps, use `bash docker/build.sh` then `bash docker/start.sh` on Linux/macOS, or `.\docker\build.ps1` then `.\docker\start.ps1` in Windows PowerShell. The start script uses existing images and does not build them. See the [Docker deployment guide](docker/README.md) for offline image packaging and startup troubleshooting.

Inside Docker, `127.0.0.1` refers to the container, not your host. For a model running on the host, use an address reachable from the API container (for example, `host.docker.internal` on Docker Desktop), and check service binding and firewall rules.

### Option B: Local development

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) **0.12.22** and [pnpm](https://pnpm.io/installation) **10.28.2**, with Node.js 22.12+ (or 24+). Clone the repository as above. uv creates `.venv` and selects Python 3.12 automatically; manual virtual-environment activation is unnecessary.

**Terminal 1 — backend**, from the repository root:

```bash
uv sync --locked
# Start PostgreSQL and configure DATABASE_URL first; see docs/postgresql.md.
export DATABASE_URL=postgresql://prismlab:prismlab@127.0.0.1:5432/prismlab
uv run --no-sync python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — frontend**:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run dev --host 127.0.0.1
```

Open **http://localhost:5173**. Vite forwards `/api` requests to the backend on port 8000. If Vite selects another port, use the URL printed in its terminal.

Application data is stored in PostgreSQL via `DATABASE_URL`; local encryption keys and report files default to `backend/volumes/`. See [PostgreSQL setup and SQLite migration](docs/postgresql.md). Keep **one API worker / instance** because the scheduler and benchmark subprocesses remain process-local.

Local development defaults to unauthenticated `basic` mode. To develop the sign-in and workspace flow, set `AUTH_MODE=app`, `AUTH_PUBLIC_URL=http://localhost:5173`, and a strong `ADMIN_PASSWORD` in the backend process environment before starting it. The public URL must match the frontend address, including its port.

## Accounts and workspaces

In `app` mode, every account gets a private personal workspace. Each fresh login opens a space chooser; use the account menu to switch spaces or create a team. Models, credentials, Dify connections, plans, runs, AI reports, and the default analysis LLM belong to the selected space. A new team starts empty; personal configurations are not automatically shared.

| Team role | Permissions |
| --- | --- |
| Owner | Full team configuration, member roles/removal, and team deletion |
| Administrator | Use models and tests, manage configurations, invite and remove ordinary members |
| Member | Use team models, create/edit/run tests, and generate AI reports; model/Dify configuration and space settings are read-only |

Members cannot add, edit, or delete providers or change space settings. Only the current team's Owner sees the **Team management** menu; personal spaces do not have team management. Ownership transfer is not supported. The local `admin` account does not automatically gain access to other users' or teams' data.

Invitations target a specific account: the recipient must sign in once first, then the inviter selects their login provider and exact username—not their nickname, profile URL, or numeric ID. The recipient accepts under **Received invitations**. There are no public invitation links or invitation emails. See [workspace isolation and permissions](docs/tenancy.md) for detailed role and invitation rules.

GitHub uses **OAuth 2.0**; GitLab uses the generic **OIDC** connection. Any valid user of a configured provider can sign in without a user-ID allowlist, but cannot access a team without membership. Different login providers remain separate identities and are not merged by email. See [GitHub, GitLab, and OIDC setup](docs/authentication.md).

## Your first test

1. **Model providers:** select a built-in provider, add a model and configure its endpoint and credentials, or fetch and select models where supported. Save the configuration.
2. **Playground:** select a test type and configured model, then send one request to verify the setup. This makes a real service call but does not create a test plan or run record.
3. **Test plans:** create a plan with your inputs, target models, concurrency levels, and request count. Start small, such as concurrency 1 and 5 requests. Saving a new plan does not start it; start it when ready.
4. **Run history:** inspect progress, failures, and results. Each execution creates a separate run record.
5. **Analysis dashboard:** compare concurrency levels or repeated runs of the same plan. Use comparable inputs and generation settings for meaningful comparisons.

For Dify, use **Dify configuration** instead of Model providers. The default service URL is `https://api.dify.ai`; replace it for self-hosted instances. Retrieval requires a knowledge base ID and Dataset API Key; Chat uses an application API Key. The refresh button retrieves the resource name without saving. Plans and Playground reuse the knowledge base ID from the configuration.

**Testing calls real APIs and may incur charges.** Verify one request before increasing concurrency or enabling recurring schedules.

## LLM Playground and AI reports

### Interactive generation

The LLM Playground provides a system prompt, streaming answers, separately displayed reasoning, and model-specific parameters. You can stop generation and retain received text. It currently sends **single requests without conversation history**.

- Supported parameters and field mappings come from [config/llm-models.yaml](config/llm-models.yaml), not hard-coded model controls in the UI.
- Thinking mode, reasoning effort, and budgets appear only for explicitly declared capabilities. Unknown models use a conservative basic profile.
- Capability refresh supplements metadata only where a provider exposes an integrated model-list API. Missing context limits remain unknown.
- **Maximum output tokens is blank by default in Playground:** no `max_tokens` is sent, so the service chooses its default. Test plans and the LLM CLI still default to 256; adjust the budget for thinking models because reasoning can consume output tokens.
- Dynamic Playground parameters and the system prompt are not yet shared as a full parameter editor across plans, CLI, and AI reports.

See [LLM model configuration](docs/llm-model-configuration.md) for YAML rules, validation, and current limitations.

### AI performance reports

Select a configured LLM under **Space settings** (Owner or administrator in a team), then open **Run history → AI report → Generate report** after a run ends. Generation is manual and may incur model charges; saving the default LLM does not call it or change benchmark targets.

Reports persist in PostgreSQL and can be viewed or downloaded without another model call. Reanalysis replaces a report only on success; failures retain the previous version. Deleting a run also deletes its AI report.

Analysis receives allowlisted performance statistics, model identifiers, input lengths, and document counts—not API keys, endpoints, raw test inputs, or raw errors. Reports interpret performance; they are not answer-quality evaluations.

## Command-line testing

CLI testing is independent of the web console: it reads process environment variables and optionally `cli/.env`, not saved web credentials. The root `.env` is not loaded.

From the repository root, install only CLI dependencies:

```bash
uv sync --locked --only-group cli
```

See the [CLI configuration reference](docs/cli-reference.md) for optional `cli/.env` setup and provider settings. Keep API keys out of commands and committed files.

Run **one** of these examples after configuring the corresponding endpoint, model, and credentials:

```bash
uv run --no-sync python -m cli.perf_llm --provider deepseek --max-tokens 2048 -c 1 -n 5 --json-report output/llm.json
uv run --no-sync python -m cli.perf_embedding --provider vllm --model BAAI/bge-m3 -c 1 -n 5 --json-report output/embedding.json
uv run --no-sync python -m cli.perf_reranker --provider xinference -c 1 -n 5 --json-report output/reranker.json
uv run --no-sync python -m cli.perf_audio --provider xinference --file audio/asr_example.wav -c 1 -n 5 --json-report output/audio.json
uv run --no-sync python -m cli.perf_dify retrieve -c 1 -n 5 --json-report output/dify-retrieve.json
uv run --no-sync python -m cli.perf_dify chat -c 1 -n 5 --json-report output/dify-chat.json
```

`-c` is concurrency; `-n` is the total request count. Increase them only after checking correctness. Use `--help` for full options, for example:

```bash
uv run --no-sync python -m cli.perf_llm --help
uv run --no-sync python -m cli.perf_dify retrieve --help
```

All five CLI modules support JSON export. Exports contain timing, success status, and summary statistics, but omit credentials, URLs, query text, response bodies, and raw errors. CLI JSON files are **not currently importable into the web console**.

Endpoint presets, environment variable names, and concurrency examples are in the [CLI configuration reference](docs/cli-reference.md).

## Understanding the metrics

| Metric | Meaning |
| --- | --- |
| P50 / P95 / P99 | Latency percentiles: 50% / 95% / 99% of measured successful requests finish within this time |
| QPS | Throughput; `qps_success` in JSON is successful requests divided by elapsed wall time |
| TTFT | Client-observed time from request start to first generated content, including reasoning |
| TPOT | `(request latency − TTFT) / (output tokens − 1)` |
| tokens/s | `1000 / TPOT`, excluding the wait for the first token |
| Audio RTF | Request latency divided by audio duration; lower is faster |

LLM TPOT and tokens/s require server-reported output-token usage. Missing usage or insufficient tokens makes them unavailable; stream chunks are not counted as tokens. UI values are rounded to integers; reports retain precision.

The web console, CLI terminal summaries, and exported JSON all calculate latency from successful requests and QPS as successful requests divided by elapsed wall time.

These are **client-side end-to-end measurements**, including network overhead—not pure model inference times. Small samples are useful for checking connectivity, not stable P95/P99 conclusions. Percentiles should not be averaged across runs.

## Data and security

- API keys are encrypted with Fernet. Set a stable `BENCHMARK_SECRET_KEY`, or the server generates `secret.key` in its data directory.
- Stop the backend, back up **all PostgreSQL schemas** with `pg_dump`, and preserve the **whole data directory**, including `secret.key`, `auth-session.key`, and reports. Preserve environment-provided encryption/session secrets separately. Losing the encryption key makes saved credentials unreadable; backing up `docker/volumes/` alone does not back up the database.
- Test plans persist their input configuration. Sanitized CLI exports and AI-analysis payloads do not mean all local application data is free of sensitive inputs.
- `cli/.env` and `docker/.env` are ignored by Git. Never commit real credentials or publish runtime data.
- Set `AUTH_MODE=app` for a dedicated sign-in page, administrator password, GitHub OAuth and generic OIDC with server-side sessions; see [authentication setup](docs/authentication.md). Each account gets an isolated personal workspace. Teams support targeted user invitations and owner/admin/member permissions; see [workspace isolation](docs/tenancy.md). Existing data belongs to the local administrator's personal workspace. The default `basic` mode preserves reverse-proxy authentication without multi-tenancy. Public deployments require HTTPS and restricted backend access.
- Docker uses `docker/volumes/`; local execution uses `backend/volumes/`. Override the local path with `BENCHMARK_DATA_DIR`; for Docker, change the host bind mount. See the [deployment guide](docker/README.md).
- Docker and local execution do not automatically share their databases, keys, or report directories. Tenant isolation uses PostgreSQL schemas, not a separate database server per tenant. Database/server administrators still have operational access; there are no per-tenant quotas or distributed scheduler support.

## Development and documentation

```text
backend/    FastAPI, scheduling, persistence, and model capabilities
frontend/   React web console
docker/     Dockerfiles, Compose, Nginx, and deployment guide
cli/        Command-line benchmark modules
shared/     Provider presets, streaming client, and report utilities
config/     Versioned LLM model definitions
tests/      Regression tests
docs/       Usage, architecture, and brand documentation
audio/      Audio test samples
```

Run checks from the repository root:

```bash
uv sync --locked
TEST_DATABASE_URL=postgresql://prismlab:prismlab@127.0.0.1:5432/prismlab_test \
  uv run --no-sync python -m unittest discover -s tests
cd frontend
pnpm install --frozen-lockfile
pnpm run build
pnpm run test:auth
pnpm run test:workspaces
pnpm run test:pagination
pnpm run test:dashboard
pnpm run test:playground
pnpm run test:selection
pnpm run test:documents
```

### Documentation

- [Docker deployment and packaging scripts](docker/README.md)
- [PostgreSQL setup, backups, and SQLite migration](docs/postgresql.md)
- [Sign-in, GitHub OAuth, and GitLab / OIDC](docs/authentication.md)
- [Personal workspaces, teams, and permissions](docs/tenancy.md)
- [List pagination](docs/pagination.md)
- [Dependency management](docs/dependencies.md)
- [CLI configuration reference](docs/cli-reference.md)
- [Model discovery and region requirements](docs/model-discovery.md)
- [LLM model definitions and parameters](docs/llm-model-configuration.md)
- [Repository layout](docs/repository-layout.md)
- [PrismLab brand guidelines](docs/brand-guidelines.md)

## License

[MIT](LICENSE)
