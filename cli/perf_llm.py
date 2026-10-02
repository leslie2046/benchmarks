"""OpenAI-compatible streaming LLM benchmark with TTFT and usage-based TPOT."""
import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from shared.env_loader import load_local_env
from shared.providers import LLM_PROVIDERS
from shared.report_writer import write_json_report
from shared.llm_stream import stream_chat


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=LLM_PROVIDERS, default="siliconflow")
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--input-file")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("-c", "--concurrency", type=int, default=5)
    parser.add_argument("-n", "--requests", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--json-report")
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 10000 or not 1 <= args.requests <= 100000 or not 2 <= args.max_tokens <= 8192 or args.timeout <= 0:
        parser.error("Invalid concurrency, requests, max tokens or timeout")
    preset = LLM_PROVIDERS[args.provider]
    endpoint = args.base_url or os.getenv(preset["base_url_env"]) or preset["base_url"]
    model = args.model or os.getenv(preset["model_env"]) or preset.get("model")
    if not endpoint or not model:
        parser.error("Configure the model and chat completions endpoint")
    key = os.getenv(preset["api_key_env"])
    if preset.get("api_key_required") and not key:
        parser.error(f"Configure {preset['api_key_env']} before testing")
    query = "Explain how large language models generate text in simple terms."
    if args.input_file:
        query = json.loads(Path(args.input_file).read_text(encoding="utf-8")).get("query") or query

    def request():
        try:
            return stream_chat(endpoint, model, key, query, args.max_tokens, args.timeout)[0]
        except Exception as exc:
            print(f"Request failed: {type(exc).__name__}", flush=True)
            return {"ok": False}

    started = time.perf_counter()
    samples = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for index, future in enumerate(as_completed([pool.submit(request) for _ in range(args.requests)]), 1):
            samples.append(future.result())
            print(f"Run {index}/{args.requests}", flush=True)
    write_json_report(args, "llm", samples, time.perf_counter() - started, provider=args.provider)
    return 0 if any(row["ok"] for row in samples) else 1


if __name__ == "__main__":
    raise SystemExit(main())
