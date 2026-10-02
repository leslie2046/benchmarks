import unittest

from pydantic import ValidationError

from backend.schemas import RunCreate, ServiceConfigCreate, TestPlanCreate
from backend.validation import is_placeholder_url
from backend.endpoints import endpoint_url, server_root
from backend.catalog import get_catalog


class ServiceUrlValidationTests(unittest.TestCase):
    def test_official_provider_names_and_default_endpoint_paths(self):
        kinds = {item["id"]: item["label"] for benchmark in get_catalog()["benchmarks"] for item in benchmark["providers"]}
        self.assertEqual(kinds["siliconflow"], "SiliconFlow")
        self.assertEqual(kinds["aliyun"], "Alibaba Cloud Model Studio")
        self.assertEqual(kinds["huaweiyun"], "ModelArts Studio (MaaS)")
        self.assertEqual(kinds["xunfei"], "iFLYTEK Xingchen MaaS")
        self.assertEqual(kinds["vllm"], "vLLM")
        self.assertEqual(endpoint_url("https://api.siliconflow.cn", "embedding", "siliconflow"), "https://api.siliconflow.cn/v1/embeddings")
        self.assertEqual(endpoint_url("https://dashscope.aliyuncs.com/compatible-api", "reranker", "aliyun"), "https://dashscope.aliyuncs.com/compatible-api/v1/reranks")
        self.assertEqual(endpoint_url("https://api.modelarts-maas.com", "reranker", "huaweiyun"), "https://api.modelarts-maas.com/v1/rerank")
        self.assertEqual(endpoint_url("https://maas-api.cn-huabei-1.xf-yun.com", "reranker", "xunfei"), "https://maas-api.cn-huabei-1.xf-yun.com/v2/rerank")
        self.assertEqual(endpoint_url("https://maas-api.cn-huabei-1.xf-yun.com/v1", "reranker", "xunfei"), "https://maas-api.cn-huabei-1.xf-yun.com/v1/rerank")
        self.assertEqual(server_root("https://dashscope.aliyuncs.com/compatible-api/v1/reranks"), "https://dashscope.aliyuncs.com/compatible-api")

    def test_detects_placeholder_and_invalid_port(self):
        self.assertTrue(is_placeholder_url("https://your-xinference-host:port/v1/embeddings"))
        with self.assertRaises(ValidationError):
            ServiceConfigCreate(
                name="bad", benchmark="embedding", provider="vllm",
                base_url="https://your-xinference-host:port/v1/embeddings",
            )

    def test_accepts_concrete_http_endpoint(self):
        config = ServiceConfigCreate(
            name="valid", benchmark="embedding", provider="vllm",
            base_url="http://127.0.0.1:8000/v1/embeddings",
        )
        self.assertEqual(config.base_url, "http://127.0.0.1:8000/v1/embeddings")

    def test_model_list_rejects_duplicates(self):
        with self.assertRaises(ValidationError):
            ServiceConfigCreate(name="supplier", benchmark="embedding", provider="vllm", models=["m1", "m1"])

    def test_alias_is_unique_across_model_types_within_provider(self):
        with self.assertRaises(ValidationError):
            ServiceConfigCreate(name="supplier", provider="vllm", models=[
                {"name": "embed", "alias": "Shared", "benchmark": "embedding", "base_url": "https://example.com/v1/embeddings"},
                {"name": "rerank", "alias": " shared ", "benchmark": "reranker", "base_url": "https://example.com/v1/rerank"},
            ])

    def test_provider_accepts_models_for_multiple_benchmark_types(self):
        config = ServiceConfigCreate(name="multi", provider="xinference", models=[
            {"name": "embedding-a", "benchmark": "embedding", "base_url": "https://example.com/v1/embeddings"},
            {"name": "reranker-b", "benchmark": "reranker", "base_url": "https://example.com/v1/rerank"},
        ], icon="cloud")
        self.assertEqual([item.benchmark for item in config.models], ["embedding", "reranker"])

    def test_model_alias_defaults_to_model_name(self):
        config = ServiceConfigCreate(name="supplier", provider="vllm", models=[
            {"name": "BAAI/bge-m3", "benchmark": "embedding", "base_url": "https://example.com/v1/embeddings"},
        ])
        self.assertEqual(config.models[0].alias, "BAAI/bge-m3")

    def test_test_plan_requires_inputs_for_embedding_and_reranker(self):
        base = {"name": "plan", "providers": [{"id": "svc"}], "concurrency_levels": [1]}
        with self.assertRaises(ValidationError):
            TestPlanCreate(**base, benchmark="embedding")
        embedding = TestPlanCreate(**base, benchmark="embedding", query="A sentence to embed")
        self.assertEqual(embedding.query, "A sentence to embed")
        with self.assertRaises(ValidationError):
            TestPlanCreate(**base, benchmark="reranker", query="Which document is relevant?")
        reranker = TestPlanCreate(
            **base, benchmark="reranker", query="Which document is relevant?",
            documents=["Relevant document", "Distractor document"],
        )
        self.assertEqual(len(reranker.documents), 2)

    def test_dify_retrieve_requires_query_and_dataset_id(self):
        base = {
            "name": "retrieve", "benchmark": "dify-retrieve",
            "providers": [{"id": "dify"}], "concurrency_levels": [1],
        }
        with self.assertRaises(ValidationError):
            RunCreate(**base)
        valid = RunCreate(**base, query="What is RAG?", dataset_id="dataset-123")
        self.assertEqual(valid.dataset_id, "dataset-123")

    def test_dify_chat_requires_query_but_not_dataset_id(self):
        valid = RunCreate(
            name="chat", benchmark="dify-chat", providers=[{"id": "dify"}],
            concurrency_levels=[1], query="Hello",
        )
        self.assertIsNone(valid.dataset_id)


if __name__ == "__main__":
    unittest.main()
