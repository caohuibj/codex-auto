"""Configuration loading and policy validation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator, model_validator

from codex_auto.models import StrictModel


class ProviderConfig(StrictModel):
    type: Literal["openai", "chatgpt_app"] = "openai"
    api_key_env: str | None = "OPENAI_API_KEY"
    base_url: str | None = None
    timeout_seconds: float = Field(default=120, gt=0, le=1800)
    store: bool = False

    @model_validator(mode="after")
    def api_key_matches_provider(self) -> ProviderConfig:
        if self.type == "openai" and not self.api_key_env:
            raise ValueError("openai provider requires api_key_env")
        if self.type == "chatgpt_app" and self.api_key_env is not None:
            raise ValueError("chatgpt_app provider must not configure an API key")
        return self


class ModelRoute(StrictModel):
    provider: str = "openai"
    model: str = Field(min_length=1)
    reasoning_effort: str | None = None
    max_output_tokens: int = Field(default=8000, ge=256)
    temperature: float | None = Field(default=None, ge=0, le=2)


class RoutingConfig(StrictModel):
    planning: ModelRoute
    implementation: ModelRoute
    review: ModelRoute
    fix: ModelRoute


class GitHubConfig(StrictModel):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    base_branch: str = "main"
    remote: str = "origin"
    feature_branch_prefix: str = "codex-auto/"
    context_max_bytes: int = Field(default=120_000, ge=1_000, le=2_000_000)
    allowed_paths: list[str] = Field(default_factory=lambda: ["**"])
    forbidden_paths: list[str] = Field(
        default_factory=lambda: [
            ".env",
            ".env.*",
            ".git/**",
            ".agents/skills/**",
            ".github/workflows/**",
            ".codex-auto/**",
            "*.pem",
            "*.key",
            "**/*.pem",
            "**/*.key",
        ]
    )
    allow_deletions: bool = False
    verification_commands: dict[str, list[str]] = Field(default_factory=dict)
    required_ci_checks: list[str] = Field(default_factory=list)


class PolicyConfig(StrictModel):
    max_fix_cycles: int = Field(default=2, ge=0, le=10)
    human_merge_required: Literal[True] = True
    protocol_version: str = "v1"


class AuditConfig(StrictModel):
    path: str = ".codex-auto/audit/events.jsonl"
    max_payload_chars: int = Field(default=20_000, ge=500)


class ModelPricing(StrictModel):
    input_per_million: str = "0"
    cached_input_per_million: str = "0"
    output_per_million: str = "0"

    @field_validator("input_per_million", "cached_input_per_million", "output_per_million")
    @classmethod
    def price_is_non_negative_decimal(cls, value: str) -> str:
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("price must be a decimal string") from exc
        if not parsed.is_finite() or parsed < 0:
            raise ValueError("price must be a finite, non-negative decimal string")
        return value


class CostConfig(StrictModel):
    models: dict[str, ModelPricing] = Field(default_factory=dict)


class AppConfig(StrictModel):
    providers: dict[str, ProviderConfig]
    routing: RoutingConfig
    github: GitHubConfig
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    cost: CostConfig = Field(default_factory=CostConfig)

    @model_validator(mode="after")
    def routes_reference_known_providers(self) -> AppConfig:
        for name, route in (
            ("planning", self.routing.planning),
            ("implementation", self.routing.implementation),
            ("review", self.routing.review),
            ("fix", self.routing.fix),
        ):
            if route.provider not in self.providers:
                raise ValueError(f"route {name} references unknown provider {route.provider!r}")
        return self


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("configuration root must be a mapping")
    return AppConfig.model_validate(raw)
