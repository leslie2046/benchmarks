import base64
import gzip
import os
import re
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_IMAGE = os.getenv("TEST_WEB_IMAGE")


@unittest.skipUnless(WEB_IMAGE, "Set TEST_WEB_IMAGE to a built Web image for Docker authentication tests")
class DockerAuthTests(unittest.TestCase):
    def docker(self, *arguments, **kwargs):
        return subprocess.run(["docker", *arguments], capture_output=True, text=True, timeout=45, **kwargs)

    def start_web(self, *, username=None, password=None, legacy=None, mode=None):
        arguments = ["run", "-d", "--add-host", "api:127.0.0.1", "-p", "127.0.0.1::80"]
        if username is not None:
            arguments += ["-e", f"ADMIN_USERNAME={username}"]
        if password is not None:
            arguments += ["-e", f"ADMIN_PASSWORD={password}"]
        if legacy is not None:
            arguments += ["-v", f"{legacy}:/etc/nginx/htpasswd:ro"]
        if mode is not None:
            arguments += ["-e", f"AUTH_MODE={mode}"]
        result = self.docker(*arguments, WEB_IMAGE)
        self.assertEqual(result.returncode, 0, result.stderr)
        container = result.stdout.strip()
        self.addCleanup(self.docker, "rm", "-f", container)
        return container

    def wait_for_web(self, container):
        result = self.docker("port", container, "80/tcp")
        self.assertEqual(result.returncode, 0, result.stderr)
        address = result.stdout.strip()
        for attempt in range(100):
            try:
                self.request(address)
                return address
            except OSError:
                if self.docker("inspect", "-f", "{{.State.Running}}", container).stdout.strip() != "true":
                    self.fail(self.docker("logs", container).stderr)
                time.sleep(0.1)
        self.fail("Web container did not become ready")

    def request(self, address, path="/", *, username="admin", password=None):
        headers = {}
        if password is not None:
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        request = urllib.request.Request(f"http://{address}{path}", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    def test_static_compression_and_cache_policy(self):
        container = self.start_web(mode="app")
        address = self.wait_for_web(container)
        with urllib.request.urlopen(f"http://{address}/index.html", timeout=2) as response:
            self.assertEqual(response.headers["Cache-Control"], "no-cache")
            html = response.read().decode()
        asset = re.search(r'src="(/assets/[^" ]+\.js)"', html).group(1)
        with urllib.request.urlopen(f"http://{address}{asset}", timeout=2) as response:
            original = response.read()
        request = urllib.request.Request(f"http://{address}{asset}", headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(request, timeout=2) as response:
            compressed = response.read()
            self.assertEqual(response.headers["Content-Encoding"], "gzip")
            self.assertIn("Accept-Encoding", response.headers["Vary"])
            self.assertEqual(response.headers["Cache-Control"], "public, max-age=31536000, immutable")
        self.assertEqual(gzip.decompress(compressed), original)
        self.assertLess(len(compressed), len(original))
        self.assertEqual(self.request(address, "/assets/missing.js"), 404)

    def test_password_protects_console_and_api(self):
        password = "strong $: ' \\ test 密码"
        container = self.start_web(password=password)
        address = self.wait_for_web(container)
        for path in ("/", "/api/health"):
            with self.subTest(path=path):
                self.assertEqual(self.request(address, path), 401)
                self.assertEqual(self.request(address, path, password="wrong"), 401)
        self.assertEqual(self.request(address, password=password), 200)
        self.assertEqual(self.request(address, "/api/health", password=password), 502)
        self.assertEqual(self.request(address, username="other", password=password), 401)
        result = self.docker("exec", container, "cat", "/etc/nginx/admin.htpasswd")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("admin:$2"))
        self.assertNotIn(password, result.stdout)
        logs = self.docker("logs", container)
        self.assertNotIn(password, logs.stdout + logs.stderr)
        self.assertEqual(self.docker("restart", container).returncode, 0)
        address = self.wait_for_web(container)
        self.assertEqual(self.request(address, password=password), 200)

    def test_custom_username_and_changed_password(self):
        for password in ("first-password", "second-password"):
            with self.subTest(password=password):
                container = self.start_web(username="owner@example.com", password=password)
                address = self.wait_for_web(container)
                self.assertEqual(self.request(address, username="owner@example.com", password=password), 200)
                other_password = "second-password" if password == "first-password" else "first-password"
                self.assertEqual(self.request(address, username="owner@example.com", password=other_password), 401)
                self.assertEqual(self.request(address, password=password), 401)

    def legacy_file(self, directory):
        result = self.docker("run", "--rm", "--entrypoint", "htpasswd", "-i", WEB_IMAGE,
                             "-niB", "admin", input="legacy-password\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        path = Path(directory) / "htpasswd"
        path.write_text(result.stdout)
        path.chmod(0o644)
        return path

    def test_legacy_auth_is_preserved_and_environment_takes_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy = self.legacy_file(directory)
            original = legacy.read_bytes()
            for password in (None, "environment-password"):
                with self.subTest(environment_password=password):
                    container = self.start_web(password=password, legacy=legacy)
                    address = self.wait_for_web(container)
                    self.assertEqual(self.request(address), 401)
                    self.assertEqual(self.request(address, password=password or "legacy-password"), 200)
                    if password:
                        self.assertEqual(self.request(address, password="legacy-password"), 401)
                    self.assertEqual(legacy.read_bytes(), original)
                    self.docker("rm", "-f", container)

    def test_unconfigured_development_mode(self):
        container = self.start_web()
        address = self.wait_for_web(container)
        self.assertEqual(self.request(address), 200)
        self.assertIn("WARNING: ADMIN_PASSWORD is unset", self.docker("logs", container).stderr)

    def test_app_mode_serves_login_page_without_basic_auth_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy = self.legacy_file(directory)
            container = self.start_web(password="environment-password", legacy=legacy, mode="app")
            address = self.wait_for_web(container)
            self.assertEqual(self.request(address, "/login"), 200)
            self.assertEqual(self.request(address, "/api/auth/session"), 502)
            result = self.docker("exec", container, "cat", "/etc/nginx/admin-auth.conf")
            self.assertEqual(result.stdout, "auth_basic off;\n")
            self.docker("rm", "-f", container)

    def test_invalid_credentials_fail_closed(self):
        settings = (("bad:name", "password"), ("bad\nname", "password"), ("", "password"),
                    ("admin", "bad\npassword"), ("admin", "bad\rpassword"),
                    ("admin", "a" * 73), ("admin", "密" * 25), ("owner", None))
        for username, password in settings:
            with self.subTest(username=username):
                container = self.start_web(username=username, password=password)
                result = self.docker("wait", container)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotEqual(result.stdout.strip(), "0")
                logs = self.docker("logs", container)
                if password:
                    self.assertNotIn(password, logs.stdout + logs.stderr)

    def test_empty_legacy_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy = Path(directory) / "htpasswd"
            legacy.touch()
            container = self.start_web(legacy=legacy)
            result = self.docker("wait", container)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotEqual(result.stdout.strip(), "0")


if __name__ == "__main__":
    unittest.main()
