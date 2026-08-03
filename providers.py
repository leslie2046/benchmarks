"""Provider presets without credentials.

Secrets are referenced by environment-variable name and are never stored here.
"""

PROVIDERS = {
    "local": {
        "base_url": "http://127.0.0.1:9997/v1/rerank",
        "model": "bge-reranker-large",
        "api_key_env": None,
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1/rerank",
        "model": "BAAI/bge-reranker-v2-m3",
        "api_key_env": "SILICONFLOW_API_KEY",
    },
    "aliyun": {
        "base_url": None,
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
}
