import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from shared.providers import LLM_PROVIDERS
from backend import main
from backend import llm_parameters as parameters
from shared.llm_stream import iter_chat
from backend.playground import stream_playground
from backend.schemas import PlaygroundRequest, ServiceConfigCreate
from backend.secrets import SecretBox
from backend.store import RunStore


def config(provider="deepseek", model="deepseek-flash"):
    return {"provider": provider, "model": model, "base_url": "https://fixture.invalid/chat/completions"}


class ParameterTests(unittest.TestCase):
    def setUp(self):
        parameters._cache.clear()

    def test_all_providers_have_yaml_basic_parameters_and_unknown_models_do_not_guess(self):
        for provider in LLM_PROVIDERS:
            description = parameters.describe_parameters(config(provider, "arbitrary-reasoning-model"))
            self.assertEqual(set(description["parameters"]), {"max_tokens", "temperature", "top_p"})
            self.assertFalse(description["model_specific"])
            wire, snapshot = parameters.resolve_parameters(config(provider, "custom"), {"temperature": 0.7, "top_p": 0.8}, 512)
            self.assertEqual(wire, {"max_tokens": 512, "temperature": 0.7, "top_p": 0.8})
            self.assertNotIn("secret", json.dumps(snapshot))

    def test_deepseek_dependencies_validation_and_nested_wire_mapping(self):
        wire, _ = parameters.resolve_parameters(config(), {"thinking_mode": "enabled", "reasoning_effort": "max"})
        self.assertEqual(wire["thinking"], {"type": "enabled"})
        self.assertEqual(wire["reasoning_effort"], "max")
        wire, _ = parameters.resolve_parameters(config(), {"thinking_mode": "disabled", "temperature": 0.8})
        self.assertEqual(wire["temperature"], 0.8)
        for values in ({"reasoning_effort": "extreme"}, {"thinking_mode": "disabled", "reasoning_effort": "high"},
                       {"temperature": 1}, {"top_p": 0.5}, {"max_tokens": 9000}, {"max_tokens": 3.1},
                       {"messages": "override"}, {"temperature": float("nan")}, {"max_tokens": True}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                parameters.resolve_parameters(config(), values)

    def test_provider_scoped_models_map_different_wire_fields(self):
        for provider, model, expected in (("siliconflow", "Qwen/Qwen3-8B", {"enable_thinking": False}),
                                         ("aliyun", "qwen3-8b", {"enable_thinking": False}),
                                         ("xinference", "Qwen3-8B", {"enable_thinking": False}),
                                         ("vllm", "Qwen/Qwen3-8B", {"chat_template_kwargs": {"enable_thinking": False}})):
            wire, _ = parameters.resolve_parameters(config(provider, model), {"thinking_mode": "disabled"})
            self.assertEqual(wire, {"max_tokens": 256, **expected})
        with self.assertRaises(ValueError):
            parameters.resolve_parameters(config("huaweiyun", "Qwen/Qwen3-8B"), {"thinking_mode": "enabled"})

    def test_official_metadata_refresh_read_only_and_scoped_to_credentials(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"data": [{"id": "custom", "context_window": 9000, "max_output_tokens": 128,
            "effort": {"supported_levels": ["high", "max"], "default_level": "max"}, "api_key": "must-not-leak"}]}
        with patch("backend.model_discovery.requests.get", return_value=response) as get:
            description = parameters.describe_parameters(config(model="custom"), "secret", refresh=True)
            get.assert_called_once()
            self.assertEqual(description["parameters"]["reasoning_effort"]["values"], ["high", "max"])
            self.assertEqual(description["parameters"]["max_tokens"]["default"], 128)
            self.assertNotIn("must-not-leak", json.dumps(description))
            parameters.describe_parameters(config(model="custom"), "secret")
            get.assert_called_once()
        self.assertEqual(parameters.describe_parameters(config(model="custom"), "other-key")["metadata"], {})
        with self.assertRaises(ValueError):
            parameters.resolve_parameters(config(model="custom"), {}, 256, "secret")

    def test_yaml_is_safe_and_can_define_custom_uid_and_capacity(self):
        original = parameters.DEFINITION_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.yaml"
            path.write_text(original + "\n  - {provider: vllm, patterns: [my-deployment], profile: qwen_template, metadata: {context_window: 8192, max_output_tokens: 1000}}\n", encoding="utf-8")
            with patch.object(parameters, "DEFINITION_PATH", path):
                description = parameters.describe_parameters(config("vllm", "my-deployment"))
                self.assertEqual(description["metadata"]["context_window"], 8192)
                self.assertEqual(description["parameters"]["max_tokens"]["max"], 1000)
                wire, _ = parameters.resolve_parameters(config("vllm", "my-deployment"), {"thinking_mode": "enabled"})
                self.assertTrue(wire["chat_template_kwargs"]["enable_thinking"])
                path.write_text("!!python/object/apply:os.system ['echo unsafe']", encoding="utf-8")
                with self.assertRaises(Exception):
                    parameters.describe_parameters(config())

    def test_endpoint_rejects_invalid_parameters_before_opening_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = RunStore(root / "runs.sqlite3")
            with patch.object(main, "store", store), patch.object(main, "secret_box", SecretBox.from_data_dir(root)):
                saved = main.create_service_config(ServiceConfigCreate(name="DeepSeek", provider="deepseek", models=[{
                    "name": "deepseek-flash", "alias": "friendly-name", "benchmark": "llm",
                    "credentials": [{"name": "Default", "server_url": "https://fixture.invalid", "api_key": "secret"}]}]))
                client = TestClient(main.app)
                selection = {"id": saved["id"], "model": "friendly-name"}
                description = client.post("/api/llm/parameters", json=selection)
                self.assertEqual(description.status_code, 200)
                self.assertEqual(description.json()["model"], "deepseek-flash")
                with patch("shared.llm_stream.requests.post") as post:
                    invalid = client.post("/api/playground/stream", json={"benchmark": "llm", "provider_id": saved["id"], "model": "friendly-name", "query": "q", "llm_parameters": {"reasoning_effort": "wrong"}})
                    self.assertEqual(invalid.status_code, 400)
                    post.assert_not_called()

    def test_stream_sends_resolved_fields_and_separates_reasoning_from_answer(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"reasoning_content":"thinking"}}]}',
            'data: {"choices":[{"delta":{"content":"answer"},"finish_reason":"stop"}],"usage":{"completion_tokens":5}}',
            'data: [DONE]']
        request = PlaygroundRequest(benchmark="llm", provider_id="fixture", query="q", llm_parameters={"thinking_mode": "enabled", "reasoning_effort": "max"})
        with patch("shared.llm_stream.requests.post", return_value=response) as post:
            events = [json.loads(line) for line in stream_playground(request, config(), "secret")]
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["thinking"], {"type": "enabled"})
        self.assertEqual(body["reasoning_effort"], "max")
        self.assertTrue(body["stream"])
        self.assertEqual(events[0]["channel"], "reasoning")
        self.assertEqual(events[1]["channel"], "answer")
        self.assertEqual(events[-1]["result"]["data"]["content"], "answer")
        self.assertEqual(events[-1]["result"]["data"]["reasoning_content"], "thinking")

    def test_schema_rejects_nested_objects_and_booleans(self):
        for value in ({"thinking_mode": True}, {"temperature": {"hack": 1}}):
            with self.assertRaises(ValidationError):
                PlaygroundRequest(benchmark="llm", provider_id="fixture", query="q", llm_parameters=value)


if __name__ == "__main__":
    unittest.main()
