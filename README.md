# AI Model Benchmarks

Concurrent benchmarks for Embedding, Reranker, Xinference audio transcription, and Dify knowledge base and Chat APIs. Reports success rate, QPS, and latency percentiles.

[简体中文](README_zh-Hans.md)

## Quick start (Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` for the service you want to test. The scripts load it automatically; existing environment variables take precedence. `.env` is ignored by Git. Keep real keys out of commands and committed files.

Run the command for a service you have configured:

```bash
python3 perf_embedding.py --provider vllm --model BAAI/bge-m3 -c 5 -n 50
python3 perf_reranker.py --provider local -c 5 -n 50
python3 perf_audio.py --file audio/asr_example.wav -c 5 -n 50
python3 perf_dify.py retrieve -c 5 -n 50
python3 perf_dify.py chat -c 5 -n 50
```

`-c` sets concurrency and `-n` sets the number of requests. Start with `-c 1 -n 5` to check the configuration. Benchmarks make real API calls and may incur charges.

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
<summary>Xinference audio transcription</summary>

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

Run `python3 <script>.py --help` for the full options, or `python3 perf_dify.py retrieve --help` / `python3 perf_dify.py chat --help` for Dify.

## License

[MIT](LICENSE)
