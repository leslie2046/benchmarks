import base64
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend import main
from backend.connectivity import check_models
from backend.endpoints import endpoint_url, server_root
from backend.model_discovery import list_models
from backend.playground import run_playground
from backend.schemas import PlaygroundRequest, ServiceConfigCreate
from backend.secrets import SecretBox
from cli import perf_audio
from shared.audio_requests import audio_request
from shared.providers import AUDIO_PROVIDERS
from tests.database import create_test_store


class QwenAudioTests(unittest.TestCase):
    def test_native_endpoints_keep_host_and_gateway_prefix(self):
        for host in ("https://maas.qianwenaiapi.com", "https://gateway.test/proxy"):
            expected = host + "/api/v1/services/aigc/multimodal-generation/generation"
            for suffix in ("", "/compatible-mode", "/compatible-mode/v1", "/compatible-api/v1", "/api/v1", "/compatible-mode/v1/chat/completions"):
                self.assertEqual(endpoint_url(host + suffix, "audio", "qwen"), expected)
            self.assertEqual(endpoint_url(expected, "audio", "qwen"), expected)
            self.assertEqual(server_root(expected), host)

    def test_native_payload_and_existing_multipart(self):
        for model in ("qwen3-asr-flash", "qwen3-asr-flash-2025-09-08", "qwen-audio-3.0-asr-flash", "qwen-audio-3.1-asr-flash"):
            payload = audio_request("qwen", model, "sample.wav", b"RIFF")
            self.assertEqual(set(payload), {"json"})
            body = payload["json"]
            self.assertEqual(body["model"], model)
            content = body["input"]["messages"][0]["content"][0]
            data = content["input_audio"]["data"] if model.startswith("qwen-audio-") else content["audio"]
            self.assertEqual(data, "data:audio/wav;base64,UklGRg==")
        self.assertEqual(audio_request("vllm", "asr", "sample.mp3", b"test")["files"]["file"], ("sample.mp3", b"test", "audio/mpeg"))

    def test_rejects_unsupported_protocols_and_invalid_files(self):
        for model in ("qwen3-asr-flash-realtime", "qwen3-asr-flash-filetrans", "qwen-audio-3.1-asr-flash-filetrans", "qwen-tts", "qwen-plus"):
            with self.assertRaisesRegex(ValueError, "synchronous"):
                audio_request("qwen", model, "sample.wav", b"RIFF")
        for name, audio in (("sample.wav", b""), ("sample.wav", b"x" * 10_000_001), ("file.txt", b"text")):
            with self.assertRaises(ValueError):
                audio_request("qwen", "qwen3-asr-flash", name, audio)

    def test_playground_and_connectivity_use_same_native_payload(self):
        preset = AUDIO_PROVIDERS["qwen"]
        config = {"provider": "qwen", "benchmark": "audio", "base_url": preset["base_url"], "model": preset["model"]}
        request = PlaygroundRequest(benchmark="audio", provider_id="fixture", audio_name="sample.wav", audio_base64=base64.b64encode(b"RIFF").decode())
        response = SimpleNamespace(status_code=200, content=b'{"output":{"text":"hello"}}', encoding="utf-8")
        with patch("backend.playground.requests.post", return_value=response) as post:
            self.assertTrue(run_playground(request, config, "fixture-key")["ok"])
            self.assertEqual(post.call_args.kwargs["json"], audio_request("qwen", preset["model"], "sample.wav", b"RIFF")["json"])
            self.assertNotIn("files", post.call_args.kwargs)
            self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Bearer fixture-key"})
        with patch("backend.connectivity.requests.post", return_value=response) as post:
            check_models([config], "fixture-key")
            self.assertIn("input", post.call_args.kwargs["json"])
            self.assertNotIn("files", post.call_args.kwargs)

    def test_cli_defaults_overrides_and_native_requests(self):
        with patch("sys.argv", ["perf_audio.py", "--provider", "qwen"]), patch.dict("os.environ", {}, clear=True):
            args = perf_audio.parse_args()
        self.assertEqual(args.model, "qwen3-asr-flash")
        self.assertEqual(args.base_url, AUDIO_PROVIDERS["qwen"]["base_url"])
        args.requests = 1
        args.concurrency = 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audio.wav"
            path.write_bytes(b"RIFF")
            session = MagicMock()
            session.post.return_value.status_code = 200
            with patch.object(perf_audio, "get_session", return_value=session), patch.object(perf_audio, "write_json_report") as report, patch.dict("os.environ", {"QWEN_API_KEY": "fixture-key"}), patch("sys.stdout", new_callable=io.StringIO):
                perf_audio.benchmark(args, path)
            self.assertIn("json", session.post.call_args.kwargs)
            self.assertFalse(session.post.call_args.kwargs["allow_redirects"])
            self.assertEqual(report.call_args.args[2][0]["ok"], True)
        with patch("sys.argv", ["perf_audio.py", "--provider", "qwen"]), patch.dict("os.environ", {"QWEN_AUDIO_MODEL": "qwen-audio-3.1-asr-flash", "QWEN_AUDIO_URL": "https://gateway.test/native"}):
            args = perf_audio.parse_args()
            self.assertEqual(args.model, "qwen-audio-3.1-asr-flash")
            self.assertEqual(args.base_url, "https://gateway.test/native")

    def test_discovery_classifies_supported_asr_without_guessing_other_names(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"output": {"total": 2, "models": [{"model": "qwen3-asr-flash", "capabilities": ["TG"]}, {"model": "unrecognized-asr"}]}}
        with patch("backend.model_discovery.requests.get", return_value=response):
            models = list_models("qwen", "https://maas.qianwenaiapi.com/compatible-mode/v1", "fixture-key")
        self.assertEqual({item["id"]: item["benchmark"] for item in models}, {"qwen3-asr-flash": "audio", "unrecognized-asr": None})

    def test_saved_audio_model_resolves_to_native_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = create_test_store(self, root)
            with patch.object(main, "store", store), patch.object(main, "secret_box", SecretBox.from_data_dir(root)):
                config = main.create_service_config(ServiceConfigCreate(name="Qwen audio", provider="qwen", models=[{"name": "qwen3-asr-flash", "benchmark": "audio", "credentials": [{"name": "Default", "server_url": "https://maas.qianwenaiapi.com/compatible-mode/v1", "api_key": "fixture-key"}]}]))
                resolved, key = main._playground_access(PlaygroundRequest(benchmark="audio", provider_id=config["id"], model="qwen3-asr-flash", audio_base64="UklGRg=="))
                self.assertEqual(resolved["provider"], "qwen")
                self.assertEqual(resolved["base_url"], AUDIO_PROVIDERS["qwen"]["base_url"])
                self.assertEqual(key, "fixture-key")
