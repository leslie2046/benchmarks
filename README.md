# BenchLens · AI Model Benchmarks

BenchLens is an AI service benchmarking and analysis console. Its Chinese name is 衡镜. See the [brand guidelines](docs/brand-guidelines.md) for the original measurement-window logo, theme variants and third-party Dify asset usage.

### System settings and AI test reports

Choose an already configured LLM (and credential when applicable) under **System settings**. Saving does not invoke it or change benchmark targets. After a run ends, use **Run history → AI report → Generate report** to request analysis manually.

Reports persist independently in local SQLite with their model and generation time. Viewing or downloading a saved report makes no model call. Reanalysis replaces it only on success; failures retain the previous report. Closing the dialog does not stop background generation. Interrupted generation is recoverable after a server restart. Deleting a run also deletes its AI report.

Only allowlisted performance statistics, model identifiers, input lengths and document counts are sent, not API keys, endpoints, raw test inputs or raw errors. Reports are advisory performance interpretations, not answer-quality evaluations. Manual generation/reanalysis may incur model charges. API: `GET/PUT /api/system-settings`, `GET/POST /api/runs/{run_id}/ai-report`; POST accepts `regenerate: true` and `language: zh-CN|en`.

Concurrent benchmarks for Embedding, Reranker, Xinference audio transcription, and Dify knowledge base and Chat APIs. Reports success rate, QPS, and latency percentiles.

[简体中文](README_zh-Hans.md)

## Run (Linux)

### Streaming LLM tests

The official DeepSeek provider supports LLM, read-only API-key verification and model discovery. The default root is `https://api.deepseek.com`; the prefilled model is `deepseek-flash`, which can be replaced by an ID discovered from the server. Saved models are available in Playground, test plans and the default report-analysis model picker. CLI: `--provider deepseek`, `DEEPSEEK_API_KEY`, optional `--model` / `LLM_MODEL` override.

Playground now renders dynamic LLM parameters from `config/llm-models.yaml`: basic sampling controls for every LLM provider and thinking, effort or budget controls for explicitly declared models. Read-only capability refresh supplements metadata for integrated discovery providers. Model lists support search and type filters; the default report model picker supports search. See [LLM configuration](docs/llm-model-configuration.md) for usage and future plan/CLI/report parameter integration.

Configure an LLM model under Model providers, then select LLM in Test plans or Playground.
Tests use OpenAI-compatible `/v1/chat/completions` with streaming and usage reporting.
TTFT is client-observed time to first generated content (including reasoning content).
TPOT is `(request latency - TTFT) / (completion_tokens - 1)`, using server-reported usage;
missing usage or a single output token leaves TPOT unavailable, never estimated from chunk counts.
Generation speed is `1000 / TPOT` in tokens/s, excluding time to the first token; it is unavailable without valid positive TPOT. UI metrics are rounded to integers while reports retain precision.
Reports contain sample counts, mean, P50/P95/P99 and no prompts or response text.
The analysis dashboard supports per-run comparisons and multi-run TTFT/TPOT trends.

```bash
python3 -m cli.perf_llm --provider vllm --base-url http://127.0.0.1:8000/v1/chat/completions \
  --model Qwen/Qwen3-8B --max-tokens 256 -c 1 -n 5 --json-report output/llm.json
```

Set the provider's existing API key environment variable when required. Generation tests make
real, potentially billable requests. Client-side streaming timings include network overhead.

Python 3 and the `requests` package are required. Configure the service in environment variables or a local `.env` file; see `.env.example` for names. The scripts load `.env` automatically, while existing environment variables take precedence. `.env` is ignored by Git. Keep real keys out of commands and committed files.

Run the command for a service you have configured:

```bash
python3 -m cli.perf_embedding --provider vllm --model BAAI/bge-m3 -c 5 -n 50
python3 -m cli.perf_reranker --provider local -c 5 -n 50
python3 -m cli.perf_audio --file audio/asr_example.wav -c 5 -n 50
python3 -m cli.perf_dify retrieve -c 5 -n 50
python3 -m cli.perf_dify chat -c 5 -n 50
```

`-c` sets concurrency and `-n` sets the number of requests. Start with `-c 1 -n 5` to check the configuration. Benchmarks make real API calls and may incur charges.

### Compare concurrency levels

Run the same workload at several concurrency levels. Each run writes a separate JSON file:

```bash
for c in 1 5 10 20 30; do
  echo "====== concurrency=$c ======"
  python3 -m cli.perf_reranker --provider xinference -c "$c" -n 100 \
    --json-report "output/reranker-c${c}.json"
done
```

These commands export JSON for external analysis. For integrated visualization, run a test plan in the web console and use its Analysis dashboard to compare repeated runs. The old standalone HTML viewer has been retired; the console does not currently import standalone CLI JSON files.

## Configuration

<details>
<summary>Embedding providers</summary>

Use `--provider` to select a preset. `--base-url` and `--model` override its endpoint and model.

| Provider | Default endpoint | Default model | Key variable | Endpoint / model variables |
| --- | --- | --- | --- | --- |
| `siliconflow` | `https://api.siliconflow.cn/v1/embeddings` | `BAAI/bge-m3` | `EMBEDDING_API_KEY` (optional; falls back to `XINFERENCE_API_KEY`) | `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL` |
| `xinference` | `http://127.0.0.1:9997/v1/embeddings` | Set explicitly | `XINFERENCE_API_KEY` (optional) | `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL` |
| `vllm` | `http://127.0.0.1:8000/v1/embeddings` | Set explicitly | `VLLM_API_KEY` (optional) | `VLLM_EMBEDDING_URL`, `VLLM_EMBEDDING_MODEL` |

</details>

<details>
<summary>Reranker providers</summary>

Use `--provider` to select a preset. `--base-url` and `--model` override its endpoint and model. `--proxy` sets an HTTP proxy; `--batch-size 0` omits the provider-specific `kwargs.batch_size` hint. The vLLM preset always omits that hint.

| Provider | Default endpoint | Default model | Key variable | Endpoint / model variables |
| --- | --- | --- | --- | --- |
| `local` | `http://127.0.0.1:9997/v1/rerank` | `bge-reranker-large` | None | None |
| `siliconflow` | `https://api.siliconflow.cn/v1/rerank` | `BAAI/bge-reranker-v2-m3` | `SILICONFLOW_API_KEY` | None |
| `aliyun` | Set explicitly | `qwen3-rerank` | `ALIYUN_API_KEY` | `ALIYUN_RERANK_URL` |
| `xunfei` | `https://maas-api.cn-huabei-1.xf-yun.com/v2/rerank` | `xop3qwen8breranker` | `XUNFEI_API_KEY` | None |
| `huaweiyun` | `https://api.modelarts-maas.com/v1/rerank` | `bge-reranker-v2-m3` | `HUAWEIYUN_API_KEY` | None |
| `xinference` | Set explicitly | Set explicitly | `XINFERENCE_API_KEY` | `XINFERENCE_RERANK_URL`, `XINFERENCE_RERANK_MODEL` |
| `vllm` | `http://127.0.0.1:8000/v1/rerank` | Set explicitly | `VLLM_API_KEY` (optional) | `VLLM_RERANK_URL`, `VLLM_RERANK_MODEL` |

</details>

<details>
<summary>Audio transcription (Xinference, vLLM, SiliconFlow)</summary>

Audio supports `--provider xinference|vllm|siliconflow`; each provider uses its own API key (`XINFERENCE_API_KEY`, `VLLM_API_KEY`, or `SILICONFLOW_API_KEY`). Configure `VLLM_AUDIO_URL`/`VLLM_AUDIO_MODEL` or `SILICONFLOW_AUDIO_URL`/`SILICONFLOW_AUDIO_MODEL`, or pass `--base-url` and `--model`. Audio here means speech-to-text, not speech synthesis. See the [vLLM transcription API](https://docs.vllm.ai/en/latest/serving/online_serving/speech_to_text/) and [SiliconFlow transcription API](https://docs.siliconflow.cn/docs/api/audio-transcriptions-post).

Playground LLM responses render incrementally and can be stopped without losing received text. TTFT appears after the first chunk; TPOT and tokens/s become available after the server returns token usage. The original JSON result remains available in a collapsible section.

`perf_audio.py` uploads the same file as `multipart/form-data` on every request to `/v1/audio/transcriptions`. The file is loaded into memory once.

| Setting | Default / purpose |
| --- | --- |
| `XINFERENCE_AUDIO_URL` / `--base-url` | `http://127.0.0.1:9997/v1/audio/transcriptions` |
| `XINFERENCE_AUDIO_MODEL` / `--model` | `Qwen3-ASR-0.6B`; use the launched model UID |
| `XINFERENCE_AUDIO_FILE` / `--file` | Required file path |
| `XINFERENCE_API_KEY` | Optional bearer token |
| `--audio-duration` | Seconds; WAV is detected automatically, other formats may need this value |

With a known duration, output includes average RTF (average latency / audio duration) and audio speed (audio seconds processed / elapsed time). For example, add `--audio-duration 30.5` for a 30.5-second MP3.

</details>

<details>
<summary>Dify knowledge base and Chat</summary>

Set `DIFY_BASE_URL` (server origin, with or without `/v1`) and `DIFY_QUERY` in `.env`. Retrieval also needs `DIFY_DATASET_ID` and `DIFY_DATASET_API_KEY`; Chat needs the separate `DIFY_CHAT_API_KEY`. Use `--base-url`, `--query`, or `--dataset-id` to override non-secret values.

Retrieval calls `POST /v1/datasets/{dataset_id}/retrieve` and measures the complete request. Chat calls `POST /v1/chat-messages` in streaming mode, starting a new conversation for every request. It reports time to the first `message` event (`ttft_ms`), `message_end_ms`, optional workflow event times, and total latency. Chat succeeds only if `message_end` arrives.

Both modes accept `--timeout` and `--no-verify-ssl`; Chat also accepts `--user`. Each request uses the same query.

</details>

## Results and options

The scripts report success rate, QPS, average latency, and P50/P95/P99. Dify latency summaries include successful requests only; its QPS uses successful requests divided by elapsed wall time. Audio also reports RTF and audio speed when duration is known.

All five CLI modules accept `--json-report PATH`. JSON contains per-request timing and success data plus summary statistics; it excludes API keys, URLs, queries, response bodies, and error text. Parent directories are created automatically. CLI JSON export remains available independently of web-console run records.

Run `python3 -m cli.perf_<type> --help` from the repository root, or `python3 -m cli.perf_dify retrieve --help` / `python3 -m cli.perf_dify chat --help` for Dify. Install CLI-only dependencies with `python -m pip install -r cli/requirements.txt`.

## Repository layout and API startup

- `backend/`: FastAPI, scheduling, persistence, model capabilities and API image.
- `cli/`: five benchmark modules invoked with `python -m cli.perf_<type>`.
- `shared/`: provider presets, environment loading, streaming client and JSON report writer; no FastAPI dependency.
- `frontend/`: web console. `config/`: versioned model definitions. `tests/`: regression tests.
- `audio/`: workloads. `data/` and `output/`: runtime data; never delete their databases, keys or reports during source cleanup.

From the repository root:

```bash
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload
python -m unittest discover -s tests
```

Compose now builds the API from `backend/Dockerfile` with the repository root as its build context; it includes CLI, shared code and model YAML. Existing `.env` and data paths are unchanged. See [repository layout](docs/repository-layout.md).

## License

[MIT](LICENSE)
