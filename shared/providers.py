"""Provider presets without credentials.

Secrets are referenced by environment-variable name and are never stored here.
"""

LLM_PROVIDERS = {
    provider: {
        "base_url": url, "model": None, "api_key_env": key,
        "base_url_env": f"{provider.upper()}_LLM_URL", "model_env": "LLM_MODEL",
        "api_key_required": False,
    }
    for provider, url, key in (
        ("siliconflow", "https://api.siliconflow.cn/v1/chat/completions", "SILICONFLOW_API_KEY"),
        ("deepseek", "https://api.deepseek.com/chat/completions", "DEEPSEEK_API_KEY"),
        ("xinference", None, "XINFERENCE_API_KEY"),
        ("vllm", None, "VLLM_API_KEY"),
        ("aliyun", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", "ALIYUN_API_KEY"),
        ("huaweiyun", "https://api.modelarts-maas.com/v1/chat/completions", "HUAWEIYUN_API_KEY"),
        ("xunfei", None, "XUNFEI_API_KEY"),
    )
}

LLM_PROVIDERS["deepseek"].update(model="deepseek-flash", api_key_required=True)


AUDIO_PROVIDERS = {
    provider: {
        "base_url": url, "model": model, "api_key_env": key,
        "base_url_env": f"{provider.upper()}_AUDIO_URL",
        "model_env": f"{provider.upper()}_AUDIO_MODEL", "api_key_required": False,
    }
    for provider, url, model, key in (
        ("xinference", None, "Qwen3-ASR-0.6B", "XINFERENCE_API_KEY"),
        ("siliconflow", "https://api.siliconflow.cn/v1/audio/transcriptions", "FunAudioLLM/SenseVoiceSmall", "SILICONFLOW_API_KEY"),
        ("vllm", None, None, "VLLM_API_KEY"),
    )
}


EMBEDDING_PROVIDERS = {
    "huaweiyun": {
        "base_url": "https://api.modelarts-maas.com/v1/embeddings",
        "model": "bge-m3",
        "api_key_env": "HUAWEIYUN_API_KEY",
        "base_url_env": "HUAWEIYUN_EMBEDDING_URL",
        "model_env": "HUAWEIYUN_EMBEDDING_MODEL",
        "api_key_required": True,
    },
    "xunfei": {
        "base_url": "https://maas-api.cn-huabei-1.xf-yun.com/v2/embeddings",
        "model": None,
        "api_key_env": "XUNFEI_API_KEY",
        "base_url_env": "XUNFEI_EMBEDDING_URL",
        "model_env": "XUNFEI_EMBEDDING_MODEL",
        "api_key_required": True,
    },
    "aliyun": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        "model": "text-embedding-v4",
        "api_key_env": "ALIYUN_API_KEY",
        "base_url_env": "ALIYUN_EMBEDDING_URL",
        "model_env": "ALIYUN_EMBEDDING_MODEL",
        "api_key_required": True,
    },
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
