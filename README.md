# PrismLab

AI model testing & analysis — benchmark your services, compare performance, and understand the results.

[简体中文](README_zh-Hans.md) · [Quick start](#quick-start) · [CLI](#command-line-testing) · [Documentation](#documentation)

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

Provider presets include DeepSeek, SiliconFlow, Xinference, vLLM, Alibaba Cloud, Xunfei MaaS, and Huawei Cloud. Available test types and model discovery depend on the provider and deployed model; not every provider supports every type.

## Quick start

Choose **Docker** for deployment or **local development** to modify the code. You need a reachable model service or Dify instance for actual testing.

### Option A: Docker

Prerequisites: Git, Docker, and Docker Compose.

```bash
git clone https://github.com/leslie2046/benchmarks.git
cd benchmarks
```

Copy [.env.example](.env.example) to `.env` **only if you do not already have one**:

```bash
# Linux / macOS
cp .env.example .env
```

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

Then start the console:

```bash
docker compose up --build -d
```

Open **http://localhost:8080**. Configure model credentials in the console; provider variables in `.env` are primarily for CLI testing.

Useful deployment commands:

```bash
docker compose logs -f
docker compose up --build -d    # Rebuild after pulling updates
docker compose down           # Stop the services
```

Data is stored in the host's `data/` directory. Back it up before upgrading; see [Data and security](#data-and-security).

Inside Docker, `127.0.0.1` refers to the container, not your host. For a model running on the host, use an address reachable from the API container (for example, `host.docker.internal` on Docker Desktop), and check service binding and firewall rules.

### Option B: Local development

Use Python 3.12+ and Node.js 22.12+ (or 24+). Clone the repository as above, then create a Python virtual environment:

```bash
python -m venv .venv
```

Activate it with `source .venv/bin/activate` on Linux/macOS or `.\.venv\Scripts\Activate.ps1` in Windows PowerShell.

**Terminal 1 — backend**, from the repository root:

```bash
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — frontend**:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open **http://localhost:5173**. Vite forwards `/api` requests to the backend on port 8000. If Vite selects another port, use the URL printed in its terminal.

Local data defaults to `output/web/`. Run the production backend with **one worker**: its scheduler and SQLite lifecycle are local to that process.

## Your first test

1. **Model providers:** add a provider, enter its endpoint and credentials, and add models manually or fetch the model list where supported. Save the configuration.
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

Select a configured LLM under **System settings**, then open **Run history → AI report → Generate report** after a run ends. Generation is manual and may incur model charges; saving the default LLM does not call it or change benchmark targets.

Reports persist in SQLite and can be viewed or downloaded without another model call. Reanalysis replaces a report only on success; failures retain the previous version. Deleting a run also deletes its AI report.

Analysis receives allowlisted performance statistics, model identifiers, input lengths, and document counts—not API keys, endpoints, raw test inputs, or raw errors. Reports interpret performance; they are not answer-quality evaluations.

## Command-line testing

CLI testing is independent of the web console: it reads environment variables / the repository's `.env`, not saved web credentials. Existing environment variables take precedence over `.env`.

From the repository root, with a Python environment activated:

```bash
python -m pip install -r cli/requirements.txt
```

Copy `.env.example` to `.env` if needed, then replace only the settings for your chosen service. Keep API keys out of commands and committed files.

Run **one** of these examples after configuring the corresponding endpoint, model, and credentials:

```bash
python -m cli.perf_llm --provider deepseek --max-tokens 2048 -c 1 -n 5 --json-report output/llm.json
python -m cli.perf_embedding --provider vllm --model BAAI/bge-m3 -c 1 -n 5 --json-report output/embedding.json
python -m cli.perf_reranker --provider xinference -c 1 -n 5 --json-report output/reranker.json
python -m cli.perf_audio --provider xinference --file audio/asr_example.wav -c 1 -n 5 --json-report output/audio.json
python -m cli.perf_dify retrieve -c 1 -n 5 --json-report output/dify-retrieve.json
python -m cli.perf_dify chat -c 1 -n 5 --json-report output/dify-chat.json
```

`-c` is concurrency; `-n` is the total request count. Increase them only after checking correctness. Use `--help` for full options, for example:

```bash
python -m cli.perf_llm --help
python -m cli.perf_dify retrieve --help
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

These are **client-side end-to-end measurements**, including network overhead—not pure model inference times. Small samples are useful for checking connectivity, not stable P95/P99 conclusions. Percentiles should not be averaged across runs.

## Data and security

- API keys are encrypted with Fernet. Set a stable `BENCHMARK_SECRET_KEY`, or the server generates `secret.key` in its data directory.
- Back up the **whole data directory**, including `runs.sqlite3`, `secret.key`, and reports. If using an environment-provided encryption key, preserve it separately. Losing the key makes saved credentials unreadable.
- Test plans persist their input configuration. Sanitized CLI exports and AI-analysis payloads do not mean all local application data is free of sensitive inputs.
- `.env` is ignored by Git. Never commit real credentials or publish runtime data.
- The console has no built-in login. Before exposing it publicly, add authentication and HTTPS at a reverse proxy and restrict access to the backend and configured services.
- Docker stores data in `data/`; local execution uses `output/web/`. Override with `BENCHMARK_DATA_DIR` when needed.

## Development and documentation

```text
backend/    FastAPI, scheduling, persistence, and model capabilities
frontend/   React web console
cli/        Command-line benchmark modules
shared/     Provider presets, streaming client, and report utilities
config/     Versioned LLM model definitions
tests/      Regression tests
docs/       Usage, architecture, and brand documentation
audio/      Audio test samples
```

Run checks from the repository root (backend dependencies installed):

```bash
python -m unittest discover -s tests
cd frontend
npm ci
npm run build
npm run test:dashboard
npm run test:playground
```

### Documentation

- [CLI configuration reference](docs/cli-reference.md)
- [Model discovery and region requirements](docs/model-discovery.md)
- [LLM model definitions and parameters](docs/llm-model-configuration.md)
- [Repository layout and migration](docs/repository-layout.md)
- [PrismLab brand guidelines](docs/brand-guidelines.md)

## License

[MIT](LICENSE)
