import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend import main
from backend.catalog import allowed_provider_ids
from backend.endpoints import endpoint_url, server_root
from backend.llm_parameters import describe_parameters, resolve_parameters
from backend.model_discovery import ModelDiscoveryError, _models_url, list_models, verify_key
from backend.schemas import PlaygroundRequest, ServiceConfigCreate, SystemSettingsUpdate
from backend.secrets import SecretBox
from shared.llm_stream import stream_chat
from shared.providers import EMBEDDING_PROVIDERS, LLM_PROVIDERS, RERANK_PROVIDERS
from tests.database import create_test_store


ROOTS = {
    "moonshot": "https://api.moonshot.cn/v1",
    "qwen": "https://maas.qianwenaiapi.com/compatible-mode/v1",
    "minimax": "https://api.minimax.cn/v1",
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
}


def response(body):
    result = MagicMock(status_code=200)
    result.json.return_value = body
    return result


class AdditionalProviderTests(unittest.TestCase):
    def test_catalog_and_required_keys(self):
        for provider in ROOTS:
            with self.subTest(provider=provider):
                self.assertIn(provider, allowed_provider_ids("llm"))
                self.assertTrue(LLM_PROVIDERS[provider]["api_key_required"])
                self.assertEqual(LLM_PROVIDERS[provider]["api_key_env"], f"{provider.upper()}_API_KEY")
                for benchmark in ("embedding", "reranker", "audio"):
                    self.assertEqual(provider in allowed_provider_ids(benchmark), provider == "qwen")
        self.assertIn("aliyun", allowed_provider_ids("llm"))

    def test_chat_paths_are_idempotent_and_preserve_regions(self):
        for provider, root in ROOTS.items():
            expected = root + "/chat/completions"
            for source in (root, expected):
                self.assertEqual(endpoint_url(source, "llm", provider), expected)
            self.assertEqual(endpoint_url(server_root(expected), "llm", provider), expected)
            self.assertEqual(LLM_PROVIDERS[provider]["base_url"], expected)
        self.assertEqual(endpoint_url("https://ark.cn-beijing.volces.com", "llm", "volcengine"), ROOTS["volcengine"] + "/chat/completions")
        self.assertEqual(endpoint_url("https://gateway.test/proxy/api/v3", "llm", "volcengine"), "https://gateway.test/proxy/api/v3/chat/completions")
        self.assertEqual(endpoint_url("https://api.minimax.io/v1", "llm", "minimax"), "https://api.minimax.io/v1/chat/completions")

    def test_qwen_reuses_protocol_not_provider_identity(self):
        for benchmark, expected in (("llm", "/compatible-mode/v1/chat/completions"),
                                    ("embedding", "/compatible-mode/v1/embeddings"),
                                    ("reranker", "/compatible-api/v1/reranks")):
            url = "https://maas.qianwenaiapi.com" + expected
            self.assertEqual(endpoint_url(ROOTS["qwen"], benchmark, "qwen"), url)
            presets = {"llm": LLM_PROVIDERS, "embedding": EMBEDDING_PROVIDERS, "reranker": RERANK_PROVIDERS}
            self.assertEqual(presets[benchmark]["qwen"]["base_url"], url)
            self.assertIn("dashscope.aliyuncs.com", presets[benchmark]["aliyun"]["base_url"])
        wire, _ = resolve_parameters({"provider": "qwen", "model": "qwen3-8b"}, {"thinking_mode": "disabled"})
        self.assertEqual(wire["enable_thinking"], False)

    def test_moonshot_discovery_is_read_only_and_keeps_custom_hosts(self):
        with patch("backend.model_discovery.requests.get", return_value=response({"data": [{"id": "kimi-model"}]})) as get:
            self.assertEqual(list_models("moonshot", ROOTS["moonshot"], "fixture-key"), [{"id": "kimi-model", "benchmark": "llm"}])
            self.assertEqual(get.call_args.args[0], ROOTS["moonshot"] + "/models")
            self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "Bearer fixture-key"})
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
        self.assertEqual(_models_url("https://api.moonshot.ai/v1", "moonshot"), "https://api.moonshot.ai/v1/models")
        for provider in ("volcengine",):
            with self.assertRaises(ModelDiscoveryError):
                list_models(provider, ROOTS[provider], "fixture-key")

    def test_minimax_model_discovery_and_key_verification(self):
        body = {"object": "list", "data": [
            {"id": "MiniMax-M3", "object": "model", "owned_by": "minimax"},
            {"id": "MiniMax-M2.7", "object": "model", "owned_by": "minimax"},
            {"id": "MiniMax-M3"},
        ]}
        for root in (ROOTS["minimax"], "https://api.minimax.io", "https://gateway.test/proxy/v1/chat/completions"):
            with self.subTest(root=root), patch("backend.model_discovery.requests.get", return_value=response(body)) as get:
                self.assertEqual(list_models("minimax", root, "fixture-key"), [
                    {"id": "MiniMax-M2.7", "benchmark": "llm"},
                    {"id": "MiniMax-M3", "benchmark": "llm"},
                ])
                verify_key("minimax", root, "fixture-key")
                expected = root.removesuffix("/chat/completions").rstrip("/")
                if not expected.endswith("/v1"):
                    expected += "/v1"
                self.assertEqual(get.call_count, 2)
                for request in get.call_args_list:
                    self.assertEqual(request.args[0], expected + "/models")
                    self.assertEqual(request.kwargs["headers"], {"Authorization": "Bearer fixture-key"})
                    self.assertFalse(request.kwargs["allow_redirects"])

    def test_minimax_discovery_empty_and_error_responses(self):
        with patch("backend.model_discovery.requests.get", return_value=response({"data": []})):
            self.assertEqual(list_models("minimax", ROOTS["minimax"], "fixture-key"), [])
        for upstream in (response({}), response({"data": {}}), MagicMock(status_code=401), MagicMock(status_code=403), MagicMock(status_code=500)):
            with patch("backend.model_discovery.requests.get", return_value=upstream):
                with self.assertRaises(ModelDiscoveryError):
                    list_models("minimax", ROOTS["minimax"], "fixture-key")
                with self.assertRaises(ModelDiscoveryError):
                    verify_key("minimax", ROOTS["minimax"], "fixture-key")

    def test_qwen_discovery_uses_bailian_pagination_and_type_metadata(self):
        body = {"output": {"total": 2, "models": [{"model": "qwen3-rerank"}, {"model": "qwen-plus", "capabilities": ["TG"]}]}}
        with patch("backend.model_discovery.requests.get", return_value=response(body)) as get:
            models = list_models("qwen", ROOTS["qwen"], "fixture-key")
        self.assertEqual({item["id"]: item["benchmark"] for item in models}, {"qwen3-rerank": "reranker", "qwen-plus": "llm"})
        self.assertEqual(get.call_args.args[0], "https://maas.qianwenaiapi.com/api/v1/models")
        self.assertEqual(get.call_args.kwargs["params"]["page_no"], 1)

    def test_all_four_use_streaming_and_usage_without_guessing_capabilities(self):
        for provider, root in ROOTS.items():
            config = {"provider": provider, "model": "account-model", "base_url": endpoint_url(root, "llm", provider)}
            description = describe_parameters(config)
            self.assertEqual(set(description["parameters"]), {"max_tokens", "temperature", "top_p"})
            upstream = MagicMock()
            upstream.__enter__.return_value = upstream
            upstream.iter_lines.return_value = [
                'data: ' + json.dumps({"choices": [{"delta": {"content": "OK"}, "finish_reason": None}]}),
                'data: ' + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"completion_tokens": 4}}),
                'data: [DONE]',
            ]
            with patch("shared.llm_stream.requests.post", return_value=upstream) as post:
                sample, content = stream_chat(config["base_url"], config["model"], "fixture-key", "test", capture=True)
            self.assertEqual(content, "OK")
            self.assertEqual(sample["output_tokens"], 4)
            self.assertEqual(post.call_args.args[0], config["base_url"])
            self.assertEqual(post.call_args.kwargs["json"]["model"], "account-model")

    def test_saved_models_remain_separate_and_can_be_used_for_playground_and_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = create_test_store(self, root)
            box = SecretBox.from_data_dir(root)
            with patch.object(main, "store", store), patch.object(main, "secret_box", box):
                for provider, url in {**ROOTS, "aliyun": ROOTS["qwen"]}.items():
                    key = "fixture-private-key-" + provider
                    config = main.create_service_config(ServiceConfigCreate(name=provider, provider=provider, models=[{
                        "name": "account-model", "benchmark": "llm", "credentials": [{"name": "Default", "server_url": url, "api_key": key}]}]))
                    self.assertNotIn(key, str(config))
                    access, saved_key = main._playground_access(PlaygroundRequest(benchmark="llm", provider_id=config["id"], model="account-model", query="test"))
                    self.assertEqual(saved_key, key)
                    self.assertEqual(access["base_url"], endpoint_url(url, "llm", provider))
                    main.update_system_settings(SystemSettingsUpdate(default_llm={"id": config["id"], "model": "account-model"}))
                self.assertEqual({item["provider"] for item in store.list_service_configs()}, set(ROOTS) | {"aliyun"})
