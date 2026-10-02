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
        dockerfile = (ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")
        for directory in ("backend", "cli", "shared", "config", "audio"):
            self.assertTrue((ROOT / directory).is_dir())
            self.assertIn(f"COPY {directory} ./{directory}", dockerfile)
        self.assertIn('"backend.main:app"', dockerfile)
        compose = (ROOT / "docker" / "compose.yaml").read_text()
        self.assertIn("dockerfile: docker/backend.Dockerfile", compose)
        self.assertIn("dockerfile: docker/frontend.Dockerfile", compose)
        self.assertIn("./volumes:/app/volumes", compose)
        self.assertIn("BENCHMARK_DATA_DIR: /app/volumes", compose)
        self.assertNotIn("env_file:", compose)
        self.assertIn("COPY frontend/ ./", (ROOT / "docker" / "frontend.Dockerfile").read_text())
        self.assertTrue((ROOT / "docker" / "nginx.conf").is_file())

    def test_packaging_and_start_scripts_use_same_image_tags(self):
        for extension in ("sh", "ps1"):
            build = (ROOT / "docker" / f"build.{extension}").read_text()
            start = (ROOT / "docker" / f"start.{extension}").read_text()
            self.assertIn("prismlab-api:local prismlab-web:local", build)
            self.assertIn("image save --output", build)
            self.assertIn("up --detach --no-build", start)
            self.assertIn("compose.yaml", build)
            self.assertIn("compose.yaml", start)


if __name__ == "__main__":
    unittest.main()
