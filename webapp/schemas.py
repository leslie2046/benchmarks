from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from webapp.validation import is_placeholder_url


BenchmarkKind = Literal["embedding", "reranker", "audio", "dify-retrieve", "dify-chat"]


class ProviderSelection(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=256)
    credential_id: str | None = Field(default=None, max_length=64)


class RunCreate(BaseModel):
    name: str = Field(default="Performance test", min_length=1, max_length=120)
    benchmark: BenchmarkKind
    providers: list[ProviderSelection] = Field(min_length=1, max_length=12)
    concurrency_levels: list[int] = Field(min_length=1, max_length=20)
    requests_per_scenario: int = Field(default=100, ge=1, le=100_000)
    timeout_seconds: float = Field(default=60, gt=0, le=3600)
    query: str | None = Field(default=None, min_length=1, max_length=20_000)
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

    @model_validator(mode="after")
    def validate_dify_inputs(self):
        if self.benchmark in {"dify-retrieve", "dify-chat"} and not self.query:
            raise ValueError("query is required for Dify tests")
        if self.benchmark == "dify-retrieve" and not self.dataset_id:
            raise ValueError("dataset_id is required for Dify knowledge-base tests")
        return self


class ModelCredential(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    server_url: str = Field(min_length=1, max_length=2048)
    api_key: SecretStr | None = None
    model_uid: str | None = Field(default=None, max_length=256)

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
        if self.benchmark == "embedding" and not (self.text or "").strip():
            raise ValueError("text is required for embedding")
        if self.benchmark == "reranker" and (not (self.query or "").strip() or not self.documents or any(not item.strip() for item in self.documents)):
            raise ValueError("query and documents are required for reranking")
        if self.benchmark == "audio" and not self.audio_base64:
            raise ValueError("audio file is required")
        if self.benchmark.startswith("dify-") and not (self.query or "").strip():
            raise ValueError("query is required for Dify")
        if self.benchmark == "dify-retrieve" and not (self.dataset_id or "").strip():
            raise ValueError("dataset_id is required for Dify retrieval")
        return self


class ServiceConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    benchmark: BenchmarkKind | None = None
    provider: str = Field(min_length=1, max_length=64)
    base_url: str | None = Field(default=None, max_length=2048)
    model: str | None = Field(default=None, max_length=256)
    models: list[ModelConfig] = Field(default_factory=list, max_length=50)
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


class TestPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    benchmark: BenchmarkKind
    providers: list[ProviderSelection] = Field(min_length=1, max_length=12)
    concurrency_levels: list[int] = Field(min_length=1, max_length=20)
    requests_per_scenario: int = Field(default=100, ge=1, le=100_000)
    timeout_seconds: float = Field(default=60, gt=0, le=3600)
    query: str | None = Field(default=None, min_length=1, max_length=20_000)
    dataset_id: str | None = Field(default=None, min_length=1, max_length=256)

    _validate_concurrency = field_validator("concurrency_levels")(RunCreate.validate_concurrency.__func__)
    _validate_providers = field_validator("providers")(RunCreate.validate_providers.__func__)

    @model_validator(mode="after")
    def validate_dify_inputs(self):
        if self.benchmark in {"dify-retrieve", "dify-chat"} and not self.query:
            raise ValueError("query is required for Dify tests")
        if self.benchmark == "dify-retrieve" and not self.dataset_id:
            raise ValueError("dataset_id is required for Dify knowledge-base tests")
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
