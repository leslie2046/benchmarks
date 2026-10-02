# CLI configuration reference

[Back to README](../README.md) · [返回中文说明](../README_zh-Hans.md)

This reference covers CLI presets and environment variables. Run commands from the repository root after installing `cli/requirements.txt`.

## Optional CLI environment file

CLI commands work without an environment file. Use command-line flags for endpoints/models and process environment variables for credentials, or copy [cli/.env.example](../cli/.env.example) to `cli/.env` if you prefer a local configuration file. Do not overwrite an existing file; enable only the settings for the service you intend to test.

```bash
# Linux / macOS, from the repository root
cp cli/.env.example cli/.env
```

```powershell
# Windows PowerShell, from the repository root
Copy-Item cli/.env.example cli/.env
```

The loader always reads `cli/.env`, independently of the working directory. It does not read or fall back to the root `.env`. Existing process environment variables take precedence; command-line endpoint/model flags override their corresponding environment settings. CLI commands do not read credentials saved in the web console. `cli/.env` is ignored by Git; never commit real credentials.

For example, a minimal DeepSeek configuration in `cli/.env` is:

```dotenv
DEEPSEEK_API_KEY=replace-with-your-api-key
```

Then run `python -m cli.perf_llm --provider deepseek --max-tokens 2048 -c 1 -n 5` from the repository root. This makes real requests and may incur charges. The backend does not load this CLI environment file.

## Configuration

<details>
<summary>Embedding providers</summary>

Use `--provider` to select a preset. `--base-url` and `--model` override its endpoint and model.

| Provider | Default endpoint | Default model | Key variable | Endpoint / model variables |
| --- | --- | --- | --- | --- |
| `siliconflow` | `https://api.siliconflow.cn/v1/embeddings` | `BAAI/bge-m3` | `EMBEDDING_API_KEY` (optional; falls back to `XINFERENCE_API_KEY`) | `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL` |
| `xinference` | `http://127.0.0.1:9997/v1/embeddings` | Set explicitly | `XINFERENCE_API_KEY` (optional) | `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL` |
| `vllm` | `http://127.0.0.1:8000/v1/embeddings` | Set explicitly | `VLLM_API_KEY` (optional) | `VLLM_EMBEDDING_URL`, `VLLM_EMBEDDING_MODEL` |
| `aliyun` | `https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings` | `text-embedding-v4` | `ALIYUN_API_KEY` | `ALIYUN_EMBEDDING_URL`, `ALIYUN_EMBEDDING_MODEL` |
| `huaweiyun` | `https://api.modelarts-maas.com/v1/embeddings` | `bge-m3` | `HUAWEIYUN_API_KEY` | `HUAWEIYUN_EMBEDDING_URL`, `HUAWEIYUN_EMBEDDING_MODEL` |
| `xunfei` | `https://maas-api.cn-huabei-1.xf-yun.com/v2/embeddings` | Deployed model ID from the console | `XUNFEI_API_KEY` | `XUNFEI_EMBEDDING_URL`, `XUNFEI_EMBEDDING_MODEL` |

Huawei requires an enabled Embedding service and its regional MaaS API key. Xingchen requires the deployed service's API key and model ID; older services may use `/v1/embeddings`, which can be supplied explicitly with `--base-url`.

</details>

<details>
<summary>Reranker providers</summary>

Use `--provider` to select a preset. `--base-url` and `--model` override its endpoint and model. `--proxy` sets an HTTP proxy; `--batch-size 0` omits the provider-specific `kwargs.batch_size` hint. The vLLM preset always omits that hint.

| Provider | Default endpoint | Default model | Key variable | Endpoint / model variables |
| --- | --- | --- | --- | --- |
| `siliconflow` | `https://api.siliconflow.cn/v1/rerank` | `BAAI/bge-reranker-v2-m3` | `SILICONFLOW_API_KEY` | None |
| `aliyun` | `https://dashscope.aliyuncs.com/compatible-api/v1/reranks` | `qwen3-rerank` | `ALIYUN_API_KEY` | `ALIYUN_RERANK_URL` |
| `xunfei` | `https://maas-api.cn-huabei-1.xf-yun.com/v2/rerank` | `xop3qwen8breranker` | `XUNFEI_API_KEY` | None |
| `huaweiyun` | `https://api.modelarts-maas.com/v1/rerank` | `bge-reranker-v2-m3` | `HUAWEIYUN_API_KEY` | None |
| `xinference` | Set explicitly | Set explicitly | `XINFERENCE_API_KEY` | `XINFERENCE_RERANK_URL`, `XINFERENCE_RERANK_MODEL` |
| `vllm` | `http://127.0.0.1:8000/v1/rerank` | Set explicitly | `VLLM_API_KEY` (optional) | `VLLM_RERANK_URL`, `VLLM_RERANK_MODEL` |

</details>

<details>
<summary>Audio transcription (Xinference, vLLM, SiliconFlow)</summary>

Audio supports `--provider xinference|vllm|siliconflow`; each provider uses its own API key (`XINFERENCE_API_KEY`, `VLLM_API_KEY`, or `SILICONFLOW_API_KEY`). Configure `VLLM_AUDIO_URL`/`VLLM_AUDIO_MODEL` or `SILICONFLOW_AUDIO_URL`/`SILICONFLOW_AUDIO_MODEL`, or pass `--base-url` and `--model`. Audio here means speech-to-text, not speech synthesis. See the [vLLM transcription API](https://docs.vllm.ai/en/latest/serving/online_serving/speech_to_text/) and [SiliconFlow transcription API](https://docs.siliconflow.cn/docs/api/audio-transcriptions-post).

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


## Streaming LLM

Use `--provider`, `--model`, and `--base-url` to select the target. Provider keys and endpoint variables are defined in [shared/providers.py](../shared/providers.py); examples are in [cli/.env.example](../cli/.env.example). LLM endpoints must point to the chat-completions route, not just the server origin.

The LLM CLI defaults to `--max-tokens 256`; increase it when testing reasoning models. YAML-driven thinking/effort controls and the Playground system prompt are not yet exposed as CLI flags. Use `python -m cli.perf_llm --help` for supported options.

Set `LLM_MODEL` (or pass `--model`). Endpoint overrides use `<PROVIDER>_LLM_URL`, for example `VLLM_LLM_URL`; API keys use the variables below. A service may require a key even when the client permits unauthenticated local deployments.

| Provider | API key variable |
| --- | --- |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `siliconflow` | `SILICONFLOW_API_KEY` |
| `xinference` | `XINFERENCE_API_KEY` |
| `vllm` | `VLLM_API_KEY` |
| `aliyun` | `ALIYUN_API_KEY` |
| `xunfei` | `XUNFEI_API_KEY` |
| `huaweiyun` | `HUAWEIYUN_API_KEY` |

## Compare concurrency levels

After verifying a small workload, run the same inputs at several concurrency levels and export separate reports.

Linux / macOS:

```bash
for c in 1 5 10 20; do
  python -m cli.perf_reranker --provider xinference -c "$c" -n 100 --json-report "output/reranker-c${c}.json"
done
```

Windows PowerShell:

```powershell
foreach ($concurrency in 1, 5, 10, 20) {
  python -m cli.perf_reranker --provider xinference -c $concurrency -n 100 --json-report "output/reranker-c$concurrency.json"
}
```

These commands make real requests and may incur charges. CLI JSON exports are independent of web-console runs and cannot currently be imported into its dashboard.
