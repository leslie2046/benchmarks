"""Smoke checks for the API/CLI/shared directory separation."""
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryLayoutTests(unittest.TestCase):
    def test_all_cli_module_help_entrypoints_without_inference(self):
        for module, extra in (("embedding", []), ("reranker", []), ("audio", []),
                              ("llm", []), ("dify", ["retrieve"]), ("dify", ["chat"])):
            with self.subTest(module=module, mode=extra):
                command = [sys.executable, "-m", f"cli.perf_{module}", *extra, "--help"]
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--json-report", result.stdout)

    def test_cli_imports_do_not_load_backend_or_fastapi(self):
        result = subprocess.run([sys.executable, "-c",
            "import sys; import cli.perf_llm, cli.perf_audio, cli.perf_dify, cli.perf_embedding, cli.perf_reranker; "
            "assert not any(n == 'backend' or n.startswith('backend.') or n == 'fastapi' for n in sys.modules)"],
            cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_docker_context_includes_all_runtime_packages_and_model_definitions(self):
        dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
        for directory in ("backend", "cli", "shared", "config", "audio"):
            self.assertTrue((ROOT / directory).is_dir())
            self.assertIn(f"COPY {directory} ./{directory}", dockerfile)
        self.assertIn('"backend.main:app"', dockerfile)
        self.assertIn("dockerfile: backend/Dockerfile", (ROOT / "docker-compose.yml").read_text())


if __name__ == "__main__":
    unittest.main()
