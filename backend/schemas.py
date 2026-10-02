from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from backend.validation import is_placeholder_url


BenchmarkKind = Literal["llm", "embedding", "reranker", "audio", "dify-retrieve", "dify-chat"]


class ProviderSelection(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=256)
    credential_id: str | None = Field(default=None, max_length=64)


class SystemSettingsUpdate(BaseModel):
    default_llm: ProviderSelection | None = None


class AiReportRequest(BaseModel):
    regenerate: bool = False
    language: Literal["zh-CN", "en"] = "zh-CN"


class RunCreate(BaseModel):
    max_tokens: int = Field(default=256, ge=2, le=8192)
    name: str = Field(default="Performance test", min_length=1, max_length=120)
    benchmark: BenchmarkKind
    providers: list[ProviderSelection] = Field(min_length=1, max_length=12)
    concurrency_levels: list[int] = Field(min_length=1, max_length=20)
    requests_per_scenario: int = Field(default=100, ge=1, le=100_000)
    timeout_seconds: float = Field(default=60, gt=0, le=3600)
    query: str | None = Field(default=None, min_length=1, max_length=20_000)
    documents: list[str] = Field(default_factory=list, max_length=20)
    dataset_id: str | None = Field(default=None, min_length=1, max_length=256)

    @field_validator("concurrency_levels")
    @classmethod
    def validate_concurrency(cls, values: list[int]) -> list[int]:
        if any(value < 1 or value > 10_000 for value in values):
            raise ValueError("concurrency must be between 1 and 10000")
        return sorted(set(values))

    @field_validator("providers")
    @classmethod
    def validate_providers(cls, values: list[ProviderSelection]) -> list[ProviderSelection]:
        ids = [item.id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("provider ids must be unique")
        return values

    @field_validator("documents")
    @classmethod
    def validate_documents(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values]
        if any(not item or len(item) > 20_000 for item in cleaned) or sum(map(len, cleaned)) > 50_000:
            raise ValueError("documents must be non-empty and total no more than 50000 characters")
        return cleaned

    @model_validator(mode="after")
    def validate_dify_inputs(self):
        if self.benchmark == "llm" and not (self.query or "").strip():
            raise ValueError("query is required for LLM tests")
        if self.benchmark in {"dify-retrieve", "dify-chat"} and not self.query:
            raise ValueError("query is required for Dify tests")
        return self


class ModelCredential(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    server_url: str = Field(min_length=1, max_length=2048)
    api_key: SecretStr | None = None
    model_uid: str | None = Field(default=None, max_length=256)
    copy_key_from: str | None = Field(default=None, max_length=64)

    @field_validator("server_url")
    @classmethod
    def validate_server_url(cls, value: str) -> str:
        if is_placeholder_url(value):
            raise ValueError("server URL must be a concrete HTTP(S) URL")
        return value


class ModelConfig(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    alias: str | None = Field(default=None, max_length=120)
    benchmark: BenchmarkKind
    base_url: str | None = Field(default=None, max_length=2048)
    credentials: list[ModelCredential] = Field(default_factory=list, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def default_alias(cls, values):
        if isinstance(values, dict) and not str(values.get("alias") or "").strip() and values.get("name"):
            values = {**values, "alias": values["name"]}
        return values

    @model_validator(mode="after")
    def validate_endpoint(self):
        if not self.base_url and not self.credentials:
            raise ValueError("at least one credential is required")
        return self

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value and is_placeholder_url(value):
            raise ValueError("model endpoint must be a concrete HTTP(S) URL")
        return value


class PlaygroundRequest(BaseModel):
    system_prompt: str | None = Field(default=None, max_length=20_000)
    llm_parameters: dict[str, str | int | float] = Field(default_factory=dict, max_length=16)

    @field_validator("llm_parameters", mode="before")
    @classmethod
    def validate_llm_parameters(cls, values):
        if not isinstance(values, dict) or any(type(v) not in (str, int, float) or (isinstance(v, str) and len(v) > 100) for v in values.values()):
            raise ValueError("LLM parameters must be scalar strings or numbers")
        return values
    max_tokens: int | None = Field(default=None, ge=2, le=8192)
    benchmark: BenchmarkKind
    provider_id: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=256)
    credential_id: str | None = Field(default=None, max_length=64)
    text: str | None = Field(default=None, max_length=20_000)
    query: str | None = Field(default=None, max_length=20_000)
    documents: list[str] = Field(default_factory=list, max_length=20)
    dataset_id: str | None = Field(default=None, max_length=256)
    audio_name: str | None = Field(default=None, max_length=256)
    audio_base64: str | None = Field(default=None, max_length=10_000_000)
    timeout_seconds: float = Field(default=30, gt=0, le=60)

    @field_validator("documents")
    @classmethod
    def validate_documents(cls, values: list[str]) -> list[str]:
        if any(len(item) > 20_000 for item in values) or sum(map(len, values)) > 50_000:
            raise ValueError("candidate documents are too long")
        return values

    @model_validator(mode="after")
    def validate_input(self):
        if self.system_prompt and self.system_prompt.strip() and self.benchmark != "llm":
            raise ValueError("System prompt is only valid for LLM requests")
        if self.llm_parameters and self.benchmark != "llm":
            raise ValueError("LLM parameters are only valid for LLM requests")
        if self.benchmark == "llm" and not (self.query or "").strip():
            raise ValueError("query is required for LLM")
        if self.benchmark == "embedding" and not (self.text or "").strip():
            raise ValueError("text is required for embedding")
        if self.benchmark == "reranker" and (not (self.query or "").strip() or not self.documents or any(not item.strip() for item in self.documents)):
            raise ValueError("query and documents are required for reranking")
        if self.benchmark == "audio" and not self.audio_base64:
            raise ValueError("audio file is required")
        if self.benchmark.startswith("dify-") and not (self.query or "").strip():
            raise ValueError("query is required for Dify")
        return self


class ServiceConfigCreate(BaseModel):
    dataset_id: str | None = Field(default=None, min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=120)
    benchmark: BenchmarkKind | None = None
    provider: str = Field(min_length=1, max_length=64)
    base_url: str | None = Field(default=None, max_length=2048)
    model: str | None = Field(default=None, max_length=256)
    models: list[ModelConfig] = Field(default_factory=list, max_length=500)
    icon: Literal["cube", "spark", "cloud", "bolt", "waves", "database"] = "cube"
    api_key: SecretStr | None = None

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_models(cls, values):
        if not isinstance(values, dict):
            return values
        values = values.copy()
        models = values.get("models") or []
        if models and isinstance(models[0], str):
            values["models"] = [
                {"name": name, "benchmark": values.get("benchmark"), "base_url": values.get("base_url")}
                for name in models
            ]
        elif not models and values.get("benchmark") and values.get("base_url"):
            values["models"] = [{"name": values.get("model"), "benchmark": values["benchmark"], "base_url": values["base_url"]}]
        return values

    @model_validator(mode="after")
    def validate_unique_models(self):
        keys = [(item.alias or item.name or "").strip().casefold() for item in self.models]
        if len(keys) != len(set(keys)):
            raise ValueError("model aliases must be unique within a provider")
        return self

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value and is_placeholder_url(value):
            raise ValueError("base_url must be a concrete HTTP(S) endpoint, not a placeholder")
        return value


class ProviderAccess(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    server_url: str = Field(min_length=1, max_length=2048)
    api_key: SecretStr | None = None
    config_id: str | None = Field(default=None, max_length=64)
    credential_id: str | None = Field(default=None, max_length=64)
    benchmark: BenchmarkKind | None = None
    model: str | None = Field(default=None, max_length=256)

    @field_validator("server_url")
    @classmethod
    def validate_server_url(cls, value: str) -> str:
        if is_placeholder_url(value):
            raise ValueError("server URL must be a concrete HTTP(S) URL")
        return value


class DifyNamesRequest(ProviderAccess):
    dataset_id: str | None = Field(default=None, min_length=1, max_length=256)
    provider: Literal["dify"] = "dify"
    benchmark: Literal["dify-chat", "dify-retrieve"]
    page: int = Field(default=1, ge=1, le=10000)


class TestPlanCreate(BaseModel):
    max_tokens: int = Field(default=256, ge=2, le=8192)
    name: str = Field(min_length=1, max_length=120)
    benchmark: BenchmarkKind
    providers: list[ProviderSelection] = Field(min_length=1, max_length=12)
    concurrency_levels: list[int] = Field(min_length=1, max_length=20)
    requests_per_scenario: int = Field(default=100, ge=1, le=100_000)
    timeout_seconds: float = Field(default=60, gt=0, le=3600)
    query: str | None = Field(default=None, min_length=1, max_length=20_000)
    documents: list[str] = Field(default_factory=list, max_length=20)
    dataset_id: str | None = Field(default=None, min_length=1, max_length=256)
    start_at: datetime | None = None
    repeat_mode: Literal["once", "count", "forever"] = "once"
    repeat_count: int | None = Field(default=None, ge=2, le=10_000)
    repeat_interval_seconds: int | None = Field(default=None, ge=60, le=31_536_000)

    _validate_concurrency = field_validator("concurrency_levels")(RunCreate.validate_concurrency.__func__)
    _validate_providers = field_validator("providers")(RunCreate.validate_providers.__func__)
    _validate_documents = field_validator("documents")(RunCreate.validate_documents.__func__)

    @model_validator(mode="after")
    def validate_dify_inputs(self):
        if self.benchmark in {"embedding", "llm"} and not (self.query or "").strip():
            raise ValueError("query is required for embedding tests")
        if self.benchmark == "reranker" and (not (self.query or "").strip() or not self.documents):
            raise ValueError("query and documents are required for reranker tests")
        if self.benchmark in {"dify-retrieve", "dify-chat"} and not self.query:
            raise ValueError("query is required for Dify tests")
        if self.repeat_mode == "count" and self.repeat_count is None:
            raise ValueError("repeat_count is required for a finite repeating plan")
        if self.repeat_mode in {"count", "forever"} and self.repeat_interval_seconds is None:
            raise ValueError("repeat_interval_seconds is required for a repeating plan")
        return self


class RunSummary(BaseModel):
    id: str
    name: str
    benchmark: BenchmarkKind
    status: str
    created_at: str
    updated_at: str
    completed_scenarios: int
    total_scenarios: int
    success_rate: float | None = None
