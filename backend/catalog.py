import os
from copy import deepcopy

from shared.providers import EMBEDDING_PROVIDERS, RERANK_PROVIDERS, LLM_PROVIDERS, AUDIO_PROVIDERS


OFFICIAL_PROVIDER_NAMES = {
    "deepseek": "DeepSeek",
    "siliconflow": "SiliconFlow",
    "aliyun": "Alibaba Cloud Model Studio",
    "huaweiyun": "ModelArts Studio (MaaS)",
    "xunfei": "iFLYTEK Xingchen MaaS",
    "vllm": "vLLM",
}


def _resolved_provider(provider_id: str, raw: dict) -> dict:
    item = deepcopy(raw)
    base_url = os.getenv(item.get("base_url_env", "")) or item.get("base_url")
    model = os.getenv(item.get("model_env", "")) or item.get("model")
    key_env = item.get("api_key_env")
    fallback_env = item.get("api_key_fallback_env")
    credential_configured = bool(
        (key_env and os.getenv(key_env)) or (fallback_env and os.getenv(fallback_env))
    )
    return {
        "id": provider_id,
        "label": OFFICIAL_PROVIDER_NAMES.get(provider_id, provider_id.replace("_", " ").title()),
        "model": model,
        "endpoint_configured": bool(base_url),
        "credential_configured": credential_configured,
        "credential_required": bool(item.get("api_key_required", bool(key_env))),
    }


def get_catalog() -> dict:
    return {
        "benchmarks": [
            {"id": "llm", "label": "LLM", "providers": [
                _resolved_provider(provider_id, raw) for provider_id, raw in LLM_PROVIDERS.items()
            ]},
            {
                "id": "embedding",
                "label": "Embedding",
                "providers": [
                    _resolved_provider(provider_id, raw)
                    for provider_id, raw in EMBEDDING_PROVIDERS.items()
                ],
            },
            {
                "id": "reranker",
                "label": "Reranker",
                "providers": [
                    _resolved_provider(provider_id, raw)
                    for provider_id, raw in RERANK_PROVIDERS.items()
                ],
            },
            {
                "id": "audio",
                "label": "Audio",
                "providers": [
                    _resolved_provider(provider_id, raw)
                    for provider_id, raw in AUDIO_PROVIDERS.items()
                ],
            },
            {
                "id": "dify-retrieve",
                "label": "Dify Retrieve",
                "providers": [_dify_provider("dataset")],
            },
            {
                "id": "dify-chat",
                "label": "Dify Chat",
                "providers": [_dify_provider("chat")],
            },
        ]
    }


def _dify_provider(mode: str) -> dict:
    key_env = "DIFY_DATASET_API_KEY" if mode == "dataset" else "DIFY_CHAT_API_KEY"
    return {
        "id": "dify",
        "label": "Dify",
        "model": None,
        "endpoint_configured": bool(os.getenv("DIFY_BASE_URL")),
        "credential_configured": bool(os.getenv(key_env)),
        "credential_required": True,
    }


def allowed_provider_ids(benchmark: str) -> set[str]:
    for item in get_catalog()["benchmarks"]:
        if item["id"] == benchmark:
            return {provider["id"] for provider in item["providers"]}
    return set()
