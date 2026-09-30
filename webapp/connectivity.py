"""Lightweight endpoint and credential checks before persisting a provider."""

import requests

from webapp.endpoints import endpoint_url


class ConnectivityError(ValueError):
    pass


def check_models(models: list[dict], api_key: str | None) -> None:
    for model in models:
        endpoint = model["base_url"]
        model_key = model.get("api_key") if "api_key" in model else api_key
        model_headers = {"Authorization": f"Bearer {model_key}"} if model_key else {}
        try:
            if model.get("model") and model["benchmark"] in {"embedding", "reranker"}:
                payload = {"model": model["model"], "input": "connectivity test"} if model["benchmark"] == "embedding" else {"model": model["model"], "query": "connectivity test", "documents": ["connectivity test"]}
                response = requests.post(endpoint, headers=model_headers, json=payload, timeout=(3, 10), allow_redirects=False)
            else:
                response = requests.get(endpoint, headers=model_headers, timeout=(3, 5), allow_redirects=False)
        except requests.RequestException as exc:
            raise ConnectivityError(
                f"Cannot connect to {model['benchmark']} endpoint: {exc.__class__.__name__}"
            ) from exc
        if 200 <= response.status_code < 300:
            continue
        # Legacy configs may omit a model ID; a bodyless GET can only check
        # whether the route exists, not whether inference succeeds.
        if not model.get("model") and response.status_code in {400, 405, 422}:
            continue
        if response.status_code in {401, 403}:
            raise ConnectivityError(f"Credential rejected by {model['benchmark']} endpoint (HTTP {response.status_code})")
        if response.status_code == 404 and model.get("provider") in {"xinference", "vllm"}:
            provider_name = "vLLM" if model["provider"] == "vllm" else "Xinference"
            models_url = endpoint_url(model["server_url"], "embedding", "xinference").removesuffix("/embeddings") + "/models"
            try:
                listed = requests.get(models_url, headers=model_headers, timeout=(3, 5), allow_redirects=False)
                if listed.status_code == 200:
                    catalog = listed.json()
                    running = catalog.get("data", catalog) if isinstance(catalog, dict) else catalog
                    ids = [item.get("id") for item in running if isinstance(item, dict)] if isinstance(running, list) else list(running) if isinstance(running, dict) else []
                    if model.get("model") not in ids:
                        sample = ", ".join(str(item) for item in ids[:8]) or "none"
                        raise ConnectivityError(f"The configured {provider_name} server URL does not expose model ID '{model['model']}'. IDs reported by this URL: {sample}. Check this model's server URL or port.")
                    raise ConnectivityError(f"{provider_name} model ID exists, but {model['benchmark']} endpoint returned HTTP 404; check the server URL and model type")
            except requests.RequestException:
                pass
        raise ConnectivityError(f"{model['benchmark']} endpoint returned HTTP {response.status_code}")
