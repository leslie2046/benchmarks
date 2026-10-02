import argparse
import json
import os
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from shared.env_loader import load_local_env
from shared.providers import RERANK_PROVIDERS
from shared.report_writer import write_json_report


load_local_env()

DOCUMENTS = [
    "Reducing screen brightness can significantly extend the battery life of a smartphone.",
    "Keeping your phone software updated often includes battery optimization improvements.",
    "Closing unused background applications may reduce unnecessary battery consumption.",
    "Using airplane mode in areas with poor signal helps save power.",
    "Fast charging is convenient but does not necessarily improve battery longevity.",
    "Enabling battery saver mode automatically limits background activities.",
    "Replacing an old battery can restore the original battery performance of a device.",
    "Playing graphics-intensive games consumes much more battery than browsing the web.",
    "Wireless charging is generally less energy efficient than wired charging.",
    "Turning off Bluetooth and GPS when they are not needed can reduce power usage.",
]

_thread_local = threading.local()


def parse_args():
    parser = argparse.ArgumentParser(description="Reranker benchmark")
    parser.add_argument("--provider", default="local", choices=RERANK_PROVIDERS.keys())
    parser.add_argument("-c", "--concurrency", type=int, default=10)
    parser.add_argument("-n", "--requests", type=int, default=100)
    parser.add_argument("--model", help="Override the provider model")
    parser.add_argument("--base-url", help="Override the provider endpoint")
    parser.add_argument("--proxy", help="HTTP proxy, for example http://127.0.0.1:21026")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Provider batch_size hint; use 0 to omit provider-specific kwargs",
    )
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--json-report", help="Save per-request results as JSON")
    parser.add_argument("--input-file", help="JSON file containing a custom query and documents")
    return parser.parse_args()


def get_session():
    if not hasattr(_thread_local, "session"):
        _thread_local.session = requests.Session()
    return _thread_local.session


def percentile(values, percent):
    ordered = sorted(values)
    index = min(int(len(ordered) * percent / 100), len(ordered) - 1)
    return ordered[index]


def resolve_config(args):
    provider = RERANK_PROVIDERS[args.provider]
    base_url = args.base_url or (
        os.getenv(provider.get("base_url_env", "")) if provider.get("base_url_env") else None
    ) or provider.get("base_url")
    if not base_url:
        env_name = provider.get("base_url_env", "the provider endpoint variable")
        raise SystemExit(f"Missing endpoint: set {env_name} or pass --base-url")

    api_key_env = provider.get("api_key_env")
    api_key = os.getenv(api_key_env) if api_key_env else None
    if provider.get("api_key_required", bool(api_key_env)) and not api_key:
        raise SystemExit(f"Missing API key: set the {api_key_env} environment variable")

    model = args.model or (
        os.getenv(provider.get("model_env", "")) if provider.get("model_env") else None
    ) or provider.get("model")
    if not model:
        env_name = provider.get("model_env", "--model")
        raise SystemExit(f"Missing model: set {env_name} or pass --model")

    return base_url, model, api_key


def validate_args(args):
    if args.concurrency < 1 or args.requests < 1:
        raise SystemExit("--concurrency and --requests must be greater than 0")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than 0")
    if args.batch_size < 0:
        raise SystemExit("--batch-size must be 0 or greater")


def benchmark(args):
    base_url, model, api_key = resolve_config(args)
    provider = RERANK_PROVIDERS[args.provider]
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    proxies = {"http": args.proxy, "https": args.proxy} if args.proxy else None
    query = "How can I improve smartphone battery life without affecting performance?"
    documents = DOCUMENTS
    if args.input_file:
        with open(args.input_file, encoding="utf-8") as source:
            test_input = json.load(source)
        query = (test_input.get("query") or "").strip() or query
        documents = [item.strip() for item in test_input.get("documents", []) if item.strip()] or documents
    payload = {
        "model": model,
        "query": query,
        "documents": documents,
        "return_documents": True,
        "top_n": 4,
    }
    if args.batch_size and provider.get("supports_batch_size", True):
        payload["kwargs"] = json.dumps({"batch_size": args.batch_size})

    def worker():
        start = time.perf_counter()
        try:
            response = get_session().post(
                base_url,
                headers=headers,
                json=payload,
                proxies=proxies,
                timeout=args.timeout,
            )
            latency = (time.perf_counter() - start) * 1000
            if 200 <= response.status_code < 300:
                return True, latency
            print(f"HTTP {response.status_code}: {response.text[:500]}")
            return False, latency
        except requests.RequestException as exc:
            latency = (time.perf_counter() - start) * 1000
            print(f"Request failed: {exc}")
            return False, latency

    print(
        f"Provider: {args.provider} | Base URL: {base_url} | Model: {model} | "
        f"Concurrency: {args.concurrency} | Requests: {args.requests}"
    )
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(worker) for _ in range(args.requests)]
        samples = [future.result() for future in as_completed(futures)]
    elapsed = time.perf_counter() - started

    latencies = [latency for _, latency in samples]
    successes = sum(ok for ok, _ in samples)
    print("\n===== Result =====")
    print(f"Elapsed Time : {elapsed:.2f}s")
    print(f"Success      : {successes}/{args.requests}")
    print(f"Success Rate : {successes / args.requests * 100:.2f}%")
    print(f"QPS          : {args.requests / elapsed:.2f}")
    print(f"Average      : {statistics.mean(latencies):.2f} ms")
    for percent in (50, 95, 99):
        print(f"P{percent:<2}          : {percentile(latencies, percent):.2f} ms")
    print(f"Max          : {max(latencies):.2f} ms")
    print(f"Min          : {min(latencies):.2f} ms")
    write_json_report(
        args, "Reranker",
        [{"ok": ok, "latency_ms": latency} for ok, latency in samples],
        elapsed, provider=args.provider,
    )


if __name__ == "__main__":
    cli_args = parse_args()
    validate_args(cli_args)
    benchmark(cli_args)
