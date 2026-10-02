import os
import unittest
from unittest.mock import patch

from cli import perf_embedding


class AliyunEmbeddingCliTests(unittest.TestCase):
    def test_other_cloud_embedding_configs(self):
        for provider, model, endpoint in [
            ("huaweiyun", "bge-m3", "https://api.modelarts-maas.com/v1/embeddings"),
            ("xunfei", "deployment-test", "https://maas-api.cn-huabei-1.xf-yun.com/v2/embeddings"),
        ]:
            with self.subTest(provider=provider), patch("sys.argv", ["perf_embedding", "--provider", provider]):
                args = perf_embedding.parse_args()
                prefix = provider.upper()
                with patch.dict(os.environ, {f"{prefix}_API_KEY": "test-key", f"{prefix}_EMBEDDING_MODEL": model}, clear=True):
                    self.assertEqual(perf_embedding.resolve_config(args), (endpoint, model, "test-key"))

    def test_cli_provider_defaults_and_overrides(self):
        with patch("sys.argv", ["perf_embedding", "--provider", "aliyun"]):
            args = perf_embedding.parse_args()
        with patch.dict(os.environ, {"ALIYUN_API_KEY": "test-key"}, clear=True):
            self.assertEqual(perf_embedding.resolve_config(args),
                             ("https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings", "text-embedding-v4", "test-key"))
        with patch.dict(os.environ, {"ALIYUN_API_KEY": "test-key", "ALIYUN_EMBEDDING_URL": "https://gateway.test/v1/embeddings",
                                    "ALIYUN_EMBEDDING_MODEL": "qwen3.7-text-embedding"}, clear=True):
            self.assertEqual(perf_embedding.resolve_config(args),
                             ("https://gateway.test/v1/embeddings", "qwen3.7-text-embedding", "test-key"))
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SystemExit, "ALIYUN_API_KEY"):
                perf_embedding.resolve_config(args)
