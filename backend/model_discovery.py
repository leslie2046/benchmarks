"""Read-only model discovery with provider-specific routes and response adapters."""

from urllib.parse import urlsplit, urlunsplit

import requests

from backend.endpoints import server_root


DISCOVERABLE_PROVIDERS = {"siliconflow", "xinference", "vllm", "deepseek", "aliyun", "huaweiyun"}
MAX_DISCOVERY_MODELS = 10000
MAX_DISCOVERY_PAGES = 100

# Explicit IDs verified against Model Studio's embedding/rerank catalog.
# TR is a coarse retrieval capability, not a reliable final benchmark type.
# https://help.aliyun.com/zh/model-studio/embedding-rerank-model
ALIYUN_MODEL_TYPES = {
    **dict.fromkeys(("qwen3-rerank", "qwen3-vl-rerank", "qwen3.7-text-rerank", "gte-rerank-v2"), "reranker"),
    **dict.fromkeys(("text-embedding-v1", "text-embedding-v2", "text-embedding-v3", "text-embedding-v4",
                     "qwen3.7-text-embedding", "qwen3.7-text-embedding-flash", "qwen3-vl-embedding",
                     "qwen2.5-vl-embedding", "tongyi-embedding-vision-plus", "tongyi-embedding-vision-flash",
                     "tongyi-embedding-vision-plus-2026-03-06", "tongyi-embedding-vision-flash-2026-03-06"), "embedding"),
}

HUAWEI_MODEL_TYPES = {"bge-m3": "embedding", "bge-reranker-v2-m3": "reranker"}

TYPE_ALIASES = {
    **dict.fromkeys(("embedding", "embeddings", "embed", "text-embedding"), "embedding"),
    **dict.fromkeys(("rerank", "reranker", "reranking", "text-rerank"), "reranker"),
    **dict.fromkeys(("audio", "speech-to-text", "asr"), "audio"),
    **dict.fromkeys(("llm", "chat", "text-generation", "tg", "reasoning"), "llm"),
}


def _type_alias(value: object) -> str | None:
    return TYPE_ALIASES.get(value.strip().lower().replace("_", "-")) if isinstance(value, str) else None


class ModelDiscoveryError(ValueError):
    pass


def _models_url(server_url: str, provider: str | None = None) -> str:
    parts = urlsplit(server_root(server_url))
    path = parts.path.rstrip("/")
    if provider in {"aliyun", "huaweiyun"}:
        # Keep the configured host/region and any gateway prefix. Inference
        # compatibility paths are not the providers' discovery API roots.
        for suffix in ("/api/v1/models", "/v2/models", "/compatible-mode/v1", "/compatible-mode", "/compatible-api/v1", "/compatible-api", "/api/v1", "/v1", "/v2"):
            if path.endswith(suffix):
                path = path[:-len(suffix)]
                break
        route = "/api/v1/models" if provider == "aliyun" else "/v2/models"
        return urlunsplit((parts.scheme, parts.netloc, path + route, "", ""))
    if provider != "deepseek" and not path.endswith("/v1"):
        path += "/v1"
    return urlunsplit((parts.scheme, parts.netloc, path + "/models", "", ""))


def _request_json(url: str, api_key: str | None, params: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=(3, 12), allow_redirects=False)
    except requests.RequestException as exc:
        raise ModelDiscoveryError(f"Cannot connect to model list: {exc.__class__.__name__}") from exc
    if response.status_code in {401, 403}:
        raise ModelDiscoveryError(f"API key was rejected (HTTP {response.status_code})")
    if not 200 <= response.status_code < 300:
        raise ModelDiscoveryError(f"Model list returned HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError as exc:
        raise ModelDiscoveryError("Model list did not return JSON") from exc
    if not isinstance(body, dict):
        raise ModelDiscoveryError("Model list response is not an object")
    if body.get("success") is False:
        raise ModelDiscoveryError("Model list request was rejected by the provider")
    return body


def _fetch(url: str, api_key: str | None, params: dict | None = None) -> list[dict]:
    body = _request_json(url, api_key, params)
    data = body.get("data")
    if not isinstance(data, list):
        raise ModelDiscoveryError("Model list response has no data array")
    return [item for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)]


def fetch_model_entries(provider: str, url: str, api_key: str | None) -> list[dict]:
    """Normalize list responses for both discovery and capability refresh."""
    if provider != "aliyun":
        return _fetch(url, api_key)
    entries = {}
    received = 0
    for page in range(1, MAX_DISCOVERY_PAGES + 1):
        body = _request_json(url, api_key, {"page_no": page, "page_size": 100})
        output = body.get("output")
        if not isinstance(output, dict) or not isinstance(output.get("models"), list):
            raise ModelDiscoveryError("Model list response has no output.models array")
        rows = output["models"]
        total = output.get("total")
        if type(total) is not int or total < 0:
            raise ModelDiscoveryError("Model list response has invalid output.total")
        before = len(entries)
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("model"), str):
                continue
            entry = {**row, "id": row["model"]}
            info = row.get("model_info")
            if isinstance(info, dict):
                for field in ("context_window", "max_output_tokens"):
                    if type(info.get(field)) is int and info[field] > 0:
                        entry[field] = info[field]
            entries[entry["id"]] = entry
        received += len(rows)
        if total > MAX_DISCOVERY_MODELS or len(entries) > MAX_DISCOVERY_MODELS:
            raise ModelDiscoveryError("Model list exceeds the 10000-model discovery safety limit")
        if rows and page > 1 and len(entries) == before:
            raise ModelDiscoveryError("Model list pagination did not advance")
        if received >= total:
            return list(entries.values())
        if not rows or len(entries) == before:
            raise ModelDiscoveryError("Model list pagination did not advance")
    raise ModelDiscoveryError("Model list pagination exceeded the page limit")


def _benchmark(item: dict, provider: str | None = None) -> str | None:
    for field in ("model_type", "type", "sub_type", "task"):
        explicit_type = _type_alias(item.get(field))
        if explicit_type:
            return explicit_type
    catalog = {"aliyun": ALIYUN_MODEL_TYPES, "huaweiyun": HUAWEI_MODEL_TYPES}.get(provider, {})
    known_type = catalog.get(item.get("id") or item.get("model"))
    if known_type:
        return known_type
    capabilities = item.get("capabilities")
    if isinstance(capabilities, list):
        types = {_type_alias(value) for value in capabilities}
        if "reranker" in types:
            return "reranker"
        if "embedding" in types or "TR" in capabilities:
            return "embedding"
        if "audio" in types:
            return "audio"
        if "llm" in types:
            return "llm"
    return None


def list_models(provider: str, server_url: str, api_key: str | None) -> list[dict]:
    if provider not in DISCOVERABLE_PROVIDERS:
        raise ModelDiscoveryError("This provider does not support model discovery")
    url = _models_url(server_url, provider)
    if provider == "siliconflow":
        all_models = _fetch(url, api_key)
        groups = (("embedding", "embedding"), ("reranker", "reranker"), ("chat", "llm"), ("speech-to-text", "audio"))
        supported = {
            item["id"]: benchmark
            for sub_type, benchmark in groups
            for item in _fetch(url, api_key, {"sub_type": sub_type})
        }
        entries = [{"id": item["id"], "benchmark": supported.get(item["id"]) or _benchmark(item, provider)} for item in all_models]
        entries += [{"id": model_id, "benchmark": benchmark} for model_id, benchmark in supported.items() if model_id not in {item["id"] for item in all_models}]
    else:
        entries = [{"id": item["id"], "benchmark": "llm" if provider == "deepseek" else _benchmark(item, provider)} for item in fetch_model_entries(provider, url, api_key)]
    unique = {item["id"]: item for item in entries if 0 < len(item["id"]) <= 256}
    if len(unique) > MAX_DISCOVERY_MODELS:
        raise ModelDiscoveryError("Model list exceeds the 10000-model discovery safety limit")
    return sorted(unique.values(), key=lambda item: (item["benchmark"] or "zz", item["id"].casefold()))


def verify_key(provider: str, server_url: str, api_key: str | None) -> None:
    if provider not in DISCOVERABLE_PROVIDERS:
        raise ModelDiscoveryError("This provider does not support model-list verification")
    fetch_model_entries(provider, _models_url(server_url, provider), api_key)
