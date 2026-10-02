"""Client-observed streaming latency; chunks are deliberately not treated as tokens."""
import json
import time

import requests


def iter_chat(endpoint, model, api_key, query, max_tokens=256, timeout=60, *, capture=False, capture_reasoning=True, require_complete=False, request_parameters=None, separate_reasoning=False):
    started = time.perf_counter()
    first = None
    tokens = None
    finished = False
    content = ""
    reasoning = ""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {
        "model": model, "messages": [{"role": "user", "content": query}],
        "max_tokens": max_tokens, "stream": True, "stream_options": {"include_usage": True},
    }
    if request_parameters:
        if set(request_parameters) - {"max_tokens", "temperature", "top_p", "thinking", "enable_thinking", "reasoning_effort", "thinking_budget", "chat_template_kwargs"}:
            raise ValueError("Unsupported LLM request fields")
        payload.update(request_parameters)
    with requests.post(endpoint, headers=headers, json=payload, stream=True, timeout=(min(5, timeout), timeout), allow_redirects=False) as response:
        response.raise_for_status()
        response.encoding = "utf-8"
        # Small chunks prevent requests' default buffering from inflating TTFT.
        for line in response.iter_lines(chunk_size=1, decode_unicode=True):
            if time.perf_counter() - started > timeout:
                raise requests.Timeout("LLM stream exceeded the request deadline")
            if not line or not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if raw == "[DONE]":
                finished = True
                break
            event = json.loads(raw)
            if event.get("error"):
                raise ValueError("LLM stream returned an error")
            usage = event.get("usage") or {}
            count = usage.get("completion_tokens")
            if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                tokens = count
            choices = event.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            delta = choice.get("delta") or {}
            parts = [("reasoning", delta.get("reasoning_content")), ("answer", delta.get("content"))] if separate_reasoning else [("answer", delta.get("content") or delta.get("reasoning_content"))]
            for channel, text in parts:
                if text:
                    if first is None:
                        first = time.perf_counter()
                    if capture:
                        if separate_reasoning and channel == "reasoning":
                            reasoning = (reasoning + text)[:100_000]
                        elif capture_reasoning or delta.get("content"):
                            content = (content + text)[:100_000]
                    yield {"type": "delta", "content": text, "channel": channel, "ttft_ms": (first - started) * 1000}
            if choice.get("finish_reason") is not None:
                if require_complete and choice["finish_reason"] not in {"stop"}:
                    raise ValueError("LLM report was truncated or not completed normally")
                finished = True
    ended = time.perf_counter()
    if first is None or not finished:
        raise ValueError("LLM response was empty, non-streaming, or incomplete")
    latency = (ended - started) * 1000
    ttft = (first - started) * 1000
    sample = {"ok": True, "latency_ms": latency, "ttft_ms": ttft}
    if tokens is not None:
        sample["output_tokens"] = tokens
        if tokens > 1:
            sample["tpot_ms"] = (latency - ttft) / (tokens - 1)
            if sample["tpot_ms"] > 0:
                sample["tokens_per_second"] = 1000 / sample["tpot_ms"]
    yield {"type": "complete", "sample": sample, "content": content, "reasoning_content": reasoning}


def stream_chat(*args, **kwargs):
    for event in iter_chat(*args, **kwargs):
        if event["type"] == "complete":
            return event["sample"], event["content"]
