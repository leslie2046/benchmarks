import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse

from env_loader import load_local_env
from webapp.catalog import allowed_provider_ids, default_service_configs, get_catalog
from webapp.runner import BenchmarkRunner
from webapp.schemas import RunCreate, ServiceConfigCreate, TestPlanCreate
from webapp.secrets import SecretBox
from webapp.store import RunStore, TERMINAL_STATUSES, utc_now
from webapp.validation import is_placeholder_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_local_env()
DATA_DIR = Path(os.getenv("BENCHMARK_DATA_DIR", PROJECT_ROOT / "output" / "web"))
store = RunStore(DATA_DIR / "runs.sqlite3")
secret_box = SecretBox.from_data_dir(DATA_DIR)
runner = BenchmarkRunner(store, PROJECT_ROOT, DATA_DIR / "reports", secret_box)

if not store.list_service_configs():
    for default_config in default_service_configs():
        env_name = default_config.get("api_key_env")
        default_config["api_key_encrypted"] = secret_box.encrypt(os.getenv(env_name)) if env_name else None
        store.put_service_config(default_config)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    for task in list(runner.tasks.values()):
        if not task.done():
            task.cancel()


app = FastAPI(title="PerfLab API", version="1.0.0", lifespan=lifespan)
origins = [item.strip() for item in os.getenv("BENCHMARK_CORS_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


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
                "model": item.get("model"),
                "endpoint_configured": not is_placeholder_url(item.get("base_url")),
                "credential_configured": bool(item.get("api_key_encrypted")),
                "credential_required": bool(item.get("api_key_env")),
            }
            for item in configs
        ]
    return data


@app.get("/api/service-configs")
def list_service_configs(benchmark: str | None = None) -> list[dict]:
    return [_public_config(item) for item in store.list_service_configs(benchmark)]


def _public_config(config: dict) -> dict:
    return {
        key: value for key, value in config.items()
        if key not in {"api_key_encrypted", "api_key_env"}
    } | {
        "has_api_key": bool(config.get("api_key_encrypted")),
        "endpoint_configured": not is_placeholder_url(config.get("base_url")),
    }


def _credential_env(benchmark: str, provider: str) -> str | None:
    if benchmark == "embedding":
        from providers import EMBEDDING_PROVIDERS
        return EMBEDDING_PROVIDERS[provider].get("api_key_env")
    if benchmark == "reranker":
        from providers import RERANK_PROVIDERS
        return RERANK_PROVIDERS[provider].get("api_key_env")
    if benchmark == "audio":
        return "XINFERENCE_API_KEY"
    if benchmark == "dify-retrieve":
        return "DIFY_DATASET_API_KEY"
    if benchmark == "dify-chat":
        return "DIFY_CHAT_API_KEY"
    return None


@app.post("/api/service-configs", status_code=201)
def create_service_config(payload: ServiceConfigCreate) -> dict:
    if payload.provider not in allowed_provider_ids(payload.benchmark):
        raise HTTPException(400, "Provider is not supported by this benchmark")
    now = utc_now()
    values = payload.model_dump(exclude={"api_key"})
    config = {
        "id": uuid.uuid4().hex[:12], **values,
        "api_key_env": _credential_env(payload.benchmark, payload.provider),
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
    if payload.provider not in allowed_provider_ids(payload.benchmark):
        raise HTTPException(400, "Provider is not supported by this benchmark")
    values = payload.model_dump(exclude={"api_key"})
    config = {
        **current, **values,
        "api_key_env": _credential_env(payload.benchmark, payload.provider),
        "updated_at": utc_now(),
    }
    if payload.api_key:
        config["api_key_encrypted"] = secret_box.encrypt(payload.api_key.get_secret_value())
    store.put_service_config(config)
    return _public_config(config)


@app.get("/api/plans")
def list_plans(limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    return store.list_plans(limit)


@app.post("/api/plans", status_code=201)
def create_plan(payload: TestPlanCreate) -> dict:
    configs = _resolve_configs(payload.benchmark, [item.id for item in payload.providers])
    now = utc_now()
    plan = {"id": uuid.uuid4().hex[:12], **payload.model_dump(), "created_at": now, "updated_at": now, "run_count": 0}
    store.put_plan(plan)
    return plan


def _resolve_configs(benchmark: str, config_ids: list[str]) -> list[dict]:
    configs = []
    for config_id in config_ids:
        config = store.get_service_config(config_id)
        if not config or config["benchmark"] != benchmark:
            raise HTTPException(400, f"Invalid service config: {config_id}")
        if is_placeholder_url(config.get("base_url")):
            raise HTTPException(400, f"Service config '{config['name']}' needs a valid Endpoint")
        configs.append(config)
    return configs


@app.post("/api/runs", status_code=202)
async def create_run(payload: RunCreate) -> dict:
    configs = _resolve_configs(payload.benchmark, [item.id for item in payload.providers])
    now = utc_now()
    plan = {
        "id": uuid.uuid4().hex[:12], **payload.model_dump(),
        "created_at": now, "updated_at": now, "run_count": 1,
    }
    store.put_plan(plan)
    return runner.create_run(payload.model_dump(), plan["id"], configs)


@app.post("/api/plans/{plan_id}/runs", status_code=202)
async def run_plan(plan_id: str) -> dict:
    plan = store.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "Test plan not found")
    configs = _resolve_configs(plan["benchmark"], [item["id"] for item in plan["providers"]])
    plan["run_count"] = plan.get("run_count", 0) + 1
    plan["updated_at"] = utc_now()
    store.put_plan(plan)
    request = {
        key: plan.get(key) for key in (
            "name", "benchmark", "providers", "concurrency_levels",
            "requests_per_scenario", "timeout_seconds", "query", "dataset_id",
        )
    }
    return runner.create_run(request, plan_id, configs)


@app.get("/api/runs")
def list_runs(limit: int = Query(default=30, ge=1, le=200)) -> list[dict]:
    return store.list(limit)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = store.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


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
