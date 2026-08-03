# AI Model Benchmarks

Concurrent benchmarks for OpenAI-compatible Embedding and Reranker APIs. Reports success rate, QPS, average latency, and P50/P95/P99 latency.

[简体中文](README_zh-Hans.md)

## Configuration

Create a local configuration file from the template:

```powershell
Copy-Item .env.example .env
```

Put credentials in `.env`. It is ignored by Git and loaded automatically by the scripts; system environment variables take precedence. Do not put real keys in source code, READMEs, command-line arguments, or commits.

## Embedding

Default settings:

| Parameter / environment variable | Default value |
| --- | --- |
| `EMBEDDING_BASE_URL` | `https://api.siliconflow.cn/v1/embeddings` |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` |
| `EMBEDDING_API_KEY` | Unset; falls back to `XINFERENCE_API_KEY` when available |
| `-c` / `--concurrency` | `5` |
| `-n` / `--requests` | `100` |
| `--timeout` | `60` seconds |

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

Override provider defaults when needed:

```powershell
python perf_reranker.py --provider local --base-url http://127.0.0.1:8000/v1/rerank --model bge-reranker-v2-m3 -c 20 -n 1000 --proxy http://127.0.0.1:7890 --timeout 30
```

## Xinference

Use these OpenAI-compatible endpoints:

| Purpose | URL suffix | Configuration |
| --- | --- | --- |
| List models | `/v1/models` | Use it to get model IDs |
| Embeddings | `/v1/embeddings` | `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL` |
| Reranking | `/v1/rerank` | `XINFERENCE_RERANK_URL`, `XINFERENCE_RERANK_MODEL` |

Example `.env`:

```env
XINFERENCE_API_KEY=replace-with-your-api-key
EMBEDDING_BASE_URL=https://your-xinference-host:port/v1/embeddings
EMBEDDING_MODEL=bge-m3
XINFERENCE_RERANK_URL=https://your-xinference-host:port/v1/rerank
XINFERENCE_RERANK_MODEL=bge-reranker-large
```

View all command options:

```powershell
python perf_embedding.py --help
python perf_reranker.py --help
```

Benchmarks create real API calls and may incur charges. Start with `-c 1 -n 5` to validate the configuration.

## License

[MIT](LICENSE)
