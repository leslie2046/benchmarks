from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from webapp.validation import is_placeholder_url


BenchmarkKind = Literal["embedding", "reranker", "audio", "dify-retrieve", "dify-chat"]


class ProviderSelection(BaseModel):
    id: str = Field(min_length=1, max_length=64)


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


class ServiceConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    benchmark: BenchmarkKind
    provider: str = Field(min_length=1, max_length=64)
    base_url: str | None = Field(default=None, max_length=2048)
    model: str | None = Field(default=None, max_length=256)
    api_key: SecretStr | None = None

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
