import base64
import hashlib
import json
import logging
import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey

from backend.auth import AuthConfig, AuthLogFilter, AuthService, SESSION_COOKIE, origin
from backend.auth_store import AuthStore
from backend.store import RunStore
from tests.database import create_test_store


class AuthConfigurationTests(unittest.TestCase):
    def test_defaults_preserve_basic_authentication(self):
        with patch.dict(os.environ, {}, clear=True):
            config = AuthConfig.from_env()
        self.assertEqual(config.mode, "basic")
        self.assertFalse(config.enabled)

    def test_application_mode_fails_closed_without_login_method(self):
        with self.assertRaisesRegex(ValueError, "requires"):
            AuthConfig(mode="app").validate()

    def test_rejects_incomplete_provider_configuration(self):
        configurations = (
            {"github_client_id": "client"},
            {"github_client_secret": "secret"},
            {"oidc_issuer": "https://issuer.example"},
            {"oidc_client_id": "client", "oidc_client_secret": "secret"},
            {"oidc_issuer": "https://issuer.example", "oidc_client_id": "client"},
        )
        for configuration in configurations:
            with self.subTest(configuration=configuration), self.assertRaises(ValueError):
                AuthConfig(mode="app", password="password", **configuration).validate()

    def test_validates_public_origin_and_issuer(self):
        for url in ("//evil.example", "javascript:bad", "https://example.com/path", "https://admin:secret@example.com", "https://example.com?query"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                AuthConfig(mode="app", password="password", public_url=url).validate()
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            AuthConfig(mode="app", oidc_issuer="http://issuer.example", oidc_client_id="client", oidc_client_secret="secret").validate()

    def test_additional_origins_are_explicit_and_normalized(self):
        with patch.dict(os.environ, {"AUTH_MODE": "app", "ADMIN_PASSWORD": "password",
                                    "AUTH_PUBLIC_URL": "https://Primary.Example:443",
                                    "AUTH_ALLOWED_ORIGINS": " https://Alias.Example:8441,https://primary.example "}, clear=True):
            config = AuthConfig.from_env()
        self.assertEqual(config.trusted_origins, frozenset({"https://primary.example", "https://alias.example:8441"}))
        self.assertEqual(origin("http://[::1]:8080"), "http://[::1]:8080")
        self.assertEqual(origin("http://localhost:80"), "http://localhost")

    def test_invalid_origin_allowlists_fail_closed(self):
        for value in ("*", "null", "https://*.example.com", "//example.com", "https://example.com/path",
                      "https://user:password@example.com", "https://example.com?query", "https://example.com#fragment",
                      "http://example.com:invalid", "http://example.com:99999", "http://exam ple.com", "http://example.com\\evil"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                AuthConfig(mode="app", password="password", allowed_origins=frozenset({value})).validate()

    def test_complete_identity_providers_do_not_require_account_allowlists(self):
        configurations = (
            {"GITHUB_CLIENT_ID": "client", "GITHUB_CLIENT_SECRET": "secret"},
            {"OIDC_ISSUER_URL": "https://issuer.example/", "OIDC_CLIENT_ID": "client", "OIDC_CLIENT_SECRET": "secret"},
        )
        for configuration in configurations:
            with self.subTest(provider=next(iter(configuration))), patch.dict(os.environ, {"AUTH_MODE": "app", **configuration}, clear=True):
                config = AuthConfig.from_env()
                self.assertTrue(config.enabled)
                self.assertFalse(config.password)

    def test_legacy_account_allowlist_variables_are_ignored(self):
        environment = {"AUTH_MODE": "app", "GITHUB_CLIENT_ID": "client", "GITHUB_CLIENT_SECRET": "secret",
                       "OIDC_ISSUER_URL": "https://issuer.example/", "OIDC_CLIENT_ID": "client", "OIDC_CLIENT_SECRET": "secret"}
        with patch.dict(os.environ, environment, clear=True):
            original = AuthConfig.from_env()
            with patch.dict(os.environ, {"GITHUB_ALLOWED_IDS": "1234", "GITHUB_ALLOWED_USERS": "owner",
                                         "OIDC_ALLOWED_SUBJECTS": "subject", "OIDC_ALLOWED_EMAILS": "owner@example.com"}):
                config = AuthConfig.from_env()
        self.assertEqual(config, original)
        self.assertEqual(config.version(), original.version())
        self.assertEqual(config.oidc_issuer, "https://issuer.example/")

    def test_sensitive_values_are_not_in_configuration_repr(self):
        config = AuthConfig(password="password-secret", github_client_secret="github-secret", oidc_client_secret="oidc-secret")
        for secret in (config.password, config.github_client_secret, config.oidc_client_secret):
            self.assertNotIn(secret, repr(config))

    def test_access_logs_redact_callback_query(self):
        record = logging.LogRecord("uvicorn.access", 20, "", 0, "%s %s %s %s %s",
                                   ("client", "GET", "/api/auth/oidc/callback?code=secret&state=secret", "1.1", 303), None)
        self.assertTrue(AuthLogFilter().filter(record))
        self.assertNotIn("secret", record.getMessage())

    def test_session_signing_key_is_persistent_private_and_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"AUTH_MODE": "app", "ADMIN_PASSWORD": "password"}, clear=True):
            first = AuthService.from_env(RunStore("", initialize=False), Path(directory))
            second = AuthService.from_env(RunStore("", initialize=False), Path(directory))
            self.assertEqual(first.signing_secret, second.signing_secret)
            self.assertEqual(first.version, second.version)
            path = Path(directory) / "auth-session.key"
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.write_text("")
            with self.assertRaises(ValueError):
                AuthService.from_env(RunStore("", initialize=False), Path(directory))

    def test_explicit_short_signing_secret_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "AUTH_MODE": "app", "ADMIN_PASSWORD": "password", "AUTH_SESSION_SECRET": "short",
        }, clear=True), self.assertRaises(ValueError):
            AuthService.from_env(RunStore("", initialize=False), Path(directory))


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = create_test_store(self, Path(self.temporary.name))
        self.storage = AuthStore(self.store)
        self.storage.initialize()
        self.config = AuthConfig(
            mode="app", public_url="http://testserver", password="fixture-password",
            allowed_origins=frozenset({"http://localhost:8441"}),
            github_client_id="github-client", github_client_secret="github-secret",
            oidc_issuer="https://issuer.example/", oidc_client_id="oidc-client", oidc_client_secret="oidc-secret",
        )
        self.service = AuthService(self.config, self.storage, "fixture-signing-secret-which-is-at-least-32-characters")
        self.key = RSAKey.generate_key(2048, parameters={"kid": "fixture"})
        self.bad_key = RSAKey.generate_key(2048, parameters={"kid": "fixture"})
        self.claim_overrides = {}
        self.github_profile = {"id": 1234, "login": "owner", "name": "Workspace owner"}
        self.token_overrides = {}
        self.token_requests = []
        self.metadata_overrides = {}
        self.signing_key = self.key
        self.nonce = ""
        self.challenge = ""
        for provider in ("github", "oidc"):
            self.service.oauth.create_client(provider).client_kwargs["transport"] = httpx.MockTransport(self.provider_request)
        self.app = FastAPI()
        self.service.install(self.app)

        @self.app.get("/api/private")
        def private():
            return {"private": True}

        @self.app.post("/api/private")
        def mutate():
            return {"saved": True}

        @self.app.get("/api/health")
        def health():
            return {"status": "ok"}

        self.client = TestClient(self.app, follow_redirects=False)
        self.addCleanup(self.client.close)

    def provider_request(self, request):
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={
                "issuer": self.config.oidc_issuer, "authorization_endpoint": "https://issuer.example/authorize",
                "token_endpoint": "https://issuer.example/token", "jwks_uri": "https://issuer.example/jwks",
                "id_token_signing_alg_values_supported": ["RS256"], **self.metadata_overrides,
            })
        if request.url.path == "/jwks":
            return httpx.Response(200, json={"keys": [self.key.as_dict(private=False)]})
        if request.url.path in {"/token", "/login/oauth/access_token"}:
            parameters = parse_qs(request.content.decode())
            self.assertEqual(parameters["redirect_uri"][0], f"{self.config.public_url}/api/auth/{'oidc' if request.url.host == 'issuer.example' else 'github'}/callback")
            verifier = parameters["code_verifier"][0]
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            self.assertEqual(challenge, self.challenge)
            self.token_requests.append(request)
            token = {"access_token": "provider-access-token", "token_type": "Bearer"}
            if request.url.host == "issuer.example":
                claims = {"iss": self.config.oidc_issuer, "sub": "subject", "aud": "oidc-client",
                          "exp": int(time.time()) + 300, "iat": int(time.time()), "nonce": self.nonce,
                          "preferred_username": "oidc-owner", "name": "OIDC Owner", **self.claim_overrides}
                token["id_token"] = jwt.encode({"alg": "RS256", "kid": "fixture"}, claims, self.signing_key)
            token.update(self.token_overrides)
            return httpx.Response(200, json=token)
        if request.url.host == "api.github.com" and request.url.path == "/user":
            self.assertEqual(request.headers["Authorization"], "Bearer provider-access-token")
            return httpx.Response(200, json=self.github_profile)
        raise AssertionError(f"Unexpected provider request: {request.method} {request.url.host}{request.url.path}")

    def login(self):
        result = self.client.post("/api/auth/login", json={"username": "admin", "password": "fixture-password"})
        self.assertEqual(result.status_code, 200, result.text)
        return result

    def start_flow(self, provider):
        result = self.client.get(f"/api/auth/{provider}/login")
        self.assertEqual(result.status_code, 302, result.text)
        parameters = parse_qs(urlsplit(result.headers["location"]).query)
        self.assertEqual(parameters["code_challenge_method"], ["S256"])
        self.challenge = parameters["code_challenge"][0]
        self.nonce = parameters.get("nonce", [""])[0]
        self.assertNotIn("secret", result.headers["location"])
        return parameters["state"][0]

    def callback(self, provider, state):
        return self.client.get(f"/api/auth/{provider}/callback", params={"code": "fixture-code", "state": state})

    def test_anonymous_api_access_is_denied_without_browser_basic_prompt(self):
        result = self.client.get("/api/private")
        self.assertEqual(result.status_code, 401)
        self.assertNotIn("WWW-Authenticate", result.headers)
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/docs").status_code, 401)
        status = self.client.get("/api/auth/session").json()
        self.assertTrue(status["enabled"])
        self.assertIsNone(status["user"])
        for secret in (self.config.password, self.config.github_client_secret, self.config.oidc_client_secret):
            self.assertNotIn(secret, json.dumps(status))

    def test_password_login_and_cookie_security_and_csrf(self):
        result = self.login()
        cookie = result.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertIn("Max-Age=86400", cookie)
        self.assertEqual(self.client.get("/api/private").status_code, 200)
        self.assertEqual(self.client.post("/api/private").status_code, 403)
        headers = {"X-CSRF-Token": result.json()["csrf_token"], "Origin": "http://testserver"}
        self.assertEqual(self.client.post("/api/private", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/api/private", headers={**headers, "Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.post("/api/private", headers={"X-CSRF-Token": "wrong"}).status_code, 403)
        self.assertEqual(self.client.get("/api/auth/session").headers["Cache-Control"], "no-store")
        with self.store._session() as connection:
            row = connection.execute("SELECT token_hash FROM auth_sessions").fetchone()
        self.assertNotEqual(row["token_hash"], self.client.cookies[SESSION_COOKIE])

    def test_logout_revokes_stolen_session_and_requires_csrf(self):
        login = self.login().json()
        token = self.client.cookies[SESSION_COOKIE]
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 403)
        self.assertEqual(self.client.post("/api/auth/logout", headers={"X-CSRF-Token": login["csrf_token"]}).status_code, 204)
        self.assertEqual(self.client.get("/api/private").status_code, 401)
        self.client.cookies.set(SESSION_COOKIE, token)
        self.assertEqual(self.client.get("/api/private").status_code, 401)

    def test_reauthentication_rotates_session_and_password_changes_revoke_sessions(self):
        self.login()
        token = self.client.cookies[SESSION_COOKIE]
        self.login()
        self.assertNotEqual(self.client.cookies[SESSION_COOKIE], token)
        self.assertIsNone(self.storage.user(token, self.service.version))
        new_version = replace(self.config, password="changed-password").version()
        self.assertIsNone(self.storage.user(self.client.cookies[SESSION_COOKIE], new_version))
        other_service = AuthService(self.config, self.storage, "different-signing-secret-at-least-32-characters")
        self.assertIsNone(self.storage.user(self.client.cookies[SESSION_COOKIE], other_service.version))

    def test_expired_sessions_and_cookie_tampering_are_rejected(self):
        self.login()
        with self.store._session() as connection:
            connection.execute("UPDATE auth_sessions SET expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'")
        self.assertEqual(self.client.get("/api/private").status_code, 401)
        self.client.cookies.set(SESSION_COOKIE, "forged-session")
        self.assertEqual(self.client.get("/api/private").status_code, 401)

    def test_cross_origin_login_is_rejected_and_failures_are_throttled(self):
        credentials = {"username": "admin", "password": "fixture-password"}
        self.assertEqual(self.client.post("/api/auth/login", json=credentials, headers={"Origin": "https://evil.example"}).status_code, 403)
        for attempt in range(10):
            result = self.client.post("/api/auth/login", json={**credentials, "password": "incorrect"})
            self.assertEqual(result.status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json=credentials).status_code, 429)
        now = time.monotonic()
        with patch("backend.auth.time.monotonic", return_value=now + 61):
            self.assertEqual(self.client.post("/api/auth/login", json=credentials).status_code, 200)

    def test_allowed_alias_can_login_mutate_and_logout_with_csrf(self):
        alias = {"Origin": "http://localhost:8441"}
        result = self.client.post("/api/auth/login", json={"username": "admin", "password": "fixture-password"}, headers=alias)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.post("/api/private", headers=alias).status_code, 403)
        headers = {**alias, "X-CSRF-Token": result.json()["csrf_token"]}
        self.assertEqual(self.client.post("/api/private", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/api/private").status_code, 401)

    def test_untrusted_origin_returns_actionable_error_and_ignores_spoofed_hosts(self):
        credentials = {"username": "admin", "password": "fixture-password"}
        for value in ("http://localhost:8442", "https://localhost:8441", "http://localhost:8441.evil.example",
                      "https://evil.example", "null", "", "http://localhost:8441/path", "http://localhost:invalid"):
            with self.subTest(origin=value):
                response = self.client.post("/api/auth/login", json=credentials, headers={
                    "Origin": value, "Host": "evil.example", "X-Forwarded-Host": "evil.example",
                })
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "origin_not_allowed")
                self.assertIn("AUTH_ALLOWED_ORIGINS", response.json()["detail"])
                self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.post("/api/auth/login", json=credentials).status_code, 200)

    def test_github_login_persists_stable_identity_without_provider_tokens(self):
        state = self.start_flow("github")
        result = self.callback("github", state)
        self.assertEqual(result.headers["location"], "/")
        user = self.client.get("/api/auth/session").json()["user"]
        self.assertEqual(user["provider"], "github")
        self.assertEqual(user["username"], "owner")
        self.github_profile["login"] = "renamed-owner"
        state = self.start_flow("github")
        self.callback("github", state)
        self.assertEqual(self.client.get("/api/auth/session").json()["user"]["id"], user["id"])
        with self.store._session() as connection:
            rows = connection.execute("SELECT * FROM auth_users").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["subject"], "1234")
        self.assertNotIn("provider-access-token", str(rows))

    def test_any_authenticated_github_account_can_access_the_workspace(self):
        self.github_profile["id"] = 9876
        self.github_profile["login"] = "another-user"
        state = self.start_flow("github")
        result = self.callback("github", state)
        self.assertEqual(result.headers["location"], "/")
        self.assertEqual(self.client.get("/api/auth/session").json()["user"]["username"], "another-user")
        self.assertEqual(self.client.get("/api/private").status_code, 200)

    def test_github_still_rejects_invalid_user_profiles(self):
        for identifier, username in ((None, "owner"), (True, "owner"), (-1, "owner"), (1234, ""), (1234, None)):
            with self.subTest(identifier=identifier, username=username):
                self.client.cookies.clear()
                self.github_profile = {"id": identifier, "login": username}
                state = self.start_flow("github")
                result = self.callback("github", state)
                self.assertEqual(result.headers["location"], "/login?auth_error=provider_error")
                self.assertIsNone(self.client.get("/api/auth/session").json()["user"])
                self.assertEqual(self.client.get("/api/private").status_code, 401)

    def test_oauth_state_is_browser_bound_and_single_use(self):
        state = self.start_flow("github")
        oauth_cookie = self.client.cookies["prismlab_oauth"]
        with TestClient(self.app, follow_redirects=False) as outsider:
            result = outsider.get("/api/auth/github/callback", params={"state": state, "code": "attacker-code"})
        self.assertEqual(result.headers["location"], "/login?auth_error=provider_error")
        self.assertEqual(len(self.token_requests), 0)
        self.assertEqual(self.callback("github", state).headers["location"], "/")
        with TestClient(self.app, follow_redirects=False) as replay:
            replay.cookies.set("prismlab_oauth", oauth_cookie)
            result = replay.get("/api/auth/github/callback", params={"state": state, "code": "fresh-code"})
        self.assertEqual(result.headers["location"], "/login?auth_error=provider_error")
        self.assertEqual(len(self.token_requests), 1)

    def test_expired_oauth_state_and_cancelled_authorization_fail_safely(self):
        state = self.start_flow("github")
        with self.store._session() as connection:
            connection.execute("UPDATE auth_flows SET expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'")
        self.assertEqual(self.callback("github", state).headers["location"], "/login?auth_error=provider_error")
        state = self.start_flow("github")
        result = self.client.get("/api/auth/github/callback", params={"state": state, "error": "access_denied", "error_description": "secret"})
        self.assertEqual(result.headers["location"], "/login?auth_error=provider_error")
        self.assertNotIn("secret", result.text)

    def test_valid_oidc_logins_preserve_distinct_subject_identities(self):
        state = self.start_flow("oidc")
        self.assertTrue(self.nonce)
        self.assertEqual(self.callback("oidc", state).headers["location"], "/")
        first_user = self.client.get("/api/auth/session").json()["user"]
        self.assertEqual(first_user["provider"], "oidc")
        self.client.cookies.clear()
        self.claim_overrides = {"sub": "another-subject", "email": "Owner@Example.COM", "email_verified": True}
        state = self.start_flow("oidc")
        self.assertEqual(self.callback("oidc", state).headers["location"], "/")
        self.assertNotEqual(self.client.get("/api/auth/session").json()["user"]["id"], first_user["id"])

    def test_any_authenticated_oidc_subject_can_access_without_email_verification(self):
        for claims in ({"sub": "another-subject", "email": "owner@example.com", "email_verified": False},
                       {"sub": "user-without-email"}):
            with self.subTest(claims=claims):
                self.client.cookies.clear()
                self.claim_overrides = claims
                state = self.start_flow("oidc")
                self.assertEqual(self.callback("oidc", state).headers["location"], "/")
                self.assertEqual(self.client.get("/api/private").status_code, 200)

    def test_oidc_still_requires_a_valid_subject(self):
        for subject in (None, "", 1234):
            with self.subTest(subject=subject):
                self.client.cookies.clear()
                self.claim_overrides = {"sub": subject}
                state = self.start_flow("oidc")
                self.assertEqual(self.callback("oidc", state).headers["location"], "/login?auth_error=provider_error")
                self.assertIsNone(self.client.get("/api/auth/session").json()["user"])
                self.assertEqual(self.client.get("/api/private").status_code, 401)

    def test_oidc_rejects_bad_signature_issuer_audience_nonce_and_expiry(self):
        failures = ({"iss": "https://evil.example"}, {"aud": "another-client"}, {"nonce": "wrong"},
                    {"exp": int(time.time()) - 3600}, {"signature": "wrong"})
        for failure in failures:
            with self.subTest(failure=failure):
                self.client.cookies.clear()
                self.claim_overrides = {key: value for key, value in failure.items() if key != "signature"}
                self.signing_key = self.bad_key if "signature" in failure else self.key
                state = self.start_flow("oidc")
                self.assertEqual(self.callback("oidc", state).headers["location"], "/login?auth_error=provider_error")
                self.assertIsNone(self.client.get("/api/auth/session").json()["user"])

    def test_oidc_rejects_missing_id_token_even_if_token_response_contains_profile(self):
        self.token_overrides = {"id_token": None, "userinfo": {"sub": "subject", "name": "unverified"}}
        state = self.start_flow("oidc")
        self.assertEqual(self.callback("oidc", state).headers["location"], "/login?auth_error=provider_error")

    def test_oidc_metadata_must_match_configured_issuer(self):
        self.metadata_overrides = {"issuer": "https://evil.example"}
        result = self.client.get("/api/auth/oidc/login")
        self.assertEqual(result.headers["location"], "/login?auth_error=provider_error")

    def test_session_count_is_bounded(self):
        for attempt in range(12):
            self.storage.create_session("local", "admin", "admin", "admin", self.service.version)
        with self.store._session() as connection:
            count = connection.execute("SELECT COUNT(*) AS total FROM auth_sessions").fetchone()["total"]
        self.assertEqual(count, 10)


if __name__ == "__main__":
    unittest.main()
