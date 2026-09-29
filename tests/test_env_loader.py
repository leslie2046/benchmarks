import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import env_loader


class LoadLocalEnvTests(unittest.TestCase):
    def load_fixture(self, data, initial=None):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_bytes(data)
            with patch.object(env_loader, "__file__", str(Path(directory) / "env_loader.py")):
                with patch.dict(os.environ, initial or {}, clear=True):
                    env_loader.load_local_env()
                    return dict(os.environ)

    def test_windows_chinese_encoding(self):
        content = "# 中文注释\nBENCHMARK_TEST_QUERY=知识库检索\n"
        loaded = self.load_fixture(content.encode("cp936"))
        self.assertEqual(loaded["BENCHMARK_TEST_QUERY"], "知识库检索")

    def test_utf8_bom_and_environment_precedence(self):
        content = "BENCHMARK_TEST_QUERY=来自文件\nBENCHMARK_TEST_BOM=parsed\n"
        loaded = self.load_fixture(
            content.encode("utf-8-sig"), {"BENCHMARK_TEST_QUERY": "existing"}
        )
        self.assertEqual(loaded["BENCHMARK_TEST_QUERY"], "existing")
        self.assertEqual(loaded["BENCHMARK_TEST_BOM"], "parsed")


if __name__ == "__main__":
    unittest.main()
