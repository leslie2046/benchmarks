"""Smoke checks for the API/CLI/shared directory separation."""
import subprocess
import sys
import json
import tomllib
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

    def test_postgresql_deployment_and_backend_only_dependency(self):
        import yaml

        compose = yaml.safe_load((ROOT / "docker" / "compose.yaml").read_text())
        self.assertEqual(compose["services"]["db"]["image"], "postgres:16")
        self.assertNotIn("ports", compose["services"]["db"])
        self.assertEqual(compose["services"]["api"]["depends_on"]["db"]["condition"], "service_healthy")
        self.assertIn("DATABASE_URL", compose["services"]["api"]["environment"])
        self.assertIn("postgres_data", compose["volumes"])
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertTrue(any(isinstance(item, str) and item.startswith("psycopg[binary]")
                            for item in project["dependency-groups"]["backend"]))
        self.assertFalse(any("psycopg" in item for item in project["dependency-groups"]["cli"]))
        for extension in ("sh", "ps1"):
            build = (ROOT / "docker" / f"build.{extension}").read_text()
            self.assertIn("pull db", build)
            self.assertIn("prismlab-api:local prismlab-web:local postgres:16", build)

    def test_dependency_groups_and_locked_docker_installs(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(project["tool"]["uv"]["default-groups"], ["backend", "dev"])
        self.assertIn({"include-group": "cli"}, project["dependency-groups"]["backend"])
        self.assertEqual(project["dependency-groups"]["cli"], ["requests>=2.32,<3"])
        self.assertFalse(project["tool"]["uv"]["package"])
        lock = tomllib.loads((ROOT / "uv.lock").read_text())
        self.assertTrue(lock["package"])
        frontend = json.loads((ROOT / "frontend" / "package.json").read_text())
        self.assertEqual(frontend["packageManager"], "pnpm@10.28.2")
        self.assertTrue((ROOT / "frontend" / "pnpm-lock.yaml").is_file())
        self.assertFalse((ROOT / "frontend" / "package-lock.json").exists())
        api_docker = (ROOT / "docker" / "backend.Dockerfile").read_text()
        web_docker = (ROOT / "docker" / "frontend.Dockerfile").read_text()
        self.assertIn("uv sync --locked --no-default-groups --group backend", api_docker)
        self.assertIn("pnpm install --frozen-lockfile", web_docker)
        self.assertIn("pnpm@10.28.2", web_docker)
        self.assertIn("uv:0.12.22", api_docker)

    def test_authentication_environment_is_scoped_to_relevant_services(self):
        import yaml

        compose = yaml.safe_load((ROOT / "docker" / "compose.yaml").read_text())
        environment = compose["services"]["web"]["environment"]
        self.assertEqual(environment["ADMIN_USERNAME"], "${ADMIN_USERNAME:-admin}")
        self.assertEqual(environment["ADMIN_PASSWORD"], "${ADMIN_PASSWORD:-}")
        self.assertEqual(compose["services"]["api"]["environment"]["ADMIN_PASSWORD"], "${ADMIN_PASSWORD:-}")
        self.assertEqual(environment["AUTH_MODE"], "${AUTH_MODE:-basic}")
        self.assertEqual(compose["services"]["api"]["environment"]["AUTH_MODE"], "${AUTH_MODE:-basic}")
        self.assertNotIn("ADMIN_PASSWORD", compose["services"]["db"]["environment"])
        for variable in ("GITHUB_CLIENT_SECRET", "OIDC_CLIENT_SECRET", "AUTH_SESSION_SECRET"):
            self.assertIn(variable, compose["services"]["api"]["environment"])
            self.assertNotIn(variable, environment)
        self.assertEqual(compose["services"]["api"]["environment"]["AUTH_ALLOWED_ORIGINS"], "${AUTH_ALLOWED_ORIGINS:-}")
        for variable in ("GITHUB_ALLOWED_IDS", "GITHUB_ALLOWED_USERS", "OIDC_ALLOWED_SUBJECTS", "OIDC_ALLOWED_EMAILS"):
            self.assertNotIn(variable, compose["services"]["api"]["environment"])
            self.assertNotIn(variable, (ROOT / "docker" / ".env.example").read_text())
        dockerfile = (ROOT / "docker" / "frontend.Dockerfile").read_text()
        self.assertIn("apk add --no-cache apache2-utils", dockerfile)
        self.assertIn("COPY --chmod=755 docker/25-admin-auth.sh /docker-entrypoint.d/25-admin-auth.sh", dockerfile)
        nginx = (ROOT / "docker" / "nginx.conf").read_text()
        self.assertIn("include /etc/nginx/admin-auth.conf;", nginx)
        self.assertIn('proxy_set_header Authorization "";', nginx)


if __name__ == "__main__":
    unittest.main()
