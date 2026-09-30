import os
from copy import deepcopy
import re
import uuid

from providers import EMBEDDING_PROVIDERS, RERANK_PROVIDERS
from webapp.store import utc_now
from webapp.validation import is_placeholder_url


OFFICIAL_PROVIDER_NAMES = {
    "siliconflow": "SiliconFlow",
    "aliyun": "Alibaba Cloud Model Studio",
    "huaweiyun": "ModelArts Studio (MaaS)",
    "xunfei": "SparkDesk",
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
                    {
                        "id": "xinference",
                        "label": "Xinference",
                        "model": os.getenv("XINFERENCE_AUDIO_MODEL", "Qwen3-ASR-0.6B"),
                        "endpoint_configured": bool(os.getenv("XINFERENCE_AUDIO_URL")),
                        "credential_configured": bool(os.getenv("XINFERENCE_API_KEY")),
                        "credential_required": False,
                    }
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


def default_service_configs() -> list[dict]:
    """Create stable, persisted configs from the existing CLI provider presets."""
    now = utc_now()
    configs = []
    for benchmark in get_catalog()["benchmarks"]:
        for provider in benchmark["providers"]:
            provider_id = provider["id"]
            slug = re.sub(r"[^a-z0-9-]+", "-", f"{benchmark['id']}-{provider_id}".lower()).strip("-")
            raw = None
            if benchmark["id"] == "embedding":
                raw = EMBEDDING_PROVIDERS[provider_id]
            elif benchmark["id"] == "reranker":
                raw = RERANK_PROVIDERS[provider_id]
            config = {
                "id": slug or uuid.uuid4().hex[:12],
                "name": provider["label"],
                "benchmark": benchmark["id"],
                "provider": provider_id,
                "base_url": (
                    os.getenv(raw.get("base_url_env", "")) or raw.get("base_url")
                    if raw else os.getenv("DIFY_BASE_URL") if provider_id == "dify" else os.getenv("XINFERENCE_AUDIO_URL")
                ),
                "model": provider["model"],
                "api_key_env": raw.get("api_key_env") if raw else (
                    "DIFY_DATASET_API_KEY" if benchmark["id"] == "dify-retrieve" else
                    "DIFY_CHAT_API_KEY" if benchmark["id"] == "dify-chat" else "XINFERENCE_API_KEY"
                ),
                "created_at": now,
                "updated_at": now,
            }
            if is_placeholder_url(config["base_url"]):
                config["base_url"] = None
            configs.append(config)
    return configs
