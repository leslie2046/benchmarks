"""Concurrent benchmarks for Dify dataset retrieval and streaming chat APIs."""

import argparse
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from cli.env_loader import load_local_env
from shared.report_writer import write_json_report


load_local_env()


def percentile(values, percent):
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="api", required=True)
    for api in ("retrieve", "chat"):
        sub = subparsers.add_parser(api)
        sub.add_argument("--base-url", help="Dify origin, optionally ending in /v1")
        sub.add_argument("--query", help="Query sent on every request")
        sub.add_argument("-c", "--concurrency", type=int, default=1)
        sub.add_argument("-n", "--requests", type=int, default=10)
        sub.add_argument("--timeout", type=float, default=120)
        sub.add_argument("--no-verify-ssl", action="store_false", dest="verify_ssl")
        sub.add_argument("--json-report", help="Save per-request results as JSON")
        if api == "retrieve":
            sub.add_argument("--dataset-id", help="Dify knowledge base ID")
        else:
            sub.add_argument("--user", default="benchmark", help="Dify end-user ID")
    return parser.parse_args()


def resolve_config(args):
    if args.concurrency < 1 or args.requests < 1 or args.timeout <= 0:
        raise SystemExit("--concurrency, --requests and --timeout must be greater than 0")
    base_url = args.base_url or os.getenv("DIFY_BASE_URL")
    query = args.query or os.getenv("DIFY_QUERY")
    key_name = "DIFY_DATASET_API_KEY" if args.api == "retrieve" else "DIFY_CHAT_API_KEY"
    api_key = os.getenv(key_name)
    if not base_url or not query or not api_key:
        raise SystemExit(f"Set DIFY_BASE_URL, DIFY_QUERY, {key_name} or pass --base-url/--query")
    if args.api == "retrieve":
        dataset_id = args.dataset_id or os.getenv("DIFY_DATASET_ID")
        if not dataset_id:
            raise SystemExit("Set DIFY_DATASET_ID or pass --dataset-id")
    else:
        dataset_id = None
    root = base_url.rstrip("/")
    if not root.endswith("/v1"):
        root += "/v1"
    return root, query, api_key, dataset_id


def run_once(args, url, headers, query):
    start = time.perf_counter()
    result = {"ok": False}
    if args.api == "retrieve":
        payload = {"query": query}
    else:
        payload = {
            "inputs": {}, "query": query, "response_mode": "streaming",
            "conversation_id": "", "auto_generate_name": False, "user": args.user,
        }
    try:
        with requests.Session() as session:
            with session.post(
                url, headers=headers, json=payload, timeout=args.timeout,
                verify=args.verify_ssl, stream=args.api == "chat",
            ) as response:
                response.raise_for_status()
                if args.api == "chat":
                    events = {}
                    for line in response.iter_lines(decode_unicode=True):
                        if not line or not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        event = data.get("event")
                        if event == "error":
                            raise ValueError(f"Dify stream error: {data.get('message', data)}")
                        if event in ("workflow_started", "workflow_finished", "message", "message_end"):
                            events.setdefault(event, (time.perf_counter() - start) * 1000)
                        if event == "message_end":
                            break
                    if "message_end" not in events:
                        raise ValueError("Dify stream ended without message_end")
                    result.update({
                        "workflow_started_ms": events.get("workflow_started"),
                        "workflow_finished_ms": events.get("workflow_finished"),
                        "ttft_ms": events.get("message"),
                        "message_end_ms": events["message_end"],
                    })
                result["ok"] = True
    except (requests.RequestException, ValueError) as exc:
        result["error"] = str(exc)
    result["total_ms"] = (time.perf_counter() - start) * 1000
    return result


def print_metric(name, results):
    values = [item[name] for item in results if item.get(name) is not None]
    if values:
        print(
            f"{name:<21} avg={statistics.mean(values):8.2f} ms  "
            f"p50={percentile(values, 50):8.2f}  "
            f"p95={percentile(values, 95):8.2f}  "
            f"p99={percentile(values, 99):8.2f}  max={max(values):8.2f}"
            f"  samples={len(values)}"
        )


def main():
    args = parse_args()
    root, query, api_key, dataset_id = resolve_config(args)
    path = f"/datasets/{dataset_id}/retrieve" if args.api == "retrieve" else "/chat-messages"
    url = root + path
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    print(f"API: {args.api} | URL: {url} | Concurrency: {args.concurrency} | Requests: {args.requests}")
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(run_once, args, url, headers, query) for _ in range(args.requests)]
        results = []
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            number = len(results)
            if result["ok"]:
                detail = f" ttft={result['ttft_ms']:.2f}ms" if result.get("ttft_ms") is not None else ""
                print(f"Run {number:02d} total={result['total_ms']:.2f}ms{detail}")
            else:
                print(f"Run {number:02d} ERROR {result['error']}")
    elapsed = time.perf_counter() - started
    success = [item for item in results if item["ok"]]
    print("\n===== Result =====")
    print(f"Elapsed Time : {elapsed:.2f}s")
    print(f"Success      : {len(success)}/{args.requests}")
    print(f"Success Rate : {len(success) / args.requests * 100:.2f}%")
    print(f"QPS          : {len(success) / elapsed:.2f}")
    for name in ("workflow_started_ms", "workflow_finished_ms", "ttft_ms", "message_end_ms", "total_ms"):
        print_metric(name, success)
    write_json_report(
        args, f"Dify {args.api}",
        [{**result, "latency_ms": result["total_ms"]} for result in results],
        elapsed,
    )
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
