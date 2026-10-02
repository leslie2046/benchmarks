"""Single interactive requests using the same endpoints as the benchmark scripts."""

import base64
import json
import binascii
import mimetypes
import time
from pathlib import Path
from urllib.parse import quote

import requests

from backend.schemas import PlaygroundRequest


def llm_result(sample, content):
    return {"ok": True, "status_code": 200, "duration_ms": sample["latency_ms"],
            "data": {"content": content, "ttft_ms": sample["ttft_ms"],
                     "tpot_ms": sample.get("tpot_ms"), "output_tokens": sample.get("output_tokens"),
                     "tokens_per_second": sample.get("tokens_per_second")},
            "truncated": len(content) >= 100_000}


def stream_playground(request, config, api_key, resolved=None):
    from shared.llm_stream import iter_chat
    from backend.llm_parameters import resolve_parameters
    wire, snapshot = resolved or resolve_parameters(config, request.llm_parameters, request.max_tokens, api_key)
    try:
        for event in iter_chat(config["base_url"], config.get("model"), api_key,
                               request.query.strip(), request.max_tokens,
                               request.timeout_seconds, capture=True, request_parameters=wire, separate_reasoning=True):
            if event["type"] == "complete":
                result = llm_result(event["sample"], event["content"])
                result["data"].update(reasoning_content=event["reasoning_content"], parameters=snapshot,
                                      metric_scope="TTFT: first output (reasoning or answer); TPOT/tokens/s: reported total output tokens")
                result["truncated"] = result["truncated"] or len(event["reasoning_content"]) >= 100_000
                event = {"type": "result", "result": result}
            yield json.dumps(event, ensure_ascii=False) + "\n"
    except (ValueError, requests.RequestException):
        # Do not send upstream URLs, headers or credentials in streaming errors.
        yield json.dumps({"type": "error", "message": "LLM stream failed or was incomplete; check the service and retry."}) + "\n"


def run_playground(request: PlaygroundRequest, config: dict, api_key: str | None) -> dict:
    benchmark = request.benchmark
    endpoint = config["base_url"]
    model = config.get("model")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    kwargs: dict = {"headers": headers, "timeout": (5, request.timeout_seconds)}
    if benchmark == "llm":
        from shared.llm_stream import stream_chat
        from backend.llm_parameters import resolve_parameters
        wire, snapshot = resolve_parameters(config, request.llm_parameters, request.max_tokens, api_key)
        sample, content = stream_chat(endpoint, model, api_key, request.query.strip(),
                                      request.max_tokens, request.timeout_seconds, capture=True, request_parameters=wire)
        result = llm_result(sample, content)
        result["data"]["parameters"] = snapshot
        return result

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
            dataset_id = config.get("dataset_id") or request.dataset_id
            if not dataset_id:
                raise ValueError("请在 Dify 配置中填写知识库 ID。")
            endpoint = f"{root}/datasets/{quote(dataset_id, safe='')}/retrieve"
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
