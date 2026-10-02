import asyncio
import json
import os
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse

from shared.env_loader import load_local_env
from backend.connectivity import ConnectivityError, check_models
from backend.model_discovery import DISCOVERABLE_PROVIDERS, ModelDiscoveryError, list_models, verify_key
from backend.endpoints import endpoint_url, server_root
from backend.catalog import allowed_provider_ids, get_catalog
from backend.model_configs import configured_models
from backend.playground import run_playground
from backend.runner import BenchmarkRunner
from backend.schemas import AiReportRequest, SystemSettingsUpdate, DifyNamesRequest, PlaygroundRequest, ProviderAccess, ProviderSelection, RunCreate, ServiceConfigCreate, TestPlanCreate
from backend.secrets import SecretBox
from backend.store import RunStore, TERMINAL_STATUSES, utc_now
from backend.validation import is_placeholder_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_local_env()
DATA_DIR = Path(os.getenv("BENCHMARK_DATA_DIR", PROJECT_ROOT / "output" / "web"))
store = RunStore(DATA_DIR / "runs.sqlite3")
secret_box = SecretBox.from_data_dir(DATA_DIR)
runner = BenchmarkRunner(store, PROJECT_ROOT, DATA_DIR / "reports", secret_box)

@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler_task = asyncio.create_task(_plan_scheduler())
    try:
        yield
    finally:
        scheduler_task.cancel()
        for task in list(runner.tasks.values()):
            if not task.done():
                task.cancel()


app = FastAPI(title="PrismLab API", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json")
origins = [item.strip() for item in os.getenv("BENCHMARK_CORS_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/api/docs")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/catalog")
def catalog() -> dict:
    data = get_catalog()
    for benchmark in data["benchmarks"]:
        benchmark["provider_kinds"] = [
            {"id": item["id"], "label": item["label"]}
            for item in benchmark["providers"]
        ]
        configs = store.list_service_configs(benchmark["id"])
        benchmark["providers"] = [
            {
                "id": item["id"],
                "provider": item["provider"],
                "label": item["name"],
                "model": next((model["name"] for model in _models(item) if model["benchmark"] == benchmark["id"]), None),
                "models": [_public_model(model, item) for model in _models(item) if model["benchmark"] == benchmark["id"]],
                "icon": item.get("icon", "cube"),
                "dataset_id": item.get("dataset_id"),
                "endpoint_configured": any(bool(model.get("credentials")) or not is_placeholder_url(model.get("base_url")) for model in _models(item) if model["benchmark"] == benchmark["id"]),
                "credential_configured": bool(item.get("api_key_encrypted")) or any(credential.get("api_key_encrypted") for model in _models(item) for credential in model.get("credentials", [])),
                "credential_required": bool(item.get("api_key_env")),
            }
            for item in configs
        ]
        if benchmark["id"] == "dify-retrieve":
            for provider in benchmark["providers"]:
                provider["endpoint_configured"] = provider["endpoint_configured"] and bool((provider.get("dataset_id") or "").strip())
    return data


@app.get("/api/service-configs")
def list_service_configs(benchmark: str | None = None) -> list[dict]:
    return [_public_config(item) for item in store.list_service_configs(benchmark)]


def _masked_api_key(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    try:
        value = secret_box.decrypt(encrypted)
    except ValueError:
        return "••••••••"
    if not value:
        return None
    visible = 4 if len(value) >= 8 else 2 if len(value) >= 4 else 1
    return f"{value[:visible]}••••••••"


def _public_config(config: dict) -> dict:
    return {
        key: value for key, value in config.items()
        if key not in {"api_key_encrypted", "api_key_env"}
    } | {
        "models": [_public_model(model, config) for model in _models(config)],
        "has_api_key": bool(config.get("api_key_encrypted")),
        "api_key_masked": _masked_api_key(config.get("api_key_encrypted")),
        "endpoint_configured": bool(_models(config)) and all(bool(model.get("credentials")) or not is_placeholder_url(model.get("base_url")) for model in _models(config)),
        "icon": config.get("icon", "cube"),
    }


def _models(config: dict) -> list[dict]:
    return configured_models(config)


def _public_model(model: dict, config: dict) -> dict:
    result = {key: value for key, value in model.items() if key != "credentials"}
    credentials = model.get("credentials") or []
    if not credentials and model.get("base_url") and config.get("provider") != "dify":
        credentials = [{"id": "legacy", "name": "Default", "server_url": server_root(model["base_url"]), "model_uid": model.get("name"), "api_key_encrypted": config.get("api_key_encrypted")}]
    result["credentials"] = [
        {"id": item["id"], "name": item["name"], "server_url": item["server_url"],
         "model_uid": item.get("model_uid"), "has_api_key": bool(item.get("api_key_encrypted")),
         "api_key_masked": _masked_api_key(item.get("api_key_encrypted"))}
        for item in credentials
    ]
    return result


def _validate_provider(payload: ServiceConfigCreate, key: str | None, current: dict | None = None) -> list[dict]:
    models = []
    existing = {item.get("id"): item for model in _models(current) for item in model.get("credentials", [])} if current else {}
    for item in payload.models:
        model = item.model_dump(exclude={"credentials"})
        credentials = []
        for credential in item.credentials:
            raw = credential.model_dump(exclude={"api_key"})
            raw["id"] = raw.get("id") or uuid.uuid4().hex[:12]
            raw["server_url"] = server_root(raw["server_url"])
            previous = existing.get(raw["id"], {})
            source = existing.get(credential.copy_key_from, {}) if credential.copy_key_from else {}
            if credential.copy_key_from == "legacy" and current and not source:
                source = {"server_url": server_root(current.get("base_url") or ""), "api_key_encrypted": current.get("api_key_encrypted")}
            if source and source.get("server_url") != raw["server_url"]:
                raise HTTPException(400, "Saved API key can only be reused for the same server URL")
            credential_key = credential.api_key.get_secret_value() if credential.api_key else secret_box.decrypt(previous.get("api_key_encrypted") or source.get("api_key_encrypted"))
            if not credential_key and credential.copy_key_from == "legacy" and current:
                credential_key = os.getenv(current.get("api_key_env") or "") or None
            if raw["id"] == "legacy" and not credential_key and current:
                credential_key = secret_box.decrypt(current.get("api_key_encrypted"))
            raw["api_key_encrypted"] = secret_box.encrypt(credential_key) if credential_key else None
            raw.pop("copy_key_from", None)
            raw["model_uid"] = raw.get("model_uid") or item.name
            credentials.append(raw)
        model["credentials"] = credentials
        models.append(model)
    for model in models:
        if payload.provider not in allowed_provider_ids(model["benchmark"]):
            raise HTTPException(400, f"{payload.provider} does not support {model['benchmark']}")
    if payload.provider == "dify":
        if any(model["benchmark"] == "dify-retrieve" for model in models) and not (payload.dataset_id or "").strip():
            raise HTTPException(400, "请在 Dify 配置中填写知识库 ID。")
        try:
            check_models([{"benchmark": model["benchmark"], "base_url": model.get("base_url"), "api_key": key} for model in models], key)
        except ConnectivityError as exc:
            raise HTTPException(400, str(exc)) from exc
    return models


def _provider_access(payload: ProviderAccess) -> tuple[str, str | None]:
    if payload.provider not in {item for benchmark in get_catalog()["benchmarks"] for item in allowed_provider_ids(benchmark["id"])}:
        raise HTTPException(400, "Unknown provider")
    key = payload.api_key.get_secret_value() if payload.api_key else None
    if not key and payload.config_id and payload.credential_id:
        current = store.get_service_config(payload.config_id)
        if not current or current.get("provider") != payload.provider:
            raise HTTPException(404, "Saved provider not found")
        credential = next((entry for model in _models(current) for entry in model.get("credentials", []) if entry.get("id") == payload.credential_id), None)
        if not credential and payload.credential_id == "legacy":
            credential = {"server_url": server_root(current.get("base_url") or ""), "api_key_encrypted": current.get("api_key_encrypted")}
        if not credential:
            raise HTTPException(404, "Saved credential not found")
        if server_root(credential["server_url"]) != server_root(payload.server_url):
            raise HTTPException(400, "Enter a new API key when changing the server URL")
        key = secret_box.decrypt(credential.get("api_key_encrypted"))
        if not key and payload.credential_id == "legacy":
            key = os.getenv(current.get("api_key_env") or "") or None
    return server_root(payload.server_url), key


@app.post("/api/dify/names")
def dify_names(payload: DifyNamesRequest) -> dict:
    from backend.dify_names import api_root, fetch_names
    key = payload.api_key.get_secret_value() if payload.api_key else None
    if not key and payload.config_id:
        current = store.get_service_config(payload.config_id)
        if not current or current.get("provider") != "dify":
            raise HTTPException(404, "Dify 配置不存在。")
        if current.get("benchmark") != payload.benchmark or api_root(current.get("base_url") or "") != api_root(payload.server_url):
            raise HTTPException(400, "更改服务地址或 Dify 类型后，请填写新的 API Key。")
        key = secret_box.decrypt(current.get("api_key_encrypted"))
        if not key:
            key = os.getenv(current.get("api_key_env") or "")
    if not key and not payload.config_id:
        key = os.getenv(_credential_env(payload.benchmark, "dify") or "")
    try:
        return fetch_names(payload.server_url, payload.benchmark, key, payload.page, payload.dataset_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/provider-models/verify")
def verify_provider_access(payload: ProviderAccess) -> dict:
    server_url, key = _provider_access(payload)
    try:
        if payload.provider in DISCOVERABLE_PROVIDERS:
            verify_key(payload.provider, server_url, key)
        elif payload.benchmark and payload.model:
            check_models([{"benchmark": payload.benchmark, "base_url": endpoint_url(server_url, payload.benchmark, payload.provider), "api_key": key, "model": payload.model, "provider": payload.provider, "server_url": server_url}], None)
        else:
            raise HTTPException(400, "Select a model to verify this provider")
    except (ConnectivityError, ModelDiscoveryError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"valid": True}


@app.post("/api/provider-models/list")
def list_provider_models(payload: ProviderAccess) -> dict:
    server_url, key = _provider_access(payload)
    try:
        return {"models": list_models(payload.provider, server_url, key)}
    except ModelDiscoveryError as exc:
        raise HTTPException(400, str(exc)) from exc


def _validate_unique_aliases(models: list[dict], provider: str, config_id: str | None = None) -> None:
    aliases = [str(model.get("alias") or model.get("name") or "").strip().casefold() for model in models if not model["benchmark"].startswith("dify-")]
    if len(aliases) != len(set(aliases)):
        raise HTTPException(400, "Model aliases must be unique within a provider")
    for config in store.list_service_configs():
        if config["id"] == config_id or config.get("provider") != provider:
            continue
        for model in _models(config):
            alias = str(model.get("alias") or model.get("name") or "").strip().casefold()
            if alias in aliases:
                raise HTTPException(400, f"Model alias already exists: {model.get('alias') or model.get('name')}")


def _credential_env(benchmark: str, provider: str) -> str | None:
    if benchmark == "llm":
        from shared.providers import LLM_PROVIDERS
        return LLM_PROVIDERS.get(provider, {}).get("api_key_env")
    if benchmark == "embedding":
        from shared.providers import EMBEDDING_PROVIDERS
        return EMBEDDING_PROVIDERS.get(provider, {}).get("api_key_env")
    if benchmark == "reranker":
        from shared.providers import RERANK_PROVIDERS
        return RERANK_PROVIDERS.get(provider, {}).get("api_key_env")
    if benchmark == "audio":
        from shared.providers import AUDIO_PROVIDERS
        return AUDIO_PROVIDERS.get(provider, {}).get("api_key_env")
    if benchmark == "dify-retrieve":
        return "DIFY_DATASET_API_KEY"
    if benchmark == "dify-chat":
        return "DIFY_CHAT_API_KEY"
    return None


@app.post("/api/service-configs", status_code=201)
def create_service_config(payload: ServiceConfigCreate) -> dict:
    if not payload.models:
        raise HTTPException(400, "Add a model before saving a provider")
    if payload.provider != "dify" and any(item["provider"] == payload.provider for item in store.list_service_configs()):
        raise HTTPException(409, "This provider already exists; add models to it")
    key = payload.api_key.get_secret_value() if payload.api_key else None
    if not key and payload.models:
        key = os.getenv(_credential_env(payload.models[0].benchmark, payload.provider) or "")
    models = _validate_provider(payload, key)
    _validate_unique_aliases(models, payload.provider)
    now = utc_now()
    values = payload.model_dump(exclude={"api_key"})
    values["models"] = models
    values["benchmark"] = models[0]["benchmark"]
    values["base_url"] = models[0].get("base_url") or endpoint_url(models[0]["credentials"][0]["server_url"], models[0]["benchmark"], payload.provider)
    values["model"] = models[0]["name"]
    config = {
        "id": uuid.uuid4().hex[:12], **values,
        "api_key_env": _credential_env(models[0]["benchmark"], payload.provider),
        "api_key_encrypted": secret_box.encrypt(payload.api_key.get_secret_value()) if payload.api_key else None,
        "created_at": now, "updated_at": now,
    }
    store.put_service_config(config)
    return _public_config(config)


@app.put("/api/service-configs/{config_id}")
def update_service_config(config_id: str, payload: ServiceConfigCreate) -> dict:
    current = store.get_service_config(config_id)
    if not current:
        raise HTTPException(404, "Service config not found")
    key = payload.api_key.get_secret_value() if payload.api_key else secret_box.decrypt(current.get("api_key_encrypted"))
    if not key and payload.models:
        key = os.getenv(_credential_env(payload.models[0].benchmark, payload.provider) or "")
    models = _validate_provider(payload, key, current)
    _validate_unique_aliases(models, payload.provider, config_id)
    values = payload.model_dump(exclude={"api_key"})
    values["models"] = models
    values["benchmark"] = models[0]["benchmark"] if models else None
    values["base_url"] = (models[0].get("base_url") or endpoint_url(models[0]["credentials"][0]["server_url"], models[0]["benchmark"], payload.provider)) if models else None
    values["model"] = models[0]["name"] if models else None
    config = {
        **current, **values,
        "api_key_env": _credential_env(models[0]["benchmark"], payload.provider) if models else current.get("api_key_env"),
        "updated_at": utc_now(),
    }
    if payload.api_key:
        config["api_key_encrypted"] = secret_box.encrypt(payload.api_key.get_secret_value())
    store.put_service_config(config)
    return _public_config(config)


@app.delete("/api/service-configs/{config_id}", status_code=204)
def delete_service_config(config_id: str) -> None:
    config = store.get_service_config(config_id)
    if not config:
        raise HTTPException(404, "Model provider not found")
    if config.get("provider") != "dify":
        raise HTTPException(409, "Model providers cannot be deleted")
    if store.has_active_run_for_config(config_id):
        raise HTTPException(409, "Model provider is used by an active run")
    store.delete_service_config(config_id)


@app.get("/api/plans")
def list_plans(limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    return [_normalize_plan(item) for item in store.list_plans(limit)]


@app.post("/api/plans", status_code=201)
def create_plan(payload: TestPlanCreate) -> dict:
    _resolve_configs(payload.benchmark, [item.model_dump() for item in payload.providers], payload.dataset_id)
    now = utc_now()
    values = payload.model_dump(mode="json")
    plan = {
        "id": uuid.uuid4().hex[:12], **values,
        "created_at": now, "updated_at": now,
        "status": "paused", "next_run_at": values.get("start_at"),
        "run_count": 0, "schedule_run_count": 0,
        "last_run_id": None, "last_run_at": None, "schedule_error": None,
    }
    store.put_plan(plan)
    return plan


@app.put("/api/plans/{plan_id}")
async def update_plan(plan_id: str, payload: TestPlanCreate) -> dict:
    existing = store.get_plan(plan_id)
    if not existing:
        raise HTTPException(404, "Test plan not found")
    current = _normalize_plan(existing)
    if current["status"] == "active" or store.has_active_run_for_plan(plan_id):
        raise HTTPException(409, "Pause the plan and wait for its active run to finish before editing")
    _resolve_configs(payload.benchmark, [item.model_dump() for item in payload.providers], payload.dataset_id)
    values = payload.model_dump(mode="json")
    updated = {
        **current, **values, "updated_at": utc_now(), "status": "paused",
        "next_run_at": values.get("start_at"), "schedule_run_count": 0,
        "schedule_error": None,
    }
    store.put_plan(updated)
    return updated


def _normalize_plan(plan: dict) -> dict:
    return {
        "status": "stopped", "repeat_mode": "once", "repeat_count": None,
        "repeat_interval_seconds": None, "start_at": None, "next_run_at": None,
        "run_count": 0, "schedule_run_count": 0, "last_run_id": None,
        "last_run_at": None, "schedule_error": None, **plan,
    }


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _plan_request(plan: dict) -> dict:
    return {
        key: plan.get(key) for key in (
            "name", "benchmark", "providers", "concurrency_levels",
            "requests_per_scenario", "timeout_seconds", "query", "documents", "dataset_id", "max_tokens",
        )
    }


def _trigger_scheduled_plan(plan: dict) -> dict | None:
    plan = _normalize_plan(plan)
    if store.has_active_run_for_plan(plan["id"]):
        return None
    configs = _resolve_configs(plan["benchmark"], plan["providers"], plan.get("dataset_id"))
    run = runner.create_run(_plan_request(plan), plan["id"], configs)
    now = datetime.now(timezone.utc)
    plan["run_count"] += 1
    plan["schedule_run_count"] += 1
    plan["last_run_id"] = run["id"]
    plan["last_run_at"] = now.isoformat(timespec="microseconds")
    interval = plan.get("repeat_interval_seconds")
    repeat_mode = plan.get("repeat_mode", "once")
    has_more = repeat_mode == "forever" or (
        repeat_mode == "count" and plan["schedule_run_count"] < (plan.get("repeat_count") or 0)
    )
    plan["next_run_at"] = (now + timedelta(seconds=interval)).isoformat(timespec="microseconds") if has_more and interval else None
    plan["updated_at"] = utc_now()
    plan["schedule_error"] = None
    store.put_plan(plan)
    return run


async def _plan_scheduler() -> None:
    while True:
        now = datetime.now(timezone.utc)
        for raw_plan in store.list_plans(500):
            plan = _normalize_plan(raw_plan)
            if plan["status"] != "active":
                continue
            next_run_at = _parse_time(plan.get("next_run_at"))
            if next_run_at is None:
                if not store.has_active_run_for_plan(plan["id"]):
                    plan["status"] = "completed"
                    plan["updated_at"] = utc_now()
                    store.put_plan(plan)
                continue
            if next_run_at > now or store.has_active_run_for_plan(plan["id"]):
                continue
            try:
                _trigger_scheduled_plan(plan)
            except Exception as exc:
                plan["status"] = "error"
                plan["next_run_at"] = None
                plan["schedule_error"] = str(exc)
                plan["updated_at"] = utc_now()
                store.put_plan(plan)
        await asyncio.sleep(1)


@app.post("/api/plans/{plan_id}/start")
async def start_plan(plan_id: str) -> dict:
    raw_plan = store.get_plan(plan_id)
    if not raw_plan:
        raise HTTPException(404, "Test plan not found")
    plan = _normalize_plan(raw_plan)
    previous_status = plan["status"]
    if previous_status in {"completed", "stopped", "error"}:
        plan["schedule_run_count"] = 0
    plan["status"] = "active"
    plan["schedule_error"] = None
    if previous_status != "paused" or not plan.get("next_run_at"):
        configured_start = _parse_time(plan.get("start_at"))
        now = datetime.now(timezone.utc)
        plan["next_run_at"] = (configured_start if configured_start and configured_start > now else now).isoformat(timespec="microseconds")
    plan["updated_at"] = utc_now()
    store.put_plan(plan)
    due = _parse_time(plan["next_run_at"])
    if due and due <= datetime.now(timezone.utc) and not store.has_active_run_for_plan(plan_id):
        _trigger_scheduled_plan(plan)
    return _normalize_plan(store.get_plan(plan_id) or plan)


@app.post("/api/plans/{plan_id}/pause")
def pause_plan(plan_id: str) -> dict:
    raw_plan = store.get_plan(plan_id)
    if not raw_plan:
        raise HTTPException(404, "Test plan not found")
    plan = _normalize_plan(raw_plan)
    if plan["status"] != "active":
        raise HTTPException(409, "Only an active plan can be paused")
    plan["status"] = "paused"
    plan["updated_at"] = utc_now()
    store.put_plan(plan)
    return plan


@app.post("/api/plans/{plan_id}/stop")
async def stop_plan(plan_id: str) -> dict:
    raw_plan = store.get_plan(plan_id)
    if not raw_plan:
        raise HTTPException(404, "Test plan not found")
    plan = _normalize_plan(raw_plan)
    for run in store.active_runs_for_plan(plan_id):
        await runner.cancel(run["id"])
    plan["status"] = "stopped"
    plan["next_run_at"] = None
    plan["updated_at"] = utc_now()
    store.put_plan(plan)
    return plan


@app.delete("/api/plans/{plan_id}", status_code=204)
async def delete_plan(plan_id: str) -> None:
    if not store.get_plan(plan_id):
        raise HTTPException(404, "Test plan not found")
    for run in store.active_runs_for_plan(plan_id):
        await runner.cancel(run["id"])
    store.delete_plan(plan_id)


def _resolve_configs(benchmark: str, selections: list[dict], legacy_dataset_id: str | None = None) -> list[dict]:
    configs = []
    for selection in selections:
        config_id = selection["id"]
        config = store.get_service_config(config_id)
        if not config:
            raise HTTPException(400, f"Invalid service config: {config_id}")
        matching = [item for item in _models(config) if item["benchmark"] == benchmark]
        model_name = selection.get("model")
        model = next((item for item in matching if item.get("alias") == model_name), None) if model_name else None
        model = model or (next((item for item in matching if item["name"] == model_name), None) if model_name else (matching[0] if matching else None))
        if not model:
            raise HTTPException(400, f"Model '{model_name}' is not configured for '{config['name']}' and {benchmark}")
        credentials = model.get("credentials") or []
        credential_id = selection.get("credential_id")
        if credentials and not credential_id and len(credentials) > 1:
            raise HTTPException(400, f"Select a credential for model '{model.get('alias') or model['name']}'")
        credential = next((item for item in credentials if item["id"] == credential_id), None) if credential_id else (credentials[0] if credentials else None)
        if credential_id and not credential:
            raise HTTPException(400, f"Invalid credential for model '{model.get('alias') or model['name']}'")
        base_url = endpoint_url(credential["server_url"], benchmark, config["provider"]) if credential else model.get("base_url")
        if is_placeholder_url(base_url):
            raise HTTPException(400, f"Model '{model['name']}' needs a valid Endpoint")
        if benchmark == "dify-retrieve":
            config = {**config, "dataset_id": config.get("dataset_id") or legacy_dataset_id}
            if not (config.get("dataset_id") or "").strip():
                raise HTTPException(400, f"请在 Dify 配置「{config['name']}」中填写知识库 ID。")
        configs.append({**config, "base_url": base_url, "model": credential.get("model_uid") or model["name"] if credential else model["name"], "model_selected": True, "credential_id": credential["id"] if credential else None,
                        "api_key_env": _credential_env(benchmark, config["provider"])})
    return configs


def _playground_access(payload: PlaygroundRequest):
    selection = {"id": payload.provider_id, "model": payload.model}
    if payload.credential_id:
        selection["credential_id"] = payload.credential_id
    config = _resolve_configs(payload.benchmark, [selection], payload.dataset_id)[0]
    key = None
    if config.get("credential_id"):
        key = next((secret_box.decrypt(c.get("api_key_encrypted")) for m in _models(config) for c in m.get("credentials", []) if c["id"] == config["credential_id"]), None)
    if not key:
        key = secret_box.decrypt(config.get("api_key_encrypted"))
    if not key and config.get("api_key_env"):
        key = os.getenv(config["api_key_env"])
    return config, key


@app.get("/api/system-settings")
def system_settings() -> dict:
    return store.system_settings()


@app.put("/api/system-settings")
def update_system_settings(payload: SystemSettingsUpdate) -> dict:
    selection = payload.default_llm.model_dump() if payload.default_llm else None
    if selection:
        config = _resolve_configs("llm", [selection])[0]
        matching = [item for item in _models(config) if item["benchmark"] == "llm"]
        model = next((item for item in matching if selection["model"] and item.get("alias") == selection["model"]), None)
        model = model or next(item for item in matching if not selection["model"] or item.get("name") == selection["model"])
        selection.update(model=model.get("alias") or model["name"], credential_id=config.get("credential_id"))
    return store.save_system_settings({"default_llm": selection})


@app.get("/api/runs/{run_id}/ai-report")
def get_ai_report(run_id: str) -> dict:
    if not store.get(run_id):
        raise HTTPException(404, "Run not found")
    return store.ai_report(run_id)


def _generate_ai_report(report_store, run, generation_id, config, key, language):
    from backend.ai_reports import generate_report
    try:
        content = generate_report(run, config, key, language)
        report_store.finish_ai_report(run["id"], generation_id, content)
    except Exception:
        # Provider exceptions may include URLs or credentials: never persist or expose them.
        report_store.finish_ai_report(run["id"], generation_id, None,
                                     "AI 分析失败，请检查默认 LLM 的连接、认证或额度后重试。已有报告仍保留。")


@app.post("/api/runs/{run_id}/ai-report", status_code=202)
def create_ai_report(run_id: str, payload: AiReportRequest, background_tasks: BackgroundTasks) -> dict:
    run = store.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run["status"] not in TERMINAL_STATUSES:
        raise HTTPException(409, "请等待测试运行结束后再分析。")
    previous = store.ai_report(run_id)
    if previous["status"] == "generating":
        raise HTTPException(409, "此运行记录正在分析，请勿重复提交。")
    if previous.get("content") and not payload.regenerate:
        return previous
    selection = store.system_settings().get("default_llm")
    if not selection:
        raise HTTPException(400, "请先在系统配置中选择默认 LLM。")
    config, key = _playground_access(PlaygroundRequest(benchmark="llm", provider_id=selection["id"],
                                    model=selection.get("model"), credential_id=selection.get("credential_id"), query="analyse"))
    generation_id = uuid.uuid4().hex
    try:
        report = store.begin_ai_report(run_id, generation_id, {"provider": config["name"], "model": selection["model"]})
    except ValueError as exc:
        raise HTTPException(404, "Run not found") from exc
    if report is None:
        raise HTTPException(409, "此运行记录正在分析，请勿重复提交。")
    background_tasks.add_task(_generate_ai_report, store, run, generation_id, config, key, payload.language)
    return report


@app.post("/api/playground/stream")
def playground_stream(payload: PlaygroundRequest) -> StreamingResponse:
    if payload.benchmark != "llm":
        raise HTTPException(400, "Streaming is only supported for LLM")
    config, key = _playground_access(payload)
    from backend.llm_parameters import resolve_parameters
    try:
        resolved = resolve_parameters(config, payload.llm_parameters, payload.max_tokens, key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    from backend.playground import stream_playground
    return StreamingResponse(stream_playground(payload, config, key, resolved),
                             media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/llm/parameters")
def llm_parameters(payload: ProviderSelection, refresh: bool = False) -> dict:
    from backend.llm_parameters import describe_parameters
    config, key = _playground_access(PlaygroundRequest(benchmark="llm", provider_id=payload.id,
                         model=payload.model, credential_id=payload.credential_id, query="capabilities"))
    try:
        return describe_parameters(config, key, refresh=refresh)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/playground")
def playground(payload: PlaygroundRequest) -> dict:
    config, key = _playground_access(payload)
    try:
        return run_playground(payload, config, key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(502, f"Provider request failed: {exc}") from exc


@app.post("/api/runs", status_code=202)
async def create_run(payload: RunCreate) -> dict:
    configs = _resolve_configs(payload.benchmark, [item.model_dump() for item in payload.providers], payload.dataset_id)
    now = utc_now()
    plan = {
        "id": uuid.uuid4().hex[:12], **payload.model_dump(),
        "created_at": now, "updated_at": now, "run_count": 1,
        "schedule_run_count": 1, "status": "completed", "repeat_mode": "once",
        "repeat_count": None, "repeat_interval_seconds": None,
        "start_at": now, "next_run_at": None, "last_run_at": now,
        "last_run_id": None, "schedule_error": None,
    }
    store.put_plan(plan)
    run = runner.create_run(payload.model_dump(), plan["id"], configs)
    plan["last_run_id"] = run["id"]
    store.put_plan(plan)
    return run


@app.post("/api/plans/{plan_id}/runs", status_code=202)
async def run_plan(plan_id: str) -> dict:
    raw_plan = store.get_plan(plan_id)
    if not raw_plan:
        raise HTTPException(404, "Test plan not found")
    plan = _normalize_plan(raw_plan)
    configs = _resolve_configs(plan["benchmark"], plan["providers"], plan.get("dataset_id"))
    plan["run_count"] = plan.get("run_count", 0) + 1
    plan["updated_at"] = utc_now()
    run = runner.create_run(_plan_request(plan), plan_id, configs)
    plan["last_run_id"] = run["id"]
    plan["last_run_at"] = utc_now()
    store.put_plan(plan)
    return run


@app.get("/api/runs")
def list_runs(limit: int = Query(default=30, ge=1, le=200)) -> list[dict]:
    return store.list(limit)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = store.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@app.delete("/api/runs/{run_id}", status_code=204)
def delete_run(run_id: str) -> None:
    run = store.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run["status"] not in TERMINAL_STATUSES:
        raise HTTPException(409, "Cancel the active run before deleting it")
    if re.fullmatch(r"[0-9a-f]{12}", run_id):
        report_dir = runner.reports_dir / run_id
        if report_dir.is_dir():
            shutil.rmtree(report_dir)
    store.delete_run(run_id)


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict:
    if not store.get(run_id):
        raise HTTPException(404, "Run not found")
    if not await runner.cancel(run_id):
        raise HTTPException(409, "Run is not active")
    return store.get(run_id)


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    if not store.get(run_id):
        raise HTTPException(404, "Run not found")

    async def stream():
        revision = None
        while not await request.is_disconnected():
            run = store.get(run_id)
            if not run:
                break
            if run["updated_at"] != revision:
                revision = run["updated_at"]
                yield f"data: {json.dumps(run, ensure_ascii=False)}\n\n"
            if run["status"] in TERMINAL_STATUSES:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")
