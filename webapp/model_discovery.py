"""Read-only model discovery for providers with a documented /v1/models API."""

from urllib.parse import urlsplit, urlunsplit

import requests

from webapp.endpoints import server_root


DISCOVERABLE_PROVIDERS = {"siliconflow", "xinference", "vllm"}


class ModelDiscoveryError(ValueError):
    pass


def _models_url(server_url: str) -> str:
    parts = urlsplit(server_root(server_url))
    path = parts.path.rstrip("/")
    if not path.endswith("/v1"):
        path += "/v1"
    return urlunsplit((parts.scheme, parts.netloc, path + "/models", "", ""))


def _fetch(url: str, api_key: str | None, params: dict | None = None) -> list[dict]:
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
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        raise ModelDiscoveryError("Model list response has no data array")
    return [item for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)]


def _benchmark(item: dict) -> str | None:
    raw = str(item.get("model_type") or item.get("type") or item.get("sub_type") or "").lower()
    if raw in {"embedding", "embed"}:
        return "embedding"
    if raw in {"rerank", "reranker"}:
        return "reranker"
    if raw in {"audio", "speech-to-text", "asr"}:
        return "audio"
    return None


def list_models(provider: str, server_url: str, api_key: str | None) -> list[dict]:
    if provider not in DISCOVERABLE_PROVIDERS:
        raise ModelDiscoveryError("This provider does not support model discovery")
    url = _models_url(server_url)
    if provider == "siliconflow":
        all_models = _fetch(url, api_key)
        groups = (("embedding", "embedding"), ("reranker", "reranker"))
        supported = {
            item["id"]: benchmark
            for sub_type, benchmark in groups
            for item in _fetch(url, api_key, {"sub_type": sub_type})
        }
        entries = [{"id": item["id"], "benchmark": supported.get(item["id"])} for item in all_models]
        entries += [{"id": model_id, "benchmark": benchmark} for model_id, benchmark in supported.items() if model_id not in {item["id"] for item in all_models}]
    else:
        entries = [{"id": item["id"], "benchmark": _benchmark(item)} for item in _fetch(url, api_key)]
    unique = {item["id"]: item for item in entries if 0 < len(item["id"]) <= 256}
    return sorted(unique.values(), key=lambda item: (item["benchmark"] or "zz", item["id"].casefold()))[:500]


def verify_key(provider: str, server_url: str, api_key: str | None) -> None:
    if provider not in DISCOVERABLE_PROVIDERS:
        raise ModelDiscoveryError("This provider does not support model-list verification")
    _fetch(_models_url(server_url), api_key)
