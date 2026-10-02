import argparse
import mimetypes
import os
import statistics
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from shared.env_loader import load_local_env
from shared.report_writer import write_json_report
from shared.providers import AUDIO_PROVIDERS


load_local_env()

_thread_local = threading.local()


def parse_args():
    parser = argparse.ArgumentParser(
        description="OpenAI-compatible audio transcription benchmark"
    )
    parser.add_argument("--provider", choices=list(AUDIO_PROVIDERS), default="xinference")
    parser.add_argument(
        "--base-url",
        default=None,
        help="Transcription endpoint (default: XINFERENCE_AUDIO_URL or local Xinference)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Launched Xinference model UID (default: XINFERENCE_AUDIO_MODEL or Qwen3-ASR-0.6B)",
    )
    parser.add_argument(
        "--file",
        default=os.getenv("XINFERENCE_AUDIO_FILE"),
        help="Audio file sent by every request (or set XINFERENCE_AUDIO_FILE)",
    )
    parser.add_argument(
        "--audio-duration",
        type=float,
        help="Audio duration in seconds; WAV duration is detected automatically",
    )
    parser.add_argument("-c", "--concurrency", type=int, default=5)
    parser.add_argument("-n", "--requests", type=int, default=100)
    parser.add_argument("--proxy", help="HTTP proxy, for example http://127.0.0.1:7890")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--json-report", help="Save per-request results as JSON")
    args = parser.parse_args()
    preset = AUDIO_PROVIDERS[args.provider]
    args.base_url = args.base_url or os.getenv(preset["base_url_env"]) or preset["base_url"]
    if not args.base_url and args.provider == "xinference":
        args.base_url = "http://127.0.0.1:9997/v1/audio/transcriptions"
    args.model = args.model or os.getenv(preset["model_env"]) or preset["model"]
    return args


def get_session():
    if not hasattr(_thread_local, "session"):
        _thread_local.session = requests.Session()
    return _thread_local.session


def percentile(values, percent):
    ordered = sorted(values)
    index = min(int(len(ordered) * percent / 100), len(ordered) - 1)
    return ordered[index]


def detect_wav_duration(audio_path):
    try:
        with wave.open(str(audio_path), "rb") as audio:
            frame_rate = audio.getframerate()
            if frame_rate:
                return audio.getnframes() / frame_rate
    except (EOFError, wave.Error):
        pass
    return None


def validate_args(args):
    if not args.base_url:
        raise SystemExit("Missing endpoint: set XINFERENCE_AUDIO_URL or pass --base-url")
    if not args.model:
        raise SystemExit("Missing model UID: set XINFERENCE_AUDIO_MODEL or pass --model")
    if args.concurrency < 1 or args.requests < 1:
        raise SystemExit("--concurrency and --requests must be greater than 0")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than 0")
    if args.audio_duration is not None and args.audio_duration <= 0:
        raise SystemExit("--audio-duration must be greater than 0")
    if not args.file:
        raise SystemExit("Missing audio file: pass --file or set XINFERENCE_AUDIO_FILE")

    audio_path = Path(args.file).expanduser()
    if not audio_path.is_file():
        raise SystemExit(f"Audio file does not exist or is not a file: {audio_path}")
    if audio_path.stat().st_size == 0:
        raise SystemExit(f"Audio file is empty: {audio_path}")
    return audio_path


def benchmark(args, audio_path):
    api_key = os.getenv(AUDIO_PROVIDERS[getattr(args, "provider", "xinference")]["api_key_env"])
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    audio_bytes = audio_path.read_bytes()
    content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
    duration = args.audio_duration or detect_wav_duration(audio_path)
    proxies = {"http": args.proxy, "https": args.proxy} if args.proxy else None
    data = {"model": args.model}

    def worker():
        start = time.perf_counter()
        try:
            response = get_session().post(
                args.base_url,
                headers=headers,
                data=data,
                files={"file": (audio_path.name, audio_bytes, content_type)},
                proxies=proxies,
                timeout=args.timeout,
            )
            latency = time.perf_counter() - start
            if 200 <= response.status_code < 300:
                return True, latency
            print(f"HTTP {response.status_code}: {response.text[:500]}")
            return False, latency
        except requests.RequestException as exc:
            latency = time.perf_counter() - start
            print(f"Request failed: {exc}")
            return False, latency

    duration_text = f" | Audio Duration: {duration:.2f}s" if duration else ""
    print(
        f"Base URL: {args.base_url} | Model: {args.model} | File: {audio_path} | "
        f"Concurrency: {args.concurrency} | Requests: {args.requests}{duration_text}"
    )
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(worker) for _ in range(args.requests)]
        samples = [future.result() for future in as_completed(futures)]
    elapsed = time.perf_counter() - started

    latencies = [latency for _, latency in samples]
    successful_latencies = [latency for ok, latency in samples if ok]
    successes = len(successful_latencies)
    print("\n===== Result =====")
    print(f"Elapsed Time : {elapsed:.2f}s")
    print(f"Success      : {successes}/{args.requests}")
    print(f"Success Rate : {successes / args.requests * 100:.2f}%")
    print(f"QPS          : {args.requests / elapsed:.2f}")
    print(f"Average      : {statistics.mean(latencies) * 1000:.2f} ms")
    for percent in (50, 95, 99):
        print(f"P{percent:<2}          : {percentile(latencies, percent) * 1000:.2f} ms")
    print(f"Max          : {max(latencies) * 1000:.2f} ms")
    print(f"Min          : {min(latencies) * 1000:.2f} ms")
    if duration and successful_latencies:
        print(f"Average RTF  : {statistics.mean(successful_latencies) / duration:.3f}")
        print(f"Audio Speed  : {successes * duration / elapsed:.2f} audio-sec/s")
    write_json_report(
        args, "Audio transcription",
        [{"ok": ok, "latency_ms": latency * 1000} for ok, latency in samples],
        elapsed, audio_duration=duration,
    )


if __name__ == "__main__":
    cli_args = parse_args()
    cli_audio_path = validate_args(cli_args)
    benchmark(cli_args, cli_audio_path)
