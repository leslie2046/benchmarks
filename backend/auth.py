import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, SecretStr
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from backend.auth_store import AuthStore
from backend.profile import MAX_AVATAR_BYTES, ProfileUpdate, normalize_avatar
from backend.store import RunStore
from backend.tenant_context import workspace_context


SESSION_COOKIE = "prismlab_session"
SESSION_AGE = 24 * 60 * 60
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def values(name: str) -> frozenset[str]:
    return frozenset(item.strip() for item in os.getenv(name, "").split(",") if item.strip())


def origin(url: str) -> str:
    if not url or any(character.isspace() for character in url) or "\\" in url:
        raise ValueError("Expected an absolute HTTP(S) origin without a path")
    parsed = urlsplit(url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or "*" in parsed.hostname
            or parsed.username is not None or parsed.password is not None or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("Expected an absolute HTTP(S) origin without a path")
    hostname = parsed.hostname.lower()
    if ":" in hostname:
        hostname = f"[{hostname}]"
    port = parsed.port
    suffix = f":{port}" if port is not None and port != {"http": 80, "https": 443}[parsed.scheme] else ""
    return f"{parsed.scheme}://{hostname}{suffix}"


@dataclass(frozen=True)
class AuthConfig:
    mode: str = "basic"
    public_url: str = "http://localhost:8080"
    allowed_origins: frozenset[str] = frozenset()
    username: str = "admin"
    password: str = field(default="", repr=False)
    github_client_id: str = ""
    github_client_secret: str = field(default="", repr=False)
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = field(default="", repr=False)
    oidc_name: str = "Single sign-on"

    @classmethod
    def from_env(cls):
        config = cls(
            mode=os.getenv("AUTH_MODE", "basic"), public_url=os.getenv("AUTH_PUBLIC_URL", "http://localhost:8080").rstrip("/"),
            allowed_origins=values("AUTH_ALLOWED_ORIGINS"),
            username=os.getenv("ADMIN_USERNAME", "admin"), password=os.getenv("ADMIN_PASSWORD", ""),
            github_client_id=os.getenv("GITHUB_CLIENT_ID", ""), github_client_secret=os.getenv("GITHUB_CLIENT_SECRET", ""),
            oidc_issuer=os.getenv("OIDC_ISSUER_URL", ""), oidc_client_id=os.getenv("OIDC_CLIENT_ID", ""),
            oidc_client_secret=os.getenv("OIDC_CLIENT_SECRET", ""), oidc_name=os.getenv("OIDC_PROVIDER_NAME", "Single sign-on"),
        )
        config.validate()
        return config

    @property
    def enabled(self):
        return self.mode == "app"

    @property
    def secure(self):
        return self.public_url.startswith("https://")

    @property
    def trusted_origins(self):
        return frozenset(origin(value) for value in (self.public_url, *self.allowed_origins))

    def validate(self):
        if self.mode not in {"basic", "app"}:
            raise ValueError("AUTH_MODE must be basic or app")
        if not self.enabled:
            return
        try:
            self.trusted_origins
        except ValueError as error:
            raise ValueError("AUTH_PUBLIC_URL and AUTH_ALLOWED_ORIGINS must be absolute HTTP(S) origins without paths or wildcards") from error
        if not re.fullmatch(r"[a-zA-Z0-9_.@-]{1,128}", self.username):
            raise ValueError("ADMIN_USERNAME contains invalid characters")
        if self.password and ("\n" in self.password or "\r" in self.password or len(self.password.encode()) > 72):
            raise ValueError("ADMIN_PASSWORD must be at most 72 bytes without line breaks")
        github = [self.github_client_id, self.github_client_secret]
        if any(github) and not all(github):
            raise ValueError("GitHub requires client ID and client secret")
        oidc = [self.oidc_issuer, self.oidc_client_id, self.oidc_client_secret]
        if any(oidc):
            if not all(oidc):
                raise ValueError("OIDC requires issuer, client ID and client secret")
            issuer = urlsplit(self.oidc_issuer)
            if issuer.scheme != "https" or not issuer.hostname or issuer.username or issuer.password or issuer.query or issuer.fragment:
                raise ValueError("OIDC_ISSUER_URL must use HTTPS")
        if not self.password and not self.github_client_id and not self.oidc_client_id:
            raise ValueError("App authentication requires an administrator password or a configured identity provider")

    def version(self):
        data = {name: sorted(value) if isinstance(value, frozenset) else value for name, value in vars(self).items()}
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class LoginRequest(BaseModel):
    username: str = Field(max_length=128)
    password: SecretStr = Field(max_length=1024)


class AuthLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, path, version, status = record.args
            if isinstance(path, str) and path.startswith("/api/auth/"):
                record.args = (client, method, path.split("?", 1)[0], version, status)
        return True


class AuthService:
    def __init__(self, config: AuthConfig, storage: AuthStore, signing_secret: str):
        config.validate()
        self.config = config
        self.trusted_origins = config.trusted_origins if config.enabled else frozenset()
        self.storage = storage
        self.workspaces = None
        self.signing_secret = signing_secret
        self.version = hashlib.sha256((config.version() + signing_secret + "workspaces-v1").encode()).hexdigest()
        self.salt = secrets.token_bytes(16)
        self.password_hash = self.password_digest(config.password)
        self.attempts = {}
        self.attempts_lock = threading.Lock()
        self.oauth = OAuth()
        if config.github_client_id:
            self.oauth.register(
                "github", client_id=config.github_client_id, client_secret=config.github_client_secret,
                authorize_url="https://github.com/login/oauth/authorize", access_token_url="https://github.com/login/oauth/access_token",
                api_base_url="https://api.github.com/",
                client_kwargs={"scope": "read:user", "code_challenge_method": "S256", "timeout": 10.0},
            )
        if config.oidc_client_id:
            self.oauth.register(
                "oidc", client_id=config.oidc_client_id, client_secret=config.oidc_client_secret,
                server_metadata_url=f"{config.oidc_issuer.rstrip('/')}/.well-known/openid-configuration",
                client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256", "timeout": 10.0},
            )

    @classmethod
    def from_env(cls, store: RunStore, data_dir: Path):
        config = AuthConfig.from_env()
        secret = os.getenv("AUTH_SESSION_SECRET", "")
        if config.enabled and not secret:
            path = data_dir / "auth-session.key"
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "w") as stream:
                    stream.write(secrets.token_urlsafe(48))
            secret = path.read_text().strip()
        if config.enabled and len(secret) < 32:
            raise ValueError("AUTH_SESSION_SECRET must be at least 32 characters")
        return cls(config, AuthStore(store), secret or secrets.token_urlsafe(48))

    def initialize(self):
        if self.config.enabled:
            self.storage.initialize()

    def password_digest(self, password):
        return hashlib.scrypt(password.encode(), salt=self.salt, n=16384, r=8, p=1)

    def csrf(self, token):
        return hmac.new(self.signing_secret.encode(), token.encode(), hashlib.sha256).hexdigest()

    def status(self, user=None, token=""):
        return {
            "enabled": self.config.enabled, "user": user,
            "password_enabled": bool(self.config.password) and self.config.enabled,
            "csrf_token": self.csrf(token) if user else None,
            "providers": [
                {"id": "github", "name": "GitHub", "enabled": bool(self.config.github_client_id), "login_url": "/api/auth/github/login"},
                {"id": "oidc", "name": self.config.oidc_name, "enabled": bool(self.config.oidc_client_id), "login_url": "/api/auth/oidc/login"},
            ],
            **(self.workspaces.list_for_user(user) if user and self.workspaces else {}),
        }

    def check_attempt(self, address):
        now = time.monotonic()
        with self.attempts_lock:
            self.attempts = {key: queue for key, queue in self.attempts.items() if queue and now - queue[-1] < 60}
            if address not in self.attempts and len(self.attempts) >= 10000:
                raise HTTPException(429, "Too many login attempts", headers={"Retry-After": "60"})
            queue = self.attempts.setdefault(address, deque())
            while queue and now - queue[0] >= 60:
                queue.popleft()
            if len(queue) >= 10:
                raise HTTPException(429, "Too many login attempts", headers={"Retry-After": "60"})
            queue.append(now)

    def new_session(self, response, provider, subject, username, name, previous_token=""):
        if previous_token:
            self.storage.revoke(previous_token)
        token, user = self.storage.create_session(provider, subject, username, name, self.version)
        response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_AGE, httponly=True,
                            secure=self.config.secure, samesite="lax", path="/")
        return self.status(user, token)

    async def provider(self, name):
        if name not in {"github", "oidc"}:
            raise HTTPException(404, "Unknown identity provider")
        client = self.oauth.create_client(name)
        if client is None or not self.config.enabled:
            raise HTTPException(404, "Identity provider is not configured")
        if name == "oidc":
            metadata = await client.load_server_metadata()
            if metadata.get("issuer") != self.config.oidc_issuer:
                raise ValueError("OIDC issuer mismatch")
            for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
                if urlsplit(metadata.get(key, "")).scheme != "https":
                    raise ValueError("OIDC endpoints must use HTTPS")
            algorithms = metadata.get("id_token_signing_alg_values_supported", ["RS256"])
            safe_algorithms = {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"}
            metadata["id_token_signing_alg_values_supported"] = [value for value in algorithms if value in safe_algorithms]
            if not metadata["id_token_signing_alg_values_supported"]:
                raise ValueError("OIDC must support asymmetric ID token signatures")
        return client

    def install(self, app):
        service = self
        public_paths = {"/api/health", "/api/auth/session", "/api/auth/login",
                        "/api/auth/github/login", "/api/auth/github/callback",
                        "/api/auth/oidc/login", "/api/auth/oidc/callback"}

        @app.middleware("http")
        async def protect(request: Request, call_next):
            if not service.config.enabled:
                return await call_next(request)
            token = request.cookies.get(SESSION_COOKIE, "")
            user = await run_in_threadpool(service.storage.user, token, service.version)
            request.state.auth_user = user
            unsafe = request.method not in SAFE_METHODS
            if unsafe:
                request_origin = request.headers.get("origin")
                if request_origin is not None:
                    try:
                        trusted = origin(request_origin) in service.trusted_origins
                    except ValueError:
                        trusted = False
                    if not trusted:
                        return JSONResponse({"detail": "This site address is not allowed for sign-in. Check AUTH_PUBLIC_URL and AUTH_ALLOWED_ORIGINS.",
                                             "code": "origin_not_allowed"}, status_code=403,
                                            headers={"Cache-Control": "no-store"})
            if request.url.path not in public_paths:
                if not user:
                    return JSONResponse({"detail": "Authentication required"}, status_code=401,
                                        headers={"Cache-Control": "no-store"})
                if unsafe and not hmac.compare_digest(request.headers.get("x-csrf-token", "").encode(), service.csrf(token).encode()):
                    return JSONResponse({"detail": "Invalid CSRF token"}, status_code=403)
            context_token = None
            if user and service.workspaces:
                try:
                    access = await run_in_threadpool(service.workspaces.access, request, user)
                except HTTPException as error:
                    return JSONResponse({"detail": error.detail}, status_code=error.status_code)
                context_token = workspace_context.set(access)
            try:
                response = await call_next(request)
            finally:
                if context_token is not None:
                    workspace_context.reset(context_token)
            response.headers["Cache-Control"] = "no-store"
            if request.url.path.startswith("/api/auth/"):
                response.headers["Referrer-Policy"] = "no-referrer"
            return response

        app.add_middleware(SessionMiddleware, secret_key=self.signing_secret, session_cookie="prismlab_oauth",
                           max_age=600, same_site="lax", https_only=self.config.secure)
        logging.getLogger("uvicorn.access").addFilter(AuthLogFilter())
        router = APIRouter(prefix="/api/auth", tags=["authentication"])

        @router.get("/session")
        def session(request: Request):
            return service.status(getattr(request.state, "auth_user", None), request.cookies.get(SESSION_COOKIE, ""))

        def profile_user(request):
            user = getattr(request.state, "auth_user", None)
            if not service.config.enabled or not user:
                raise HTTPException(401, "Authentication required")
            return user

        @router.patch("/profile")
        def update_profile(payload: ProfileUpdate, request: Request):
            return service.storage.update_nickname(profile_user(request)["id"], payload.nickname)

        @router.put("/profile/avatar")
        async def upload_avatar(request: Request):
            user = profile_user(request)
            if request.headers.get("content-type", "").split(";", 1)[0].lower() not in {"image/png", "image/jpeg", "image/webp"}:
                raise HTTPException(415, "Upload a PNG, JPEG or WebP image")
            data = bytearray()
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_AVATAR_BYTES:
                    raise HTTPException(413, "Avatar must be at most 1 MB")
                data.extend(chunk)
            avatar = await run_in_threadpool(normalize_avatar, bytes(data))
            return await run_in_threadpool(service.storage.update_avatar, user["id"], avatar)

        @router.delete("/profile/avatar")
        def remove_avatar(request: Request):
            return service.storage.update_avatar(profile_user(request)["id"], None)

        @router.get("/profile/avatar/{user_id}/{version}")
        def avatar(user_id: str, version: str, request: Request):
            user = profile_user(request)
            if user_id != user["id"] and (not service.workspaces or not service.workspaces.shares_team(user["id"], user_id)):
                raise HTTPException(404, "Avatar not found")
            data = service.storage.avatar(user_id, version)
            if not data:
                raise HTTPException(404, "Avatar not found")
            return Response(data, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"})

        @router.post("/login")
        def login(payload: LoginRequest, request: Request, response: Response):
            if not service.config.enabled or not service.config.password:
                raise HTTPException(404, "Password login is not configured")
            if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
                raise HTTPException(415, "JSON is required")
            service.check_attempt(request.client.host if request.client else "unknown")
            valid = hmac.compare_digest(service.password_digest(payload.password.get_secret_value()), service.password_hash)
            if not valid or not hmac.compare_digest(payload.username.encode(), service.config.username.encode()):
                raise HTTPException(401, "Invalid username or password")
            return service.new_session(response, "local", service.config.username, service.config.username,
                                       service.config.username, request.cookies.get(SESSION_COOKIE, ""))

        @router.post("/logout", status_code=204)
        def logout(request: Request):
            if not service.config.enabled:
                raise HTTPException(404, "Application authentication is disabled")
            service.storage.revoke(request.cookies.get(SESSION_COOKIE, ""))
            response = Response(status_code=204)
            response.delete_cookie(SESSION_COOKIE, path="/", secure=service.config.secure, httponly=True, samesite="lax")
            request.session.clear()
            return response

        @router.get("/{provider}/login")
        async def provider_login(provider: str, request: Request):
            try:
                client = await service.provider(provider)
                binding = request.session.setdefault("binding", secrets.token_urlsafe(32))
                state = secrets.token_urlsafe(32)
                await run_in_threadpool(service.storage.save_flow, state, provider, binding)
                callback = f"{service.config.public_url}/api/auth/{provider}/callback"
                return await client.authorize_redirect(request, callback, state=state)
            except HTTPException:
                raise
            except Exception as error:
                logging.getLogger(__name__).warning("Identity provider initialization failed (%s)", type(error).__name__)
                return RedirectResponse("/login?auth_error=provider_error", status_code=303)

        @router.get("/{provider}/callback")
        async def provider_callback(provider: str, request: Request):
            try:
                client = await service.provider(provider)
                consumed = await run_in_threadpool(service.storage.consume_flow, request.query_params.get("state", ""),
                                                   provider, request.session.get("binding", ""))
                if not consumed:
                    raise OAuthError(error="invalid_state")
                token = await client.authorize_access_token(request, leeway=30)
                if provider == "github":
                    result = await client.get("user", token=token, headers={"Accept": "application/vnd.github+json"})
                    result.raise_for_status()
                    profile = result.json()
                    identifier = profile.get("id")
                    if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0:
                        raise OAuthError(error="invalid_identity")
                    subject = str(identifier)
                    username = profile.get("login", "")
                    if not isinstance(username, str) or not username:
                        raise OAuthError(error="invalid_identity")
                    name = profile.get("name") or username
                else:
                    profile = token.get("userinfo")
                    if not token.get("id_token") or not profile or not isinstance(profile.get("sub"), str) or not profile["sub"]:
                        raise OAuthError(error="invalid_identity")
                    subject = profile["sub"]
                    email = profile.get("email", "")
                    username = profile.get("preferred_username") or email or subject
                    name = profile.get("name") or username
                    subject = json.dumps([service.config.oidc_issuer, subject], separators=(",", ":"))
                response = RedirectResponse("/", status_code=303)
                await run_in_threadpool(service.new_session, response, provider, subject, username, name,
                                        request.cookies.get(SESSION_COOKIE, ""))
                return response
            except HTTPException:
                raise
            except Exception as error:
                logging.getLogger(__name__).warning("Identity provider callback rejected (%s)", type(error).__name__)
                return RedirectResponse("/login?auth_error=provider_error", status_code=303)
            finally:
                request.session.clear()

        app.include_router(router)
