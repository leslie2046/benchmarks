"""Cloud discovery contracts; all upstream requests are mocked."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend import main
from backend.endpoints import endpoint_url
from backend.llm_parameters import describe_parameters
from backend.model_discovery import ModelDiscoveryError, _benchmark, _models_url, list_models, verify_key


def response(body, status=200):
    result = MagicMock(status_code=status)
    result.json.return_value = body
    return result


def aliyun_page(models, total):
    return response({"success": True, "output": {"total": total, "models": models}})


class CloudModelDiscoveryTests(unittest.TestCase):
    def test_siliconflow_uses_metadata_when_subtype_lists_omit_model(self):
        with patch("backend.model_discovery.requests.get", side_effect=[
            response({"data": [{"id": "deployment-1", "task": "text_embedding"}, {"id": "unknown"}]}),
            *[response({"data": []}) for _ in range(4)],
        ]):
            models = {row["id"]: row["benchmark"] for row in list_models("siliconflow", "https://api.siliconflow.cn", None)}
        self.assertEqual(models, {"deployment-1": "embedding", "unknown": None})

    def test_all_providers_classify_explicit_metadata_consistently(self):
        for provider in ["aliyun", "huaweiyun", "xinference", "vllm", "siliconflow"]:
            for item, expected in [({"task": "text_embedding"}, "embedding"),
                                   ({"model_type": "unknown", "sub_type": "reranking"}, "reranker"),
                                   ({"capabilities": ["TR", "rerank"]}, "reranker"),
                                   ({"capabilities": ["embedding"]}, "embedding"),
                                   ({"model_type": "LLM"}, "llm")]:
                with self.subTest(provider=provider, item=item):
                    self.assertEqual(_benchmark(item, provider), expected)

    def test_huawei_official_embedding_and_rerank_ids(self):
        with patch("backend.model_discovery.requests.get", return_value=response({"data": [{"id": "bge-m3"}, {"id": "bge-reranker-v2-m3"}]})):
            models = {row["id"]: row["benchmark"] for row in list_models("huaweiyun", "https://api.modelarts-maas.com", None)}
        self.assertEqual(models, {"bge-m3": "embedding", "bge-reranker-v2-m3": "reranker"})

    def test_provider_routes_preserve_hosts_and_gateway_prefixes(self):
        roots = ["https://dashscope.aliyuncs.com", "https://dashscope.aliyuncs.com/compatible-api",
                 "https://dashscope.aliyuncs.com/compatible-mode",
                 "https://dashscope.aliyuncs.com/compatible-mode/v1",
                 "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                 "https://dashscope.aliyuncs.com/compatible-api/v1/chat/completions"]
        for root in roots:
            self.assertEqual(_models_url(root, "aliyun"), "https://dashscope.aliyuncs.com/api/v1/models")
        self.assertEqual(_models_url("https://workspace.cn-beijing.maas.aliyuncs.com", "aliyun"),
                         "https://workspace.cn-beijing.maas.aliyuncs.com/api/v1/models")
        self.assertEqual(_models_url("https://gateway.test/prefix/compatible-api/v1", "aliyun"),
                         "https://gateway.test/prefix/api/v1/models")
        self.assertEqual(_models_url("https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1", "aliyun"),
                         "https://workspace.cn-beijing.maas.aliyuncs.com/api/v1/models")
        self.assertEqual(_models_url("https://gateway.test/prefix/compatible-mode/v1", "aliyun"),
                         "https://gateway.test/prefix/api/v1/models")
        for suffix in ["", "/v1", "/v2", "/v2/models", "/v1/chat/completions"]:
            self.assertEqual(_models_url("https://api.modelarts-maas.com" + suffix, "huaweiyun"),
                             "https://api.modelarts-maas.com/v2/models")
        self.assertEqual(_models_url("https://api-ap-southeast-1.modelarts-maas.com/v1", "huaweiyun"),
                         "https://api-ap-southeast-1.modelarts-maas.com/v2/models")

    def test_aliyun_chat_and_rerank_use_distinct_compatibility_prefixes(self):
        for host in ["https://dashscope.aliyuncs.com", "https://workspace.cn-beijing.maas.aliyuncs.com", "https://gateway.test/prefix"]:
            for prefix in ["compatible-api", "compatible-mode"]:
                for suffix in ["", "/v1", "/v1/chat/completions"]:
                    self.assertEqual(endpoint_url(f"{host}/{prefix}{suffix}", "llm", "aliyun"),
                                     f"{host}/compatible-mode/v1/chat/completions")
                for suffix in ["", "/v1", "/v1/reranks"]:
                    self.assertEqual(endpoint_url(f"{host}/{prefix}{suffix}", "reranker", "aliyun"),
                                     f"{host}/compatible-api/v1/reranks")
        self.assertEqual(endpoint_url("https://custom.test/proxy", "llm", "aliyun"),
                         "https://custom.test/proxy/v1/chat/completions")

    def test_aliyun_pagination_capabilities_and_unknown_models(self):
        pages = [aliyun_page([{"model": "qwen", "capabilities": ["TG", "Reasoning"]},
                             {"model": "image-only", "capabilities": ["IG"]}], 3),
                 aliyun_page([{"model": "embedding", "capabilities": ["TR"]}], 3)]
        with patch("backend.model_discovery.requests.get", side_effect=pages) as get:
            models = list_models("aliyun", "https://dashscope.aliyuncs.com/compatible-api", "test-key")
        self.assertEqual({row["id"]: row["benchmark"] for row in models},
                         {"qwen": "llm", "embedding": "embedding", "image-only": None})
        self.assertEqual([call.kwargs["params"]["page_no"] for call in get.call_args_list], [1, 2])
        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "Bearer test-key"})
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_huawei_unknown_type_is_not_assumed_to_be_llm(self):
        body = {"data": [{"id": "deepseek-v4-flash", "object": "list"},
                         {"id": "reranker", "model_type": "rerank"}]}
        with patch("backend.model_discovery.requests.get", return_value=response(body)):
            models = list_models("huaweiyun", "https://api.modelarts-maas.com", "test-key")
        self.assertEqual({row["id"]: row["benchmark"] for row in models},
                         {"deepseek-v4-flash": None, "reranker": "reranker"})

    def test_aliyun_official_types_override_coarse_capabilities(self):
        rows = [{"model": name, "capabilities": ["TR"]} for name in
                ["qwen3-rerank", "qwen3-vl-rerank", "qwen3.7-text-rerank", "gte-rerank-v2",
                 "qwen3.7-text-embedding", "qwen3.7-text-embedding-flash", "text-embedding-v4"]]
        rows += [{"model": "unknown-rerank-looking-name", "capabilities": []},
                 {"model": "new-model", "model_type": "reranker", "capabilities": ["TR"]}]
        with patch("backend.model_discovery.requests.get", return_value=aliyun_page(rows, len(rows))):
            models = {item["id"]: item["benchmark"] for item in list_models("aliyun", "https://dashscope.aliyuncs.com", None)}
        for name in ["qwen3-rerank", "qwen3-vl-rerank", "qwen3.7-text-rerank", "gte-rerank-v2", "new-model"]:
            self.assertEqual(models[name], "reranker")
        for name in ["qwen3.7-text-embedding", "qwen3.7-text-embedding-flash", "text-embedding-v4"]:
            self.assertEqual(models[name], "embedding")
        self.assertIsNone(models["unknown-rerank-looking-name"])

    def test_discovery_returns_all_models_beyond_import_limit(self):
        rows = [{"model": f"qwen-{index:04}", "capabilities": ["TG"]} for index in range(601)]
        pages = [aliyun_page(rows[start:start + 100], len(rows)) for start in range(0, len(rows), 100)]
        with patch("backend.model_discovery.requests.get", side_effect=pages) as get:
            models = list_models("aliyun", "https://dashscope.aliyuncs.com/compatible-mode", "test-key")
        self.assertEqual(len(models), 601)
        self.assertEqual(get.call_count, 7)
        self.assertEqual(models[-1]["id"], "qwen-0600")
        with patch("backend.model_discovery.requests.get", return_value=response({"data": [{"id": row["model"]} for row in rows]})):
            self.assertEqual(len(list_models("huaweiyun", "https://api.modelarts-maas.com", None)), 601)

    def test_aliyun_discovery_retains_separate_safety_limit(self):
        with patch("backend.model_discovery.requests.get", return_value=aliyun_page([{"model": "qwen"}], 10001)):
            with self.assertRaisesRegex(ModelDiscoveryError, "discovery safety limit"):
                list_models("aliyun", "https://dashscope.aliyuncs.com", None)

    def test_authentication_invalid_responses_and_pagination_failures(self):
        cases = [response({}, 401), response({}, 403), response({}, 500), response({"success": False}),
                 response({"output": {"models": [], "total": "3"}}),
                 aliyun_page([], 1)]
        for result in cases:
            with self.subTest(body=result.json.return_value, status=result.status_code):
                with patch("backend.model_discovery.requests.get", return_value=result):
                    with self.assertRaises(ModelDiscoveryError):
                        verify_key("aliyun", "https://dashscope.aliyuncs.com", "test-key")
        with patch("backend.model_discovery.requests.get", return_value=aliyun_page([{"model": "qwen"}], 2)):
            with self.assertRaisesRegex(ModelDiscoveryError, "did not advance"):
                list_models("aliyun", "https://dashscope.aliyuncs.com", None)

    def test_capability_refresh_reads_aliyun_nested_metadata(self):
        model = {"model": "qa-cloud-model", "capabilities": ["TG"],
                 "model_info": {"context_window": 32768, "max_output_tokens": 4096}}
        with patch("backend.model_discovery.requests.get", return_value=aliyun_page([model], 1)):
            description = describe_parameters({"provider": "aliyun", "model": model["model"],
                                               "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"},
                                              "test-key", refresh=True)
        self.assertTrue(description["can_refresh"])
        self.assertEqual(description["metadata"]["context_window"], 32768)
        self.assertEqual(description["parameters"]["max_tokens"]["max"], 4096)

    def test_api_discovery_and_verification_are_read_only(self):
        client = TestClient(main.app)
        for provider in ["aliyun", "huaweiyun"]:
            result = aliyun_page([{"model": "qwen", "capabilities": ["TG"]}], 1) if provider == "aliyun" else response({"data": [{"id": "llm"}]})
            with patch.object(main, "_provider_access", return_value=("https://cloud.test", "test-key")), \
                 patch("backend.model_discovery.requests.get", return_value=result), \
                 patch.object(main, "store") as store, \
                 patch("backend.connectivity.requests.post") as inference:
                self.assertEqual(client.post("/api/provider-models/list", json={"provider": provider, "server_url": "https://cloud.test"}).status_code, 200)
                self.assertEqual(client.post("/api/provider-models/verify", json={"provider": provider, "server_url": "https://cloud.test"}).status_code, 200)
                self.assertEqual(store.mock_calls, [])
                inference.assert_not_called()


if __name__ == "__main__":
    unittest.main()
