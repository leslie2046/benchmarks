"""Provider presets without credentials.

Secrets are referenced by environment-variable name and are never stored here.
"""

EMBEDDING_PROVIDERS = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1/embeddings",
        "model": "BAAI/bge-m3",
        "api_key_env": "EMBEDDING_API_KEY",
        "api_key_fallback_env": "XINFERENCE_API_KEY",
        "base_url_env": "EMBEDDING_BASE_URL",
        "model_env": "EMBEDDING_MODEL",
        "api_key_required": False,
    },
    "xinference": {
        "base_url": "http://127.0.0.1:9997/v1/embeddings",
        "model": None,
        "api_key_env": "XINFERENCE_API_KEY",
        "base_url_env": "EMBEDDING_BASE_URL",
        "model_env": "EMBEDDING_MODEL",
        "api_key_required": False,
    },
    "vllm": {
        "base_url": "http://127.0.0.1:8000/v1/embeddings",
        "model": None,
        "api_key_env": "VLLM_API_KEY",
        "base_url_env": "VLLM_EMBEDDING_URL",
        "model_env": "VLLM_EMBEDDING_MODEL",
        "api_key_required": False,
    },
}


RERANK_PROVIDERS = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1/rerank",
        "model": "BAAI/bge-reranker-v2-m3",
        "api_key_env": "SILICONFLOW_API_KEY",
    },
    "aliyun": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-api/v1/reranks",
        "model": "qwen3-rerank",
        "api_key_env": "ALIYUN_API_KEY",
        "base_url_env": "ALIYUN_RERANK_URL",
    },
    "xunfei": {
        "base_url": "https://maas-api.cn-huabei-1.xf-yun.com/v2/rerank",
        "model": "xop3qwen8breranker",
        "api_key_env": "XUNFEI_API_KEY",
    },
    "huaweiyun": {
        "base_url": "https://api.modelarts-maas.com/v1/rerank",
        "model": "bge-reranker-v2-m3",
        "api_key_env": "HUAWEIYUN_API_KEY",
    },
    "xinference": {
        "base_url": None,
        "model": None,
        "api_key_env": "XINFERENCE_API_KEY",
        "base_url_env": "XINFERENCE_RERANK_URL",
        "model_env": "XINFERENCE_RERANK_MODEL",
    },
    "vllm": {
        "base_url": "http://127.0.0.1:8000/v1/rerank",
        "model": None,
        "api_key_env": "VLLM_API_KEY",
        "base_url_env": "VLLM_RERANK_URL",
        "model_env": "VLLM_RERANK_MODEL",
        "api_key_required": False,
        "supports_batch_size": False,
    },
}


# Backwards-compatible name used by older imports.
PROVIDERS = RERANK_PROVIDERS
