# AI Model Benchmarks

OpenAI 兼容 Embedding、Reranker 与 Xinference 语音转文字 API 的并发压测脚本，输出成功率、QPS、平均延迟和 P50/P95/P99。

[English](README.md)

## 配置

从模板创建本地配置：

```powershell
Copy-Item .env.example .env
```

将密钥填入 `.env`。该文件已被 Git 忽略，脚本会自动加载它，且系统环境变量优先。不要将真实密钥写入代码、README、命令行或提交记录。

## Embedding

```powershell
python perf_embedding.py --provider vllm --model BAAI/bge-m3 -c 10 -n 100 --timeout 30
```

支持的 `--provider` 与默认参数：

| Provider | 默认 `base_url` | 默认 `model` | 密钥环境变量 | 额外环境变量 |
| --- | --- | --- | --- | --- |
| `siliconflow` | `https://api.siliconflow.cn/v1/embeddings` | `BAAI/bge-m3` | `EMBEDDING_API_KEY`（可选；未设置时使用 `XINFERENCE_API_KEY`） | `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL` |
| `xinference` | `http://127.0.0.1:9997/v1/embeddings` | 无 | `XINFERENCE_API_KEY`（可选） | `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL` |
| `vllm` | `http://127.0.0.1:8000/v1/embeddings` | 无 | `VLLM_API_KEY`（可选） | `VLLM_EMBEDDING_URL`、`VLLM_EMBEDDING_MODEL` |

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
| `vllm` | `http://127.0.0.1:8000/v1/rerank` | 无 | `VLLM_API_KEY`（可选） | `VLLM_RERANK_URL`、`VLLM_RERANK_MODEL` |

通用覆盖参数：

```powershell
python perf_reranker.py --provider local --base-url http://127.0.0.1:8000/v1/rerank --model bge-reranker-v2-m3 -c 20 -n 1000 --proxy http://127.0.0.1:7890 --timeout 30
```

## 语音转文字（Audio Transcription）

`perf_audio.py` 压测 Xinference 的 OpenAI 兼容 `/v1/audio/transcriptions` 接口。每个请求都会上传同一个音频文件：

```powershell
python perf_audio.py --file C:\path\to\audio.mp3 -c 5 -n 50
```

脚本使用 `multipart/form-data` 上传真实的音频字节，不要把本地文件路径当作 `file` 字段的文本值发送。音频会在压测前一次性读入内存。

| 参数 / 环境变量 | 说明 / 默认值 |
| --- | --- |
| `XINFERENCE_AUDIO_URL` / `--base-url` | `http://127.0.0.1:9997/v1/audio/transcriptions` |
| `XINFERENCE_AUDIO_MODEL` / `--model` | `Qwen3-ASR-0.6B`；应使用已启动的 Xinference 模型 UID |
| `XINFERENCE_AUDIO_FILE` / `--file` | 必填；本地音频文件路径 |
| `XINFERENCE_API_KEY` | 可选 Bearer Token |
| `--audio-duration` | 音频时长（秒）；WAV 可自动识别，MP3 等格式可手动传入 |
| `-c` / `--concurrency` | `5` |
| `-n` / `--requests` | `100` |
| `--timeout` | `120` 秒 |

当已知音频时长时，结果还会显示 `Average RTF`（平均延迟 / 音频时长，越低越好）和 `Audio Speed`（每秒处理的音频秒数）。对于 MP3 等不能自动识别时长的文件，可传入 `--audio-duration 30.5`。

## Xinference

当前配置的服务地址应使用以下接口：

| 用途 | URL 后缀 | 配置项 |
| --- | --- | --- |
| 模型列表 | `/v1/models` | 用于查询模型 ID |
| Embedding | `/v1/embeddings` | `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL` |
| Rerank | `/v1/rerank` | `XINFERENCE_RERANK_URL`、`XINFERENCE_RERANK_MODEL` |
| 语音转文字 | `/v1/audio/transcriptions` | `XINFERENCE_AUDIO_URL`、`XINFERENCE_AUDIO_MODEL`、`XINFERENCE_AUDIO_FILE` |

示例 `.env`：

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

查看参数：

```powershell
python perf_embedding.py --help
python perf_reranker.py --help
python perf_audio.py --help
```

压测会产生实际 API 调用与费用；建议先用 `-c 1 -n 5` 验证配置。

## vLLM

分别启动 embedding 与 reranker 模型的 vLLM 服务，然后传入与服务一致的模型名：

```powershell
python perf_embedding.py --provider vllm --model BAAI/bge-m3
python perf_reranker.py --provider vllm --model BAAI/bge-reranker-v2-m3
```

该 provider 使用 vLLM 的 OpenAI 兼容 `/v1/embeddings` 接口和 `/v1/rerank` 接口。`VLLM_API_KEY` 可选；vLLM reranker 请求不会发送 provider 专用的 `kwargs.batch_size` 扩展字段。

## License

[MIT](LICENSE)
