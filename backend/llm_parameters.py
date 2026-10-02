"""One interface for YAML capabilities, read-only discovery and validated wire parameters."""
import copy
import hashlib
import math
import time
from pathlib import Path
from threading import Lock
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.providers import LLM_PROVIDERS
from backend.model_discovery import DISCOVERABLE_PROVIDERS, fetch_model_entries, _models_url

DEFINITION_PATH = Path(__file__).resolve().parents[1] / "config" / "llm-models.yaml"
WIRE_FIELDS = {"max_tokens", "temperature", "top_p", "thinking.type", "enable_thinking",
               "reasoning_effort", "thinking_budget", "chat_template_kwargs.enable_thinking"}
_cache = {}
_lock = Lock()


class Parameter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["integer", "number", "enum"]
    label: str
    description: str = ""
    api_field: str
    min: float | None = None
    max: float | None = None
    step: float | None = None
    default: str | int | float | None = None
    values: list[str] = Field(default_factory=list, max_length=20)
    wire_values: dict[str, str | bool] = Field(default_factory=dict)
    enabled_when: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid(self):
        if self.api_field not in WIRE_FIELDS:
            raise ValueError("Unsupported request field in model definition")
        if self.type == "enum" and (not self.values or (self.default is not None and self.default not in self.values)):
            raise ValueError("Invalid enum definition")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("Invalid parameter range")
        return self


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str | None = None
    parameters: dict[str, dict]


class ModelRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    patterns: list[str]
    profile: str
    metadata: dict[Literal["context_window", "max_output_tokens"], int] = Field(default_factory=dict)


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    providers: dict[str, str]
    profiles: dict[str, Profile]
    models: list[ModelRule]


def _definition():
    raw = DEFINITION_PATH.read_bytes()
    if len(raw) > 1_000_000:
        raise ValueError("Model definition file is too large")
    definition = Definition.model_validate(yaml.safe_load(raw))
    for profile in definition.providers.values():
        if profile not in definition.profiles:
            raise ValueError("Unknown base profile")
    return definition, hashlib.sha256(raw).hexdigest()[:16]


def _identity(config, key):
    return (config.get("provider"), config.get("base_url"), config.get("model"),
            hashlib.sha256((key or "").encode()).hexdigest())


def _metadata(config, key, refresh):
    identity = _identity(config, key)
    with _lock:
        cached = _cache.get(identity)
    if not refresh:
        return copy.deepcopy(cached[1]) if cached and time.monotonic() - cached[0] < 3600 else None
    provider = config.get("provider")
    if provider not in DISCOVERABLE_PROVIDERS:
        raise ValueError("此供应商尚无已接入的能力发现接口，请使用 YAML 定义。")
    entries = fetch_model_entries(provider, _models_url(config["base_url"], provider), key)
    item = next((entry for entry in entries if entry["id"] == config.get("model")), None)
    if item is None:
        raise ValueError("服务模型列表中没有当前模型，请检查实际模型 UID。")
    # Only import declared metadata, never arbitrary API fields or executable content.
    metadata = {"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    for field in ("context_window", "max_output_tokens", "context_length"):
        value = item.get(field)
        if type(value) is int and 0 < value <= 100_000_000:
            metadata[field] = value
    effort = item.get("effort")
    if provider == "deepseek" and isinstance(effort, dict):
        levels = effort.get("supported_levels")
        if isinstance(levels, list) and levels and len(levels) <= 20 and all(isinstance(v, str) and 0 < len(v) <= 30 for v in levels):
            metadata["effort"] = {"supported_levels": levels}
            if effort.get("default_level") in levels:
                metadata["effort"]["default_level"] = effort["default_level"]
    with _lock:
        if len(_cache) >= 200:
            _cache.pop(next(iter(_cache)))
        _cache[identity] = (time.monotonic(), metadata)
    return metadata


def describe_parameters(config, key=None, *, refresh=False):
    definition, version = _definition()
    provider, model = config.get("provider", "vllm"), config.get("model") or ""
    if provider not in LLM_PROVIDERS:
        raise ValueError("Unsupported LLM provider")
    profile_id = definition.providers.get(provider, "basic")
    base = definition.profiles[profile_id]
    fields = copy.deepcopy(base.parameters)
    source = base.source
    matched = False
    yaml_metadata = {}
    for rule in definition.models:
        # Exact UIDs: local deployment aliases can be added explicitly in YAML.
        if rule.provider == provider and model in rule.patterns:
            profile = definition.profiles[rule.profile]
            for name, spec in profile.parameters.items():
                fields[name] = {**fields.get(name, {}), **spec}
            source, matched = profile.source, True
            yaml_metadata.update(rule.metadata)
    metadata = {**yaml_metadata, **(_metadata(config, key, refresh) or {})}
    if metadata and metadata.get("effort") and provider == "deepseek":
        deep = definition.profiles["deepseek"]
        for name, spec in deep.parameters.items():
            fields[name] = {**fields.get(name, {}), **spec}
        fields["reasoning_effort"]["values"] = metadata["effort"]["supported_levels"]
        fields["reasoning_effort"]["default"] = metadata["effort"].get("default_level")
        source, matched = deep.source, True
    fields["max_tokens"]["max"] = min(8192, fields["max_tokens"].get("max", 8192), metadata.get("max_output_tokens", 8192))
    if fields["max_tokens"]["max"] < 2:
        raise ValueError("模型声明的输出上限小于本系统的最小输出长度。")
    if metadata.get("max_output_tokens"):
        fields["max_tokens"]["default"] = min(fields["max_tokens"].get("default", 256), fields["max_tokens"]["max"])
    parameters = {name: Parameter.model_validate(spec).model_dump(exclude_none=True) for name, spec in fields.items()}
    for spec in parameters.values():
        if any(name not in parameters for name in spec["enabled_when"]):
            raise ValueError("Unknown parameter dependency")
    return {"model": model, "provider": provider, "version": version, "source": source,
            "model_specific": matched, "parameters": parameters, "metadata": metadata or {},
            "can_refresh": provider in DISCOVERABLE_PROVIDERS}


def resolve_parameters(config, overrides, max_tokens=256, key=None):
    description = describe_parameters(config, key)
    specs = description["parameters"]
    values = {**({"max_tokens": max_tokens} if max_tokens is not None else {}), **overrides}
    unknown = set(values) - set(specs)
    if unknown:
        raise ValueError("不支持的 LLM 参数：" + ", ".join(sorted(unknown)))
    effective = {name: spec.get("default") for name, spec in specs.items()}
    effective.update(values)
    wire = {}
    for name, value in values.items():
        spec = specs[name]
        if any(effective.get(dep) != wanted for dep, wanted in spec["enabled_when"].items()):
            raise ValueError(f"参数 {name} 在当前思考模式下不生效。")
        if spec["type"] == "enum":
            if not isinstance(value, str) or value not in spec["values"]:
                raise ValueError(f"参数 {name} 的取值不受支持。")
        else:
            if type(value) not in (int, float) or not math.isfinite(value) or (spec["type"] == "integer" and type(value) is not int):
                raise ValueError(f"参数 {name} 必须为有效的数字。")
            if value < spec.get("min", -math.inf) or value > spec.get("max", math.inf):
                raise ValueError(f"参数 {name} 超出允许范围。")
        path = spec["api_field"].split(".")
        parent = wire
        for segment in path[:-1]:
            parent = parent.setdefault(segment, {})
        parent[path[-1]] = spec["wire_values"].get(value, value) if spec["type"] == "enum" else value
    return wire, {"definition_version": description["version"], "explicit_parameters": values,
                  "capability_metadata": description["metadata"],
                  "service_defaults": {name: spec.get("default") for name, spec in specs.items() if name != "max_tokens" and name not in values and spec.get("default") is not None},
                  "model": description["model"], "provider": description["provider"]}
