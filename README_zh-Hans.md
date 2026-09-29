# AI Model Benchmarks

Embedding、Reranker、Xinference 语音转文字及 Dify 知识库和 Chat API 的并发压测脚本，输出成功率、QPS 和延迟分位数。

[English](README.md)

## 快速开始（Linux）

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

在 `.env` 中配置要测试的服务。脚本会自动加载该文件，已有的系统环境变量优先；`.env` 已被 Git 忽略。不要把真实密钥写入命令或提交的文件。

选择已配置的服务运行：

```bash
python3 perf_embedding.py --provider vllm --model BAAI/bge-m3 -c 5 -n 50
python3 perf_reranker.py --provider local -c 5 -n 50
python3 perf_audio.py --file audio/asr_example.wav -c 5 -n 50
python3 perf_dify.py retrieve -c 5 -n 50
python3 perf_dify.py chat -c 5 -n 50
```

`-c` 指定并发数，`-n` 指定请求数。建议先用 `-c 1 -n 5` 检查配置。压测会产生实际 API 调用，可能产生费用。

## 配置说明

<details>
<summary>Embedding 服务</summary>

用 `--provider` 选择预设；`--base-url` 和 `--model` 可以覆盖预设值。

| Provider | 默认接口 | 默认模型 | 密钥变量 | 接口 / 模型变量 |
| --- | --- | --- | --- | --- |
| `siliconflow` | `https://api.siliconflow.cn/v1/embeddings` | `BAAI/bge-m3` | `EMBEDDING_API_KEY`（可选；未设置时使用 `XINFERENCE_API_KEY`） | `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL` |
| `xinference` | `http://127.0.0.1:9997/v1/embeddings` | 需指定 | `XINFERENCE_API_KEY`（可选） | `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL` |
| `vllm` | `http://127.0.0.1:8000/v1/embeddings` | 需指定 | `VLLM_API_KEY`（可选） | `VLLM_EMBEDDING_URL`、`VLLM_EMBEDDING_MODEL` |

</details>

<details>
<summary>Reranker 服务</summary>

用 `--provider` 选择预设；`--base-url` 和 `--model` 可以覆盖预设值。`--proxy` 指定 HTTP 代理；`--batch-size 0` 不发送服务专用的 `kwargs.batch_size` 参数。vLLM 预设始终不发送该参数。

| Provider | 默认接口 | 默认模型 | 密钥变量 | 接口 / 模型变量 |
| --- | --- | --- | --- | --- |
| `local` | `http://127.0.0.1:9997/v1/rerank` | `bge-reranker-large` | 无 | 无 |
| `siliconflow` | `https://api.siliconflow.cn/v1/rerank` | `BAAI/bge-reranker-v2-m3` | `SILICONFLOW_API_KEY` | 无 |
| `aliyun` | 需指定 | `qwen3-rerank` | `ALIYUN_API_KEY` | `ALIYUN_RERANK_URL` |
| `xunfei` | `https://maas-api.cn-huabei-1.xf-yun.com/v2/rerank` | `xop3qwen8breranker` | `XUNFEI_API_KEY` | 无 |
| `huaweiyun` | `https://api.modelarts-maas.com/v1/rerank` | `bge-reranker-v2-m3` | `HUAWEIYUN_API_KEY` | 无 |
| `xinference` | 需指定 | 需指定 | `XINFERENCE_API_KEY` | `XINFERENCE_RERANK_URL`、`XINFERENCE_RERANK_MODEL` |
| `vllm` | `http://127.0.0.1:8000/v1/rerank` | 需指定 | `VLLM_API_KEY`（可选） | `VLLM_RERANK_URL`、`VLLM_RERANK_MODEL` |

</details>

<details>
<summary>Xinference 语音转文字</summary>

`perf_audio.py` 每次请求都向 `/v1/audio/transcriptions` 以 `multipart/form-data` 上传同一音频文件；文件只会在压测开始前读入内存一次。

| 配置 | 默认值 / 用途 |
| --- | --- |
| `XINFERENCE_AUDIO_URL` / `--base-url` | `http://127.0.0.1:9997/v1/audio/transcriptions` |
| `XINFERENCE_AUDIO_MODEL` / `--model` | `Qwen3-ASR-0.6B`；填写已启动的模型 UID |
| `XINFERENCE_AUDIO_FILE` / `--file` | 必填，音频文件路径 |
| `XINFERENCE_API_KEY` | 可选 Bearer Token |
| `--audio-duration` | 音频时长（秒）；WAV 可自动识别，其他格式可能需要手动指定 |

已知时长时，结果还会显示平均 RTF（平均延迟 / 音频时长）和音频速度（处理的音频秒数 / 总运行时间）。例如，对 30.5 秒的 MP3 添加 `--audio-duration 30.5`。

</details>

<details>
<summary>Dify 知识库和 Chat</summary>

在 `.env` 中设置 `DIFY_BASE_URL`（服务地址，可带或不带 `/v1`）和 `DIFY_QUERY`。知识库检索还需 `DIFY_DATASET_ID`、`DIFY_DATASET_API_KEY`；Chat 使用单独的 `DIFY_CHAT_API_KEY`。非密钥参数可用 `--base-url`、`--query` 或 `--dataset-id` 覆盖。

知识库检索调用 `POST /v1/datasets/{dataset_id}/retrieve`，统计完整请求延迟。Chat 以流式模式调用 `POST /v1/chat-messages`，每次请求创建新会话，统计首个 `message` 事件耗时（`ttft_ms`）、`message_end_ms`、可选的 workflow 事件耗时及总耗时。只有收到 `message_end` 才算 Chat 请求成功。

两个模式均支持 `--timeout` 和 `--no-verify-ssl`；Chat 还支持 `--user`。每次请求使用同一查询。

</details>

## 结果与参数

脚本输出成功率、QPS、平均延迟和 P50/P95/P99。Dify 的延迟汇总只计算成功请求，QPS 为成功请求数除以总运行时间。已知音频时长时，语音测试还会输出 RTF 和音频速度。

完整参数可运行 `python3 <脚本名>.py --help`；Dify 使用 `python3 perf_dify.py retrieve --help` 或 `python3 perf_dify.py chat --help`。

## License

[MIT](LICENSE)
