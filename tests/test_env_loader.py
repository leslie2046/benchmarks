import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared import env_loader


class LoadLocalEnvTests(unittest.TestCase):
    def load_fixture(self, data, initial=None):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_bytes(data)
            with patch.object(env_loader, "__file__", str(Path(directory) / "shared" / "env_loader.py")):
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

    def test_root_environment_path_is_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("LAYOUT_TEST_VALUE=from-root\n", encoding="utf-8")
            with patch.object(env_loader, "__file__", str(root / "shared" / "env_loader.py")), \
                    patch.dict(os.environ, {}, clear=True), patch("os.getcwd", return_value=str(root / "cli")):
                env_loader.load_local_env()
                self.assertEqual(os.getenv("LAYOUT_TEST_VALUE"), "from-root")


if __name__ == "__main__":
    unittest.main()
