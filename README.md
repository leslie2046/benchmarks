# AI Model Benchmarks

Concurrent benchmarks for OpenAI-compatible Embedding, Reranker, and Xinference audio transcription APIs. Reports success rate, QPS, average latency, and P50/P95/P99 latency.

[简体中文](README_zh-Hans.md)

## Configuration

Create a local configuration file from the template:

```powershell
Copy-Item .env.example .env
```

Put credentials in `.env`. It is ignored by Git and loaded automatically by the scripts; system environment variables take precedence. Do not put real keys in source code, READMEs, command-line arguments, or commits.

## Embedding

```powershell
python perf_embedding.py --provider vllm --model BAAI/bge-m3 -c 10 -n 100 --timeout 30
```

Supported `--provider` values and defaults:

| Provider | Default `base_url` | Default `model` | API-key environment variable | Additional environment variables |
| --- | --- | --- | --- | --- |
| `siliconflow` | `https://api.siliconflow.cn/v1/embeddings` | `BAAI/bge-m3` | `EMBEDDING_API_KEY` (optional; falls back to `XINFERENCE_API_KEY`) | `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL` |
| `xinference` | `http://127.0.0.1:9997/v1/embeddings` | None | `XINFERENCE_API_KEY` (optional) | `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL` |
| `vllm` | `http://127.0.0.1:8000/v1/embeddings` | None | `VLLM_API_KEY` (optional) | `VLLM_EMBEDDING_URL`, `VLLM_EMBEDDING_MODEL` |

```powershell
python perf_embedding.py -c 10 -n 100 --timeout 30
```

## Reranker

```powershell
python perf_reranker.py --provider xinference -c 10 -n 100 --timeout 30
```

Supported `--provider` values and defaults:

| Provider | Default `base_url` | Default `model` | API-key environment variable | Additional environment variables |
| --- | --- | --- | --- | --- |
| `local` | `http://127.0.0.1:9997/v1/rerank` | `bge-reranker-large` | None | None |
| `siliconflow` | `https://api.siliconflow.cn/v1/rerank` | `BAAI/bge-reranker-v2-m3` | `SILICONFLOW_API_KEY` | None |
| `aliyun` | None | `qwen3-rerank` | `ALIYUN_API_KEY` | `ALIYUN_RERANK_URL` |
| `xunfei` | `https://maas-api.cn-huabei-1.xf-yun.com/v2/rerank` | `xop3qwen8breranker` | `XUNFEI_API_KEY` | None |
| `huaweiyun` | `https://api.modelarts-maas.com/v1/rerank` | `bge-reranker-v2-m3` | `HUAWEIYUN_API_KEY` | None |
| `xinference` | None | None | `XINFERENCE_API_KEY` | `XINFERENCE_RERANK_URL`, `XINFERENCE_RERANK_MODEL` |
| `vllm` | `http://127.0.0.1:8000/v1/rerank` | None | `VLLM_API_KEY` (optional) | `VLLM_RERANK_URL`, `VLLM_RERANK_MODEL` |

Override provider defaults when needed:

```powershell
python perf_reranker.py --provider local --base-url http://127.0.0.1:8000/v1/rerank --model bge-reranker-v2-m3 -c 20 -n 1000 --proxy http://127.0.0.1:7890 --timeout 30
```

## Audio transcription

`perf_audio.py` benchmarks Xinference's OpenAI-compatible `/v1/audio/transcriptions` endpoint. Every request uploads the same audio file:

```powershell
python perf_audio.py --file C:\path\to\audio.mp3 -c 5 -n 50
```

The script uploads the actual audio bytes as `multipart/form-data`; do not send a local path as the text value of the `file` field. The audio is read into memory once before the benchmark starts.

| Parameter / environment variable | Description / default |
| --- | --- |
| `XINFERENCE_AUDIO_URL` / `--base-url` | `http://127.0.0.1:9997/v1/audio/transcriptions` |
| `XINFERENCE_AUDIO_MODEL` / `--model` | `Qwen3-ASR-0.6B`; use the UID of the launched Xinference model |
| `XINFERENCE_AUDIO_FILE` / `--file` | Required local audio-file path |
| `XINFERENCE_API_KEY` | Optional bearer token |
| `--audio-duration` | Audio length in seconds; detected for WAV, supplied manually for formats such as MP3 |
| `-c` / `--concurrency` | `5` |
| `-n` / `--requests` | `100` |
| `--timeout` | `120` seconds |

When the audio duration is known, the result also reports `Average RTF` (average latency divided by audio duration; lower is better) and `Audio Speed` (audio seconds processed per wall-clock second). For an MP3 or another file whose duration cannot be detected automatically, pass a value such as `--audio-duration 30.5`.

## Xinference

Use these OpenAI-compatible endpoints:

| Purpose | URL suffix | Configuration |
| --- | --- | --- |
| List models | `/v1/models` | Use it to get model IDs |
| Embeddings | `/v1/embeddings` | `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL` |
| Reranking | `/v1/rerank` | `XINFERENCE_RERANK_URL`, `XINFERENCE_RERANK_MODEL` |
| Audio transcription | `/v1/audio/transcriptions` | `XINFERENCE_AUDIO_URL`, `XINFERENCE_AUDIO_MODEL`, `XINFERENCE_AUDIO_FILE` |

Example `.env`:

```env
XINFERENCE_API_KEY=replace-with-your-api-key
EMBEDDING_BASE_URL=https://your-xinference-host:port/v1/embeddings
EMBEDDING_MODEL=bge-m3
XINFERENCE_RERANK_URL=https://your-xinference-host:port/v1/rerank
XINFERENCE_RERANK_MODEL=bge-reranker-large
XINFERENCE_AUDIO_URL=https://your-xinference-host:port/v1/audio/transcriptions
XINFERENCE_AUDIO_MODEL=Qwen3-ASR-0.6B
XINFERENCE_AUDIO_FILE=C:\path\to\audio.mp3
```

View all command options:

```powershell
python perf_embedding.py --help
python perf_reranker.py --help
python perf_audio.py --help
```

Benchmarks create real API calls and may incur charges. Start with `-c 1 -n 5` to validate the configuration.

## vLLM

Start separate vLLM servers for the embedding and reranker models, then set the matching model names:

```powershell
python perf_embedding.py --provider vllm --model BAAI/bge-m3
python perf_reranker.py --provider vllm --model BAAI/bge-reranker-v2-m3
```

The provider uses vLLM's OpenAI-compatible `/v1/embeddings` endpoint and its `/v1/rerank` endpoint. `VLLM_API_KEY` is optional. The vLLM reranker request does not send the provider-specific `kwargs.batch_size` extension.

## License

[MIT](LICENSE)
