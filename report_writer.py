"""Write privacy-conscious benchmark JSON for the offline HTML viewer."""

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path


METRICS = (
    "latency_ms",
    "ttft_ms",
    "message_end_ms",
    "workflow_started_ms",
    "workflow_finished_ms",
)


def percentile(values, percent):
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def metric_summary(samples, name):
    values = [row[name] for row in samples if row["ok"] and row.get(name) is not None]
    if not values:
        return None
    return {
        "count": len(values),
        "avg": statistics.mean(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "min": min(values),
        "max": max(values),
    }


def write_json_report(args, benchmark, samples, elapsed_seconds, *, provider=None, audio_duration=None):
    """Write sanitized results; never persist URLs, keys, queries, or response bodies."""
    if not args.json_report:
        return

    json_path = Path(args.json_report)
    rows = []
    for index, sample in enumerate(samples, 1):
        row = {"completion_order": index, "ok": bool(sample["ok"])}
        for name in METRICS:
            value = sample.get(name)
            if value is not None:
                row[name] = round(float(value), 4)
        rows.append(row)

    successes = sum(row["ok"] for row in rows)
    metrics = {}
    for name in METRICS:
        summary = metric_summary(rows, name)
        if summary:
            metrics[name] = summary
    report = {
        "schema_version": 1,
        "benchmark": benchmark,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "concurrency": args.concurrency,
        "requests": len(rows),
        "elapsed_seconds": round(elapsed_seconds, 4),
        "success_count": successes,
        "failure_count": len(rows) - successes,
        "success_rate": successes / len(rows) * 100 if rows else 0,
        "qps_success": successes / elapsed_seconds if elapsed_seconds else 0,
        "metrics": metrics,
        "samples": rows,
    }
    if provider:
        report["provider"] = provider
    if audio_duration:
        report["audio_duration_seconds"] = audio_duration

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"JSON Report  : {json_path.resolve()}")
