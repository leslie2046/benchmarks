# AI Model Benchmarks

OpenAI 兼容 Embedding API 与 Reranker API 的并发压测脚本，输出成功率、QPS、平均延迟和 P50/P95/P99。

[English](README.md)

## 配置

从模板创建本地配置：

```powershell
Copy-Item .env.example .env
```

将密钥填入 `.env`。该文件已被 Git 忽略，脚本会自动加载它，且系统环境变量优先。不要将真实密钥写入代码、README、命令行或提交记录。

## Embedding

默认参数：

| 参数 / 环境变量 | 默认值 |
| --- | --- |
| `EMBEDDING_BASE_URL` | `https://api.siliconflow.cn/v1/embeddings` |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` |
| `EMBEDDING_API_KEY` | 未设置；若存在则使用 `XINFERENCE_API_KEY` |
| `-c` / `--concurrency` | `5` |
| `-n` / `--requests` | `100` |
| `--timeout` | `60` 秒 |

```powershell
python perf_embedding.py -c 10 -n 100 --timeout 30
```

## Reranker

```powershell
python perf_reranker.py --provider xinference -c 10 -n 100 --timeout 30
```

支持的 `--provider` 与默认参数：

| Provider | 默认 `base_url` | 默认 `model` | 密钥环境变量 | 额外环境变量 |
| --- | --- | --- | --- | --- |
| `local` | `http://127.0.0.1:9997/v1/rerank` | `bge-reranker-large` | 无 | 无 |
| `siliconflow` | `https://api.siliconflow.cn/v1/rerank` | `BAAI/bge-reranker-v2-m3` | `SILICONFLOW_API_KEY` | 无 |
| `aliyun` | 无 | `qwen3-rerank` | `ALIYUN_API_KEY` | `ALIYUN_RERANK_URL` |
| `xunfei` | `https://maas-api.cn-huabei-1.xf-yun.com/v2/rerank` | `xop3qwen8breranker` | `XUNFEI_API_KEY` | 无 |
| `huaweiyun` | `https://api.modelarts-maas.com/v1/rerank` | `bge-reranker-v2-m3` | `HUAWEIYUN_API_KEY` | 无 |
| `xinference` | 无 | 无 | `XINFERENCE_API_KEY` | `XINFERENCE_RERANK_URL`、`XINFERENCE_RERANK_MODEL` |

通用覆盖参数：

```powershell
python perf_reranker.py --provider local --base-url http://127.0.0.1:8000/v1/rerank --model bge-reranker-v2-m3 -c 20 -n 1000 --proxy http://127.0.0.1:7890 --timeout 30
```

## Xinference

当前配置的服务地址应使用以下接口：

| 用途 | URL 后缀 | 配置项 |
| --- | --- | --- |
| 模型列表 | `/v1/models` | 用于查询模型 ID |
| Embedding | `/v1/embeddings` | `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL` |
| Rerank | `/v1/rerank` | `XINFERENCE_RERANK_URL`、`XINFERENCE_RERANK_MODEL` |

示例 `.env`：

```env
XINFERENCE_API_KEY=replace-with-your-api-key
EMBEDDING_BASE_URL=https://your-xinference-host:port/v1/embeddings
EMBEDDING_MODEL=bge-m3
XINFERENCE_RERANK_URL=https://your-xinference-host:port/v1/rerank
XINFERENCE_RERANK_MODEL=bge-reranker-large
```

查看参数：

```powershell
python perf_embedding.py --help
python perf_reranker.py --help
```

压测会产生实际 API 调用与费用；建议先用 `-c 1 -n 5` 验证配置。

## License

[MIT](LICENSE)
