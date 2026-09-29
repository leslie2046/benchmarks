import unittest

from pydantic import ValidationError

from webapp.schemas import ServiceConfigCreate
from webapp.schemas import RunCreate
from webapp.validation import is_placeholder_url


class ServiceUrlValidationTests(unittest.TestCase):
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
