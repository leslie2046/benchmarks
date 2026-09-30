"""Single interactive requests using the same endpoints as the benchmark scripts."""

import base64
import binascii
import mimetypes
import time
from pathlib import Path
from urllib.parse import quote

import requests

from webapp.schemas import PlaygroundRequest


def run_playground(request: PlaygroundRequest, config: dict, api_key: str | None) -> dict:
    benchmark = request.benchmark
    endpoint = config["base_url"]
    model = config.get("model")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    kwargs: dict = {"headers": headers, "timeout": (5, request.timeout_seconds)}

    if benchmark == "embedding":
        kwargs["json"] = {"model": model, "input": request.text.strip()}
    elif benchmark == "reranker":
        kwargs["json"] = {
            "model": model,
            "query": request.query.strip(),
            "documents": request.documents,
            "return_documents": True,
            "top_n": min(4, len(request.documents)),
        }
    elif benchmark == "audio":
        try:
            audio = base64.b64decode(request.audio_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid audio file encoding") from exc
        if not audio or len(audio) > 5_000_000:
            raise ValueError("Audio file must be between 1 byte and 5 MB")
        name = Path(request.audio_name or "audio.wav").name
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        kwargs["data"] = {"model": model}
        kwargs["files"] = {"file": (name, audio, content_type)}
    else:
        if not api_key:
            raise ValueError("Dify API key is required")
        root = endpoint.rstrip("/")
        if not root.endswith("/v1"):
            root += "/v1"
        if benchmark == "dify-retrieve":
            endpoint = f"{root}/datasets/{quote(request.dataset_id, safe='')}/retrieve"
            kwargs["json"] = {"query": request.query.strip()}
        else:
            endpoint = f"{root}/chat-messages"
            kwargs["json"] = {
                "inputs": {}, "query": request.query.strip(),
                "response_mode": "blocking", "conversation_id": "",
                "auto_generate_name": False, "user": "perflab-playground",
            }

    started = time.perf_counter()
    response = requests.post(endpoint, **kwargs)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    truncated = len(response.content) > 100_000
    body = response.content[:100_000].decode(response.encoding or "utf-8", errors="replace")
    if not truncated:
        try:
            import json
            data = json.loads(body)
        except ValueError:
            data = body
    else:
        data = body
    return {
        "ok": 200 <= response.status_code < 300,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
        "data": data,
        "truncated": truncated,
    }
