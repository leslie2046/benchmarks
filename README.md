# AI Model Benchmarks

用于测试 OpenAI 兼容的 Embedding API 和多家 Reranker API 的并发性能，输出成功率、QPS、平均延迟以及 P50/P95/P99 延迟。

## 安全说明

本项目不会将 API Key 写入受版本控制的代码或配置文件，也不通过命令行参数传递。密钥从环境变量或本地、被 Git 忽略的 `.env` 文件读取：

| 服务 | 环境变量 |
| --- | --- |
| Embedding | `EMBEDDING_API_KEY` |
| SiliconFlow Reranker | `SILICONFLOW_API_KEY` |
| 阿里云 Reranker | `ALIYUN_API_KEY` |
| 讯飞 Reranker | `XUNFEI_API_KEY` |
| 华为云 Reranker | `HUAWEIYUN_API_KEY` |
| Xinference（Embedding / Reranker） | `XINFERENCE_API_KEY` |

`.env` 文件已加入 `.gitignore`，脚本启动时会自动读取它，且不会覆盖系统中已设置的同名环境变量。不要把真实密钥写进 README、脚本、提交记录或聊天截图。

如果密钥曾经被提交或分享，请立即在对应服务商控制台吊销并重新生成。仅从最新代码中删除密钥并不能清除 Git 历史中的内容。

## 环境要求

- Python 3.9+
- 可访问目标 API 的网络环境

先从示例文件创建本地配置：

```powershell
Copy-Item .env.example .env
```

然后将新生成的密钥和服务地址填入 `.env`。脚本会自动加载该文件；系统环境变量优先级更高，也可以按需覆盖 `.env` 中的值。

安装依赖：

```bash
python -m venv .venv
```

PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Embedding 基准测试

PowerShell 示例：

```powershell
python perf_embedding.py -c 5 -n 100
```

默认使用 SiliconFlow 的 `BAAI/bge-m3`。也可以连接任意 OpenAI 兼容服务：

```powershell
$env:EMBEDDING_API_KEY = "你的新密钥"
$env:EMBEDDING_BASE_URL = "https://example.com/v1/embeddings"
$env:EMBEDDING_MODEL = "your-model"
python perf_embedding.py -c 10 -n 500 --timeout 30
```

本地无鉴权服务可不设置 `EMBEDDING_API_KEY`，通过 `--base-url` 和 `--model` 指定地址与模型。

## Reranker 基准测试

本地服务默认地址为 `http://127.0.0.1:9997/v1/rerank`：

```bash
python perf_reranker.py --provider local -c 10 -n 100
```

SiliconFlow 示例：

```powershell
python perf_reranker.py --provider siliconflow -c 10 -n 100
```

阿里云的地址通常与部署实例相关，因此需要单独设置：

```powershell
$env:ALIYUN_API_KEY = "你的新密钥"
$env:ALIYUN_RERANK_URL = "https://你的实例地址/compatible-api/v1/reranks"
python perf_reranker.py --provider aliyun
```

支持的 provider：`local`、`siliconflow`、`aliyun`、`xunfei`、`huaweiyun`、`xinference`。可用 `--model`、`--base-url`、`--proxy` 和 `--timeout` 覆盖默认配置：

```bash
python perf_reranker.py --provider local --base-url http://127.0.0.1:8000/v1/rerank --model bge-reranker-v2-m3 -c 20 -n 1000 --timeout 30
```

### Xinference

Xinference 的 OpenAI 兼容接口分别为 `/v1/embeddings`、`/v1/rerank` 与 `/v1/models`。在 `.env` 中填写服务地址和已部署的模型 ID：

```env
XINFERENCE_RERANK_URL=https://你的服务地址/v1/rerank
XINFERENCE_RERANK_MODEL=你的-reranker-模型ID

EMBEDDING_BASE_URL=https://你的服务地址/v1/embeddings
EMBEDDING_MODEL=你的-embedding-模型ID
```

如果只有一把 Xinference Key，保留 `XINFERENCE_API_KEY` 即可；Embedding 脚本会在 `EMBEDDING_API_KEY` 未设置时自动使用它。随后运行：

```bash
python perf_reranker.py --provider xinference -c 10 -n 100
python perf_embedding.py -c 10 -n 100
```

可先查询当前服务的模型 ID（PowerShell）：

```powershell
curl.exe -H "Authorization: Bearer $env:XINFERENCE_API_KEY" https://你的服务地址/v1/models
```

先以 `-c 1 -n 5` 验证配置，再逐步提高并发；压测会产生实际的模型调用与资源消耗。

查看全部参数：

```bash
python perf_embedding.py --help
python perf_reranker.py --help
```

## 指标说明

| 指标 | 含义 |
| --- | --- |
| Success Rate | HTTP 2xx 请求占总请求数的比例 |
| QPS | 每秒完成的请求数，包括失败请求 |
| Average | 所有请求的平均响应时间 |
| P50/P95/P99 | 对应百分位的响应时间 |
| Min/Max | 最短和最长响应时间 |

压测会产生真实 API 调用和费用。建议先用较小的 `-n` 验证配置，再逐步提高并发；同时遵守服务商的速率限制。

## 项目结构

```text
.
├── perf_embedding.py  # Embedding 并发测试
├── perf_reranker.py   # Reranker 并发测试
├── providers.py       # 不含密钥的 provider 预设
└── requirements.txt   # Python 依赖
```

## License

[MIT](LICENSE)
