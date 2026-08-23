"""Configuration loading and policy validation."""

from __future__ import annotations

import tomllib
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
            ".codex/**",
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


def validate_chatgpt_app_routes(config: AppConfig, repo_path: str | Path) -> None:
    """Fail closed when repo-local App and orchestrator routes do not match exactly."""

    routes = config.routing
    route_pairs = (
        ("planning", routes.planning),
        ("implementation", routes.implementation),
        ("review", routes.review),
        ("fix", routes.fix),
    )
    for phase, route in route_pairs:
        provider = config.providers[route.provider]
        if provider.type != "chatgpt_app":
            raise ValueError(f"App checkpoint route {phase} must use a chatgpt_app provider")
    if (routes.planning.model, routes.planning.reasoning_effort) != (
        routes.review.model,
        routes.review.reasoning_effort,
    ):
        raise ValueError("planning and review must use the same exact Sol model and effort")
    if (routes.implementation.model, routes.implementation.reasoning_effort) != (
        routes.fix.model,
        routes.fix.reasoning_effort,
    ):
        raise ValueError("implementation and fix must use the same exact Luna model and effort")

    root = Path(repo_path).resolve()
    project_path = root / ".codex/config.toml"
    agent_path = root / ".codex/agents/luna-implementer.toml"
    try:
        with project_path.open("rb") as handle:
            project = tomllib.load(handle)
        with agent_path.open("rb") as handle:
            agent = tomllib.load(handle)
    except (FileNotFoundError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(
            "ChatGPT App route configuration is missing or invalid; rerun init-project and "
            "do not substitute models"
        ) from exc

    agents = project.get("agents")
    expected_project = {
        "model": routes.planning.model,
        "model_reasoning_effort": routes.planning.reasoning_effort,
    }
    for key, expected in expected_project.items():
        if project.get(key) != expected:
            raise ValueError(f"ChatGPT App primary route mismatch for {key}; refusing to continue")
    if not isinstance(agents, dict) or agents.get("enabled") is not True:
        raise ValueError("ChatGPT App subagents must be enabled; refusing to continue")
    expected_subagent = {
        "default_subagent_model": routes.implementation.model,
        "default_subagent_reasoning_effort": routes.implementation.reasoning_effort,
    }
    for key, expected in expected_subagent.items():
        if agents.get(key) != expected:
            raise ValueError(f"ChatGPT App Luna route mismatch for {key}; refusing to continue")
    if agents.get("max_concurrent_threads_per_session") != 1:
        raise ValueError("ChatGPT App workflow requires exactly one concurrent Luna subagent")

    expected_agent = {
        "name": "luna_implementer",
        "model": routes.implementation.model,
        "model_reasoning_effort": routes.implementation.reasoning_effort,
    }
    for key, expected in expected_agent.items():
        if agent.get(key) != expected:
            raise ValueError(f"luna_implementer route mismatch for {key}; refusing to continue")
