import base64
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from backend import main as web_main
from backend.playground import run_playground
from backend.schemas import PlaygroundRequest
from backend.endpoints import endpoint_url


class PlaygroundTests(unittest.TestCase):
    def test_aliyun_text_embedding_uses_openai_compatible_payload(self):
        request = PlaygroundRequest(benchmark="embedding", provider_id="aliyun", model="text-embedding-v4", text="hello")
        endpoint = endpoint_url("https://dashscope.aliyuncs.com/compatible-mode", "embedding", "aliyun")
        response = SimpleNamespace(status_code=200, content=b'{"data":[{"embedding":[0.1]}]}', encoding="utf-8")
        with patch("backend.playground.requests.post", return_value=response) as post:
            result = run_playground(request, {"base_url": endpoint, "model": request.model}, "test-key")
        self.assertTrue(result["ok"])
        self.assertEqual(post.call_args.args[0], "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings")
        self.assertEqual(post.call_args.kwargs["json"], {"model": "text-embedding-v4", "input": "hello"})
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Bearer test-key"})

    def test_embedding_uses_selected_model_and_key(self):
        request = PlaygroundRequest(benchmark="embedding", provider_id="svc", model="embed-v2", text="hello")
        config = {"base_url": "https://example.test/v1/embeddings", "model": "embed-v2"}
        response = SimpleNamespace(status_code=200, content=json.dumps({"data": [{"embedding": [0.1, 0.2]}]}).encode(), encoding="utf-8")
        with patch("backend.playground.requests.post", return_value=response) as post:
            result = run_playground(request, config, "secret")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["data"][0]["embedding"], [0.1, 0.2])
        self.assertEqual(post.call_args.args[0], config["base_url"])
        self.assertEqual(post.call_args.kwargs["json"], {"model": "embed-v2", "input": "hello"})
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Bearer secret"})

    def test_dify_retrieval_builds_dataset_url(self):
        request = PlaygroundRequest(benchmark="dify-retrieve", provider_id="dify", query="question", dataset_id="dataset 1")
        response = SimpleNamespace(status_code=403, content=b'{"message":"forbidden"}', encoding="utf-8")
        with patch("backend.playground.requests.post", return_value=response) as post:
            result = run_playground(request, {"base_url": "https://dify.test", "model": None}, "key")
        self.assertFalse(result["ok"])
        self.assertEqual(post.call_args.args[0], "https://dify.test/v1/datasets/dataset%201/retrieve")
        self.assertEqual(post.call_args.kwargs["json"], {"query": "question"})

    def test_reranker_and_dify_chat_request_shapes(self):
        response = SimpleNamespace(status_code=200, content=b'{"answer":"hello"}', encoding="utf-8")
        rerank = PlaygroundRequest(benchmark="reranker", provider_id="svc", model="rank", query="question", documents=["first", "second"])
        with patch("backend.playground.requests.post", return_value=response) as post:
            run_playground(rerank, {"base_url": "https://example.test/rerank", "model": "rank"}, None)
        self.assertEqual(post.call_args.kwargs["json"]["documents"], ["first", "second"])
        self.assertEqual(post.call_args.kwargs["json"]["top_n"], 2)

        chat = PlaygroundRequest(benchmark="dify-chat", provider_id="dify", query="hello")
        with patch("backend.playground.requests.post", return_value=response) as post:
            run_playground(chat, {"base_url": "https://dify.test/v1", "model": None}, "key")
        self.assertEqual(post.call_args.args[0], "https://dify.test/v1/chat-messages")
        self.assertEqual(post.call_args.kwargs["json"]["query"], "hello")

    def test_audio_uses_multipart_and_rejects_invalid_encoding(self):
        request = PlaygroundRequest(benchmark="audio", provider_id="audio", audio_name="sample.wav", audio_base64=base64.b64encode(b"RIFF").decode())
        response = SimpleNamespace(status_code=200, content=b'{"text":"hello"}', encoding="utf-8")
        with patch("backend.playground.requests.post", return_value=response) as post:
            run_playground(request, {"base_url": "https://example.test/audio", "model": "asr"}, None)
        self.assertEqual(post.call_args.kwargs["files"]["file"][1], b"RIFF")
        self.assertEqual(post.call_args.kwargs["data"], {"model": "asr"})
        with self.assertRaises(ValueError):
            run_playground(request.model_copy(update={"audio_base64": "!"}), {"base_url": "https://example.test/audio", "model": "asr"}, None)

    def test_required_inputs_are_validated(self):
        with self.assertRaises(ValidationError):
            PlaygroundRequest(benchmark="reranker", provider_id="svc", query="question")
        request = PlaygroundRequest(benchmark="dify-retrieve", provider_id="svc", query="question")
        self.assertIsNone(request.dataset_id)  # Resolved from the saved Dify configuration.

    def test_api_uses_saved_credential_for_selected_model(self):
        request = PlaygroundRequest(benchmark="embedding", provider_id="svc", model="embed-v2", text="hello")
        config = {"base_url": "https://example.test/embeddings", "model": "embed-v2", "api_key_encrypted": "ciphertext"}
        expected = {"ok": True, "status_code": 200, "duration_ms": 1.0, "data": {}, "truncated": False}
        with patch.object(web_main, "_resolve_configs", return_value=[config]) as resolve, \
             patch.object(web_main.secret_box, "decrypt", return_value="saved-key") as decrypt, \
             patch.object(web_main, "run_playground", return_value=expected) as run:
            result = web_main.playground(request)
        self.assertEqual(result, expected)
        resolve.assert_called_once_with("embedding", [{"id": "svc", "model": "embed-v2"}], None)
        decrypt.assert_called_once_with("ciphertext")
        run.assert_called_once_with(request, config, "saved-key")


if __name__ == "__main__":
    unittest.main()
